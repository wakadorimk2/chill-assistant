"""
プリセット音声モジュール

事前定義された音声パターンの再生と管理を行います。
"""

import logging
import os
from typing import Dict, Optional

from .player import play_voice

# ロガーの設定
logger = logging.getLogger(__name__)

# プリセット音声のパス
PRESET_VOICE_DIR = os.path.join("assets", "sounds", "presets")


def play_preset_voice(filename: str) -> None:
    """
    プリセット音声を再生する

    Args:
        filename: プリセット音声ファイル名
    """
    try:
        preset_path = os.path.join(PRESET_VOICE_DIR, filename)
        if os.path.exists(preset_path):
            play_voice(preset_path)
            logger.debug(f"プリセット音声を再生: {filename}")
        else:
            logger.warning(f"プリセット音声ファイルが見つかりません: {filename}")
    except Exception as e:
        logger.error(f"プリセット音声再生エラー: {e}")


def speak_with_preset(
    text: str,
    preset_name: str,
    speaker_id: int = 0,
    speed: float = 1.0,
    pitch: float = 0.0,
    intonation: float = 1.0,
    volume: float = 1.0,
    delay: float = 0.5,
) -> None:
    """
    プリセットを使用して音声を合成・再生する

    Args:
        text: 発話するテキスト
        preset_name: プリセット名
        speaker_id: 話者ID
        speed: 話速
        pitch: ピッチ
        intonation: イントネーション
        volume: 音量
        delay: 遅延時間（秒）
    """
    logger.info(f"プリセット音声合成: {preset_name} - '{text}'")
    # 実装はプロジェクトの要件に応じて追加
    pass


def safe_speak_with_preset(
    text: str,
    preset_name: str,
    speaker_id: Optional[int] = None,
    emotion: str = "normal",
    force: bool = False,
) -> None:
    """
    プリセットを使用して安全に音声を合成・再生する

    Args:
        text: 発話するテキスト
        preset_name: プリセット名
        speaker_id: 話者ID（オプション）
        emotion: 感情タイプ
        force: 強制再生フラグ
    """
    logger.info(f"安全なプリセット音声合成: {preset_name} - '{text}' ({emotion})")
    # 実装はプロジェクトの要件に応じて追加
    pass


# プリセット定義 (chill 秘書たん路線 — intonation は 1.2 上限に揃える)
VOICE_PRESETS: Dict[str, Dict[str, float]] = {
    "normal": {
        "speed_scale": 0.98,
        "pitch_scale": 0.0,
        "intonation_scale": 1.0,
        "volume_scale": 1.0,
    },
    "happy": {
        "speed_scale": 1.02,
        "pitch_scale": 0.04,
        "intonation_scale": 1.15,
        "volume_scale": 1.0,
    },
    "sad": {
        "speed_scale": 0.92,
        "pitch_scale": -0.05,
        "intonation_scale": 0.9,
        "volume_scale": 0.95,
    },
    "angry": {
        "speed_scale": 1.05,
        "pitch_scale": 0.0,
        "intonation_scale": 1.2,
        "volume_scale": 1.0,
    },
    "surprised": {
        "speed_scale": 1.10,
        "pitch_scale": 0.08,
        "intonation_scale": 1.2,
        "volume_scale": 1.0,
    },
    "whisper": {
        "speed_scale": 0.9,
        "pitch_scale": -0.02,
        "intonation_scale": 0.85,
        "volume_scale": 0.7,
    },
}
