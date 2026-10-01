"""Baseline predictor (PLAN §2 ML: "Baseline: active DTC or threshold breach").

Fires only once a signal has already crossed the same threshold the real-time
Flink rules use (session 4) — by construction it has ~0 lead time on a
gradual failure, which is exactly the gap the trained model (`train.py`) is
meant to beat with `lead_days`. Deliberately dumb and threshold-only: no
trend, no cross-signal reasoning.
"""
from __future__ import annotations

# Same thresholds as the real-time rules (services/simulator/.../signals.py,
# stream/flink/sql/03_realtime_rules.sql) — a predictive-window baseline that
# reuses the real-time cutoff, not an easier one.
COOLANT_ALERT_C = 110.0
OIL_KPA_ALERT = 40.0
CHARGE_V_ALERT = 12.5
BRAKE_PAD_ALERT_PCT = 8.0
# 6-8 (session 10b) — same cutoffs as the new real-time rules
# (stream/flink/sql/03_realtime_rules.sql).
TRANS_C_ALERT = 130.0
TIRE_KPA_ALERT = 550.0
CELL_TEMP_ALERT_C = 60.0


def predict(row: dict) -> int:
    """1 if any threshold is breached or a DTC is active on this feature row."""
    if row.get("any_dtc_today"):
        return 1
    max_coolant = row.get("max_coolant_c")
    if max_coolant is not None and max_coolant > COOLANT_ALERT_C:
        return 1
    min_oil = row.get("min_oil_kpa")
    if min_oil is not None and min_oil < OIL_KPA_ALERT:
        return 1
    min_charge = row.get("min_charge_v")
    if min_charge is not None and min_charge < CHARGE_V_ALERT:
        return 1
    min_pad = row.get("min_brake_pad_pct")
    if min_pad is not None and min_pad < BRAKE_PAD_ALERT_PCT:
        return 1
    max_trans = row.get("max_trans_c")
    if max_trans is not None and max_trans > TRANS_C_ALERT:
        return 1
    min_tire = row.get("min_tire_kpa")
    if min_tire is not None and min_tire < TIRE_KPA_ALERT:
        return 1
    max_cell_temp = row.get("max_cell_temp_c")
    if max_cell_temp is not None and max_cell_temp > CELL_TEMP_ALERT_C:
        return 1
    return 0
