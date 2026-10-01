"""Read-only access to the vehicle twin state-writer maintains in Redis
(session 4: `vehicle:latest:{vin}`). The MCP server never writes here.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any

from redis import Redis


@lru_cache(maxsize=1)
def get_client() -> Redis:
    return Redis(
        host=os.environ.get("REDIS_HOST", "redis"),
        port=int(os.environ.get("REDIS_PORT", 6379)),
        decode_responses=True,
    )


def get_vehicle_twin(vin: str) -> dict[str, Any] | None:
    raw = get_client().get(f"vehicle:latest:{vin}")
    return json.loads(raw) if raw else None
