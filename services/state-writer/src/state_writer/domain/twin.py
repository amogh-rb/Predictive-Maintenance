"""Pure merge logic for the vehicle digital twin (PLAN §2's MongoDB row).

No infra here (no Kafka/Redis/Mongo clients), so this is testable without a
running service — see tests/unit/state_writer/test_twin.py.
"""
from __future__ import annotations

from typing import Any


def _seq_key(msg_type: str) -> str:
    return f"_last_seq_{msg_type.lower()}"


def merge_twin(existing: dict[str, Any] | None, message: dict[str, Any]) -> dict[str, Any] | None:
    """Fold one telemetry message into the vehicle's twin document.

    Returns the updated doc, or `None` if `message` is a stale duplicate or
    out-of-order retry for its msg_type — the caller should skip the write
    entirely rather than persist stale data. One seq counter per msg_type
    (not a single "last seq seen"), since FAST/HEALTH/EVENT are independent
    streams at different cadences (PLAN §1); an out-of-order HEALTH message
    must not be judged against a FAST seq.

    Fields are flattened from `payload` with `None` values dropped, so the
    twin doc's shape naturally differs by drivetrain/tyre-count (PLAN §2)
    without any ICE/EV/6-tyre special-casing here — an EV message simply
    never contributes a `coolant_c` key, and a `None` in a later message
    (a field that msg_type doesn't carry) never clobbers a value an earlier
    message already set.
    """
    msg_type = message["msg_type"]
    seq = message["seq"]
    doc: dict[str, Any] = dict(existing) if existing else {"vin": message["vin"], "tenant": message["tenant"]}

    seq_key = _seq_key(msg_type)
    last_seq = doc.get(seq_key)
    if last_seq is not None and seq <= last_seq:
        return None

    doc[seq_key] = seq
    doc["updated_at"] = message["ts"]
    doc["last_msg_type"] = msg_type

    for field, value in (message.get("payload") or {}).items():
        if value is not None:
            doc[field] = value

    return doc
