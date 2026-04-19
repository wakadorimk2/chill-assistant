"""
Watcher モジュール

画面差分検知 + フォアグラウンドウィンドウ監視を担当。
検知イベントを WebSocket で broadcast し、Step 3 の companion が
Queue を consume して Vision LLM に渡す。
"""

from .events import WatcherEvent, WatcherEventKind
from .service import WatcherService

__all__ = ["WatcherService", "WatcherEvent", "WatcherEventKind"]
