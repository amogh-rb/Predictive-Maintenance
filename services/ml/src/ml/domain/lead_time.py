"""Estimates `prediction.lead_days` for a live-scored vehicle-day: how many
days until this failure type's real-time threshold (stream/flink/sql/03_
realtime_rules.sql) is projected to be crossed, extrapolating the same 7-day
trailing slope features `batch/spark/feature_job.py` already computes.

Ground truth `days_to_failure` (used for the test-set "recall at >=5d lead"
metric) only exists for historical, already-resolved vin-days — a live
prediction is, by definition, before the failure has happened, so there's no
ground truth to report. This is a same-signal linear extrapolation instead
(PLAN §1's own "early-warning pattern" column describes exactly this: "creeps
up over days" / "projects the date pads hit the minimum"), not a second model.

Known gap this closes: `services/ml/train.py` never wrote this column before
session 9's follow-up — the UI always showed "—" (PROGRESS.md session 7).
"""
from __future__ import annotations

MAX_LEAD_DAYS = 30.0  # cap — a barely-moving slope shouldn't claim "3650 days"
TRAIL_DAYS = 7  # matches feature_job.py's TRAIL_DAYS


def _days_to_cross(current: float, threshold: float, slope_7d: float, rising: bool) -> float | None:
    """`slope_7d` is the change over the last 7 days. Returns None if the
    trend isn't moving toward the threshold at all (flat or improving) —
    "we don't have evidence of an approaching failure by this signal", not
    "0 days left"."""
    per_day = slope_7d / TRAIL_DAYS
    if rising:
        if per_day <= 0 or current >= threshold:
            return None
        days = (threshold - current) / per_day
    else:
        if per_day >= 0 or current <= threshold:
            return None
        days = (current - threshold) / -per_day
    return days if days <= MAX_LEAD_DAYS else None


# One entry per failure type with a usable trailing-slope feature (PLAN §1
# thresholds, matching the real-time Flink rules exactly). "misfire" has no
# numeric slope feature (it's DTC-recurrence based) and is deliberately left
# out — its lead_days stays null rather than guessed.
_ESTIMATORS = {
    "cooling": lambda row: _days_to_cross(row["max_coolant_c"], 110.0, row["coolant_slope_7d"], rising=True),
    "lubrication": lambda row: _days_to_cross(row["min_oil_kpa"], 100.0, row["oil_kpa_slope_7d"], rising=False),
    "battery": lambda row: _days_to_cross(row["min_charge_v"], 12.5, row["charge_v_slope_7d"], rising=False),
    "brake_wear": lambda row: _days_to_cross(row["min_brake_pad_pct"], 20.0, row["brake_pad_slope_7d"], rising=False),
    # 6-8 (session 10b), same thresholds as baseline.py / the Flink rules.
    "tyre": lambda row: _days_to_cross(row["min_tire_kpa"], 550.0, row["min_tire_kpa_slope_7d"], rising=False),
    "transmission": lambda row: _days_to_cross(row["max_trans_c"], 130.0, row["trans_c_slope_7d"], rising=True),
    "ev_battery": lambda row: _days_to_cross(row["max_cell_temp_c"], 60.0, row["max_cell_temp_c_slope_7d"], rising=True),
}


def estimate_lead_days(failure_type: str, row: dict) -> float | None:
    estimator = _ESTIMATORS.get(failure_type)
    if estimator is None:
        return None
    return estimator(row)
