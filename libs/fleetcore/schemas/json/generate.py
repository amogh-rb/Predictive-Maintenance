"""Regenerates the JSON-Schema contract files for the telemetry message
(PLAN §6.2 "JSON-Schema contract test for the `telemetry` message" — the
Pact *message* contract was the piece actually dropped from scope, not
contract testing itself; a schema is the natural contract for a
publish-once/read-by-many Kafka topic with no single "provider" to verify
against).

Run after any change to `libs/fleetcore/domain/envelope.py`:
    python libs/fleetcore/schemas/json/generate.py
`tests/contract/test_telemetry_schema_contract.py` fails the build if the
committed files here drift from what envelope.py currently produces.
"""
from __future__ import annotations

import json
from pathlib import Path

from fleetcore.domain.envelope import EventMessage, FastMessage, HealthMessage

OUT_DIR = Path(__file__).parent

SCHEMAS = {
    "fast_message.schema.json": FastMessage,
    "health_message.schema.json": HealthMessage,
    "event_message.schema.json": EventMessage,
}


def main() -> None:
    for filename, model in SCHEMAS.items():
        schema = model.model_json_schema()
        (OUT_DIR / filename).write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
        print(f"wrote {filename}")


if __name__ == "__main__":
    main()
