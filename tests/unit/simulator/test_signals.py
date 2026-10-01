from datetime import datetime, timedelta, timezone

from fleetcore.domain.envelope import parse_message
from simulator.app.simulate import build_envelope
from simulator.domain.failure import FailurePlan, FailureType
from simulator.domain.signals import (
    CELL_TEMP_CRITICAL_C,
    COOLANT_CRITICAL_C,
    TIRE_KPA_CRITICAL,
    TRANS_C_CRITICAL,
    SignalEngine,
)
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


def test_tyre_leak_drains_one_tyre_toward_critical_and_leaves_the_others_alone():
    v = _vehicle()
    now = datetime.now(timezone.utc)
    plan = FailurePlan(vin=v.vin, failure_type=FailureType.TYRE_LEAK, onset_at=now, failure_at=now)
    engine = SignalEngine(v, plan)
    payload = engine.health_payload(now)  # severity 1.0
    idx = engine.weak_tyre_idx
    assert payload["tire_kpa"][idx] <= TIRE_KPA_CRITICAL + 30  # +/-30 sensor noise on top of the leak
    others = [k for i, k in enumerate(payload["tire_kpa"]) if i != idx]
    assert all(k > TIRE_KPA_CRITICAL + 100 for k in others)


def test_transmission_failure_drives_trans_c_toward_critical_and_inflates_rpm():
    v = _vehicle()
    now = datetime.now(timezone.utc)
    plan = FailurePlan(vin=v.vin, failure_type=FailureType.TRANSMISSION, onset_at=now, failure_at=now)
    healthy_engine = SignalEngine(v)
    failing_engine = SignalEngine(v, plan)
    healthy_engine.step(1.0)
    failing_engine.step(1.0)
    healthy_engine.state.gear = failing_engine.state.gear = 3  # force driving so rpm > 0
    healthy_payload = healthy_engine.fast_payload(now)
    failing_payload = failing_engine.fast_payload(now)
    assert failing_payload["trans_c"] >= TRANS_C_CRITICAL - 3
    assert failing_payload["rpm"] > healthy_payload["rpm"]


def test_ev_hv_battery_failure_widens_cell_imbalance_and_overheats():
    v = _vehicle(VehicleType.EV)
    now = datetime.now(timezone.utc)
    plan = FailurePlan(vin=v.vin, failure_type=FailureType.EV_HV_BATTERY, onset_at=now, failure_at=now)
    engine = SignalEngine(v, plan)
    payload = engine.health_payload(now)
    assert payload["cell_temp_max_c"] >= CELL_TEMP_CRITICAL_C - 3
    assert payload["cell_v_delta_mv"] > 100
    assert payload["soh_pct"] < 80


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
