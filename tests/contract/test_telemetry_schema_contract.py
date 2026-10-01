"""Contract test for the `telemetry` Kafka topic (PLAN §6.2: a JSON-Schema
contract test stands in for the dropped Pact *message* contract — a
publish-once/many-readers topic (ingest-gateway -> Flink + state-writer) has
no single provider to run a Pact verifier against, but a schema pins down
exactly the same thing: "the message shape every consumer can rely on").

Two checks:
1. The committed schema files under `libs/fleetcore/schemas/json/` are
   exactly what `envelope.py` currently produces — catches a producer-side
   change that silently drifts from what's documented for consumers,
   without anyone remembering to re-run `generate.py`.
2. A real message built through the same envelope models the simulator and
   ingest-gateway actually use validates against that schema — proves the
   schema isn't just internally consistent but actually accepts real traffic.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import jsonschema
import pytest

from fleetcore.domain.envelope import (
    EventMessage,
    EventPayload,
    EventType,
    FastMessage,
    FastPayload,
    HealthMessage,
    HealthPayload,
    MsgType,
)

SCHEMA_DIR = Path(__file__).parents[2] / "libs" / "fleetcore" / "schemas" / "json"

VALID_VIN = "1HGCM82633A004352"  # a real check-digit-valid VIN, per fleetcore.algorithms.vin

SAMPLE_MESSAGES = {
    "fast_message.schema.json": FastMessage(
        vin=VALID_VIN,
        msg_type=MsgType.FAST,
        seq=1,
        ts=datetime.now(timezone.utc),
        fw_version="1.0.0",
        payload=FastPayload(
            lat=13.08, lon=80.27, heading=90.0, gps_hdop=0.9, speed_kmh=62.0,
            odo_km=104233.5, accel_long_g=0.1, accel_lat_g=0.0, ambient_c=31.0,
            rpm=1800, load_pct=45.0, throttle_pct=30.0, coolant_c=88.0,
            oil_c=95.0, oil_kpa=310.0, trans_c=80.0, gear=4, fuel_pct=62.0,
            fuel_rate_lph=9.5,
        ),
    ),
    "health_message.schema.json": HealthMessage(
        vin=VALID_VIN,
        msg_type=MsgType.HEALTH,
        seq=2,
        ts=datetime.now(timezone.utc),
        fw_version="1.0.0",
        payload=HealthPayload(
            tire_kpa=[820, 815, 818, 822], tire_c=[35, 34, 36, 35],
            brake_pad_pct=[70, 68, 71, 69], batt_12v_rest_v=12.7,
            crank_min_v=10.8, charge_v=14.1, engine_hours=1204.5,
            idle_s=310, mil_on=False, active_dtc=["P0128"],
        ),
    ),
    "event_message.schema.json": EventMessage(
        vin=VALID_VIN,
        msg_type=MsgType.EVENT,
        seq=3,
        ts=datetime.now(timezone.utc),
        fw_version="1.0.0",
        payload=EventPayload(event_type=EventType.DTC_SET, dtc="P0128"),
    ),
}


@pytest.mark.parametrize("filename", sorted(SAMPLE_MESSAGES))
def test_committed_schema_matches_envelope(filename: str) -> None:
    model = type(SAMPLE_MESSAGES[filename])
    committed = json.loads((SCHEMA_DIR / filename).read_text())
    current = model.model_json_schema()
    assert committed == current, (
        f"{filename} is stale — run `python libs/fleetcore/schemas/json/generate.py` "
        "after changing envelope.py"
    )


@pytest.mark.parametrize("filename", sorted(SAMPLE_MESSAGES))
def test_real_message_validates_against_schema(filename: str) -> None:
    schema = json.loads((SCHEMA_DIR / filename).read_text())
    message = SAMPLE_MESSAGES[filename]
    wire_json = json.loads(message.model_dump_json())
    jsonschema.validate(wire_json, schema)
