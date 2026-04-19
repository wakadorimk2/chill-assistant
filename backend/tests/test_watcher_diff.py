"""差分計算と state machine の遷移を検証"""

import numpy as np
import pytest
from app.modules.watcher.screen_watcher import ScreenWatcher


async def _noop_dispatch(_event, _frame):  # type: ignore[no-untyped-def]
    pass


def _make_watcher(threshold: float = 12.0) -> ScreenWatcher:
    return ScreenWatcher(
        dispatch=_noop_dispatch,
        get_phase=lambda: "active",
        get_window_title=lambda: None,
        diff_threshold=threshold,
    )


def test_compute_diff_identical_zero() -> None:
    arr = np.full((10, 10), 100, dtype=np.uint8)
    assert ScreenWatcher._compute_diff(arr, arr) == 0.0


def test_compute_diff_full_max() -> None:
    a = np.zeros((10, 10), dtype=np.uint8)
    b = np.full((10, 10), 255, dtype=np.uint8)
    # 全画素 255 差なので mean は 255.0
    assert ScreenWatcher._compute_diff(a, b) == pytest.approx(255.0)


def test_state_machine_idle_to_animating_on_jump() -> None:
    """idle 中: しきい値超 + 急変 (前平均の 2 倍以上) で animating 遷移し enqueue"""
    w = _make_watcher(threshold=12.0)
    # 平穏 (recent_avg = 2.0)
    assert w._update_state(2.0) is False
    assert w._update_state(2.0) is False
    # 急変ジャンプ (50 > 12 かつ 50 >= 2.0 * 2.0)
    assert w._update_state(50.0) is True
    assert w._state == "animating"


def test_state_machine_animating_no_reenqueue() -> None:
    """animating 中: しきい値超でも再 enqueue されない (broadcast 洪水防止)"""
    w = _make_watcher(threshold=12.0)
    w._update_state(2.0)
    w._update_state(2.0)
    w._update_state(50.0)  # idle → animating, enqueue=True
    # 動画継続: しきい値超だが再 enqueue されない
    assert w._update_state(40.0) is False
    assert w._update_state(45.0) is False
    assert w._state == "animating"


def test_state_machine_animating_to_idle_after_calm() -> None:
    """animating 中: 平穏 (recent_avg が threshold * 0.5 未満) が 3 連続で idle 復帰

    deque(maxlen=3) が大きな値を含む間は recent_avg が下がりきらないので、
    平穏値が deque を満たしてからさらに 3 連続で calm_streak が 3 に達する。
    """
    w = _make_watcher(threshold=12.0)
    w._update_state(2.0)
    w._update_state(2.0)
    w._update_state(50.0)  # animating
    # 平穏値を 6 回 (= deque を満たす 3 回 + 3 連続平穏判定)
    for _ in range(6):
        w._update_state(1.0)
    assert w._state == "idle"


def test_state_machine_below_threshold_no_enqueue() -> None:
    """しきい値未満なら enqueue されない"""
    w = _make_watcher(threshold=12.0)
    assert w._update_state(5.0) is False
    assert w._update_state(8.0) is False
    assert w._state == "idle"
