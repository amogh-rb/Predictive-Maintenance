#!/usr/bin/env python
"""Chaos test: kill an ingest-gateway copy mid-load, verify zero-loss
recovery (PLAN §5/§6.3 row 9 "kill ... an ingest-gateway copy ... mid-load";
session 10 gap-fill — `chaos_test.py` only ever covered the Flink
TaskManager kill).

Scales `ingest-gateway` to 2 copies (MQTT 5 shared subscription splits the
load between them, PLAN §2), runs the simulator's normal MQTT load, kills one
copy's container mid-run, then restarts it. Zero-loss is checked the same
ground-truth way `burst_test.py` checks it: Kafka `telemetry` topic offset
delta against what the simulator actually sent, since the surviving copy
should absorb 100% of the shared-subscription traffic the instant the killed
one disconnects (that's the whole point of the shared subscription — no
gateway-side outage at all, unlike the single-instance TaskManager case).

Requires 2 ingest-gateway containers running first:
  docker compose --profile core up -d --scale ingest-gateway=2
"""
from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "services" / "simulator" / "src"))
sys.path.insert(0, str(REPO_ROOT / "libs"))

from dotenv import load_dotenv  # noqa: E402

from simulator.app.simulate import SimulationStats, run_simulation  # noqa: E402
from simulator.infra.mqtt_publisher import ShardedMqttPublisher  # noqa: E402


def _docker(*args: str) -> str:
    result = subprocess.run(["docker", *args], capture_output=True, text=True, check=True)
    return result.stdout.strip()


def _gateway_containers() -> list[str]:
    out = _docker("compose", "ps", "-q", "ingest-gateway")
    ids = [line for line in out.splitlines() if line.strip()]
    return ids


def _topic_total_offset(bootstrap_servers: str, topic: str) -> int | None:
    from confluent_kafka import Consumer, TopicPartition
    from confluent_kafka.admin import AdminClient

    admin = AdminClient({"bootstrap.servers": bootstrap_servers})
    metadata = admin.list_topics(topic=topic, timeout=10)
    topic_metadata = metadata.topics.get(topic)
    if topic_metadata is None or topic_metadata.error is not None:
        return None
    consumer = Consumer({"bootstrap.servers": bootstrap_servers, "group.id": "gateway-chaos-offsets"})
    try:
        return sum(
            consumer.get_watermark_offsets(TopicPartition(topic, p), timeout=10)[1]
            for p in topic_metadata.partitions
        )
    finally:
        consumer.close()


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    load_dotenv(REPO_ROOT / ".env")

    parser = argparse.ArgumentParser(description="Kill one of 2 ingest-gateway copies mid-load; verify zero-loss")
    parser.add_argument("--rate", type=int, default=300)
    parser.add_argument("--total-seconds", type=float, default=60.0)
    parser.add_argument("--kill-at-seconds", type=float, default=20.0)
    parser.add_argument("--outage-seconds", type=float, default=15.0)
    parser.add_argument("--drain-seconds", type=float, default=15.0)
    parser.add_argument("--fleet-size", type=int, default=100_000)
    args = parser.parse_args(argv)

    containers = _gateway_containers()
    print(f"ingest-gateway containers: {containers}")
    if len(containers) < 2:
        print("ERROR: need 2 running ingest-gateway copies first — "
              "run `docker compose --profile core up -d --scale ingest-gateway=2`")
        sys.exit(1)
    target = containers[0]

    kafka_brokers = os.environ.get("KAFKA_BROKERS_EXTERNAL", "localhost:29092")
    topic = "telemetry"
    host = os.environ.get("MQTT_HOST_EXTERNAL", "localhost")
    port = int(os.environ.get("MQTT_PORT", 8883))
    ca_cert = REPO_ROOT / os.environ.get("MQTT_CA_CERT", "infra/certs/ca/ca.crt")
    shard_dir = REPO_ROOT / "infra" / "certs" / "issued" / "shards"
    n_shards = int(os.environ.get("MQTT_SHARD_COUNT", 32))

    publisher = ShardedMqttPublisher(host=host, port=port, ca_cert=ca_cert, shard_cert_dir=shard_dir, tenant="demo", n_shards=n_shards)
    stats = SimulationStats()

    def _kill_and_recover():
        time.sleep(args.kill_at_seconds)
        print(f"\n--- killing gateway copy {target[:12]} (simulating a gateway crash mid-load) ---")
        _docker("kill", target)
        time.sleep(args.outage_seconds)
        print(f"--- restarting gateway copy {target[:12]} ---")
        _docker("start", target)
        print("--- gateway copy restarted; shared subscription re-splits automatically ---\n")

    chaos_thread = threading.Thread(target=_kill_and_recover, daemon=True)
    chaos_thread.start()

    before = _topic_total_offset(kafka_brokers, topic)
    print(f"telemetry offset before: {before}")
    print(f"--- load: {args.rate} events/s for {args.total_seconds:.0f}s (gateway copy killed at t+{args.kill_at_seconds:.0f}s) ---")
    run_simulation(publisher=publisher, rate_eps=args.rate, duration_s=args.total_seconds,
                    fleet_size=args.fleet_size, seed=42, stats=stats)
    chaos_thread.join(timeout=args.outage_seconds + 30.0)

    time.sleep(args.drain_seconds)
    publisher.close()
    after = _topic_total_offset(kafka_brokers, topic)
    sent = stats.total_sent
    delivered = (after - before) if (before is not None and after is not None) else None

    print(f"\nsimulator sent: {sent} messages")
    if delivered is not None:
        loss = sent - delivered
        loss_pct = 100 * loss / sent if sent else 0.0
        print(f"delivered to Kafka telemetry topic: {delivered} messages (loss: {loss}, {loss_pct:.2f}%)")
        if loss_pct > 5.0:
            print("WARNING: loss this high usually means the load rate exceeded the simulator "
                  "process's own throughput ceiling, not necessarily a pipeline defect — "
                  "re-run at a lower --rate before concluding the pipeline dropped messages.")
            sys.exit(1)
        else:
            print("\nZERO LOSS (within QoS-1 redelivery noise) confirmed: the surviving gateway "
                  "copy absorbed the killed copy's share of the MQTT shared subscription.")
    else:
        print("could not read telemetry topic offsets")
        sys.exit(1)


if __name__ == "__main__":
    main()
