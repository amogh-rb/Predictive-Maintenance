#!/usr/bin/env bash
# One-time (idempotent) setup for the Garage S3-compatible lake bucket,
# closing the TODO left in sessions 1-2: Garage provisions buckets/keys via
# its own CLI, not env vars like the old MinIO image. Imports a fixed
# dev-only keypair (matching .env.example's GARAGE_ACCESS_KEY/SECRET_KEY, and
# the Flink S3 plugin config in docker-compose.yml) rather than `garage key
# new`'s randomly generated one, so no manual copy-paste step is needed
# before Flink's telemetry_lake_sink (stream/flink/sql/02_sinks_ddl.sql) can
# write to it. Run via `make lake-init` after `make up`.
set -euo pipefail

BUCKET="${MINIO_BUCKET:-fleetpulse-lake}"
ACCESS_KEY="${GARAGE_ACCESS_KEY:-GKdeadbeefdeadbeefdeadbeef}"
SECRET_KEY="${GARAGE_SECRET_KEY:-deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef}"

garage() { docker compose exec -T minio /garage "$@"; }

# Garage refuses all bucket/key operations until its single-node cluster
# layout is assigned and applied (this has nothing to do with the MinIO
# image it replaced — Garage's own bootstrap step, never done since the
# session 1 swap). Idempotent: re-applying an already-committed layout is a
# harmless no-op error, swallowed below.
NODE_ID=$(garage node id -q | cut -d'@' -f1)
garage layout assign -z dc1 -c 10GB "$NODE_ID" 2>/dev/null || true
garage layout apply --version 1 2>/dev/null || echo "cluster layout already applied"

garage bucket create "$BUCKET" 2>/dev/null || echo "bucket $BUCKET already exists"
garage key import "$ACCESS_KEY" "$SECRET_KEY" -n flink-dev --yes 2>/dev/null || echo "key flink-dev already imported"
garage bucket allow --key flink-dev --read --write "$BUCKET"

echo "lake ready: bucket=$BUCKET key=$ACCESS_KEY"
