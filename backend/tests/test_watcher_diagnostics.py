"""診断機能 (Decision / snapshot / recent_decisions) の検証"""

import json

import pytest
from app.modules.watcher.diagnostics import Decision
from app.modules.watcher.screen_watcher import ScreenWatcher


async def _noop_dispatch(_event, _frame):  # type: ignore[no-untyped-def]
    pass


def _make_watcher(
    threshold: float = 12.0,
    strong_multiplier: float = 2.0,
    cooldown: float = 5.0,
    verbose_log: bool = False,
) -> ScreenWatcher:
    return ScreenWatcher(
        dispatch=_noop_dispatch,
        get_phase=lambda: "active",
        get_window_title=lambda: None,
        diff_threshold=threshold,
        strong_diff_multiplier=strong_multiplier,
        reenqueue_cooldown_sec=cooldown,
        verbose_log=verbose_log,
    )


# ==== 5 分岐 reason 網羅 ====


def test_reason_skip_below_threshold() -> None:
    w = _make_watcher(threshold=12.0)
    should, dec = w._update_state(5.0, 0.0)
    assert should is False
    assert dec.reason == "skip_below_threshold"
    assert dec.state_before == "idle"
    assert dec.state_after == "idle"


def test_reason_skip_not_jump() -> None:
    """idle: threshold 超だが前平均の 2 倍未満 (動きの途中参加など)"""
    w = _make_watcher(threshold=12.0)
    # 事前に recent_diffs を大きな値で満たしておく → prev_avg が高くなる
    w._update_state(20.0, 0.0)  # idle → animating (急変)
    # ここで idle に戻すため平穏値を deque に流し込む
    for t in range(10):
        w._update_state(0.5, 10.0 + t)
    # idle に戻った前提、recent_diffs は [0.5, 0.5, 0.5]、prev_avg=0.5
    # threshold 超 だが 0.5 * 2 = 1.0 は下回らないので「not_jump」にするには条件工夫必要
    # → ここでは recent_diffs を大きな値で手動上書きして検証
    w._state = "idle"
    w._recent_diffs.clear()
    w._recent_diffs.extend([20.0, 20.0, 20.0])  # prev_avg=20, jump 条件=40 以上
    should, dec = w._update_state(
        25.0, 100.0
    )  # 25 > 12 (threshold) だが 25 < 40 (2x)
    assert should is False
    assert dec.reason == "skip_not_jump"


def test_reason_enqueue_idle_jump() -> None:
    w = _make_watcher(threshold=12.0)
    w._update_state(2.0, 0.0)
    w._update_state(2.0, 1.0)
    should, dec = w._update_state(50.0, 2.0)
    assert should is True
    assert dec.reason == "enqueue_idle_jump"
    assert dec.state_before == "idle"
    assert dec.state_after == "animating"


def test_reason_skip_animating_cooldown() -> None:
    w = _make_watcher(threshold=12.0, cooldown=5.0)
    w._update_state(2.0, 0.0)
    w._update_state(2.0, 1.0)
    w._update_state(50.0, 2.0)  # animating, last_ts=2.0
    should, dec = w._update_state(30.0, 4.0)  # クールダウン中 (2s 経過)
    assert should is False
    assert dec.reason == "skip_animating_cooldown"
    assert dec.cooldown_remaining_sec > 0.0


def test_reason_skip_animating_below_strong() -> None:
    w = _make_watcher(threshold=12.0, strong_multiplier=2.0, cooldown=5.0)
    w._update_state(2.0, 0.0)
    w._update_state(2.0, 1.0)
    w._update_state(50.0, 2.0)  # animating
    # クールダウン経過 (7s - 2s = 5s 以上) だが score=20 < 24 (threshold*2)
    should, dec = w._update_state(20.0, 8.0)
    assert should is False
    assert dec.reason == "skip_animating_below_strong"


def test_reason_enqueue_strong_during_anim() -> None:
    w = _make_watcher(threshold=12.0, strong_multiplier=2.0, cooldown=5.0)
    w._update_state(2.0, 0.0)
    w._update_state(2.0, 1.0)
    w._update_state(50.0, 2.0)  # animating
    # クールダウン経過 + 強い急変 (30 >= 24)
    should, dec = w._update_state(30.0, 8.0)
    assert should is True
    assert dec.reason == "enqueue_strong_during_anim"
    assert dec.state_after == "animating"


# ==== snapshot のキーセット / 型 ====


EXPECTED_SNAPSHOT_KEYS = {
    "state",
    "recent_diffs",
    "calm_streak",
    "last_enqueue_ts",
    "seconds_since_last_enqueue",
    "cooldown_remaining_sec",
    "interval_multiplier",
    "current_interval_sec",
    "frame_count",
    "enqueue_count",
    "skip_count",
    "last_decision",
    "diff_threshold",
    "strong_diff_multiplier",
    "reenqueue_cooldown_sec",
    "verbose_log",
}


def test_snapshot_has_expected_keys() -> None:
    w = _make_watcher()
    snap = w.get_snapshot()
    assert set(snap.keys()) == EXPECTED_SNAPSHOT_KEYS


def test_snapshot_types() -> None:
    w = _make_watcher()
    w._update_state(20.0, 0.0)  # 1 回 update しておく
    snap = w.get_snapshot()
    assert snap["state"] in ("idle", "animating")
    assert isinstance(snap["recent_diffs"], list)
    assert isinstance(snap["calm_streak"], int)
    assert isinstance(snap["frame_count"], int)
    # 未実行なので frame_count は 0 (update_state 呼んだだけでは増えない)
    assert snap["last_decision"] is None or isinstance(snap["last_decision"], dict)


def test_snapshot_json_serializable() -> None:
    w = _make_watcher()
    w._update_state(20.0, 0.0)
    snap = w.get_snapshot()
    json.dumps(snap)  # raise しなければ OK


# ==== recent_decisions のリングバッファ ====


def test_recent_decisions_ring_buffer(monkeypatch: pytest.MonkeyPatch) -> None:
    """51 件以上 append すると最古が落ちて maxlen=50 を維持する"""
    w = _make_watcher()
    for i in range(60):
        _, dec = w._update_state(float(i), float(i))
        w._recent_decisions.append(dec)  # 通常 run() で行う操作を模倣
    result = w.get_recent_decisions()
    assert len(result) == 50


def test_recent_decisions_returns_dicts() -> None:
    w = _make_watcher()
    _, dec = w._update_state(20.0, 0.0)
    w._recent_decisions.append(dec)
    result = w.get_recent_decisions()
    assert len(result) == 1
    assert isinstance(result[0], dict)
    assert "reason" in result[0]


def test_recent_decisions_limit_respected() -> None:
    w = _make_watcher()
    for i in range(10):
        _, dec = w._update_state(float(i), float(i))
        w._recent_decisions.append(dec)
    result = w.get_recent_decisions(limit=3)
    assert len(result) == 3


# ==== Decision の to_dict ====


def test_decision_to_dict_shape() -> None:
    d = Decision(
        ts=1.0,
        score=20.0,
        prev_avg=10.0,
        threshold=12.0,
        state_before="idle",
        state_after="animating",
        reason="enqueue_idle_jump",
        cooldown_remaining_sec=0.0,
    )
    assert d.to_dict() == {
        "ts": 1.0,
        "score": 20.0,
        "prev_avg": 10.0,
        "threshold": 12.0,
        "state_before": "idle",
        "state_after": "animating",
        "reason": "enqueue_idle_jump",
        "cooldown_remaining_sec": 0.0,
    }
