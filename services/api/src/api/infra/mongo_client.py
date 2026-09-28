"""Erasure's Mongo side (PLAN §2 "Privacy": "erasure endpoint ... delete that
driver's rows in ... Mongo"). Only `raw_archive` carries `driver_token`
(the envelope field, libs/fleetcore/domain/envelope.py) — `vehicle_twin` is
keyed by VIN, not driver, and Timescale's `telemetry_fast`/`telemetry_health`
never had a driver column at all (PLAN §1: "Not sent: ... driver PII"), so
there is nothing to erase in either. Documented, not a gap.
"""
from __future__ import annotations

import os

from pymongo import MongoClient

_client: MongoClient | None = None


def get_mongo() -> MongoClient:
    global _client
    if _client is None:
        user = os.environ.get("MONGO_ROOT_USER", "fleetpulse")
        password = os.environ.get("MONGO_ROOT_PASSWORD", "changeme")
        host = os.environ.get("MONGO_HOST", "localhost")
        port = os.environ.get("MONGO_PORT", "27017")
        _client = MongoClient(f"mongodb://{user}:{password}@{host}:{port}/")
    return _client


def erase_driver_archive(driver_token: str) -> int:
    db = get_mongo()[os.environ.get("MONGO_DB", "fleetpulse")]
    result = db["raw_archive"].delete_many({"driver_token": driver_token})
    return result.deleted_count
