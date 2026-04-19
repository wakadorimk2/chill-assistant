"""Companion サブシステム (Step 3)

watcher の WatcherEvent を consume して、LM Studio 経由の Vision LLM に
画面キャプチャ + 文脈を投げ、40 字以内の秘書たん口調発話を生成する。
"""

from .runtime import Companion
from .service import CompanionService

__all__ = ["Companion", "CompanionService"]
