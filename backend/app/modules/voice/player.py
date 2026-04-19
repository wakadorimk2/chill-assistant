"""
音声再生モジュール

音声の再生と非同期処理、再生制御を管理する機能を提供します。
"""

import concurrent.futures
import logging
import sys
import threading
import time
from typing import Dict, Optional, Tuple

# ロガーの設定
logger = logging.getLogger(__name__)

# 音声再生の最終時刻を記録する変数
last_voice_time = 0
# 音声再生用の排他ロック
voice_lock = threading.Lock()
# 最後に再生したメッセージのキャッシュ
last_message_cache: Dict[str, Tuple[str, float]] = {}
# 音声再生中フラグ
audio_playing = False
# ThreadPoolExecutor for background tasks
executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)


def reset_audio_playback() -> None:
    """
    音声再生の終了フラグをリセットする
    """
    global audio_playing
    with voice_lock:
        if audio_playing:
            # audioフラグをリセット
            audio_playing = False
            logger.info("音声再生の終了をリセットしました")


# メッセージキャッシュをチェックして短時間での重複メッセージを防ぐ
def is_message_duplicate(
    message_type: str, message: str, cooldown: float = 3.0
) -> bool:
    """
    短時間内に同じメッセージが再生されたかどうかをチェック

    Args:
        message_type: メッセージのタイプ
        message: メッセージ内容
        cooldown: クールダウン時間（秒）

    Returns:
        bool: 重複メッセージの場合True
    """
    current_time = time.time()

    if message_type in last_message_cache:
        cache_entry = last_message_cache[message_type]
        last_message = cache_entry[0]
        last_time = cache_entry[1]

        # 同じメッセージかつ、指定されたクールダウン時間内の場合
        if last_message == message and current_time - last_time < cooldown:
            logger.debug(f"重複メッセージを検出: '{message_type}' - '{message}'")
            return True

    # 新しいメッセージをキャッシュに記録
    last_message_cache[message_type] = (message, current_time)
    return False


def play_voice(wav_path: str) -> None:
    """
    音声ファイルを再生する (同期、executor ワーカ経由で非同期化される想定)

    Args:
        wav_path: WAVファイルのパス
    """
    global audio_playing
    with voice_lock:
        audio_playing = True
        try:
            if sys.platform == "win32":
                # Windows 標準ライブラリ、追加依存なし
                import winsound

                winsound.PlaySound(wav_path, winsound.SND_FILENAME)
            else:
                # フォールバック: pydub (requirements.txt で入れてある)
                from pydub import AudioSegment
                from pydub.playback import play as _pydub_play

                _pydub_play(AudioSegment.from_wav(wav_path))
        except Exception as e:
            logger.error(f"音声再生エラー (path={wav_path}): {e}")
        finally:
            audio_playing = False


def play_voice_async(wav_path: str) -> Optional[concurrent.futures.Future[None]]:
    """
    音声ファイルを非同期で再生する

    Args:
        wav_path: WAVファイルのパス

    Returns:
        Future: 非同期タスクのFutureオブジェクト
    """
    try:
        return executor.submit(play_voice, wav_path)
    except Exception as e:
        logger.error(f"音声再生エラー: {e}")
        return None
