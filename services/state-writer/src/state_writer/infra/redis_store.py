"""Latest per-vehicle state in Redis (PLAN §2: "latest state -> Redis" for
sub-millisecond reads). Stores the same flattened twin snapshot Mongo
persists — Redis is a fast mirror of it, not a separate document shape.
"""
from __future__ import annotations

import json
from typing import Any

import redis


class LatestStateStore:
    def __init__(self, host: str, port: int):
        self._client = redis.Redis(host=host, port=port, decode_responses=True)

    def set_latest(self, vin: str, doc: dict[str, Any]) -> None:
        self._client.set(f"vehicle:latest:{vin}", json.dumps(doc, default=str))

    def get_latest(self, vin: str) -> dict[str, Any] | None:
        raw = self._client.get(f"vehicle:latest:{vin}")
        return json.loads(raw) if raw else None
