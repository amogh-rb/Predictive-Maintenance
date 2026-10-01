#!/usr/bin/env python
"""Chaos test: kill a Kafka broker mid-load, verify zero-loss recovery
(PLAN §5/§6.3 row 9 "kill a broker ... mid-load"; session 10 gap-fill —
`chaos_test.py` only ever covered the Flink TaskManager kill and explicitly
recorded the broker case as untested, since the `core` profile's Kafka is a
single broker by design and the `chaos` profile's 3-broker cluster has no
gateway/Flink wired to it).

Tests the 3-broker `chaos` profile cluster directly with a real
producer/consumer (acks=all, RF=3, min.insync.replicas=2) rather than routing
the whole gateway+Flink pipeline through it — that pipeline rewiring is out
of scope for what this gap-fill needs to prove, which is Kafka's own
replication/failover guarantee. "Zero loss" is checked by key, the same
ground-truth style as `chaos_test.py` and `burst_test.py`: every message
produced is looked up individually after the outage, not just counted.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import threading
import time

BOOTSTRAP = "localhost:29093,localhost:29094,localhost:29095"
TOPIC = "chaos-broker-test"
KILL_CONTAINER = "fleetpulse-kafka-chaos-2-1"


def _docker(*args: str) -> str:
    result = subprocess.run(["docker", *args], capture_output=True, text=True, check=True)
    return result.stdout.strip()


def main(argv: list[str] | None = None) -> None:
    from confluent_kafka import Consumer, Producer
    from confluent_kafka.admin import AdminClient, NewTopic

    parser = argparse.ArgumentParser(description="Kill a Kafka broker mid-produce; verify zero-loss recovery")
    parser.add_argument("--rate", type=int, default=200, help="messages/s")
    parser.add_argument("--total-seconds", type=float, default=60.0)
    parser.add_argument("--kill-at-seconds", type=float, default=15.0)
    parser.add_argument("--outage-seconds", type=float, default=15.0)
    args = parser.parse_args(argv)

    admin = AdminClient({"bootstrap.servers": BOOTSTRAP})
    print(f"--- creating topic {TOPIC} (RF=3, min.insync.replicas=2) ---")
    fut = admin.create_topics([NewTopic(TOPIC, num_partitions=6, replication_factor=3,
                                         config={"min.insync.replicas": "2"})])
    for name, f in fut.items():
        try:
            f.result(timeout=30)
        except Exception as e:
            if "already exists" not in str(e):
                raise
    time.sleep(3.0)  # let metadata propagate before producing

    producer = Producer({
        "bootstrap.servers": BOOTSTRAP,
        "acks": "all",
        "enable.idempotence": True,
        "retries": 10,
        "retry.backoff.ms": 500,
    })

    sent: list[str] = []
    failed: list[str] = []
    lock = threading.Lock()

    def _delivery(err, msg):
        key = msg.key().decode()
        with lock:
            (failed if err else sent).append(key)

    def _kill_and_recover():
        time.sleep(args.kill_at_seconds)
        print(f"\n--- killing {KILL_CONTAINER} (simulating a broker crash mid-load) ---")
        _docker("kill", KILL_CONTAINER)
        time.sleep(args.outage_seconds)
        print(f"--- restarting {KILL_CONTAINER} ---")
        _docker("start", KILL_CONTAINER)
        print("--- broker restarted; giving it time to rejoin the ISR ---\n")

    chaos_thread = threading.Thread(target=_kill_and_recover, daemon=True)
    chaos_thread.start()

    print(f"--- producing {args.rate}/s for {args.total_seconds:.0f}s (broker killed at t+{args.kill_at_seconds:.0f}s) ---")
    n = int(args.rate * args.total_seconds)
    interval = 1.0 / args.rate
    start = time.monotonic()
    for i in range(n):
        key = f"msg-{i}"
        producer.produce(TOPIC, key=key.encode(), value=b"x", callback=_delivery)
        producer.poll(0)
        target = start + i * interval
        sleep_for = target - time.monotonic()
        if sleep_for > 0:
            time.sleep(sleep_for)
    print("--- flushing producer (this blocks until every in-flight send is acked or times out) ---")
    remaining = producer.flush(timeout=120)
    chaos_thread.join(timeout=args.outage_seconds + 30.0)

    print(f"\nattempted {n}, acked {len(sent)}, failed {len(failed)}, still unflushed {remaining}")
    if failed:
        print(f"FAILED (never acked): {failed[:10]}{'...' if len(failed) > 10 else ''}")

    print("--- consuming the full topic back to verify by key ---")
    consumer = Consumer({"bootstrap.servers": BOOTSTRAP, "group.id": "chaos-broker-verify",
                          "auto.offset.reset": "earliest"})
    consumer.subscribe([TOPIC])
    landed: set[str] = set()
    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        msg = consumer.poll(1.0)
        if msg is None:
            continue
        if msg.error():
            continue
        landed.add(msg.key().decode())
        if len(landed) >= len(sent):
            break
    consumer.close()

    missing = [k for k in sent if k not in landed]
    print(f"landed in topic: {len(sent) - len(missing)} / {len(sent)} acked messages")

    print("--- cleanup: deleting test topic ---")
    admin.delete_topics([TOPIC])[TOPIC].result(timeout=30)

    if missing or failed:
        print(f"\nLOSS DETECTED: {len(missing)} acked-but-missing, {len(failed)} never acked")
        sys.exit(1)
    else:
        print("\nZERO LOSS confirmed: every acked message survived the broker kill/restart "
              "(Kafka replication + acks=all did its job).")


if __name__ == "__main__":
    main()
