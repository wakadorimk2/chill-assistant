"""
画面差分検知

mss でプライマリモニタを定期キャプチャし、cv2.absdiff のグレースケール平均値が
しきい値を超えた場合に WatcherEvent を dispatch する。

state machine で「動画再生中の継続的な差分」と「単発の急変」を区別し、
animating 状態中は再 enqueue しないことで broadcast 洪水を防ぐ。
"""

import asyncio
import logging
import time
import traceback
from collections import deque
from typing import Awaitable, Callable, Literal, Optional

import cv2
import numpy as np
import psutil
from numpy.typing import NDArray

from .capture import capture_primary_screen, to_gray_small
from .events import WatcherEvent, WatcherEventKind

logger = logging.getLogger(__name__)

DispatchFn = Callable[[WatcherEvent, Optional[NDArray[np.uint8]]], Awaitable[None]]
PhaseFn = Callable[[], Literal["active", "idle", "funya"]]
TitleFn = Callable[[], Optional[str]]
FrameSinkFn = Callable[[NDArray[np.uint8]], None]


class ScreenWatcher:
    """画面差分検知ループ"""

    def __init__(
        self,
        dispatch: DispatchFn,
        get_phase: PhaseFn,
        get_window_title: TitleFn,
        on_frame_captured: Optional[FrameSinkFn] = None,
        diff_threshold: float = 12.0,
        active_interval: float = 3.0,
        idle_interval: float = 10.0,
        funya_interval: float = 30.0,
        resize: tuple[int, int] = (240, 135),
        cpu_high_threshold: float = 70.0,
        cpu_check_interval: float = 10.0,
    ) -> None:
        self._dispatch = dispatch
        self._get_phase = get_phase
        self._get_window_title = get_window_title
        self._on_frame_captured = on_frame_captured
        self._diff_threshold = diff_threshold
        self._active_interval = active_interval
        self._idle_interval = idle_interval
        self._funya_interval = funya_interval
        self._resize = resize
        self._cpu_high_threshold = cpu_high_threshold
        self._cpu_check_interval = cpu_check_interval

        # state machine
        self._state: Literal["idle", "animating"] = "idle"
        self._recent_diffs: deque[float] = deque(maxlen=3)
        self._calm_streak: int = 0  # animating → idle 復帰判定用

        # adaptive interval (CPU 高負荷時に伸縮)
        self._interval_multiplier: float = 1.0
        self._last_cpu_check: float = 0.0

    def _interval_for_phase(self) -> float:
        """現在のフェーズに応じた基準 interval"""
        phase = self._get_phase()
        if phase == "funya":
            base = self._funya_interval
        elif phase == "idle":
            base = self._idle_interval
        else:
            base = self._active_interval
        return base * self._interval_multiplier

    def _maybe_adjust_for_cpu(self) -> None:
        """CPU 高負荷時に interval_multiplier を 1.5 倍に伸ばす"""
        now = time.time()
        if now - self._last_cpu_check < self._cpu_check_interval:
            return
        self._last_cpu_check = now
        try:
            cpu = psutil.cpu_percent(interval=None)
        except Exception as e:
            logger.warning(f"CPU 使用率取得に失敗: {e}")
            return
        if cpu > self._cpu_high_threshold:
            self._interval_multiplier = min(self._interval_multiplier * 1.5, 2.0)
            logger.info(
                f"高 CPU ({cpu:.1f}%) のため interval を {self._interval_multiplier:.2f}x に伸長"
            )
        elif self._interval_multiplier > 1.0:
            self._interval_multiplier = 1.0
            logger.info(f"CPU 平常化 ({cpu:.1f}%) のため interval を 1.0x に戻す")

    @staticmethod
    def _compute_diff(
        prev: NDArray[np.uint8], cur: NDArray[np.uint8]
    ) -> float:
        """グレースケール 2 枚の絶対差の平均値"""
        return float(np.mean(cv2.absdiff(prev, cur)))

    def _update_state(self, score: float) -> bool:
        """
        state machine 更新。enqueue すべきなら True を返す。

        idle → animating: latest > threshold AND latest >= recent_avg * 2.0
        animating → idle: recent_avg < threshold * 0.5 が 3 連続
        """
        prev_avg = (
            sum(self._recent_diffs) / len(self._recent_diffs)
            if self._recent_diffs
            else 0.0
        )
        self._recent_diffs.append(score)

        if self._state == "idle":
            # 急変ジャンプ判定: 直近平均の 2 倍以上 かつ しきい値超
            jump = score >= max(prev_avg * 2.0, self._diff_threshold)
            if score > self._diff_threshold and jump:
                self._state = "animating"
                self._calm_streak = 0
                return True
            return False

        # state == "animating"
        cur_avg = sum(self._recent_diffs) / len(self._recent_diffs)
        if cur_avg < self._diff_threshold * 0.5:
            self._calm_streak += 1
            if self._calm_streak >= 3:
                self._state = "idle"
                self._calm_streak = 0
                logger.debug("ScreenWatcher state → idle")
        else:
            self._calm_streak = 0
        return False

    async def _capture_and_reduce(
        self,
    ) -> Optional[tuple[NDArray[np.uint8], NDArray[np.uint8]]]:
        """ブロッキング処理を executor に逃がして frame と縮小グレーを取得"""
        loop = asyncio.get_running_loop()
        try:
            frame = await loop.run_in_executor(None, capture_primary_screen)
            small = await loop.run_in_executor(
                None, to_gray_small, frame, self._resize
            )
            return frame, small
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"画面キャプチャに失敗: {e}")
            return None

    async def run(self) -> None:
        """メインループ。CancelledError で graceful 終了"""
        logger.info("ScreenWatcher 開始")
        prev_small: Optional[NDArray[np.uint8]] = None
        try:
            while True:
                interval = self._interval_for_phase()
                await asyncio.sleep(interval)

                self._maybe_adjust_for_cpu()

                result = await self._capture_and_reduce()
                if result is None:
                    continue
                frame, small = result

                if self._on_frame_captured is not None:
                    self._on_frame_captured(frame)

                if prev_small is None:
                    prev_small = small
                    continue

                try:
                    score = self._compute_diff(prev_small, small)
                except Exception as e:
                    logger.error(f"差分計算に失敗: {e}")
                    prev_small = small
                    continue

                should_enqueue = self._update_state(score)
                prev_small = small

                if not should_enqueue:
                    continue

                event = WatcherEvent(
                    kind=WatcherEventKind.SCREEN_DIFF,
                    score=score,
                    window_title=self._get_window_title(),
                    ts=time.time(),
                    extra={"state": self._state},
                )
                try:
                    await self._dispatch(event, frame)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error(f"dispatch に失敗: {e}\n{traceback.format_exc()}")
        except asyncio.CancelledError:
            logger.info("ScreenWatcher キャンセルされました")
            raise
        finally:
            logger.info("ScreenWatcher 終了")
