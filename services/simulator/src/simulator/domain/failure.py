"""Planted failures 1-5 (Must, per PLAN §1) and the schedule that assigns them.

Each planted failure has a hidden `failure_at` timestamp — the ground truth
used only for ML labels later (never sent on the wire) — and an `onset_at`
some days earlier, when the vehicle's signals start drifting away from
healthy baseline. `severity(at)` turns that window into a 0..1 ramp that the
signal engine uses to bend FAST/HEALTH values toward the failure.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum


class FailureType(str, Enum):
    COOLING = "cooling"
    LUBRICATION = "lubrication"
    BATTERY = "battery"
    MISFIRE = "misfire"
    BRAKE_WEAR = "brake_wear"


# DTCs associated with each failure (PLAN §1 table). Brake wear is detected by
# threshold (brake_pad_pct), not a DTC, so it has none.
FAILURE_DTCS: dict[FailureType, list[str]] = {
    FailureType.COOLING: ["P0128", "P0217"],
    FailureType.LUBRICATION: ["P0520", "P0521", "P0522", "P0523", "P0524"],
    FailureType.BATTERY: ["P0562", "P0615"],
    FailureType.MISFIRE: ["P0300", "P0301", "P0302", "P0303", "P0304", "P0305", "P0306", "P0307", "P0308"],
    FailureType.BRAKE_WEAR: [],
}


@dataclass(frozen=True)
class FailurePlan:
    vin: str
    failure_type: FailureType
    onset_at: datetime
    failure_at: datetime

    def severity(self, at: datetime) -> float:
        """0.0 before onset, ramping linearly to 1.0 at failure_at, then held at 1.0."""
        if at >= self.failure_at:
            return 1.0
        if at <= self.onset_at:
            return 0.0
        span = (self.failure_at - self.onset_at).total_seconds()
        elapsed = (at - self.onset_at).total_seconds()
        return elapsed / span


def plan_failures(
    vins: list[str],
    now: datetime,
    window_days: int = 30,
    rate_range: tuple[float, float] = (0.03, 0.05),
    onset_days_before_window_end: tuple[int, int] = (3, 10),
    seed: int | None = None,
) -> dict[str, FailurePlan]:
    """Pick 3-5% of `vins` (PLAN §1) to fail within the next `window_days`.

    `failure_at` is drawn uniformly across the window; `onset_at` is 3-10
    days before it (clamped to `now`), matching a Must-failure's early-warning
    pattern being visible days ahead, per PLAN §1.
    """
    rng = random.Random(seed)
    rate = rng.uniform(*rate_range)
    n_failing = round(len(vins) * rate)
    chosen = rng.sample(vins, k=min(n_failing, len(vins)))

    plans: dict[str, FailurePlan] = {}
    failure_types = list(FailureType)
    for v in chosen:
        failure_at = now + timedelta(days=rng.uniform(0, window_days))
        onset_offset = rng.uniform(*onset_days_before_window_end)
        onset_at = max(now, failure_at - timedelta(days=onset_offset))
        plans[v] = FailurePlan(
            vin=v,
            failure_type=rng.choice(failure_types),
            onset_at=onset_at,
            failure_at=failure_at,
        )
    return plans
