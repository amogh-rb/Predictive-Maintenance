#!/usr/bin/env python
"""3x burst load test (PLAN §3 "A 3x burst test measures lag and zero loss",
`make burst`). Runs a baseline rate for a warm-up, then 3x that rate for a
burst window, then measures: (1) zero-loss — every message the simulator
sent actually landed on Kafka's `telemetry` topic (offset delta == sent
count, same ground-truth method `bench_ingest.py` uses); (2) consumer lag —
how far the real `state-writer` consumer group falls behind during the
burst, and how long it takes to drain back to ~0 afterward.
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

from simulator.app.simulate import SimulationStats, run_simulation  # noqa: E402
from simulator.infra.mqtt_publisher import ShardedMqttPublisher  # noqa: E402


def _topic_total_offset(bootstrap_servers: str, topic: str) -> int | None:
    from confluent_kafka import Consumer, TopicPartition
    from confluent_kafka.admin import AdminClient

    admin = AdminClient({"bootstrap.servers": bootstrap_servers})
    metadata = admin.list_topics(topic=topic, timeout=10)
    topic_metadata = metadata.topics.get(topic)
    if topic_metadata is None or topic_metadata.error is not None:
        return None
    consumer = Consumer({"bootstrap.servers": bootstrap_servers, "group.id": "burst-test-offsets"})
    try:
        return sum(
            consumer.get_watermark_offsets(TopicPartition(topic, p), timeout=10)[1]
            for p in topic_metadata.partitions
        )
    finally:
        consumer.close()


def _consumer_group_lag(bootstrap_servers: str, topic: str, group_id: str) -> int | None:
    """Uses the AdminClient's list_consumer_group_offsets, which (unlike
    Consumer.committed()) can query another group's committed offsets
    without joining it — this is exactly what `kafka-consumer-groups.sh
    --describe` does under the hood."""
    from confluent_kafka import ConsumerGroupTopicPartitions, TopicPartition
    from confluent_kafka.admin import AdminClient

    admin = AdminClient({"bootstrap.servers": bootstrap_servers})
    metadata = admin.list_topics(topic=topic, timeout=10)
    topic_metadata = metadata.topics.get(topic)
    if topic_metadata is None or topic_metadata.error is not None:
        return None
    partitions = list(topic_metadata.partitions.keys())

    fut = admin.list_consumer_group_offsets([ConsumerGroupTopicPartitions(group_id)])[group_id]
    result = fut.result(timeout=10)
    committed_by_partition = {tp.partition: tp.offset for tp in result.topic_partitions if tp.topic == topic}

    from confluent_kafka import Consumer

    consumer = Consumer({"bootstrap.servers": bootstrap_servers, "group.id": "burst-test-watermark-probe"})
    try:
        lag_total = 0
        for p in partitions:
            _low, high = consumer.get_watermark_offsets(TopicPartition(topic, p), timeout=10)
            committed = committed_by_partition.get(p, 0)
            if committed < 0:  # -1001 = no committed offset yet for this partition
                committed = 0
            lag_total += max(0, high - committed)
        return lag_total
    finally:
        consumer.close()


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    load_dotenv(REPO_ROOT / ".env")

    parser = argparse.ArgumentParser(description="3x burst load test")
    # 500, not something like 2000: session 2's own bench_ingest.py finding
    # holds here too — above roughly ~1000 events/s this single Python
    # process (paho + per-tick JSON) becomes the bottleneck before Mosquitto/
    # gateway/Kafka do, which shows up as "loss" that's really "still queued
    # in this process," not a pipeline defect. 500 baseline / 1500 burst
    # stays under that ceiling so the zero-loss number actually reflects the
    # pipeline, not the load generator.
    parser.add_argument("--baseline-rate", type=int, default=500)
    parser.add_argument("--baseline-seconds", type=float, default=30.0)
    parser.add_argument("--burst-multiplier", type=float, default=3.0)
    parser.add_argument("--burst-seconds", type=float, default=60.0)
    parser.add_argument("--recovery-timeout", type=float, default=120.0)
    parser.add_argument("--drain-seconds", type=float, default=15.0,
                         help="wait after send stops before reading telemetry offsets for the zero-loss check")
    parser.add_argument("--consumer-group", default="state-writer")
    parser.add_argument("--fleet-size", type=int, default=100_000)
    args = parser.parse_args(argv)

    kafka_brokers = os.environ.get("KAFKA_BROKERS_EXTERNAL", "localhost:29092")
    topic = "telemetry"
    host = os.environ.get("MQTT_HOST_EXTERNAL", "localhost")
    port = int(os.environ.get("MQTT_PORT", 8883))
    ca_cert = REPO_ROOT / os.environ.get("MQTT_CA_CERT", "infra/certs/ca/ca.crt")
    shard_dir = REPO_ROOT / "infra" / "certs" / "issued" / "shards"
    n_shards = int(os.environ.get("MQTT_SHARD_COUNT", 32))

    publisher = ShardedMqttPublisher(host=host, port=port, ca_cert=ca_cert, shard_cert_dir=shard_dir, tenant="demo", n_shards=n_shards)
    stats = SimulationStats()

    before = _topic_total_offset(kafka_brokers, topic)
    print(f"telemetry offset before: {before}")
    print(f"--- baseline: {args.baseline_rate} events/s for {args.baseline_seconds:.0f}s ---")
    run_simulation(publisher=publisher, rate_eps=args.baseline_rate, duration_s=args.baseline_seconds,
                    fleet_size=args.fleet_size, seed=42, stats=stats)

    burst_rate = int(args.baseline_rate * args.burst_multiplier)
    print(f"--- burst: {burst_rate} events/s ({args.burst_multiplier:.0f}x) for {args.burst_seconds:.0f}s ---")
    burst_start = time.monotonic()
    run_simulation(publisher=publisher, rate_eps=burst_rate, duration_s=args.burst_seconds,
                    fleet_size=args.fleet_size, seed=42, stats=stats)
    burst_elapsed = time.monotonic() - burst_start

    # Drain BEFORE disconnecting: ShardedMqttPublisher.close() calls
    # paho's disconnect() immediately, which silently discards whatever is
    # still sitting in paho's own internal outgoing queue rather than
    # flushing it — a burst's sharp spike can leave a real backlog there
    # that has nothing to do with Mosquitto/gateway/Kafka. Sleeping first
    # lets the loop_start() background thread actually push it over the
    # wire before the client goes away.
    time.sleep(args.drain_seconds)
    publisher.close()
    after = _topic_total_offset(kafka_brokers, topic)
    sent = stats.total_sent
    delivered = (after - before) if (before is not None and after is not None) else None

    print(f"\nsimulator sent (baseline+burst): {sent} messages")
    if delivered is not None:
        loss = sent - delivered
        loss_pct = 100 * loss / sent if sent else 0.0
        print(f"delivered to Kafka telemetry topic: {delivered} messages "
              f"(loss: {loss}, {loss_pct:.2f}% — a small delta of a few messages can come "
              "from in-flight QoS-1 redelivery still settling)")
        if loss_pct > 5.0:
            print(
                "WARNING: loss this high usually means the burst rate exceeded this single "
                "Python simulator process's own throughput ceiling (session 2's bench_ingest.py "
                "finding: paho + per-tick JSON overhead becomes the bottleneck above roughly "
                "~1000 events/s) — not necessarily a pipeline defect. Re-run at a lower "
                "--baseline-rate before concluding the pipeline itself is dropping messages."
            )
    else:
        print("could not read telemetry topic offsets")

    print(f"\n--- consumer lag: {args.consumer_group} group, immediately after the burst ---")
    peak_lag = _consumer_group_lag(kafka_brokers, topic, args.consumer_group)
    print(f"lag right after burst ({burst_elapsed:.0f}s burst window): {peak_lag}")

    print(f"--- polling for recovery (up to {args.recovery_timeout:.0f}s) ---")
    recovery_start = time.monotonic()
    lag = peak_lag
    while time.monotonic() - recovery_start < args.recovery_timeout:
        time.sleep(5.0)
        lag = _consumer_group_lag(kafka_brokers, topic, args.consumer_group)
        elapsed = time.monotonic() - recovery_start
        print(f"  t+{elapsed:.0f}s: lag={lag}")
        if lag is not None and lag <= 0:
            print(f"lag recovered to 0 in {elapsed:.0f}s")
            break
    else:
        print(f"lag did NOT reach 0 within {args.recovery_timeout:.0f}s (last value: {lag})")


if __name__ == "__main__":
    main()
