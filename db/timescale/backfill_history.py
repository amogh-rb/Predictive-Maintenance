"""Backfill synthetic telemetry history into TimescaleDB (PLAN §6.3 session 5).

Reuses the simulator's domain code (same as `db/postgres/seed_fleet.py` reuses
`generate_fleet`) so the VINs line up with the vehicles already seeded into
Postgres, and generates FAST/HEALTH readings for each one across a past
window using the same `SignalEngine` / `plan_failures` logic the live
simulator uses — just walked backward in time and written straight to
Timescale instead of published over MQTT, since this is training data, not a
live-ingest exercise (there's no gateway/Flink/Kafka in this path on purpose).

`plan_failures(..., now=backfill_start, window_days=days)` places each
planted failure's `failure_at` inside [backfill_start, backfill_end], exactly
like it places future failures inside [now, now+window_days] for the live
simulator — no change needed to that function.

The ground truth (vin, failure_type, onset_at, failure_at) is written to
`batch/spark/data/labels.csv`, not to any online store — PLAN §2 ML section:
"ground truth kept out of feature tables to prevent leakage." The Spark
feature job (session 5) reads it once, offline, to compute labels; nothing
else does.

Run via `make backfill`, e.g. `make backfill VEHICLES=20000 DAYS=30` for the
real overnight run (PLAN §6.3 session 5: "Run the backfill overnight").
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "services" / "simulator" / "src"))

from simulator.domain.failure import FailurePlan, plan_failures  # noqa: E402
from simulator.domain.signals import SignalEngine  # noqa: E402
from simulator.domain.vehicle import VehicleType, generate_fleet  # noqa: E402

FLEET_SIZE = 100_000
FLEET_SEED = 42  # must match db/postgres/seed_fleet.py so VINs join to `vehicle`
FAILURE_SEED = 43
TENANT_NAME = "demo"

FAST_COLUMNS = [
    "ts", "vin", "tenant", "seq", "lat", "lon", "heading", "gps_hdop",
    "speed_kmh", "odo_km", "accel_long_g", "accel_lat_g", "ambient_c",
    "rpm", "load_pct", "throttle_pct", "coolant_c", "oil_c", "oil_kpa",
    "trans_c", "gear", "fuel_pct", "fuel_rate_lph", "soc_pct", "hv_v", "hv_a",
]
HEALTH_COLUMNS = [
    "ts", "vin", "tenant", "seq", "tire_kpa", "tire_c", "brake_pad_pct",
    "batt_12v_rest_v", "crank_min_v", "charge_v", "engine_hours", "idle_s",
    "mil_on", "active_dtc", "cell_v_delta_mv", "cell_temp_max_c",
    "cell_temp_min_c", "soh_pct",
]


def _fast_row(vehicle, engine: SignalEngine, at: datetime, seq: int) -> tuple:
    p = engine.fast_payload(at)
    return (
        at, vehicle.vin, vehicle.tenant, seq,
        p.get("lat"), p.get("lon"), p.get("heading"), p.get("gps_hdop"),
        p.get("speed_kmh"), p.get("odo_km"), p.get("accel_long_g"), p.get("accel_lat_g"),
        p.get("ambient_c"), p.get("rpm"), p.get("load_pct"), p.get("throttle_pct"),
        p.get("coolant_c"), p.get("oil_c"), p.get("oil_kpa"), p.get("trans_c"),
        p.get("gear"), p.get("fuel_pct"), p.get("fuel_rate_lph"),
        p.get("soc_pct"), p.get("hv_v"), p.get("hv_a"),
    )


def _health_row(vehicle, engine: SignalEngine, at: datetime, seq: int) -> tuple:
    p = engine.health_payload(at)
    return (
        at, vehicle.vin, vehicle.tenant, seq,
        p.get("tire_kpa"), p.get("tire_c"), p.get("brake_pad_pct"),
        p.get("batt_12v_rest_v"), p.get("crank_min_v"), p.get("charge_v"),
        p.get("engine_hours"), p.get("idle_s"), p.get("mil_on"), p.get("active_dtc"),
        p.get("cell_v_delta_mv"), p.get("cell_temp_max_c"), p.get("cell_temp_min_c"),
        p.get("soh_pct"),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vehicles", type=int, default=5000, help="fleet subset to backfill")
    parser.add_argument("--days", type=int, default=30, help="days of history ending now")
    parser.add_argument("--fast-interval-s", type=int, default=300, help="FAST sample spacing")
    parser.add_argument("--health-interval-s", type=int, default=900, help="HEALTH sample spacing")
    args = parser.parse_args()

    if args.health_interval_s % args.fast_interval_s != 0:
        raise SystemExit("--health-interval-s must be a whole multiple of --fast-interval-s")
    health_every_n_ticks = args.health_interval_s // args.fast_interval_s

    load_dotenv(REPO_ROOT / ".env")
    host = os.getenv("TIMESCALE_HOST_EXTERNAL", "localhost")
    port = os.getenv("TIMESCALE_PORT_EXTERNAL", "5433")
    db = os.getenv("TIMESCALE_DB", "telemetry")
    user = os.getenv("TIMESCALE_USER", "fleetpulse")
    password = os.getenv("TIMESCALE_PASSWORD", "changeme")

    fleet = generate_fleet(size=FLEET_SIZE, tenant=TENANT_NAME, seed=FLEET_SEED)
    subset = fleet[: args.vehicles]

    backfill_end = datetime.now(timezone.utc)
    backfill_start = backfill_end - timedelta(days=args.days)
    failure_plans = plan_failures(
        [v.vin for v in subset], backfill_start, window_days=args.days, seed=FAILURE_SEED
    )

    # Every backfilled vin goes in, not just the ones with a planted failure —
    # the Spark job needs the full universe of labeled history to produce
    # negative examples (an empty failure_type means "no failure in this
    # backfill window", the majority class).
    labels_path = REPO_ROOT / "batch" / "spark" / "data" / "labels.csv"
    labels_path.parent.mkdir(parents=True, exist_ok=True)
    with labels_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["vin", "tenant", "vehicle_type", "failure_type", "onset_at", "failure_at"])
        for vehicle in subset:
            plan = failure_plans.get(vehicle.vin)
            if plan is None:
                writer.writerow([vehicle.vin, TENANT_NAME, vehicle.vehicle_type.value, "", "", ""])
            else:
                writer.writerow([
                    plan.vin, TENANT_NAME, vehicle.vehicle_type.value, plan.failure_type.value,
                    plan.onset_at.isoformat(), plan.failure_at.isoformat(),
                ])

    n_ticks = int((backfill_end - backfill_start).total_seconds() // args.fast_interval_s)
    print(
        f"backfilling vehicles={len(subset)} days={args.days} ticks/vehicle={n_ticks} "
        f"fast_interval={args.fast_interval_s}s health_interval={args.health_interval_s}s "
        f"planted_failures={len(failure_plans)}"
    )

    conn_fast = psycopg.connect(host=host, port=port, dbname=db, user=user, password=password)
    conn_health = psycopg.connect(host=host, port=port, dbname=db, user=user, password=password)
    fast_rows = health_rows = 0
    t0 = time.monotonic()

    with conn_fast, conn_fast.cursor() as cur_fast, \
         conn_health, conn_health.cursor() as cur_health, \
         cur_fast.copy(f"COPY telemetry_fast ({', '.join(FAST_COLUMNS)}) FROM STDIN") as copy_fast, \
         cur_health.copy(f"COPY telemetry_health ({', '.join(HEALTH_COLUMNS)}) FROM STDIN") as copy_health:

        for i, vehicle in enumerate(subset):
            plan: FailurePlan | None = failure_plans.get(vehicle.vin)
            engine = SignalEngine(vehicle, plan)
            at = backfill_start
            seq = 0
            for tick in range(n_ticks):
                engine.step(float(args.fast_interval_s))
                seq += 1
                copy_fast.write_row(_fast_row(vehicle, engine, at, seq))
                fast_rows += 1
                if tick % health_every_n_ticks == 0:
                    seq += 1
                    copy_health.write_row(_health_row(vehicle, engine, at, seq))
                    health_rows += 1
                at += timedelta(seconds=args.fast_interval_s)

            if (i + 1) % 500 == 0:
                elapsed = time.monotonic() - t0
                print(f"  {i + 1}/{len(subset)} vehicles, {fast_rows} fast + {health_rows} health rows, {elapsed:.0f}s")

    conn_fast.close()
    conn_health.close()
    elapsed = time.monotonic() - t0
    print(f"done: {fast_rows} fast rows, {health_rows} health rows, {elapsed:.0f}s, labels -> {labels_path}")


if __name__ == "__main__":
    main()
