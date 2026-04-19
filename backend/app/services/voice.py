"""
音声合成・再生サービス

VOICEVOXを使用したテキスト音声合成と再生機能を提供します
"""

import json
import logging
import os
import subprocess
import threading
import time
from typing import Dict, Optional, Tuple

import requests

# 設定のインポート
from ..config import get_settings

# ロガーの設定
logger = logging.getLogger(__name__)


# 音声再生の状態管理
class VoicePlaybackState:
    """音声再生の状態を管理するクラス"""

    def __init__(self):
        """初期化"""
        self.last_voice_time: float = 0.0
        self.voice_lock = threading.Lock()
        self.audio_playing = False
        self.last_message_cache: Dict[str, Tuple[str, float]] = {}

    def is_message_duplicate(
        self, message_type: str, message: str, cooldown: float = 3.0
    ) -> bool:
        """
        短時間内に同じメッセージが再生されたかどうかをチェック

        Args:
            message_type: メッセージのタイプ
            message: メッセージ内容
            cooldown: クールダウン時間（秒）

        Returns:
            bool: 重複メッセージの場合はTrue
        """
        current_time = time.time()

        if message_type in self.last_message_cache:
            last_message, last_time = self.last_message_cache[message_type]

            # 同じメッセージかつ、指定されたクールダウン時間内の場合
            if last_message == message and current_time - last_time < cooldown:
                logger.debug(f"重複メッセージを検出: '{message_type}' - '{message}'")
                return True

        # 新しいメッセージをキャッシュに記録
        self.last_message_cache[message_type] = (message, current_time)
        return False

    def register_audio_playback(self, duration: float = 3.0) -> None:
        """
        音声再生中の状態を登録

        Args:
            duration: 推定再生時間（秒）
        """
        with self.voice_lock:
            self.audio_playing = True
            # 再生時間後に自動的にリセットするタイマーを設定
            timer = threading.Timer(duration, self.reset_audio_playback)
            timer.daemon = True
            timer.start()

    def reset_audio_playback(self) -> None:
        """音声再生の終了を通知"""
        with self.voice_lock:
            if self.audio_playing:
                self.audio_playing = False
                logger.debug("音声再生の状態をリセットしました")


# シングルトンのプレイバック状態
_playback_state = VoicePlaybackState()


class VoiceService:
    """音声合成・再生サービス"""

    def __init__(self) -> None:
        """初期化"""
        self.settings = get_settings()
        self.voice_lock = _playback_state.voice_lock

    def safe_play_voice(
        self,
        text: str,
        speaker_id: Optional[int] = None,
        speed: float = 1.0,
        pitch: float = 0.0,
        intonation: float = 1.0,
        volume: float = 1.0,
        force: bool = False,
        message_type: str = "default",
    ) -> Optional[str]:
        """
        安全に音声を再生する（VOICEVOXが利用可能なら）

        Args:
            text: 再生するテキスト
            speaker_id: 話者ID（指定がなければ設定値を使用）
            speed: 話速（1.0が標準）
            pitch: ピッチ（0.0が標準）
            intonation: イントネーション（1.0が標準）
            volume: 音量（1.0が標準）
            force: 強制再生フラグ
            message_type: メッセージタイプ（重複チェック用）

        Returns:
            wav_path: 生成されたWAVファイルのパス、エラー時はNone
        """
        # speaker_idが指定されていなければ、設定から取得
        if speaker_id is None:
            speaker_id = self.settings.VOICEVOX_SPEAKER

        # 重複チェック
        if not force and _playback_state.is_message_duplicate(message_type, text, 3.0):
            logger.info(f"重複メッセージ抑制: {message_type} - {text}")
            return None

        # クールダウンチェック
        current_time = time.time()
        with self.voice_lock:
            # 強制フラグがなく、クールダウン中なら何もしない
            if (
                not force
                and current_time - _playback_state.last_voice_time
                < self.settings.VOICE_COOLDOWN
            ):
                logger.debug("音声再生クールダウン中")
                return None

            # 音声再生中なら何もしない
            if _playback_state.audio_playing and not force:
                logger.debug("前の音声再生中のため、新しい音声をスキップ")
                return None

            _playback_state.last_voice_time = current_time

        # VOICEVOXとの通信
        try:
            return self._speak(text, speaker_id, speed, pitch, intonation, volume)
        except Exception as e:
            logger.error(f"音声再生エラー: {e}")
            return None

    def _speak(
        self,
        text: str,
        speaker_id: int = 0,
        speed: float = 1.0,
        pitch: float = 0.0,
        intonation: float = 1.0,
        volume: float = 1.0,
    ) -> Optional[str]:
        """
        VOICEVOXを使用してテキストを音声に変換し再生

        Args:
            text: 発話するテキスト
            speaker_id: 話者ID
            speed: 話速
            pitch: ピッチ
            intonation: イントネーション
            volume: 音量

        Returns:
            wav_path: 生成されたWAVファイルのパス、エラー時はNone
        """
        try:
            # 音声合成リクエストを2段階で行う
            # 1. 音声合成用のクエリを作成
            params = {"text": text, "speaker": speaker_id}

            # 音声パラメータを追加
            if speed != 1.0 or pitch != 0.0 or intonation != 1.0:
                params["speedScale"] = speed
                params["pitchScale"] = pitch
                params["intonationScale"] = intonation
                params["volumeScale"] = volume

            # 音声合成クエリの作成リクエスト
            query_response = requests.post(
                f"{self.settings.VOICEVOX_HOST}/audio_query", params=params
            )

            if query_response.status_code != 200:
                logger.error(f"音声合成クエリの作成に失敗: {query_response.text}")
                return None

            voice_params = query_response.json()

            # 2. 音声合成の実行
            synthesis_response = requests.post(
                f"{self.settings.VOICEVOX_HOST}/synthesis",
                headers={"Content-Type": "application/json"},
                params={"speaker": speaker_id},
                data=json.dumps(voice_params),
            )

            if synthesis_response.status_code != 200:
                logger.error(f"音声合成に失敗: {synthesis_response.text}")
                return None

            # 一時的なWAVファイルに保存
            temp_dir = self.settings.TEMP_DIR
            os.makedirs(temp_dir, exist_ok=True)

            # タイムスタンプを含むファイル名を生成
            timestamp = int(time.time())
            wav_filename = f"voice_{timestamp}.wav"
            wav_path = os.path.join(temp_dir, wav_filename)

            with open(wav_path, "wb") as f:
                f.write(synthesis_response.content)

            logger.debug(f"WAVファイルを保存: {wav_path}")

            # 音声再生中フラグを設定
            _playback_state.register_audio_playback(
                duration=float(len(text) * 0.15)  # テキスト長から推定再生時間を計算
            )

            # 音声を再生（非同期）
            self._play_audio_file(wav_path)

            return wav_path

        except Exception as e:
            logger.error(f"音声合成エラー: {e}")
            _playback_state.reset_audio_playback()  # エラー時はフラグをリセット
            return None

    def _play_audio_file(self, audio_path: str) -> None:
        """
        音声ファイルを再生

        Args:
            audio_path: 再生する音声ファイルのパス
        """
        try:
            # Windows環境
            if os.name == "nt":
                subprocess.Popen(
                    [
                        "powershell",
                        "-c",
                        f'(New-Object Media.SoundPlayer "{audio_path}").PlaySync();',
                    ]
                )
            # Linux/Mac環境
            else:
                # mpg123 や aplay などが必要
                subprocess.Popen(["aplay", audio_path])

        except Exception as e:
            logger.error(f"音声再生プロセスの起動に失敗: {e}")
            _playback_state.reset_audio_playback()  # エラー時はフラグをリセット


# シングルトンインスタンスを取得するヘルパー関数
def get_voice_service() -> VoiceService:
    """音声サービスのインスタンスを取得"""
    return VoiceService()
