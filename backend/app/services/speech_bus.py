"""SpeechBus — 発話リクエストを一元化する asyncio.Queue ラッパ (Step 4).

companion / funya / boot / debug など複数の発話起点からのリクエストを
1 本の Queue に集約し、SpeechConsumer が単一コンシューマとして処理する。
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SpeechRequest:
    """発話 1 件のリクエスト."""

    text: str
    source: str  # "companion" / "funya" / "boot" / "debug" など
    emotion: str = "通常"
    # 重複判定キー (省略時は source を使う). source を細分化したいときに指定
    message_type: Optional[str] = None
    # rate limit を完全 bypass (debug-speak 用)
    bypass_rate_limit: bool = False
    # source ごとの rate limit. None なら settings.SPEECH_RATE_LIMIT_SEC を採用
    rate_limit_sec: Optional[float] = None
    # フロント broadcast に流したい補足 (source_event など)
    meta: dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)


class SpeechBus:
    """asyncio.Queue を 1 本持つだけのシンプル bus."""

    def __init__(self, max_size: int) -> None:
        self._queue: asyncio.Queue[SpeechRequest] = asyncio.Queue(maxsize=max_size)

    @property
    def queue(self) -> asyncio.Queue[SpeechRequest]:
        return self._queue

    @property
    def qsize(self) -> int:
        return self._queue.qsize()

    async def put(self, request: SpeechRequest) -> bool:
        """リクエストを enqueue. queue full なら drop して False."""
        try:
            self._queue.put_nowait(request)
            return True
        except asyncio.QueueFull:
            logger.warning(
                f"speech_bus: queue full でドロップ "
                f"source={request.source} text='{request.text[:20]}...'"
            )
            return False


_bus_instance: Optional[SpeechBus] = None


def get_speech_bus() -> SpeechBus:
    """シングルトン取得. 初回呼び出し時に Settings から max_size を読む."""
    global _bus_instance
    if _bus_instance is None:
        from ..config import get_settings

        settings = get_settings()
        _bus_instance = SpeechBus(max_size=settings.SPEECH_BUS_QUEUE_MAX_SIZE)
        logger.info(
            f"SpeechBus 初期化: max_size={settings.SPEECH_BUS_QUEUE_MAX_SIZE}"
        )
    return _bus_instance


def reset_speech_bus() -> None:
    """テスト・再起動用. シングルトンを破棄."""
    global _bus_instance
    _bus_instance = None
