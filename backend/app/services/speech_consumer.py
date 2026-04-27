"""SpeechConsumer — speech_bus の単一コンシューマ (Step 4).

dedup → source 別 rate limit → VOICEVOX ready 待ち → speak + ws.broadcast
を順に実行する。companion / funya / boot などの発話起点はこの 1 本に集約される。
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

from ..config import Settings
from ..modules.voice.player import is_message_duplicate
from ..modules.voice.voicevox_starter import is_voicevox_ready
from ..ws.manager import manager
from .speech_bus import SpeechBus, SpeechRequest

logger = logging.getLogger(__name__)


class SpeechConsumer:
    """speech_bus を消費して VOICEVOX 発話 + フロント broadcast を一元化."""

    def __init__(self, bus: SpeechBus, settings: Settings) -> None:
        self._bus = bus
        self._settings = settings
        self._task: Optional[asyncio.Task[None]] = None
        self._running = False
        self._last_speak_ts_by_source: dict[str, float] = {}
        self._last_speak_ts: Optional[float] = None
        self._dropped_count = 0
        self._spoken_count = 0

    @property
    def running(self) -> bool:
        return self._running

    @property
    def last_speak_ts(self) -> Optional[float]:
        return self._last_speak_ts

    def get_status(self) -> dict[str, Any]:
        return {
            "running": self._running,
            "queue_size": self._bus.qsize,
            "last_speak_ts": self._last_speak_ts,
            "spoken_count": self._spoken_count,
            "dropped_count": self._dropped_count,
            "last_speak_ts_by_source": dict(self._last_speak_ts_by_source),
        }

    async def start(self) -> None:
        if self._running:
            logger.info("SpeechConsumer は既に起動しています")
            return
        self._running = True
        self._task = asyncio.create_task(
            self._consume_loop(), name="speech.consume"
        )
        logger.info(
            f"SpeechConsumer 起動: queue_max={self._bus.queue.maxsize}, "
            f"default_rate_limit={self._settings.SPEECH_RATE_LIMIT_SEC}s, "
            f"dedup_cooldown={self._settings.SPEECH_DEDUP_COOLDOWN_SEC}s"
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
                logger.warning(f"SpeechConsumer 停止中に例外: {e}")
        self._task = None
        logger.info(
            f"SpeechConsumer 停止完了 "
            f"(spoken={self._spoken_count}, dropped={self._dropped_count})"
        )

    async def _consume_loop(self) -> None:
        queue = self._bus.queue
        while self._running:
            try:
                request = await queue.get()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"SpeechConsumer: queue.get 例外: {e}")
                await asyncio.sleep(0.5)
                continue

            try:
                await self._handle_request(request)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(
                    f"SpeechConsumer: request ハンドリング例外 (継続): "
                    f"{type(e).__name__}: {e}"
                )

    async def _handle_request(self, req: SpeechRequest) -> None:
        text = req.text.strip()
        if not text:
            self._dropped_count += 1
            logger.debug(f"speech drop (empty text): source={req.source}")
            return

        message_type = req.message_type or f"speech_{req.source}"

        # 重複抑制 (force 系は bypass_rate_limit と同扱い)
        cooldown = self._settings.SPEECH_DEDUP_COOLDOWN_SEC
        if not req.bypass_rate_limit and is_message_duplicate(
            message_type, text, cooldown
        ):
            self._dropped_count += 1
            logger.info(
                f"speech drop (dedup {cooldown}s): "
                f"source={req.source} text='{text[:20]}...'"
            )
            return

        # source 別 rate limit
        if not req.bypass_rate_limit:
            limit = (
                req.rate_limit_sec
                if req.rate_limit_sec is not None
                else self._settings.SPEECH_RATE_LIMIT_SEC
            )
            now = time.time()
            last = self._last_speak_ts_by_source.get(req.source)
            if last is not None and now - last < limit:
                self._dropped_count += 1
                logger.info(
                    f"speech drop (rate {limit}s): source={req.source} "
                    f"elapsed={now - last:.1f}s"
                )
                return

        # VOICEVOX ready 待ち (起動直後 / 再起動中はここで吸収)
        if not await self._wait_voicevox_ready():
            self._dropped_count += 1
            logger.warning(
                f"speech drop (voicevox not ready): "
                f"source={req.source} text='{text[:20]}...'"
            )
            return

        await self._dispatch(req, text)

        ts = time.time()
        self._last_speak_ts_by_source[req.source] = ts
        self._last_speak_ts = ts
        self._spoken_count += 1

    async def _wait_voicevox_ready(self) -> bool:
        retries = max(1, self._settings.SPEECH_VOICEVOX_READY_RETRIES)
        interval = self._settings.SPEECH_VOICEVOX_READY_INTERVAL_SEC
        for attempt in range(retries):
            try:
                if await is_voicevox_ready():
                    return True
            except Exception as e:
                logger.debug(f"voicevox_ready チェック例外: {e}")
            if attempt < retries - 1:
                await asyncio.sleep(interval)
        return False

    async def _dispatch(self, req: SpeechRequest, text: str) -> None:
        """VOICEVOX 発話 + フロント broadcast を実行."""
        from ..modules.voice.engine import speak

        preset = self._settings.VOICE_PRESETS.get(
            req.emotion, self._settings.VOICE_PRESETS.get("通常", {})
        )
        speaker_id = self._settings.VOICEVOX_SPEAKER

        try:
            # 重複判定は consumer で済ませているので speak 側は force=True
            await asyncio.to_thread(
                speak,
                text,
                speaker_id,
                float(preset.get("speed", 1.0)),
                float(preset.get("pitch", 0.0)),
                float(preset.get("intonation", 1.0)),
                1.0,
                True,
            )
        except Exception as e:
            logger.error(
                f"speech 発話例外: source={req.source} "
                f"{type(e).__name__}: {e}"
            )

        try:
            await manager.broadcast(
                {
                    "type": "speak",
                    "data": {
                        "text": text,
                        "emotion": req.emotion,
                        "source": req.source,
                        "ts": time.time(),
                        "meta": req.meta,
                    },
                }
            )
        except Exception as e:
            logger.error(
                f"speech broadcast 例外: source={req.source} "
                f"{type(e).__name__}: {e}"
            )
