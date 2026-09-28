"""Redis-backed token-bucket rate limiting (PLAN §2 "API": "Redis token-bucket
rate limit"). One bucket per (tenant, user), refilled continuously rather
than a fixed window, so a burst right at a window boundary can't double a
user's effective rate.
"""
from __future__ import annotations

import os
import time

import redis

# Lua keeps the read-refill-check-write cycle atomic across concurrent
# requests for the same key — a plain GET/SET round trip from Python would
# race under load and let more than `capacity` requests through.
_BUCKET_SCRIPT = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_per_sec = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local requested = tonumber(ARGV[4])

local bucket = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(bucket[1])
local ts = tonumber(bucket[2])
if tokens == nil then
    tokens = capacity
    ts = now
end

local elapsed = math.max(0, now - ts)
tokens = math.min(capacity, tokens + elapsed * refill_per_sec)

local allowed = 0
if tokens >= requested then
    tokens = tokens - requested
    allowed = 1
end

redis.call('HMSET', key, 'tokens', tokens, 'ts', now)
redis.call('EXPIRE', key, math.ceil(capacity / refill_per_sec) + 1)
return allowed
"""


class TokenBucketLimiter:
    def __init__(self, client: redis.Redis, capacity: int, refill_per_sec: float):
        self._client = client
        self._capacity = capacity
        self._refill_per_sec = refill_per_sec
        self._script = client.register_script(_BUCKET_SCRIPT)

    def allow(self, key: str, cost: int = 1) -> bool:
        allowed = self._script(
            keys=[f"ratelimit:{key}"],
            args=[self._capacity, self._refill_per_sec, time.time(), cost],
        )
        return bool(int(allowed))


def default_limiter(client: redis.Redis) -> TokenBucketLimiter:
    capacity = int(os.environ.get("RATE_LIMIT_CAPACITY", "60"))
    per_minute = float(os.environ.get("RATE_LIMIT_PER_MINUTE", "60"))
    return TokenBucketLimiter(client, capacity=capacity, refill_per_sec=per_minute / 60.0)
