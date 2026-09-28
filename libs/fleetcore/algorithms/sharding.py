"""Deterministic VIN → shard assignment.

Mosquitto is sharded by VIN hash (PLAN §2), and each shard is issued one mTLS
client cert (see `infra/certs/issue-shard-certs.py`) rather than one cert per
vehicle — 100K live per-device certs isn't a one-session build, so the trimmed
POC binds identity at shard granularity: Mosquitto's ACL only lets a shard's
cert publish under that shard's topic segment, and the ingest-gateway
re-derives the expected shard from the VIN and rejects any message whose
topic shard disagrees (`services/ingest-gateway/domain/validation.py`).
Both sides must compute the same shard for the same VIN, so the function
lives here rather than being duplicated per service.
"""
from __future__ import annotations

import hashlib


def shard_for_vin(vin: str, n_shards: int) -> int:
    if n_shards <= 0:
        raise ValueError("n_shards must be positive")
    digest = hashlib.blake2b(vin.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") % n_shards


def shard_topic(tenant: str, vin: str, n_shards: int) -> str:
    shard = shard_for_vin(vin, n_shards)
    return f"fleet/{tenant}/shard-{shard}/{vin}/telemetry"
