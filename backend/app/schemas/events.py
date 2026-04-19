"""
イベントモデル定義

アプリケーション内で使用するイベントクラスを定義します
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class EventType(Enum):
    """イベントタイプの列挙型"""

    PLAYER_STATUS_CHANGED = "player_status_changed"
    ERROR_OCCURRED = "error_occurred"
    SYSTEM_EVENT = "system_event"


@dataclass
class PlayerStatusEvent:
    """プレイヤーステータス変化イベント"""

    status: Dict[str, Any]
    changed_fields: List[str]
    event_type: EventType = field(default=EventType.PLAYER_STATUS_CHANGED, init=False)
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class ErrorEvent:
    """エラーイベント"""

    error_message: str
    error_type: str
    stacktrace: Optional[str] = None
    event_type: EventType = field(default=EventType.ERROR_OCCURRED, init=False)
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class SystemEvent:
    """システムイベント"""

    message: str
    severity: str  # "info", "warning", "error"
    event_type: EventType = field(default=EventType.SYSTEM_EVENT, init=False)
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Optional[Dict[str, Any]] = None
