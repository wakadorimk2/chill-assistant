"""
画面差分検知

mss でプライマリモニタを定期キャプチャし、cv2.absdiff のグレースケール平均値が
しきい値を超えた場合に WatcherEvent を dispatch する。

state machine で「動画再生中の継続的な差分」と「単発の急変」を区別し、
animating 状態中は再 enqueue しないことで broadcast 洪水を防ぐ。

診断用途で _update_state は各判定の理由 (Decision) を返す。直近 50 件は
リングバッファで保持し、get_snapshot() / get_recent_decisions() で参照できる。
"""

import asyncio
import logging
import time
import traceback
from collections import deque
from typing import Any, Awaitable, Callable, Literal, Optional

import cv2
import numpy as np
import psutil
from numpy.typing import NDArray

from .capture import capture_primary_screen, to_gray_small
from .diagnostics import Decision, DecisionReason
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
        strong_diff_multiplier: float = 2.0,
        reenqueue_cooldown_sec: float = 5.0,
        verbose_log: bool = False,
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
        self._strong_diff_multiplier = strong_diff_multiplier
        self._reenqueue_cooldown_sec = reenqueue_cooldown_sec
        self._verbose_log = verbose_log

        # state machine
        self._state: Literal["idle", "animating"] = "idle"
        self._recent_diffs: deque[float] = deque(maxlen=3)
        self._calm_streak: int = 0  # animating → idle 復帰判定用
        self._last_enqueue_ts: float = 0.0

        # adaptive interval (CPU 高負荷時に伸縮)
        self._interval_multiplier: float = 1.0
        self._last_cpu_check: float = 0.0

        # 診断 (PR: watcher 診断機能)
        self._last_decision: Optional[Decision] = None
        self._recent_decisions: deque[Decision] = deque(maxlen=50)
        self._last_diff_image: Optional[NDArray[np.uint8]] = None
        self._frame_count: int = 0
        self._enqueue_count: int = 0
        self._skip_count: int = 0

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

    def _cooldown_remaining(self, now: float) -> float:
        """前回 enqueue からのクールダウン残秒数 (0.0 以上)"""
        if self._last_enqueue_ts <= 0.0:
            return 0.0
        return max(
            0.0, self._reenqueue_cooldown_sec - (now - self._last_enqueue_ts)
        )

    def _update_state(
        self, score: float, now: float
    ) -> tuple[bool, Decision]:
        """
        state machine 更新。(enqueue するか, 判定理由) を返す。

        idle → animating: latest > threshold AND latest >= recent_avg * 2.0
        animating → idle: recent_avg < threshold * 0.5 が 3 連続
        animating 中の強制発火: latest >= threshold * strong_diff_multiplier
                              かつ 前回 enqueue から reenqueue_cooldown_sec 経過
        """
        prev_avg = (
            sum(self._recent_diffs) / len(self._recent_diffs)
            if self._recent_diffs
            else 0.0
        )
        state_before = self._state
        self._recent_diffs.append(score)

        should_enqueue: bool
        reason: DecisionReason

        if state_before == "idle":
            if score <= self._diff_threshold:
                should_enqueue = False
                reason = "skip_below_threshold"
            elif score < prev_avg * 2.0:
                # しきい値超だが急変ジャンプ未達
                should_enqueue = False
                reason = "skip_not_jump"
            else:
                self._state = "animating"
                self._calm_streak = 0
                self._last_enqueue_ts = now
                should_enqueue = True
                reason = "enqueue_idle_jump"
        else:
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

            cooldown_elapsed = (
                now - self._last_enqueue_ts >= self._reenqueue_cooldown_sec
            )
            strong_change = (
                score >= self._diff_threshold * self._strong_diff_multiplier
            )
            if not cooldown_elapsed:
                should_enqueue = False
                reason = "skip_animating_cooldown"
            elif not strong_change:
                should_enqueue = False
                reason = "skip_animating_below_strong"
            else:
                self._last_enqueue_ts = now
                should_enqueue = True
                reason = "enqueue_strong_during_anim"

        decision = Decision(
            ts=now,
            score=score,
            prev_avg=prev_avg,
            threshold=self._diff_threshold,
            state_before=state_before,
            state_after=self._state,
            reason=reason,
            cooldown_remaining_sec=self._cooldown_remaining(now),
        )
        return should_enqueue, decision

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

    def get_snapshot(self) -> dict[str, Any]:
        """フルスナップショット (debug エンドポイント用)"""
        now = time.time()
        sec_since_last = (
            now - self._last_enqueue_ts if self._last_enqueue_ts > 0.0 else None
        )
        return {
            "state": self._state,
            "recent_diffs": list(self._recent_diffs),
            "calm_streak": self._calm_streak,
            "last_enqueue_ts": self._last_enqueue_ts,
            "seconds_since_last_enqueue": sec_since_last,
            "cooldown_remaining_sec": self._cooldown_remaining(now),
            "interval_multiplier": self._interval_multiplier,
            "current_interval_sec": self._interval_for_phase(),
            "frame_count": self._frame_count,
            "enqueue_count": self._enqueue_count,
            "skip_count": self._skip_count,
            "last_decision": (
                self._last_decision.to_dict() if self._last_decision else None
            ),
            "diff_threshold": self._diff_threshold,
            "strong_diff_multiplier": self._strong_diff_multiplier,
            "reenqueue_cooldown_sec": self._reenqueue_cooldown_sec,
            "verbose_log": self._verbose_log,
        }

    def get_recent_decisions(self, limit: int = 50) -> list[dict[str, Any]]:
        items = list(self._recent_decisions)[-limit:]
        return [d.to_dict() for d in items]

    def get_last_diff_jpeg(self, quality: int = 70) -> Optional[bytes]:
        """cv2.absdiff の可視化 (白いほど差分が大)。直前の diff image を JPEG 化"""
        img = self._last_diff_image
        if img is None:
            return None
        try:
            ok, buf = cv2.imencode(
                ".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), quality]
            )
            if not ok:
                return None
            return bytes(buf.tobytes())
        except Exception as e:
            logger.error(f"diff JPEG エンコードに失敗: {e}")
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
                    # 直前の差分画像を可視化用に保存 (numpy 参照上書き)
                    self._last_diff_image = cv2.absdiff(prev_small, small)
                except Exception as e:
                    logger.error(f"差分計算に失敗: {e}")
                    prev_small = small
                    continue

                now = time.time()
                should_enqueue, decision = self._update_state(score, now)
                self._last_decision = decision
                self._recent_decisions.append(decision)
                self._frame_count += 1
                prev_small = small

                if not should_enqueue:
                    self._skip_count += 1
                    msg = (
                        f"diff={score:.2f} state={self._state} "
                        f"reason={decision.reason} skip"
                    )
                    if self._verbose_log:
                        logger.info(msg)
                    else:
                        logger.debug(msg)
                    continue

                self._enqueue_count += 1
                logger.info(
                    f"diff={score:.2f} state={self._state} "
                    f"reason={decision.reason} → enqueue"
                )
                event = WatcherEvent(
                    kind=WatcherEventKind.SCREEN_DIFF,
                    score=score,
                    window_title=self._get_window_title(),
                    ts=time.time(),
                    extra={
                        "state": self._state,
                        "reason": decision.reason,
                    },
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
