"""
フォアグラウンドウィンドウ監視

pywin32 で `GetForegroundWindow` + `GetWindowText` を定期ポーリングし、
タイトルが変化したら WatcherEvent(WINDOW_CHANGED) を dispatch する。

Step 2 ではタイトル文字列の変化のみ検知。プロセス名取得・優先度ロジックは
Step 3 の companion 側で実装する。
"""

import asyncio
import logging
import sys
import time
from typing import Awaitable, Callable, Optional

import numpy as np
from numpy.typing import NDArray

from .events import WatcherEvent, WatcherEventKind

logger = logging.getLogger(__name__)

if sys.platform == "win32":
    import win32gui  # type: ignore[import-not-found]
else:
    win32gui = None  # type: ignore[assignment]


DispatchFn = Callable[[WatcherEvent, Optional[NDArray[np.uint8]]], Awaitable[None]]


class WindowWatcher:
    """フォアグラウンドウィンドウタイトル監視ループ"""

    def __init__(
        self,
        dispatch: DispatchFn,
        on_title_update: Callable[[Optional[str]], None],
        interval_sec: float = 2.0,
    ) -> None:
        self._dispatch = dispatch
        self._on_title_update = on_title_update
        self._interval_sec = interval_sec

    def _read_foreground_title(self) -> Optional[str]:
        """フォアグラウンドウィンドウのタイトル取得。空文字 / 例外時は None"""
        if win32gui is None:
            return None
        try:
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                return None
            title = win32gui.GetWindowText(hwnd)
            if not title:
                return None
            return str(title)
        except Exception as e:
            logger.warning(f"GetForegroundWindow に失敗: {e}")
            return None

    async def run(self) -> None:
        """メインループ。CancelledError で graceful 終了"""
        if win32gui is None:
            logger.warning(
                "win32gui が利用できないため WindowWatcher は無効です (非 Windows 環境)"
            )
            return

        logger.info("WindowWatcher 開始")
        prev_title: Optional[str] = None
        try:
            while True:
                await asyncio.sleep(self._interval_sec)

                title = self._read_foreground_title()
                if title is None:
                    # フリッカー回避: None / "" のときは比較せずスキップ
                    continue

                self._on_title_update(title)

                if title == prev_title:
                    continue

                event = WatcherEvent(
                    kind=WatcherEventKind.WINDOW_CHANGED,
                    score=1.0,
                    window_title=title,
                    ts=time.time(),
                    extra={"prev_title": prev_title},
                )
                prev_title = title
                try:
                    await self._dispatch(event, None)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error(f"dispatch に失敗: {e}")
        except asyncio.CancelledError:
            logger.info("WindowWatcher キャンセルされました")
            raise
        finally:
            logger.info("WindowWatcher 終了")
