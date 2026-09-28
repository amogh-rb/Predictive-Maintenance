#!/usr/bin/env bash
# Apply Postgres + Timescale SQL migrations against the running `core` stack.
#
# Migrations mount as docker-entrypoint-initdb.d, but that only runs once
# against an empty data volume — these containers were first started back in
# session 1 before any migration files existed, so re-running `docker compose
# up` never replays them. Instead we pipe each file into psql inside the
# already-running container. Files are numbered and written with IF NOT
# EXISTS / DROP-then-CREATE so re-running this is safe.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== Postgres =="
for f in db/postgres/migrations/*.sql; do
    echo "-> $f"
    docker compose exec -T postgres sh -c '
        psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -q
    ' < "$f"
done

echo "== TimescaleDB =="
for f in db/timescale/migrations/*.sql; do
    echo "-> $f"
    docker compose exec -T timescaledb sh -c '
        psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -q
    ' < "$f"
done

echo "Migrations applied."
