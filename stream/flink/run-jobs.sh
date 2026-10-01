#!/usr/bin/env bash
# Concatenates stream/flink/sql/00-05 (in order) and submits the result as
# one Flink SQL Client session, which turns the STATEMENT SET in 05_pipeline
# into a single running job (PLAN §6.3 session 4). Run after `make up` once
# the core profile (Kafka, TimescaleDB, Flink) is healthy:
#   bash stream/flink/run-jobs.sh
set -euo pipefail

# Git Bash (Windows) rewrites any argv-looking-like-a-Unix-path before handing
# it to docker.exe, including paths meant for *inside* the container (the
# same class of bug session 1/2 hit with openssl -subj and CLI exec paths).
# Harmless no-op on Linux/macOS.
export MSYS_NO_PATHCONV=1

cd "$(dirname "$0")/../.."  # repo root

SQL_DIR=stream/flink/sql

# Piped over stdin via `docker compose exec`, not `docker compose cp` — `cp`'s
# source/dest paths go through Git Bash's MSYS path conversion on Windows
# (the same class of bug session 1/2 hit with openssl -subj and CLI exec
# paths) and get mangled; stdin has no path to mangle.
{
    echo "SET 'table.exec.state.ttl' = '1 h';"
    # Without this, an idle Kafka partition pins the job-wide event-time
    # watermark (it's the min across partitions), so HOP windows and
    # MATCH_RECOGNIZE never fire unless all 6 `telemetry` partitions are
    # receiving traffic — a single-VIN `make inject-fault` never alerted.
    echo "SET 'table.exec.source.idle-timeout' = '10 s';"
    # Checkpointing is load-bearing, not optional: the lake's filesystem sink
    # only finalizes part files on a checkpoint (without it, files stay as
    # forever-unfinished S3 multipart uploads), and enabling it also switches
    # Flink from no-restart to its default restart-on-failure strategy.
    echo "SET 'execution.checkpointing.interval' = '30 s';"
    echo "SET 'state.checkpoints.dir' = 's3://fleetpulse-lake/checkpoints';"
    echo "SET 'pipeline.name' = 'fleetpulse-telemetry-pipeline';"
    for f in 00_source.sql 01_dedup.sql 02_sinks_ddl.sql 03_realtime_rules.sql 04_cep_misfire.sql 05_pipeline.sql; do
        cat "$SQL_DIR/$f"  # each file's statements are already `;`-terminated
        echo
    done
} | docker compose exec -T flink-jobmanager sh -c 'cat > /tmp/fleetpulse-pipeline.sql'

docker compose exec -T flink-jobmanager ./bin/sql-client.sh -f /tmp/fleetpulse-pipeline.sql
