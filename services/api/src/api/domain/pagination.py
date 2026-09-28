"""Keyset ("seek") pagination cursors (PLAN §2 SQL-optimisation item 1: the
at-risk list moved off OFFSET). A cursor is just the last row's sort key
`(risk_score, vehicle_id)`, opaque-encoded so the API can change the
underlying columns later without breaking clients holding an old cursor.
"""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass


@dataclass(frozen=True)
class RiskCursor:
    risk_score: float
    vehicle_id: str


def encode_cursor(risk_score: float, vehicle_id: str) -> str:
    raw = json.dumps({"r": risk_score, "v": vehicle_id}, separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str) -> RiskCursor:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        data = json.loads(raw)
        return RiskCursor(risk_score=float(data["r"]), vehicle_id=str(data["v"]))
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError(f"malformed cursor: {cursor!r}") from exc
