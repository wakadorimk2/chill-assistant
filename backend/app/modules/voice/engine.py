"""
音声合成エンジンモジュール

VOICEVOXを使用した音声合成の中核機能を提供します。
"""

import json
import logging
from typing import Any, Dict, Optional, Tuple, Union

import requests

from ..emotion.analyzer import analyze_text

# 自モジュールからのインポート
from .cache import get_voice_cache_path, is_voice_cached, save_to_cache
from .player import is_message_duplicate, play_voice_async

# ロガーの設定
logger = logging.getLogger(__name__)


# テキストの感情を分析して最適なパラメータで音声合成する関数
def speak_with_emotion(
    text: str, speaker_id: int = 0, force: bool = False, message_type: str = "default"
) -> Tuple[Optional[str], Dict[str, Any]]:
    """
    テキストの感情を自動分析して最適なパラメータで音声合成する

    Args:
        text: 発話するテキスト
        speaker_id: 話者ID
        force: クールダウンを無視して強制的に再生
        message_type: メッセージタイプ（重複チェック用）

    Returns:
        Tuple[str, Dict]: WAVファイルのパス（成功時）と分析結果の辞書
    """
    # テキストから感情を分析
    analysis_result = analyze_text(text)

    # 分析結果からパラメータを取得
    params = analysis_result["parameters"]
    emotion = analysis_result["emotion"]

    logger.info(f"感情分析結果: {emotion} - {analysis_result['explanation']}")
    logger.debug(f"音声パラメータ: {params}")

    # パラメータを適用して音声合成
    wav_path = safe_play_voice(
        text,
        speaker_id,
        speed=params["speed_scale"],
        pitch=params["pitch_scale"],
        intonation=params["intonation_scale"],
        volume=params["volume_scale"],
        force=force,
        message_type=message_type,
    )

    return wav_path, analysis_result


# 安全に音声を再生する（VOICEVOXが利用可能なら）
def safe_play_voice(
    text: str,
    speaker_id: int = 0,
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
        speaker_id: 話者ID
        speed: 話速（1.0が標準）
        pitch: ピッチ（0.0が標準）
        intonation: イントネーション（1.0が標準）
        volume: 音量（1.0が標準）
        force: 強制再生フラグ
        message_type: メッセージタイプ（重複チェック用）

    Returns:
        wav_path: 生成されたWAVファイルのパス、エラー時はNone
    """
    # 重複チェック
    if not force and is_message_duplicate(message_type, text, 3.0):
        logger.info(f"重複メッセージ抑制: {message_type} - {text}")
        return None

    # VOICEVOXとの通信
    try:
        return speak(text, speaker_id, speed, pitch, intonation, volume, force)
    except Exception as e:
        logger.error(f"音声再生エラー: {e}")
        return None


# 新しい関数: 音声データを直接返す（再生なし）
async def synthesize_direct(
    text: str,
    speaker_id: int = 0,
    emotion: str = "normal",
    speed: Optional[float] = None,
    pitch: Optional[float] = None,
    intonation: Optional[float] = None,
    volume: Optional[float] = None,
    pre_phoneme_length: Optional[float] = None,
    post_phoneme_length: Optional[float] = None,
    pause_length_scale: Optional[float] = None,
) -> Optional[bytes]:
    """
    VOICEVOXを使用してテキストを音声に変換し、音声データを直接返す（再生なし）

    Args:
        text: 合成するテキスト
        speaker_id: 話者ID
        emotion: 感情タイプ（normal, happy, surprised, serious等）
        speed: 話速（1.0が標準）- オプション
        pitch: ピッチ（0.0が標準）- オプション
        intonation: イントネーション（1.0が標準）- オプション
        volume: 音量（1.0が標準）- オプション

    Returns:
        bytes: WAV音声データ（成功時）、失敗時はNone
    """
    from ...config import get_settings

    try:
        # 設定を取得（VOICEVOX_HOSTを直接使用するため）
        settings = get_settings()

        logger.info(
            f"音声合成開始 (direct): text={text[:20]}..., "
            f"speaker={speaker_id}, emotion={emotion}"
        )
        logger.debug(
            f"音声パラメータ: speed={speed}, pitch={pitch}, intonation={intonation}"
        )

        # 音声合成クエリの作成リクエスト
        logger.debug(f"VOICEVOX APIリクエスト: {settings.VOICEVOX_HOST}/audio_query")

        # 型アノテーション対応のためのキャスト
        query_params: Dict[str, Union[str, int]] = {"text": text, "speaker": speaker_id}

        query_response = requests.post(
            f"{settings.VOICEVOX_HOST}/audio_query",
            params=query_params,
        )

        if query_response.status_code != 200:
            logger.error(
                f"音声合成クエリの作成に失敗: "
                f"ステータスコード={query_response.status_code}"
            )
            logger.error(f"レスポンス内容: {query_response.text}")
            return None

        voice_params = query_response.json()

        # パラメータを設定
        # Noneでないものだけ上書きする（VOICEVOX仕様対応）
        if speed is not None:
            voice_params["speedScale"] = speed
        if pitch is not None:
            voice_params["pitchScale"] = pitch
        if intonation is not None:
            voice_params["intonationScale"] = intonation
        if volume is not None:
            voice_params["volumeScale"] = volume
        if pre_phoneme_length is not None:
            voice_params["prePhonemeLength"] = pre_phoneme_length
        if post_phoneme_length is not None:
            voice_params["postPhonemeLength"] = post_phoneme_length
        if pause_length_scale is not None:
            voice_params["pauseLengthScale"] = pause_length_scale

        # 音声合成の実行
        logger.debug(f"VOICEVOX 音声合成実行: {settings.VOICEVOX_HOST}/synthesis")

        # 型アノテーション対応のためのキャスト
        synthesis_params: Dict[str, int] = {"speaker": speaker_id}

        synthesis_response = requests.post(
            f"{settings.VOICEVOX_HOST}/synthesis",
            headers={"Content-Type": "application/json"},
            params=synthesis_params,
            data=json.dumps(voice_params),
        )

        if synthesis_response.status_code != 200:
            logger.error(
                f"音声合成に失敗: ステータスコード={synthesis_response.status_code}"
            )
            logger.error(f"レスポンス内容: {synthesis_response.text}")
            return None

        # 音声データを直接返す
        audio_data = synthesis_response.content
        logger.debug(f"音声合成完了: 音声データサイズ {len(audio_data)} バイト")

        return audio_data

    except Exception as e:
        import traceback

        logger.error(f"音声合成エラー (direct): {e}")
        logger.error(f"詳細なエラー情報: {traceback.format_exc()}")
        return None


def speak(
    text: str,
    speaker_id: int = 0,
    speed: float = 1.0,
    pitch: float = 0.0,
    intonation: float = 1.0,
    volume: float = 1.0,
    force: bool = False,
    pre_phoneme_length: Optional[float] = None,
    post_phoneme_length: Optional[float] = None,
    pause_length_scale: Optional[float] = None,
) -> Optional[str]:
    """
    VOICEVOXを使用してテキストを音声に変換し、再生する

    Args:
        text: 合成するテキスト
        speaker_id: 話者ID
        speed: 話速（1.0が標準）
        pitch: ピッチ（0.0が標準）
        intonation: イントネーション（1.0が標準）
        volume: 音量（1.0が標準）
        force: 強制再生フラグ
        pre_phoneme_length: 発話前の無音 (秒). None で settings 既定
        post_phoneme_length: 発話後の無音 (秒). None で settings 既定
        pause_length_scale: 句読点ポーズ倍率. None で settings 既定

    Returns:
        str: 生成されたWAVファイルのパス、エラー時はNone
    """
    from ...config import get_settings

    try:
        # 設定を取得
        settings = get_settings()

        if pre_phoneme_length is None:
            pre_phoneme_length = settings.VOICE_PRE_PHONEME_LENGTH
        if post_phoneme_length is None:
            post_phoneme_length = settings.VOICE_POST_PHONEME_LENGTH
        if pause_length_scale is None:
            pause_length_scale = settings.VOICE_PAUSE_LENGTH_SCALE

        # 音声キャッシュをチェック (キーはパラメータ全体に依存させる)
        cache_key = _voice_cache_key(
            text,
            speaker_id,
            speed,
            pitch,
            intonation,
            volume,
            pre_phoneme_length,
            post_phoneme_length,
            pause_length_scale,
        )
        cache_path = get_voice_cache_path(cache_key, speaker_id)
        if is_voice_cached(cache_key, speaker_id):
            logger.info(f"キャッシュから音声を再生: {cache_path}")
            play_voice_async(cache_path)
            return cache_path

        # VOICEVOXとの通信
        # 型アノテーション対応のためのキャスト
        query_params: Dict[str, Union[str, int]] = {
            "text": text,
            "speaker": speaker_id,
        }

        response = requests.post(
            f"{settings.VOICEVOX_HOST}/audio_query",
            params=query_params,
            timeout=10,
        )
        response.raise_for_status()

        # 音声合成
        audio_query = response.json()

        # スケールパラメータを設定
        audio_query["speedScale"] = speed
        audio_query["pitchScale"] = pitch
        audio_query["intonationScale"] = intonation
        audio_query["volumeScale"] = volume
        audio_query["prePhonemeLength"] = pre_phoneme_length
        audio_query["postPhonemeLength"] = post_phoneme_length
        audio_query["pauseLengthScale"] = pause_length_scale

        # 型アノテーション対応のためのキャスト
        synthesis_params: Dict[str, int] = {"speaker": speaker_id}

        response = requests.post(
            f"{settings.VOICEVOX_HOST}/synthesis",
            headers={"Content-Type": "application/json"},
            params=synthesis_params,
            data=json.dumps(audio_query),
            timeout=10,
        )
        response.raise_for_status()

        # キャッシュに保存
        save_result = save_to_cache(cache_key, response.content, speaker_id)
        if save_result:
            cache_path = save_result

            # 非同期で再生
            play_voice_async(cache_path)
            return cache_path

        return None

    except Exception as e:
        logger.error(f"音声合成エラー: {e}")
        return None


def _voice_cache_key(
    text: str,
    speaker_id: int,
    speed: float,
    pitch: float,
    intonation: float,
    volume: float,
    pre_phoneme: float,
    post_phoneme: float,
    pause_scale: float,
) -> str:
    """speak の合成パラメータを含めたキャッシュ識別キー."""
    return (
        f"{text}|sp{speaker_id}|s{speed:.3f}p{pitch:.3f}"
        f"i{intonation:.3f}v{volume:.3f}"
        f"pre{pre_phoneme:.3f}post{post_phoneme:.3f}ps{pause_scale:.3f}"
    )
