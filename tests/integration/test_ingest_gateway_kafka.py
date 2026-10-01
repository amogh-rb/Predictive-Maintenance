"""Integration test: the real `Gateway` + `TelemetryProducer` (ingest-gateway's
actual production code, not a reimplementation) against a real ephemeral
Kafka (PLAN §5 "Integration: Testcontainers"). Unit tests already cover
`validate()` and the Bloom filter in isolation with mocks; this proves the
whole pipeline actually round-trips through a real broker: a valid message
lands on `telemetry` with the right key/tenant stamp, a byte-identical
duplicate (same vin+seq) is dropped before ever reaching Kafka, and an
invalid payload lands on `dlq` instead.
"""
from __future__ import annotations

import json
import time

import pytest
from confluent_kafka import Consumer
from testcontainers.community.kafka import KafkaContainer

from fleetcore.algorithms.sharding import shard_topic
from ingest_gateway.app.gateway import Gateway
from ingest_gateway.infra.kafka_producer import TelemetryProducer

N_SHARDS = 32
VALID_VIN = "1HGCM82633A004352"
TOPIC = shard_topic("demo", VALID_VIN, N_SHARDS)


def _valid_payload(seq: int) -> bytes:
    return json.dumps(
        {
            "vin": VALID_VIN,
            "msg_type": "EVENT",
            "seq": seq,
            "ts": "2026-09-29T12:00:00Z",
            "fw_version": "1.0.0",
            "payload": {"event_type": "IGNITION_ON"},
        }
    ).encode("utf-8")


@pytest.fixture(scope="module")
def bootstrap_servers():
    with KafkaContainer("confluentinc/cp-kafka:7.6.0") as kafka:
        yield kafka.get_bootstrap_server()


def _drain(bootstrap_servers: str, topic: str, expected: int, timeout_s: float = 15.0) -> list[dict]:
    consumer = Consumer(
        {
            "bootstrap.servers": bootstrap_servers,
            "group.id": f"test-{topic}-{time.time_ns()}",
            "auto.offset.reset": "earliest",
        }
    )
    consumer.subscribe([topic])
    messages: list[dict] = []
    deadline = time.monotonic() + timeout_s
    try:
        while len(messages) < expected and time.monotonic() < deadline:
            msg = consumer.poll(1.0)
            if msg is None or msg.error():
                continue
            messages.append(json.loads(msg.value()))
    finally:
        consumer.close()
    return messages


def test_valid_message_forwarded_duplicate_dropped_invalid_dlq(bootstrap_servers):
    producer = TelemetryProducer(bootstrap_servers)
    gateway = Gateway(producer, n_shards=N_SHARDS)

    gateway._process_one(TOPIC, _valid_payload(seq=1))
    gateway._process_one(TOPIC, _valid_payload(seq=1))  # exact duplicate: same vin+seq
    gateway._process_one(TOPIC, b"not json at all")
    producer.flush()

    assert gateway.stats.forwarded == 1
    assert gateway.stats.duplicates_dropped == 1
    assert gateway.stats.dlq.get("bad_json") == 1

    telemetry_messages = _drain(bootstrap_servers, "telemetry", expected=1)
    assert len(telemetry_messages) == 1
    assert telemetry_messages[0]["vin"] == VALID_VIN
    assert telemetry_messages[0]["seq"] == 1
    assert telemetry_messages[0]["tenant"] == "demo"

    dlq_messages = _drain(bootstrap_servers, "dlq", expected=1)
    assert len(dlq_messages) == 1
    assert dlq_messages[0]["reason"] == "bad_json"
