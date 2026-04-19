"""
スキーマ定義モジュール

FastAPIで使用するPydanticモデル定義をエクスポート
"""

from .base import BaseEvent, EventModel, HealthTestModel, MessageModel
from .events import (
    ErrorEvent,
    EventType,
    PlayerStatusEvent,
    SystemEvent,
)
from .voice import VoiceSynthesisRequest

__all__ = [
    "MessageModel",
    "HealthTestModel",
    "EventModel",
    "BaseEvent",
    "EventType",
    "PlayerStatusEvent",
    "ErrorEvent",
    "SystemEvent",
    "VoiceSynthesisRequest",
]
