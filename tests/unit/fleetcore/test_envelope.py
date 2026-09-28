import pytest
from pydantic import ValidationError

from fleetcore.algorithms import vin as vin_algo
from fleetcore.domain.envelope import EventType, parse_message

VALID_VIN = vin_algo.with_check_digit("1HGCM82633A00000A")


def _fast_msg(**overrides):
    msg = {
        "vin": VALID_VIN,
        "msg_type": "FAST",
        "seq": 1,
        "ts": "2026-09-28T10:00:00Z",
        "fw_version": "1.0.0",
        "payload": {
            "lat": 12.9, "lon": 77.6, "heading": 90, "gps_hdop": 0.9,
            "speed_kmh": 60, "odo_km": 12345.6, "accel_long_g": 0.1,
            "accel_lat_g": 0.0, "ambient_c": 32.5,
        },
    }
    msg.update(overrides)
    return msg


def test_parses_valid_fast_message():
    result = parse_message(_fast_msg())
    assert result.vin == VALID_VIN
    assert result.payload.speed_kmh == 60


def test_rejects_invalid_vin():
    with pytest.raises(ValidationError):
        parse_message(_fast_msg(vin="1M8GDM9A0KP042789"))  # wrong check digit


def test_rejects_naive_timestamp():
    with pytest.raises(ValidationError):
        parse_message(_fast_msg(ts="2026-09-28T10:00:00"))


def test_health_message_validates_active_dtc():
    msg = {
        "vin": VALID_VIN, "msg_type": "HEALTH", "seq": 2,
        "ts": "2026-09-28T10:00:00Z", "fw_version": "1.0.0",
        "payload": {
            "tire_kpa": [800, 800, 800, 800], "tire_c": [30, 30, 30, 30],
            "brake_pad_pct": [80, 80, 80, 80], "batt_12v_rest_v": 12.6,
            "crank_min_v": 9.8, "charge_v": 14.1, "engine_hours": 1200.0,
            "idle_s": 300, "mil_on": False, "active_dtc": ["P0128"],
        },
    }
    result = parse_message(msg)
    assert result.payload.active_dtc == ["P0128"]


def test_health_message_rejects_bad_dtc():
    msg = {
        "vin": VALID_VIN, "msg_type": "HEALTH", "seq": 2,
        "ts": "2026-09-28T10:00:00Z", "fw_version": "1.0.0",
        "payload": {
            "tire_kpa": [800], "tire_c": [30], "brake_pad_pct": [80],
            "batt_12v_rest_v": 12.6, "crank_min_v": 9.8, "charge_v": 14.1,
            "engine_hours": 1200.0, "idle_s": 300, "mil_on": False,
            "active_dtc": ["NOTADTC"],
        },
    }
    with pytest.raises(ValidationError):
        parse_message(msg)


def test_event_dtc_set_requires_dtc_code():
    msg = {
        "vin": VALID_VIN, "msg_type": "EVENT", "seq": 3,
        "ts": "2026-09-28T10:00:00Z", "fw_version": "1.0.0",
        "payload": {"event_type": EventType.DTC_SET.value},
    }
    with pytest.raises(ValidationError):
        parse_message(msg)


def test_event_ignition_on_needs_no_dtc():
    msg = {
        "vin": VALID_VIN, "msg_type": "EVENT", "seq": 3,
        "ts": "2026-09-28T10:00:00Z", "fw_version": "1.0.0",
        "payload": {"event_type": EventType.IGNITION_ON.value},
    }
    result = parse_message(msg)
    assert result.payload.event_type == EventType.IGNITION_ON


def test_unknown_msg_type_raises():
    with pytest.raises(KeyError):
        parse_message(_fast_msg(msg_type="BOGUS"))
