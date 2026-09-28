from __future__ import annotations

import os

import redis

_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis(
            host=os.environ.get("REDIS_HOST", "localhost"),
            port=int(os.environ.get("REDIS_PORT_EXTERNAL", os.environ.get("REDIS_PORT", "6379"))),
            decode_responses=True,
        )
    return _client
