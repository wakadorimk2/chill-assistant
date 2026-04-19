"""
Watcher 診断用データ型

ScreenWatcher._update_state の判定理由を列挙し、
スナップショット API / ログ出力で共通に使う。
"""

from dataclasses import asdict, dataclass
from typing import Any, Literal

DecisionReason = Literal[
    "enqueue_idle_jump",
    "enqueue_strong_during_anim",
    "skip_below_threshold",
    "skip_not_jump",
    "skip_animating_cooldown",
    "skip_animating_below_strong",
]


@dataclass(frozen=True)
class Decision:
    """1 フレーム分の判定結果スナップショット"""

    ts: float
    score: float
    prev_avg: float
    threshold: float
    state_before: Literal["idle", "animating"]
    state_after: Literal["idle", "animating"]
    reason: DecisionReason
    cooldown_remaining_sec: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
