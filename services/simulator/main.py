#!/usr/bin/env python
"""CLI entrypoint for the truck simulator. Run from the repo root:

    python services/simulator/main.py --rate 20000 [--duration 300] [--fleet-size 100000]

Reads Mosquitto connection details from `.env` (MQTT_HOST_EXTERNAL,
MQTT_PORT, MQTT_CA_CERT, MQTT_SHARD_COUNT); CLI flags override them.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "services" / "simulator" / "src"))
sys.path.insert(0, str(REPO_ROOT / "libs"))

from dotenv import load_dotenv  # noqa: E402

from simulator.app.simulate import run_simulation  # noqa: E402
from simulator.infra.mqtt_publisher import ShardedMqttPublisher  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="FleetPulse truck simulator")
    parser.add_argument("--rate", type=int, default=1000, help="target aggregate events/s")
    parser.add_argument("--duration", type=float, default=None, help="seconds to run (default: forever)")
    parser.add_argument("--fleet-size", type=int, default=100_000)
    parser.add_argument("--active-vehicles", type=int, default=None, help="default: min(rate, fleet-size)")
    parser.add_argument("--tenant", default=os.environ.get("TENANT_DEFAULT", "demo"))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--host", default=None, help="default: $MQTT_HOST_EXTERNAL")
    parser.add_argument("--port", type=int, default=None, help="default: $MQTT_PORT")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    load_dotenv(REPO_ROOT / ".env")
    args = parse_args(argv)

    host = args.host or os.environ.get("MQTT_HOST_EXTERNAL", "localhost")
    port = args.port or int(os.environ.get("MQTT_PORT", 8883))
    ca_cert = REPO_ROOT / os.environ.get("MQTT_CA_CERT", "infra/certs/ca/ca.crt")
    shard_dir = REPO_ROOT / "infra" / "certs" / "issued" / "shards"
    n_shards = int(os.environ.get("MQTT_SHARD_COUNT", 32))

    publisher = ShardedMqttPublisher(
        host=host, port=port, ca_cert=ca_cert, shard_cert_dir=shard_dir,
        tenant=args.tenant, n_shards=n_shards,
    )
    try:
        stats = run_simulation(
            publisher=publisher,
            rate_eps=args.rate,
            duration_s=args.duration,
            fleet_size=args.fleet_size,
            active_vehicles=args.active_vehicles,
            tenant=args.tenant,
            seed=args.seed,
        )
    finally:
        publisher.close()

    print(f"Sent {stats.total_sent} messages (FAST={stats.fast_sent} HEALTH={stats.health_sent} EVENT={stats.event_sent})")


if __name__ == "__main__":
    main()
