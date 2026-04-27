"""CompanionService — watcher queue consumer + speech_bus への発話投入.

Step 4 で発話パスを `services.speech_bus` 経由に変更.
LLM 呼び出し前に rate limit を判定して LLM コストを節約しつつ、
最終的な VOICEVOX 発話 + WebSocket broadcast は SpeechConsumer 側に委譲する.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Optional

import numpy as np
from numpy.typing import NDArray

from ...config import Settings
from ...services.speech_bus import SpeechRequest, get_speech_bus
from .runtime import Companion

if TYPE_CHECKING:
    from ..watcher import WatcherService
    from ..watcher.events import WatcherEvent

logger = logging.getLogger(__name__)


class CompanionService:
    """watcher の WatcherEvent を consume して LLM → speech_bus に流す."""

    def __init__(
        self,
        companion: Companion,
        watcher: "WatcherService",
        settings: Settings,
    ) -> None:
        self._companion = companion
        self._watcher = watcher
        self._settings = settings
        self._task: Optional[asyncio.Task[None]] = None
        self._running = False
        self._last_speak_ts: Optional[float] = None

    @property
    def ready(self) -> bool:
        return self._companion.ready

    @property
    def last_speak_ts(self) -> Optional[float]:
        return self._last_speak_ts

    async def start(self) -> None:
        if self._running:
            logger.info("CompanionService は既に起動しています")
            return
        self._running = True
        self._task = asyncio.create_task(
            self._consume_loop(), name="companion.consume"
        )
        logger.info(
            f"CompanionService 起動: model={self._companion.model}, "
            f"rate_limit={self._settings.COMPANION_RATE_LIMIT_SEC}s, "
            f"ready={self._companion.ready}"
        )

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.warning(f"CompanionService 停止中に gather 例外: {e}")
        self._task = None
        logger.info("CompanionService 停止完了")

    async def _consume_loop(self) -> None:
        queue = self._watcher.queue
        while self._running:
            try:
                event = await queue.get()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"CompanionService: queue.get 例外: {e}")
                await asyncio.sleep(0.5)
                continue

            try:
                await self._handle_event(event)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                # consumer ループを死なせない
                logger.error(
                    f"CompanionService: event ハンドリング例外 (継続): "
                    f"{type(e).__name__}: {e}"
                )

    async def _handle_event(self, event: "WatcherEvent") -> None:
        # LLM コスト節約のため event 受領時点で rate limit を先判定
        now = time.time()
        rate_limit = self._settings.COMPANION_RATE_LIMIT_SEC
        if (
            self._last_speak_ts is not None
            and now - self._last_speak_ts < rate_limit
        ):
            if self._settings.WATCHER_VERBOSE_LOG:
                logger.debug(
                    f"companion skip (rate limit): "
                    f"{now - self._last_speak_ts:.1f}s < {rate_limit}s"
                )
            return

        jpeg_bytes = self._watcher.get_latest_frame_jpeg(
            quality=self._settings.COMPANION_JPEG_QUALITY
        )
        if jpeg_bytes is None:
            logger.debug("companion skip: 最新フレームなし")
            return

        user_context = (
            f"状況: {event.kind.value}、スコア {event.score:.2f}、"
            f"ウィンドウ「{event.window_title or '不明'}」"
        )
        logger.info(
            f"companion generate 開始: kind={event.kind.value}, "
            f"score={event.score:.2f}"
        )
        start = time.perf_counter()
        text = await self._companion.generate_from_jpeg(jpeg_bytes, user_context)
        latency = round(time.perf_counter() - start, 2)

        if not text:
            logger.info(f"companion generate 空応答 (latency={latency}s)")
            return

        logger.info(
            f"companion enqueue: '{text}' (latency={latency}s, len={len(text)})"
        )
        await self._enqueue_speech(text, event)
        self._last_speak_ts = time.time()

    async def _enqueue_speech(self, text: str, event: "WatcherEvent") -> None:
        """生成テキストを speech_bus に投入 (実際の発話は SpeechConsumer 側)."""
        bus = get_speech_bus()
        await bus.put(
            SpeechRequest(
                text=text,
                source="companion",
                emotion="通常",
                rate_limit_sec=self._settings.COMPANION_RATE_LIMIT_SEC,
                meta={"source_event": event.to_payload()},
            )
        )

    async def generate_once(
        self,
        image: NDArray[np.uint8],
        user_context: str,
        speak_voice: bool = True,
    ) -> tuple[str, float, bool]:
        """debug-speak 用: rate limit バイパスで 1 回生成 (+ 任意で発話)."""
        start = time.perf_counter()
        text = await self._companion.generate(image, user_context)
        latency = round(time.perf_counter() - start, 2)

        spoken = False
        if text and speak_voice:
            bus = get_speech_bus()
            ok = await bus.put(
                SpeechRequest(
                    text=text,
                    source="companion",
                    emotion="通常",
                    bypass_rate_limit=True,
                    message_type="speech_companion_debug",
                    meta={"debug": True, "user_context": user_context[:80]},
                )
            )
            spoken = ok
            if ok:
                self._last_speak_ts = time.time()
        return text, latency, spoken
