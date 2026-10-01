from __future__ import annotations

import random
import time
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from behave import given, then, when
from confluent_kafka import Consumer, TopicPartition

from simulator.infra.mqtt_publisher import ShardedMqttPublisher

KAFKA_BOOTSTRAP = "localhost:29092"

PG = dict(host="localhost", port=5434, dbname="fleetpulse", user="fleetpulse", password="changeme")
REPO_ROOT = Path(__file__).parents[3]

_publisher = ShardedMqttPublisher(
    host="localhost",
    port=8883,
    ca_cert=REPO_ROOT / "infra" / "certs" / "ca" / "ca.crt",
    shard_cert_dir=REPO_ROOT / "infra" / "certs" / "issued" / "shards",
    tenant="demo",
    n_shards=32,
)


def _fast_message(vin: str, seq: int, oil_kpa: float, rpm: float) -> dict:
    return {
        "vin": vin,
        "msg_type": "FAST",
        "seq": seq,
        "ts": datetime.now(timezone.utc).isoformat(),
        "fw_version": "1.0.0",
        "payload": {
            "lat": 13.08, "lon": 80.27, "heading": 90.0, "gps_hdop": 0.9,
            "speed_kmh": 60.0, "odo_km": 100000.0, "accel_long_g": 0.0,
            "accel_lat_g": 0.0, "ambient_c": 30.0, "rpm": rpm, "oil_kpa": oil_kpa,
        },
    }


@given("a real seeded vehicle from the demo tenant")
def step_pick_seeded_vehicle(context):
    with psycopg.connect(**PG, autocommit=True) as conn:
        row = conn.execute(
            "SELECT v.vin FROM vehicle v JOIN tenant t ON t.id = v.tenant_id "
            "WHERE t.name = 'demo' LIMIT 1"
        ).fetchone()
    assert row is not None, "no seeded vehicle found — run `make seed` first"
    context.vin = row[0].rstrip()
    # Flink stamps alerts' detected_at truncated to milliseconds; a microsecond start time would
    # make an alert raised in the same millisecond look like it predates the scenario.
    now = datetime.now(timezone.utc)
    context.scenario_started_at = now.replace(microsecond=now.microsecond // 1000 * 1000)


@when("a FAST reading with oil_kpa {oil_kpa:d} and rpm {rpm:d} is published for it over MQTT")
def step_publish_once(context, oil_kpa, rpm):
    seq = random.randint(10**9, 2 * 10**9)  # fresh, unseen by the gateway's long-lived Bloom filter
    _publisher.publish(context.vin, _fast_message(context.vin, seq, float(oil_kpa), float(rpm)))


@when("the same FAST reading with oil_kpa {oil_kpa:d} and rpm {rpm:d} is published twice for it over MQTT")
def step_publish_twice(context, oil_kpa, rpm):
    context.dedup_seq = random.randint(10**9, 2 * 10**9)
    message = _fast_message(context.vin, context.dedup_seq, float(oil_kpa), float(rpm))
    _publisher.publish(context.vin, message)
    _publisher.publish(context.vin, message)  # byte-identical redelivery


def _count_alerts(vin: str, since: datetime) -> int:
    with psycopg.connect(**PG, autocommit=True) as conn:
        return conn.execute(
            "SELECT count(*) FROM alert a JOIN vehicle v ON v.id = a.vehicle_id "
            "WHERE v.vin = %s AND a.failure_type = 'lubrication' AND a.opened_at >= %s",
            (vin, since),
        ).fetchone()[0]


@then('a "lubrication" alert for that vehicle appears in Postgres within {seconds:d} seconds')
def step_alert_appears(context, seconds):
    deadline = time.monotonic() + seconds
    count = 0
    while time.monotonic() < deadline:
        count = _count_alerts(context.vin, context.scenario_started_at)
        if count >= 1:
            break
        time.sleep(0.25)
    assert count >= 1, f"no lubrication alert for {context.vin} within {seconds}s"


@then("exactly one copy of that reading appears on the telemetry topic")
def step_exactly_one_on_telemetry(context):
    import json

    consumer = Consumer(
        {
            "bootstrap.servers": KAFKA_BOOTSTRAP,
            "group.id": f"bdd-dedup-{time.time_ns()}",
            "enable.auto.commit": False,
        }
    )
    metadata = consumer.list_topics("telemetry", timeout=5)
    partitions = []
    for p in metadata.topics["telemetry"].partitions:
        low, high = consumer.get_watermark_offsets(TopicPartition("telemetry", p), timeout=5)
        partitions.append(TopicPartition("telemetry", p, max(low, high - 100)))
    consumer.assign(partitions)

    count = 0
    deadline = time.monotonic() + 8.0
    try:
        while time.monotonic() < deadline:
            msg = consumer.poll(1.0)
            if msg is None or msg.error():
                continue
            value = json.loads(msg.value())
            if value.get("seq") == context.dedup_seq:
                count += 1
    finally:
        consumer.close()
    assert count == 1, f"expected exactly 1 copy on telemetry, found {count}"
