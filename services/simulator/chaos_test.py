#!/usr/bin/env python
"""Chaos test (PLAN §5/§6.3 "kill a Flink TaskManager mid-load, verify
zero-loss recovery via seq", `make chaos`).

Kills the real `flink-taskmanager` container partway through a load run,
brings it back, and waits for the real Flink job (checkpointing every 30s to
MinIO, per `stream/flink/run-jobs.sh` — session 4) to return to RUNNING on
its own. "Zero loss" is checked the way PLAN names it: by `seq`, not just a
row count — every (vin, seq) FAST message this process actually published is
looked up individually in TimescaleDB's `telemetry_fast` afterward, so a
silent gap would show up even if the total count happened to match.

Doesn't touch Kafka itself (a single-broker `core` Kafka can't survive a
broker kill by definition — that needs the separate 3-broker `chaos` compose
profile, which has no gateway/Flink wired to it to test end-to-end against;
recorded as a known gap, not silently skipped).
"""
from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "services" / "simulator" / "src"))
sys.path.insert(0, str(REPO_ROOT / "libs"))

import httpx  # noqa: E402
import psycopg  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

from simulator.app.simulate import SimulationStats, run_simulation  # noqa: E402
from simulator.infra.mqtt_publisher import ShardedMqttPublisher  # noqa: E402

TASKMANAGER_CONTAINER = "fleetpulse-flink-taskmanager-1"
FLINK_JOBS_URL = "http://localhost:8081/jobs"


class RecordingPublisher:
    """Wraps the real publisher: delegates every publish unchanged, but also
    records each FAST message's (vin, seq) so they can be looked up in
    Timescale afterward — the actual "did every message survive the outage"
    proof, not just a before/after row count."""

    def __init__(self, inner: ShardedMqttPublisher):
        self._inner = inner
        self.sent: list[tuple[str, int]] = []
        self._lock = threading.Lock()

    def publish(self, vin: str, message: dict) -> None:
        if message.get("msg_type") == "FAST":
            with self._lock:
                self.sent.append((vin, message["seq"]))
        self._inner.publish(vin, message)

    def close(self) -> None:
        self._inner.close()


def _docker(*args: str) -> str:
    result = subprocess.run(["docker", *args], capture_output=True, text=True, check=True)
    return result.stdout.strip()


def _flink_job_status() -> str | None:
    try:
        resp = httpx.get(FLINK_JOBS_URL, timeout=5.0)
        jobs = resp.json().get("jobs", [])
        return jobs[0]["status"] if jobs else None
    except Exception:
        return None


def _wait_for_job_status(target: str, timeout_s: float) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        status = _flink_job_status()
        print(f"  Flink job status: {status}")
        if status == target:
            return True
        time.sleep(5.0)
    return False


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    load_dotenv(REPO_ROOT / ".env")

    parser = argparse.ArgumentParser(description="Kill flink-taskmanager mid-load; verify zero-loss recovery by seq")
    parser.add_argument("--rate", type=int, default=300, help="sustainable rate — see burst_test.py's own ceiling note")
    parser.add_argument("--total-seconds", type=float, default=90.0)
    parser.add_argument("--kill-at-seconds", type=float, default=25.0)
    parser.add_argument("--outage-seconds", type=float, default=15.0)
    parser.add_argument("--settle-seconds", type=float, default=30.0, help="wait after the run ends for Flink to drain any backlog")
    parser.add_argument("--fleet-size", type=int, default=100_000)
    args = parser.parse_args(argv)

    host = os.environ.get("MQTT_HOST_EXTERNAL", "localhost")
    port = int(os.environ.get("MQTT_PORT", 8883))
    ca_cert = REPO_ROOT / os.environ.get("MQTT_CA_CERT", "infra/certs/ca/ca.crt")
    shard_dir = REPO_ROOT / "infra" / "certs" / "issued" / "shards"
    n_shards = int(os.environ.get("MQTT_SHARD_COUNT", 32))

    print("pre-flight: Flink job must already be RUNNING (run `make flink-submit` first if not)")
    if _flink_job_status() != "RUNNING":
        print("ERROR: no RUNNING Flink job found at :8081/jobs — aborting")
        sys.exit(1)

    inner = ShardedMqttPublisher(host=host, port=port, ca_cert=ca_cert, shard_cert_dir=shard_dir, tenant="demo", n_shards=n_shards)
    publisher = RecordingPublisher(inner)
    stats = SimulationStats()

    def _kill_and_recover_tm():
        time.sleep(args.kill_at_seconds)
        print(f"\n--- killing {TASKMANAGER_CONTAINER} (simulating a TaskManager crash mid-load) ---")
        _docker("kill", TASKMANAGER_CONTAINER)
        time.sleep(args.outage_seconds)
        print(f"--- restarting {TASKMANAGER_CONTAINER} ---")
        _docker("start", TASKMANAGER_CONTAINER)
        recovered = _wait_for_job_status("RUNNING", timeout_s=120.0)
        print(f"--- Flink job {'recovered to RUNNING' if recovered else 'DID NOT recover'} ---\n")

    chaos_thread = threading.Thread(target=_kill_and_recover_tm, daemon=True)
    chaos_thread.start()

    print(f"--- load: {args.rate} events/s for {args.total_seconds:.0f}s (TM killed at t+{args.kill_at_seconds:.0f}s) ---")
    test_started_at = datetime.now(timezone.utc)
    try:
        run_simulation(publisher=publisher, rate_eps=args.rate, duration_s=args.total_seconds,
                        fleet_size=args.fleet_size, seed=42, stats=stats)
    finally:
        chaos_thread.join(timeout=args.outage_seconds + 130.0)
        publisher.close()

    print(f"--- settling {args.settle_seconds:.0f}s for Flink to drain any backlog from the outage ---")
    time.sleep(args.settle_seconds)

    sent = publisher.sent
    sent_set = set(sent)
    print(f"\nsent {len(sent)} FAST (vin, seq) pairs during the test")

    conn = psycopg.connect(host="localhost", port=5433, dbname="telemetry", user="fleetpulse", password="changeme")
    vins = list({vin for vin, _ in sent})
    landed: set[tuple[str, int]] = set()
    with conn.cursor() as cur:
        for i in range(0, len(vins), 200):
            batch = vins[i : i + 200]
            # Filtered by vin + a time floor only, not by seq — seq is a
            # per-run counter shared across every vehicle (simulate.py's
            # `seq_base`), so two different VINs in the same run can and do
            # share a seq value; matching (vin, seq) as an exact pair has to
            # happen in Python against the real sent set, not as a second
            # independent SQL predicate (which would silently cross-match).
            cur.execute(
                "SELECT vin, seq FROM telemetry_fast WHERE vin = ANY(%s) AND ts >= %s",
                (batch, test_started_at),
            )
            landed.update((row[0].rstrip(), row[1]) for row in cur.fetchall() if (row[0].rstrip(), row[1]) in sent_set)
    conn.close()

    missing = [(vin, seq) for vin, seq in sent if (vin, seq) not in landed]
    print(f"landed in telemetry_fast: {len(sent) - len(missing)} / {len(sent)}")
    if missing:
        print(f"MISSING: {len(missing)} (vin, seq) pairs never arrived, e.g. {missing[:10]}")
        sys.exit(1)
    else:
        print("ZERO LOSS confirmed: every (vin, seq) sent during the TaskManager kill/restart landed in Timescale.")


if __name__ == "__main__":
    main()
