"""
Watcher イベント型定義
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Optional


class WatcherEventKind(str, Enum):
    """Watcher が発火するイベントの種類"""

    WINDOW_CHANGED = "window_changed"
    SCREEN_DIFF = "screen_diff"
    USER_IDLE = "user_idle"


@dataclass(frozen=True)
class WatcherEvent:
    """Watcher が発火するイベント本体 (画像本体は保持しない、メタデータのみ)"""

    kind: WatcherEventKind
    score: float
    window_title: Optional[str]
    ts: float
    extra: Mapping[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        """WebSocket broadcast 用 dict 化"""
        return {
            "kind": self.kind.value,
            "score": self.score,
            "window_title": self.window_title,
            "ts": self.ts,
            "extra": dict(self.extra),
        }
