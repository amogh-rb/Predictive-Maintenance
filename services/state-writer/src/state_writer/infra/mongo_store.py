"""Vehicle twin docs + raw message archive in MongoDB (PLAN §2: "vehicle twin
doc -> MongoDB; raw payload archive -> MongoDB (TTL)").
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from pymongo import MongoClient

RAW_ARCHIVE_TTL = timedelta(days=7)  # PLAN §2 lifecycle: "hot 7 d raw"


class TwinStore:
    def __init__(self, uri: str, db_name: str):
        self._client: MongoClient = MongoClient(uri)
        self._twins = self._client[db_name]["vehicle_twin"]
        self._raw = self._client[db_name]["raw_archive"]
        self._twins.create_index("vin", unique=True)
        self._raw.create_index("archived_at", expireAfterSeconds=int(RAW_ARCHIVE_TTL.total_seconds()))
        # GDPR erasure deletes by driver_token; without this every erase scans the whole archive.
        # Not partial on purpose: Mongo's planner won't use a `$type: string` partial index for an
        # equality match, so the delete silently falls back to a collection scan.
        self._raw.create_index("driver_token")

    def upsert_twin(self, vin: str, doc: dict[str, Any]) -> None:
        self._twins.replace_one({"vin": vin}, doc, upsert=True)

    def archive_raw(self, message: dict[str, Any]) -> None:
        # A separate `archived_at` (a real BSON date) drives the TTL index —
        # `ts` stays the wire-format ISO string as published, for replay.
        self._raw.insert_one({**message, "archived_at": datetime.utcnow()})
