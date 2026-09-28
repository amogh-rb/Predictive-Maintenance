#!/usr/bin/env python
"""Dedicated ingest throughput benchmark (`make bench-ingest`, PLAN §6.3
session 2's "Done when: throughput number known").

Runs the simulator at --rate for --duration seconds, then reports the
events/s actually delivered to Kafka's `telemetry` topic (measured via the
topic's own watermark offsets — the ground truth of what made it through
Mosquitto -> ingest-gateway -> Kafka — not just what the simulator attempted
to publish, which is what `main.py`'s own summary line reports).
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "services" / "simulator" / "src"))
sys.path.insert(0, str(REPO_ROOT / "libs"))

from dotenv import load_dotenv  # noqa: E402

from simulator.app.simulate import run_simulation  # noqa: E402
from simulator.infra.mqtt_publisher import ShardedMqttPublisher  # noqa: E402


def _kafka_topic_total_offset(bootstrap_servers: str, topic: str) -> int | None:
    from confluent_kafka import Consumer, TopicPartition
    from confluent_kafka.admin import AdminClient

    admin = AdminClient({"bootstrap.servers": bootstrap_servers})
    metadata = admin.list_topics(topic=topic, timeout=10)
    topic_metadata = metadata.topics.get(topic)
    if topic_metadata is None or topic_metadata.error is not None:
        return None  # topic doesn't exist yet (nothing produced so far)

    consumer = Consumer({"bootstrap.servers": bootstrap_servers, "group.id": "bench-ingest-offsets"})
    try:
        total = 0
        for partition_id in topic_metadata.partitions:
            _low, high = consumer.get_watermark_offsets(TopicPartition(topic, partition_id), timeout=10)
            total += high
        return total
    finally:
        consumer.close()


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    load_dotenv(REPO_ROOT / ".env")

    parser = argparse.ArgumentParser(description="Ingest throughput benchmark")
    parser.add_argument("--rate", type=int, default=20_000)
    parser.add_argument("--duration", type=float, default=300.0, help="seconds (default: 5 min)")
    parser.add_argument("--fleet-size", type=int, default=100_000)
    parser.add_argument("--drain-seconds", type=float, default=5.0, help="wait after send stops before re-reading offsets")
    args = parser.parse_args(argv)

    kafka_brokers = os.environ.get("KAFKA_BROKERS_EXTERNAL", "localhost:9092")
    telemetry_topic = "telemetry"

    host = os.environ.get("MQTT_HOST_EXTERNAL", "localhost")
    port = int(os.environ.get("MQTT_PORT", 8883))
    ca_cert = REPO_ROOT / os.environ.get("MQTT_CA_CERT", "infra/certs/ca/ca.crt")
    shard_dir = REPO_ROOT / "infra" / "certs" / "issued" / "shards"
    n_shards = int(os.environ.get("MQTT_SHARD_COUNT", 32))

    before = _kafka_topic_total_offset(kafka_brokers, telemetry_topic)
    print(f"telemetry topic offset before: {before if before is not None else '(topic not created yet)'}")

    publisher = ShardedMqttPublisher(
        host=host, port=port, ca_cert=ca_cert, shard_cert_dir=shard_dir, tenant="demo", n_shards=n_shards,
    )
    start = time.monotonic()
    try:
        stats = run_simulation(publisher=publisher, rate_eps=args.rate, duration_s=args.duration, fleet_size=args.fleet_size, seed=42)
    finally:
        publisher.close()
    send_elapsed = time.monotonic() - start

    time.sleep(args.drain_seconds)
    after = _kafka_topic_total_offset(kafka_brokers, telemetry_topic)

    print(f"simulator sent: {stats.total_sent} messages in {send_elapsed:.1f}s "
          f"({stats.total_sent / send_elapsed:.0f} events/s attempted)")
    if before is not None and after is not None:
        delivered = after - before
        print(f"delivered to Kafka telemetry topic: {delivered} messages "
              f"({delivered / send_elapsed:.0f} events/s achieved end-to-end)")
    else:
        print("could not read telemetry topic offsets — is the `core` compose profile up? "
              "(bench measured only what the simulator attempted to send, above)")


if __name__ == "__main__":
    main()
