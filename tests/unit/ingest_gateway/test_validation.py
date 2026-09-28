import json
from datetime import datetime, timezone

from fleetcore.algorithms import vin as vin_algo
from fleetcore.algorithms.sharding import shard_for_vin
from ingest_gateway.domain.validation import DlqReason, validate

N_SHARDS = 32
VALID_VIN = vin_algo.with_check_digit("1HGCM82633A00000A")


def _raw_fast(vin=VALID_VIN):
    return {
        "vin": vin, "msg_type": "FAST", "seq": 1, "ts": datetime.now(timezone.utc).isoformat(),
        "fw_version": "1.0.0",
        "payload": {
            "lat": 1.0, "lon": 2.0, "heading": 10, "gps_hdop": 1.0, "speed_kmh": 50,
            "odo_km": 100, "accel_long_g": 0, "accel_lat_g": 0, "ambient_c": 30,
        },
    }


def _topic_for(vin=VALID_VIN, tenant="demo", shard=None):
    shard = shard_for_vin(vin, N_SHARDS) if shard is None else shard
    return f"fleet/{tenant}/shard-{shard}/{vin}/telemetry"


def test_valid_message_passes():
    raw = _raw_fast()
    result = validate(_topic_for(), json.dumps(raw).encode(), N_SHARDS)
    assert result.ok
    assert result.message.vin == VALID_VIN


def test_rejects_malformed_topic():
    result = validate("not/a/valid/topic", b"{}", N_SHARDS)
    assert not result.ok
    assert result.error == DlqReason.BAD_TOPIC


def test_rejects_shard_mismatch():
    correct_shard = shard_for_vin(VALID_VIN, N_SHARDS)
    wrong_shard = (correct_shard + 1) % N_SHARDS
    topic = _topic_for(shard=wrong_shard)
    result = validate(topic, json.dumps(_raw_fast()).encode(), N_SHARDS)
    assert not result.ok
    assert result.error == DlqReason.SHARD_MISMATCH


def test_rejects_bad_json():
    result = validate(_topic_for(), b"{not json", N_SHARDS)
    assert not result.ok
    assert result.error == DlqReason.BAD_JSON


def test_rejects_topic_vin_payload_vin_mismatch():
    other_vin = vin_algo.with_check_digit("2HGCM82633A00000A")
    raw = _raw_fast(vin=other_vin)
    result = validate(_topic_for(vin=VALID_VIN), json.dumps(raw).encode(), N_SHARDS)
    assert not result.ok
    assert result.error == DlqReason.TOPIC_VIN_MISMATCH


def test_rejects_schema_invalid_payload():
    raw = _raw_fast()
    raw["payload"]["speed_kmh"] = -5  # violates ge=0
    result = validate(_topic_for(), json.dumps(raw).encode(), N_SHARDS)
    assert not result.ok
    assert result.error == DlqReason.SCHEMA_INVALID


def test_rejects_unparseable_vin_in_payload():
    raw = _raw_fast()
    raw["vin"] = "not-a-vin"
    # topic still carries the original (well-formed) VIN so shard check passes,
    # but the payload VIN differs -> topic/payload mismatch is caught first.
    result = validate(_topic_for(vin=VALID_VIN), json.dumps(raw).encode(), N_SHARDS)
    assert not result.ok
    assert result.error == DlqReason.TOPIC_VIN_MISMATCH
