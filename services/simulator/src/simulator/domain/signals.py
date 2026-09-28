"""Per-vehicle signal generation for FAST/HEALTH/EVENT payloads.

Each vehicle gets one `SignalEngine`, seeded from its VIN so a run is
reproducible. `step()` advances a simple driving-state random walk (speed,
ignition, gear) by `dt_s` simulated seconds; the `*_payload()` methods read
that state and bend it toward a planted failure's target values as
`FailurePlan.severity(at)` climbs from 0 to 1 (PLAN §1's "signals used" /
"early-warning pattern" columns, translated into formulas).
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime

from simulator.domain.failure import FAILURE_DTCS, FailurePlan, FailureType
from simulator.domain.vehicle import Vehicle, VehicleType

HEALTH_INTERVAL_S = 60
OVERSPEED_LIMIT_KMH = 90.0
# PLAN §1 real-time rule thresholds — crossed once severity reaches 1.0.
COOLANT_HEALTHY_C = 90.0
COOLANT_CRITICAL_C = 118.0
OIL_KPA_HEALTHY = 350.0
OIL_KPA_CRITICAL = 40.0
CHARGE_V_HEALTHY = 14.1
CHARGE_V_CRITICAL = 11.8
BRAKE_PAD_HEALTHY_PCT = 80.0
BRAKE_PAD_CRITICAL_PCT = 8.0


@dataclass
class _DriveState:
    ignition_on: bool = True
    speed_kmh: float = 0.0
    gear: int = 0
    odo_km: float = 0.0
    engine_hours: float = 0.0
    seconds_since_health: float = HEALTH_INTERVAL_S  # emit on first tick
    active_dtc: set[str] = field(default_factory=set)
    misfire_count: int = 0


class SignalEngine:
    def __init__(self, vehicle: Vehicle, failure_plan: FailurePlan | None = None):
        self.vehicle = vehicle
        self.failure_plan = failure_plan
        self.rng = random.Random(vehicle.vin)
        self.state = _DriveState(
            speed_kmh=self.rng.uniform(0, 70),
            odo_km=self.rng.uniform(5_000, 300_000),
            engine_hours=self.rng.uniform(200, 12_000),
        )

    # -- driving-state random walk ---------------------------------------
    def step(self, dt_s: float) -> None:
        s = self.state
        if self.rng.random() < 0.002:
            s.ignition_on = not s.ignition_on
        if s.ignition_on:
            s.speed_kmh = max(0.0, min(110.0, s.speed_kmh + self.rng.uniform(-8, 8)))
            s.gear = 0 if s.speed_kmh < 5 else min(8, int(s.speed_kmh // 12) + 1)
            s.engine_hours += dt_s / 3600
            s.odo_km += s.speed_kmh * dt_s / 3600
        else:
            s.speed_kmh = 0.0
            s.gear = 0
        s.seconds_since_health += dt_s

    def _severity(self, at: datetime) -> float:
        return self.failure_plan.severity(at) if self.failure_plan else 0.0

    def _failure_type(self) -> FailureType | None:
        return self.failure_plan.failure_type if self.failure_plan else None

    def health_due(self) -> bool:
        return self.state.seconds_since_health >= HEALTH_INTERVAL_S

    # -- payload builders --------------------------------------------------
    def fast_payload(self, at: datetime) -> dict:
        s, sev, ftype = self.state, self._severity(at), self._failure_type()
        rpm = 0.0 if s.gear == 0 else 700 + s.gear * 220 + self.rng.uniform(-100, 100)
        load_pct = 0.0 if s.gear == 0 else min(100.0, 20 + s.speed_kmh * 0.6 + self.rng.uniform(-5, 5))

        coolant_c = COOLANT_HEALTHY_C + self.rng.uniform(-2, 2)
        oil_kpa = OIL_KPA_HEALTHY - rpm * 0.05 + self.rng.uniform(-10, 10)
        fuel_rate_lph = 0.0 if s.gear == 0 else 2 + load_pct * 0.08 + self.rng.uniform(-0.3, 0.3)

        if ftype == FailureType.COOLING:
            coolant_c += sev * (COOLANT_CRITICAL_C - COOLANT_HEALTHY_C)
        elif ftype == FailureType.LUBRICATION:
            oil_kpa -= sev * (OIL_KPA_HEALTHY - OIL_KPA_CRITICAL)
        elif ftype == FailureType.MISFIRE:
            fuel_rate_lph *= 1 + sev * 0.6

        payload = {
            "lat": 19.0 + self.rng.uniform(-2, 2),
            "lon": 73.0 + self.rng.uniform(-2, 2),
            "heading": self.rng.uniform(0, 359.9),
            "gps_hdop": round(self.rng.uniform(0.6, 2.0), 2),
            "speed_kmh": round(s.speed_kmh, 1),
            "odo_km": round(s.odo_km, 2),
            "accel_long_g": round(self.rng.uniform(-0.3, 0.3), 3),
            "accel_lat_g": round(self.rng.uniform(-0.2, 0.2), 3),
            "ambient_c": round(28 + self.rng.uniform(-5, 8), 1),
        }
        if self.vehicle.vehicle_type in (VehicleType.ICE, VehicleType.HYBRID):
            payload.update(
                rpm=round(rpm, 0),
                load_pct=round(load_pct, 1),
                throttle_pct=round(load_pct * self.rng.uniform(0.8, 1.1), 1),
                coolant_c=round(coolant_c, 1),
                oil_c=round(coolant_c - self.rng.uniform(0, 8), 1),
                oil_kpa=round(max(0.0, oil_kpa), 1),
                trans_c=round(coolant_c + self.rng.uniform(-5, 10), 1),
                gear=s.gear,
                fuel_pct=round(max(0.0, 70 - s.odo_km * 0.0005 % 70), 1),
                fuel_rate_lph=round(max(0.0, fuel_rate_lph), 2),
            )
        if self.vehicle.vehicle_type in (VehicleType.EV, VehicleType.HYBRID):
            soc = max(5.0, 90 - (s.odo_km * 0.15) % 85)
            charge_v = CHARGE_V_HEALTHY - self.rng.uniform(0, 0.3)
            if ftype == FailureType.BATTERY:
                charge_v -= sev * (CHARGE_V_HEALTHY - CHARGE_V_CRITICAL)
            payload.update(
                soc_pct=round(soc, 1),
                hv_v=round(350 + self.rng.uniform(-10, 10), 1),
                hv_a=round(s.speed_kmh * 1.5, 1),
            )
        return payload

    def health_payload(self, at: datetime) -> dict:
        s, sev, ftype = self.state, self._severity(at), self._failure_type()
        s.seconds_since_health = 0.0

        batt_12v = 12.6 - self.rng.uniform(0, 0.2)
        crank_min_v = 10.2 - self.rng.uniform(0, 0.3)
        charge_v = CHARGE_V_HEALTHY - self.rng.uniform(0, 0.2)
        if ftype == FailureType.BATTERY:
            drop = sev * (CHARGE_V_HEALTHY - CHARGE_V_CRITICAL)
            batt_12v -= drop * 0.4
            crank_min_v -= drop * 0.6
            charge_v -= drop

        pad_base = BRAKE_PAD_HEALTHY_PCT - (s.odo_km * 0.0002)
        if ftype == FailureType.BRAKE_WEAR:
            pad_base -= sev * (BRAKE_PAD_HEALTHY_PCT - BRAKE_PAD_CRITICAL_PCT)
        brake_pad_pct = [max(0.0, round(pad_base + self.rng.uniform(-3, 3), 1)) for _ in range(2)]

        if ftype in FAILURE_DTCS and sev > 0.3:
            for code in FAILURE_DTCS[ftype][: max(1, int(sev * len(FAILURE_DTCS[ftype])))]:
                s.active_dtc.add(code)

        payload = {
            "tire_kpa": [round(800 + self.rng.uniform(-30, 30), 1) for _ in range(4)],
            "tire_c": [round(30 + self.rng.uniform(-5, 10), 1) for _ in range(4)],
            "brake_pad_pct": brake_pad_pct,
            "batt_12v_rest_v": round(batt_12v, 2),
            "crank_min_v": round(max(0.0, crank_min_v), 2),
            "charge_v": round(charge_v, 2),
            "engine_hours": round(s.engine_hours, 2),
            "idle_s": self.rng.randint(0, HEALTH_INTERVAL_S),
            "mil_on": bool(s.active_dtc),
            "active_dtc": sorted(s.active_dtc),
        }
        if self.vehicle.vehicle_type in (VehicleType.EV, VehicleType.HYBRID):
            payload.update(
                cell_v_delta_mv=round(20 + sev * 80 if ftype == FailureType.BATTERY else self.rng.uniform(5, 15), 1),
                cell_temp_max_c=round(35 + self.rng.uniform(0, 10), 1),
                cell_temp_min_c=round(30 + self.rng.uniform(0, 5), 1),
                soh_pct=round(95 - self.rng.uniform(0, 10), 1),
            )
        return payload

    def pending_events(self, at: datetime) -> list[dict]:
        events: list[dict] = []
        s, sev, ftype = self.state, self._severity(at), self._failure_type()

        if s.speed_kmh > OVERSPEED_LIMIT_KMH and self.rng.random() < 0.05:
            events.append({"event_type": "OVERSPEED", "value": round(s.speed_kmh, 1)})

        if ftype == FailureType.MISFIRE and sev > 0.2 and self.rng.random() < sev * 0.1:
            code = self.rng.choice(FAILURE_DTCS[FailureType.MISFIRE])
            if code not in s.active_dtc:
                s.active_dtc.add(code)
                events.append(
                    {
                        "event_type": "DTC_SET",
                        "dtc": code,
                        "freeze_frame": {"rpm": 900.0, "load_pct": 30.0},
                    }
                )

        if self.rng.random() < 0.001:
            events.append({"event_type": self.rng.choice(["HARSH_BRAKE", "HARSH_ACCEL", "HARSH_CORNER"])})

        return events
