"""
音声合成モジュール

VOICEVOXを使用した音声合成と再生を管理する機能を提供します
"""

from ..emotion.analyzer import analyze_text
from .cache import get_voice_cache_path, is_voice_cached
from .engine import (
    safe_play_voice,
    speak,
    speak_with_emotion,
    synthesize_direct,
)
from .player import play_voice, play_voice_async, reset_audio_playback
from .presets import safe_speak_with_preset, speak_with_preset
from .voicevox_starter import (
    cleanup_on_exit,
    is_voicevox_ready,
    is_voicevox_running,
    start_voicevox_engine,
    start_voicevox_in_thread,
    stop_voicevox_engine,
)

__all__ = [
    "speak_with_emotion",
    "safe_play_voice",
    "synthesize_direct",
    "speak",
    "analyze_text",
    "is_voice_cached",
    "get_voice_cache_path",
    "play_voice",
    "play_voice_async",
    "reset_audio_playback",
    "speak_with_preset",
    "safe_speak_with_preset",
    # voicevox_starter関連
    "is_voicevox_ready",
    "is_voicevox_running",
    "start_voicevox_engine",
    "start_voicevox_in_thread",
    "stop_voicevox_engine",
    "cleanup_on_exit",
]
