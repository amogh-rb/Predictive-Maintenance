"""Exercises the real Redis Lua token-bucket script (no fakeredis dependency
in this repo, and the bucket's atomicity guarantee is exactly what a plain
Python mock of redis-py would fail to catch). Skipped if Redis isn't
reachable — `make test` runs against the same `core` compose stack every
other integration-flavoured unit test in this repo assumes is up.
"""
from __future__ import annotations

import uuid

import pytest
import redis

from api.infra.rate_limit import TokenBucketLimiter

try:
    _client = redis.Redis(host="localhost", port=6379, socket_connect_timeout=1)
    _client.ping()
    REDIS_UP = True
except redis.exceptions.RedisError:
    REDIS_UP = False

pytestmark = pytest.mark.skipif(not REDIS_UP, reason="Redis not reachable at localhost:6379")


@pytest.fixture
def client():
    return redis.Redis(host="localhost", port=6379, decode_responses=True)


def test_allows_up_to_capacity_then_blocks(client):
    key = f"test-{uuid.uuid4()}"
    limiter = TokenBucketLimiter(client, capacity=3, refill_per_sec=0.001)
    results = [limiter.allow(key) for _ in range(5)]
    assert results == [True, True, True, False, False]
    client.delete(f"ratelimit:{key}")


def test_different_keys_have_independent_buckets(client):
    limiter = TokenBucketLimiter(client, capacity=1, refill_per_sec=0.001)
    key_a, key_b = f"test-{uuid.uuid4()}", f"test-{uuid.uuid4()}"
    assert limiter.allow(key_a) is True
    assert limiter.allow(key_a) is False
    assert limiter.allow(key_b) is True  # independent bucket, not exhausted
    client.delete(f"ratelimit:{key_a}", f"ratelimit:{key_b}")
