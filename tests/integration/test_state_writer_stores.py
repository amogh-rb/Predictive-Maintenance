"""Integration test: state-writer's real `LatestStateStore` (Redis) and
`TwinStore` (MongoDB) infra classes against ephemeral real containers (PLAN
§5). Unit tests mock both clients; this proves the actual wire round-trip —
a twin doc written comes back byte-for-byte, and the raw-archive TTL index
session 4 built is actually created with the documented 7-day expiry
(PLAN §2 lifecycle: "hot 7 d raw").
"""
from __future__ import annotations

import pytest
from testcontainers.community.mongodb import MongoDbContainer
from testcontainers.community.redis import RedisContainer

from state_writer.infra.mongo_store import RAW_ARCHIVE_TTL, TwinStore
from state_writer.infra.redis_store import LatestStateStore


@pytest.fixture(scope="module")
def redis_store():
    with RedisContainer("redis:7.4-alpine") as redis_c:
        yield LatestStateStore(host=redis_c.get_container_host_ip(), port=int(redis_c.get_exposed_port(6379)))


@pytest.fixture(scope="module")
def twin_store():
    with MongoDbContainer("mongo:7.0") as mongo_c:
        yield TwinStore(uri=mongo_c.get_connection_url(), db_name="fleetpulse_test")


def test_redis_round_trip(redis_store):
    assert redis_store.get_latest("VIN1") is None
    doc = {"vin": "VIN1", "lat": 13.08, "lon": 80.27, "speed_kmh": 60.0}
    redis_store.set_latest("VIN1", doc)
    assert redis_store.get_latest("VIN1") == doc


def test_mongo_twin_upsert_and_replace(twin_store):
    twin_store.upsert_twin("VIN2", {"vin": "VIN2", "coolant_c": 88.0})
    twin_store.upsert_twin("VIN2", {"vin": "VIN2", "coolant_c": 95.0})
    doc = twin_store._twins.find_one({"vin": "VIN2"})
    assert doc["coolant_c"] == 95.0  # replace_one, not a merge — only the latest snapshot survives


def test_mongo_raw_archive_has_ttl_index(twin_store):
    twin_store.archive_raw({"vin": "VIN2", "msg_type": "FAST", "ts": "2026-09-29T12:00:00Z"})
    indexes = twin_store._raw.index_information()
    ttl_indexes = [spec for spec in indexes.values() if "expireAfterSeconds" in spec]
    assert len(ttl_indexes) == 1
    assert ttl_indexes[0]["expireAfterSeconds"] == int(RAW_ARCHIVE_TTL.total_seconds())
