"""Planted failures 1-8 (1-5 Must, 6-8 Should — promoted to built in session
10b, PLAN §1) and the schedule that assigns them.

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

from simulator.domain.vehicle import Vehicle, VehicleType


class FailureType(str, Enum):
    COOLING = "cooling"
    LUBRICATION = "lubrication"
    BATTERY = "battery"
    MISFIRE = "misfire"
    BRAKE_WEAR = "brake_wear"
    TYRE_LEAK = "tyre"
    TRANSMISSION = "transmission"
    EV_HV_BATTERY = "ev_battery"


# DTCs associated with each failure (PLAN §1 table). Brake wear and tyre leak
# are detected by threshold, not a single DTC ("C-codes" / "C0750-series" in
# the PLAN table have no one code to plant — same call `dtc_catalog.py`
# already made for brake_wear), so both have none.
FAILURE_DTCS: dict[FailureType, list[str]] = {
    FailureType.COOLING: ["P0128", "P0217"],
    FailureType.LUBRICATION: ["P0520", "P0521", "P0522", "P0523", "P0524"],
    FailureType.BATTERY: ["P0562", "P0615"],
    FailureType.MISFIRE: ["P0300", "P0301", "P0302", "P0303", "P0304", "P0305", "P0306", "P0307", "P0308"],
    FailureType.BRAKE_WEAR: [],
    FailureType.TYRE_LEAK: [],
    FailureType.TRANSMISSION: ["P0700", "P0730"],
    FailureType.EV_HV_BATTERY: ["P0A80", "P0AFA"],
}

# Which failure types a vehicle can plausibly get, by powertrain: an ICE
# truck has no HV battery to fail, an EV has no multi-speed transmission to
# slip and can't misfire (no combustion). Hybrids carry both drivetrains, so
# everything applies.
_ELIGIBLE_BY_TYPE: dict[VehicleType, list[FailureType]] = {
    VehicleType.ICE: [
        FailureType.COOLING, FailureType.LUBRICATION, FailureType.BATTERY,
        FailureType.MISFIRE, FailureType.BRAKE_WEAR, FailureType.TYRE_LEAK,
        FailureType.TRANSMISSION,
    ],
    VehicleType.EV: [
        FailureType.BATTERY, FailureType.BRAKE_WEAR, FailureType.TYRE_LEAK,
        FailureType.EV_HV_BATTERY,
    ],
    VehicleType.HYBRID: list(FailureType),
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
    vehicles: list[Vehicle],
    now: datetime,
    window_days: int = 30,
    rate_range: tuple[float, float] = (0.03, 0.05),
    onset_days_before_window_end: tuple[int, int] = (3, 10),
    seed: int | None = None,
) -> dict[str, FailurePlan]:
    """Pick 3-5% of `vehicles` (PLAN §1) to fail within the next `window_days`.

    `failure_at` is drawn uniformly across the window; `onset_at` is 3-10
    days before it (clamped to `now`), matching a Must-failure's early-warning
    pattern being visible days ahead, per PLAN §1. The failure type is chosen
    from the ones that vehicle's powertrain can actually have (`_ELIGIBLE_BY_TYPE`).
    """
    rng = random.Random(seed)
    rate = rng.uniform(*rate_range)
    n_failing = round(len(vehicles) * rate)
    chosen = rng.sample(vehicles, k=min(n_failing, len(vehicles)))

    plans: dict[str, FailurePlan] = {}
    for v in chosen:
        failure_at = now + timedelta(days=rng.uniform(0, window_days))
        onset_offset = rng.uniform(*onset_days_before_window_end)
        onset_at = max(now, failure_at - timedelta(days=onset_offset))
        plans[v.vin] = FailurePlan(
            vin=v.vin,
            failure_type=rng.choice(_ELIGIBLE_BY_TYPE[v.vehicle_type]),
            onset_at=onset_at,
            failure_at=failure_at,
        )
    return plans
