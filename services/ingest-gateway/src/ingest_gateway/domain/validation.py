"""Validates one raw MQTT publish before it's allowed onto the `telemetry` topic.

Three checks, cheapest first, matching PLAN §2's "checks the certificate
against the VIN, then validates schema, VIN check digit and DTC regex":

1. **topic <-> VIN/shard consistency** (the cert<->VIN check, in its trimmed
   POC form). Mosquitto's ACL already restricted the publishing connection's
   cert to its own `shard-{n}` topic segment (see
   `libs/fleetcore/algorithms/sharding.py` for why shards, not per-VIN
   certs). This re-derives the expected shard from the VIN in the topic and
   rejects any mismatch — a spoofed or corrupted topic segment.
2. **schema** — the JSON body decodes and matches the universal envelope
   (`fleetcore.domain.envelope`), which itself enforces the VIN check digit
   and any DTC codes.
3. Anything that fails either lands in `ValidationResult.error`, for the
   caller to route to the DLQ instead of Kafka's `telemetry` topic.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from pydantic import ValidationError

from fleetcore.algorithms.sharding import shard_for_vin
from fleetcore.domain.envelope import EventMessage, FastMessage, HealthMessage, parse_message

_TOPIC_RE = re.compile(r"^fleet/(?P<tenant>[^/]+)/shard-(?P<shard>\d+)/(?P<vin>[^/]+)/telemetry$")


class DlqReason:
    BAD_TOPIC = "bad_topic"
    SHARD_MISMATCH = "shard_mismatch"
    BAD_JSON = "bad_json"
    SCHEMA_INVALID = "schema_invalid"
    TOPIC_VIN_MISMATCH = "topic_vin_mismatch"


@dataclass
class ValidationResult:
    message: FastMessage | HealthMessage | EventMessage | None
    error: str | None
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.error is None


def _reject(reason: str, detail: str = "") -> ValidationResult:
    return ValidationResult(message=None, error=reason, detail=detail)


def validate(topic: str, raw_payload: bytes, n_shards: int) -> ValidationResult:
    topic_match = _TOPIC_RE.match(topic)
    if not topic_match:
        return _reject(DlqReason.BAD_TOPIC, f"topic {topic!r} doesn't match fleet/{{tenant}}/shard-N/{{vin}}/telemetry")

    tenant, claimed_shard, topic_vin = topic_match["tenant"], int(topic_match["shard"]), topic_match["vin"]
    expected_shard = shard_for_vin(topic_vin, n_shards)
    if claimed_shard != expected_shard:
        return _reject(
            DlqReason.SHARD_MISMATCH,
            f"VIN {topic_vin} hashes to shard {expected_shard}, but was published on shard-{claimed_shard}",
        )

    try:
        raw = json.loads(raw_payload)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return _reject(DlqReason.BAD_JSON, str(exc))

    if raw.get("vin") != topic_vin:
        return _reject(
            DlqReason.TOPIC_VIN_MISMATCH,
            f"topic VIN {topic_vin} != payload VIN {raw.get('vin')!r}",
        )

    try:
        message = parse_message(raw)
    except (ValidationError, KeyError) as exc:
        return _reject(DlqReason.SCHEMA_INVALID, str(exc))

    return ValidationResult(message=message, error=None)
