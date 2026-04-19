"""CompanionService — watcher queue consumer + 発話ディスパッチ."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Optional

import numpy as np
from numpy.typing import NDArray

from ...config import Settings
from ...ws.manager import manager
from .runtime import Companion

if TYPE_CHECKING:
    from ..watcher import WatcherService
    from ..watcher.events import WatcherEvent

logger = logging.getLogger(__name__)


class CompanionService:
    """watcher の WatcherEvent を consume して LLM → VOICEVOX の一連を束ねる."""

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
            f"companion speak: '{text}' (latency={latency}s, len={len(text)})"
        )
        await self._dispatch_speech(text, event)
        self._last_speak_ts = time.time()

    async def _dispatch_speech(self, text: str, event: "WatcherEvent") -> None:
        """生成テキストを VOICEVOX 発話 + WebSocket broadcast に流す."""
        # 循環 import を避けるため関数内で import
        from ..voice.engine import speak

        preset = self._settings.VOICE_PRESETS.get("通常", {})
        speaker_id = self._settings.VOICEVOX_SPEAKER

        try:
            await asyncio.to_thread(
                speak,
                text,
                speaker_id,
                float(preset.get("speed", 1.0)),
                float(preset.get("pitch", 0.0)),
                float(preset.get("intonation", 1.0)),
                1.0,
                False,
            )
        except Exception as e:
            logger.error(f"companion speak 例外: {type(e).__name__}: {e}")

        try:
            await manager.broadcast(
                {
                    "type": "companion_speak",
                    "data": {
                        "text": text,
                        "emotion": "通常",
                        "ts": time.time(),
                        "source_event": event.to_payload(),
                    },
                }
            )
        except Exception as e:
            logger.error(f"companion broadcast 例外: {type(e).__name__}: {e}")

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
            from ..voice.engine import speak

            preset = self._settings.VOICE_PRESETS.get("通常", {})
            try:
                await asyncio.to_thread(
                    speak,
                    text,
                    self._settings.VOICEVOX_SPEAKER,
                    float(preset.get("speed", 1.0)),
                    float(preset.get("pitch", 0.0)),
                    float(preset.get("intonation", 1.0)),
                    1.0,
                    True,
                )
                spoken = True
                self._last_speak_ts = time.time()
            except Exception as e:
                logger.error(f"debug-speak 発話例外: {type(e).__name__}: {e}")
        return text, latency, spoken
