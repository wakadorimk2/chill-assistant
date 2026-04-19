"""
WatcherService

ScreenWatcher と WindowWatcher を統括する。
- WatcherEvent の Queue を所有 (Step 3 で companion が consume する)
- 最新フレームを 1 枚保持 (Step 3 で companion が画像取得用)
- dispatch で 「Queue put + WebSocket broadcast」 を 1 トランザクションで実施
"""

import asyncio
import logging
import time
from typing import Any, Literal, Optional

import cv2
import numpy as np
from numpy.typing import NDArray

from ...config import Settings
from ...ws.manager import manager
from .events import WatcherEvent
from .screen_watcher import ScreenWatcher
from .window_watcher import WindowWatcher

logger = logging.getLogger(__name__)


class WatcherService:
    """画面・ウィンドウ監視サブシステムの統括"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._queue: asyncio.Queue[WatcherEvent] = asyncio.Queue(
            maxsize=settings.WATCHER_QUEUE_MAX_SIZE
        )
        self._latest_frame: Optional[NDArray[np.uint8]] = None
        self._frame_lock = asyncio.Lock()
        self._last_event: Optional[WatcherEvent] = None
        self._current_window_title: Optional[str] = None
        self._tasks: list[asyncio.Task[None]] = []
        self._running: bool = False

        # 起動時刻記録 (Step 2 では active/idle 判定に使う簡易フォールバック)
        self._started_at: float = time.time()

    def get_phase(self) -> Literal["active", "idle", "funya"]:
        """現在の動作フェーズ。funya 状態と無操作時間で決める"""
        try:
            from ..services.funya_state import get_funya_state_service

            status = get_funya_state_service().get_status()
            if status.get("watching"):
                return "funya"
            last_active = float(status.get("last_active_seconds") or 0.0)
            if last_active >= 30.0:
                return "idle"
            return "active"
        except Exception as e:
            logger.debug(f"funya 状態取得失敗、active として扱います: {e}")
            return "active"

    def _get_window_title(self) -> Optional[str]:
        return self._current_window_title

    def _set_window_title(self, title: Optional[str]) -> None:
        self._current_window_title = title

    def _set_latest_frame_sync(self, frame: NDArray[np.uint8]) -> None:
        """同期コンテキストから呼ばれる最新フレーム保存。
        単一プロデューサ (ScreenWatcher) なので Lock なしで上書きで足りる。"""
        self._latest_frame = frame

    async def _dispatch(
        self, event: WatcherEvent, frame: Optional[NDArray[np.uint8]]
    ) -> None:
        """
        Queue put + WebSocket broadcast を 1 トランザクションで実施。
        Step 3 で companion が consume する際は broadcast を speech_bus 側に移す。
        """
        self._last_event = event

        if frame is not None:
            async with self._frame_lock:
                self._latest_frame = frame

        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning(
                f"WatcherEvent キューが満杯のため drop: kind={event.kind.value}"
            )

        try:
            await manager.broadcast(
                {"type": "watcher_event", "data": event.to_payload()}
            )
        except Exception as e:
            logger.error(f"WebSocket broadcast に失敗: {e}")

    async def start(self) -> None:
        if self._running:
            logger.info("WatcherService は既に起動しています")
            return

        screen = ScreenWatcher(
            dispatch=self._dispatch,
            get_phase=self.get_phase,
            get_window_title=self._get_window_title,
            on_frame_captured=self._set_latest_frame_sync,
            diff_threshold=self._settings.WATCHER_SCREEN_DIFF_THRESHOLD,
            active_interval=self._settings.WATCHER_ACTIVE_INTERVAL_SEC,
            idle_interval=self._settings.WATCHER_IDLE_INTERVAL_SEC,
            funya_interval=self._settings.WATCHER_FUNYA_INTERVAL_SEC,
            resize=(
                self._settings.WATCHER_DIFF_RESIZE_W,
                self._settings.WATCHER_DIFF_RESIZE_H,
            ),
        )
        window = WindowWatcher(
            dispatch=self._dispatch,
            on_title_update=self._set_window_title,
            interval_sec=self._settings.WATCHER_WINDOW_POLL_INTERVAL_SEC,
        )

        self._tasks = [
            asyncio.create_task(screen.run(), name="watcher.screen"),
            asyncio.create_task(window.run(), name="watcher.window"),
        ]
        self._running = True
        self._started_at = time.time()
        logger.info(
            f"WatcherService 起動: threshold={self._settings.WATCHER_SCREEN_DIFF_THRESHOLD}, "
            f"active={self._settings.WATCHER_ACTIVE_INTERVAL_SEC}s, "
            f"idle={self._settings.WATCHER_IDLE_INTERVAL_SEC}s, "
            f"funya={self._settings.WATCHER_FUNYA_INTERVAL_SEC}s"
        )

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        for task in self._tasks:
            task.cancel()
        try:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        except Exception as e:
            logger.warning(f"WatcherService 停止中の gather でエラー: {e}")
        self._tasks = []
        logger.info("WatcherService 停止完了")

    def get_status(self) -> dict[str, Any]:
        return {
            "running": self._running,
            "initialized": True,
            "phase": self.get_phase(),
            "queue_depth": self._queue.qsize(),
            "queue_max_size": self._settings.WATCHER_QUEUE_MAX_SIZE,
            "current_window_title": self._current_window_title,
            "last_event": (
                self._last_event.to_payload() if self._last_event else None
            ),
            "diff_threshold": self._settings.WATCHER_SCREEN_DIFF_THRESHOLD,
            "active_interval_sec": self._settings.WATCHER_ACTIVE_INTERVAL_SEC,
            "idle_interval_sec": self._settings.WATCHER_IDLE_INTERVAL_SEC,
            "funya_interval_sec": self._settings.WATCHER_FUNYA_INTERVAL_SEC,
            "uptime_sec": time.time() - self._started_at if self._running else 0.0,
        }

    def get_latest_frame_jpeg(self, quality: int = 70) -> Optional[bytes]:
        """最新キャプチャを JPEG bytes で返す (デバッグ用エンドポイント用)"""
        frame = self._latest_frame
        if frame is None:
            return None
        try:
            ok, buf = cv2.imencode(
                ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality]
            )
            if not ok:
                return None
            return bytes(buf.tobytes())
        except Exception as e:
            logger.error(f"JPEG エンコードに失敗: {e}")
            return None

    @property
    def queue(self) -> asyncio.Queue[WatcherEvent]:
        """Step 3 で companion が consume するためのアクセサ"""
        return self._queue
