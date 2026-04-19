"""差分計算と state machine の遷移を検証

`_update_state` はタプル `(should_enqueue, Decision)` を返す。
ここでは bool 部分のみ検証し、Decision.reason は test_watcher_diagnostics.py で網羅。
"""

import numpy as np
import pytest
from app.modules.watcher.screen_watcher import ScreenWatcher


async def _noop_dispatch(_event, _frame):  # type: ignore[no-untyped-def]
    pass


def _make_watcher(
    threshold: float = 12.0,
    strong_multiplier: float = 2.0,
    cooldown: float = 5.0,
) -> ScreenWatcher:
    return ScreenWatcher(
        dispatch=_noop_dispatch,
        get_phase=lambda: "active",
        get_window_title=lambda: None,
        diff_threshold=threshold,
        strong_diff_multiplier=strong_multiplier,
        reenqueue_cooldown_sec=cooldown,
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
    assert w._update_state(2.0, 0.0)[0] is False
    assert w._update_state(2.0, 1.0)[0] is False
    # 急変ジャンプ (50 > 12 かつ 50 >= 2.0 * 2.0)
    assert w._update_state(50.0, 2.0)[0] is True
    assert w._state == "animating"


def test_state_machine_animating_within_cooldown_suppressed() -> None:
    """animating 中: クールダウン内は再 enqueue されない (動画洪水防止)"""
    w = _make_watcher(threshold=12.0, cooldown=5.0)
    w._update_state(2.0, 0.0)
    w._update_state(2.0, 1.0)
    w._update_state(50.0, 2.0)  # idle → animating, enqueue, last_ts=2.0
    # クールダウン (5秒) 内: 動画継続でも再 enqueue されない
    assert w._update_state(15.0, 3.0)[0] is False
    assert w._update_state(20.0, 5.0)[0] is False
    assert w._state == "animating"


def test_state_machine_animating_to_idle_after_calm() -> None:
    """animating 中: 平穏 (recent_avg が threshold * 0.5 未満) が 3 連続で idle 復帰

    deque(maxlen=3) が大きな値を含む間は recent_avg が下がりきらないので、
    平穏値が deque を満たしてからさらに 3 連続で calm_streak が 3 に達する。
    """
    w = _make_watcher(threshold=12.0)
    w._update_state(2.0, 0.0)
    w._update_state(2.0, 1.0)
    w._update_state(50.0, 2.0)  # animating
    # 平穏値を 6 回 (= deque を満たす 3 回 + 3 連続平穏判定)
    for i in range(6):
        w._update_state(1.0, 100.0 + i)  # クールダウン外でも平穏なので enqueue されない
    assert w._state == "idle"


def test_state_machine_below_threshold_no_enqueue() -> None:
    """しきい値未満なら enqueue されない"""
    w = _make_watcher(threshold=12.0)
    assert w._update_state(5.0, 0.0)[0] is False
    assert w._update_state(8.0, 1.0)[0] is False
    assert w._state == "idle"


def test_state_machine_strong_change_after_cooldown_reenqueue() -> None:
    """animating 中でも、しきい値の 2 倍超 かつ クールダウン経過後なら再 enqueue

    ゲーム画面でメニュー開閉や大きな変化を取りこぼさないため。
    """
    w = _make_watcher(threshold=12.0, strong_multiplier=2.0, cooldown=5.0)
    w._update_state(2.0, 0.0)
    w._update_state(2.0, 1.0)
    w._update_state(50.0, 2.0)  # idle → animating, enqueue, last_ts=2.0
    # クールダウン中: 強い急変も抑制
    assert w._update_state(30.0, 4.0)[0] is False
    # クールダウン経過 + 強い急変 (>= 12*2=24): 再 enqueue
    assert w._update_state(30.0, 8.0)[0] is True


def test_state_machine_strong_change_below_threshold_no_reenqueue() -> None:
    """animating 中: クールダウン経過でも 2 倍未満なら enqueue されない (動画継続)"""
    w = _make_watcher(threshold=12.0, strong_multiplier=2.0, cooldown=5.0)
    w._update_state(2.0, 0.0)
    w._update_state(2.0, 1.0)
    w._update_state(50.0, 2.0)  # animating, last_ts=2.0
    # クールダウン経過しても 24 未満なので enqueue されない
    assert w._update_state(20.0, 8.0)[0] is False
    assert w._update_state(15.0, 14.0)[0] is False
