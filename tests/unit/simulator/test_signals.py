from datetime import datetime, timedelta, timezone

from fleetcore.domain.envelope import parse_message
from simulator.app.simulate import build_envelope
from simulator.domain.failure import FailurePlan, FailureType
from simulator.domain.signals import COOLANT_CRITICAL_C, SignalEngine
from simulator.domain.vehicle import Vehicle, VehicleType


def _vehicle(vtype=VehicleType.ICE) -> Vehicle:
    return Vehicle(
        vin="1M8GDM9AXKP042788", tenant="demo", vehicle_type=vtype,
        depot="mumbai", fw_version="1.0.0", driver_token="drv-1",
    )


def test_fast_payload_validates_against_the_universal_schema():
    v = _vehicle()
    engine = SignalEngine(v)
    at = datetime.now(timezone.utc)
    engine.step(1.0)
    msg = build_envelope(v, "FAST", 1, at, engine.fast_payload(at))
    parsed = parse_message(msg)
    assert parsed.payload.speed_kmh >= 0


def test_health_payload_validates_against_the_universal_schema():
    v = _vehicle()
    engine = SignalEngine(v)
    at = datetime.now(timezone.utc)
    msg = build_envelope(v, "HEALTH", 1, at, engine.health_payload(at))
    parsed = parse_message(msg)
    assert isinstance(parsed.payload.active_dtc, list)


def test_cooling_failure_drives_coolant_toward_critical_at_full_severity():
    v = _vehicle()
    now = datetime.now(timezone.utc)
    plan = FailurePlan(vin=v.vin, failure_type=FailureType.COOLING, onset_at=now, failure_at=now)
    engine = SignalEngine(v, plan)
    engine.step(1.0)
    payload = engine.fast_payload(now)  # severity is 1.0 since at >= failure_at
    assert payload["coolant_c"] >= COOLANT_CRITICAL_C - 3


def test_healthy_vehicle_stays_well_below_critical_coolant():
    v = _vehicle()
    engine = SignalEngine(v)
    at = datetime.now(timezone.utc)
    for _ in range(20):
        engine.step(1.0)
    payload = engine.fast_payload(at)
    assert payload["coolant_c"] < COOLANT_CRITICAL_C - 10


def test_ev_payload_has_no_ice_fields_but_has_hv_fields():
    v = _vehicle(VehicleType.EV)
    engine = SignalEngine(v)
    at = datetime.now(timezone.utc)
    engine.step(1.0)
    payload = engine.fast_payload(at)
    assert "soc_pct" in payload and "hv_v" in payload
    assert "rpm" not in payload


def test_misfire_failure_eventually_emits_dtc_set_event():
    v = _vehicle()
    now = datetime.now(timezone.utc)
    plan = FailurePlan(
        vin=v.vin, failure_type=FailureType.MISFIRE,
        onset_at=now, failure_at=now + timedelta(seconds=1),
    )
    engine = SignalEngine(v, plan)
    at = now + timedelta(seconds=2)  # severity 1.0
    engine.step(1.0)
    seen_dtc_set = any(
        e["event_type"] == "DTC_SET" for _ in range(500) for e in engine.pending_events(at)
    )
    assert seen_dtc_set
