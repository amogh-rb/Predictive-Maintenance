"""Kafka producer: batches valid telemetry to `telemetry`, invalid raw
messages to `dlq` (PLAN §2). Batching and back-pressure both come from
librdkafka's own internal queue (`linger.ms` batches, `queue.buffering.max.messages`
bounds memory); `produce()` blocks on `BufferError` by polling the client
until room frees up, so a slow Kafka propagates back to the caller instead
of an unbounded queue growing here.
"""
from __future__ import annotations

import json
import logging

from confluent_kafka import KafkaError, Producer

logger = logging.getLogger("ingest_gateway.kafka")


class TelemetryProducer:
    def __init__(
        self,
        bootstrap_servers: str,
        telemetry_topic: str = "telemetry",
        dlq_topic: str = "dlq",
        linger_ms: int = 20,
        batch_num_messages: int = 500,
    ):
        self.telemetry_topic = telemetry_topic
        self.dlq_topic = dlq_topic
        self._producer = Producer(
            {
                "bootstrap.servers": bootstrap_servers,
                "linger.ms": linger_ms,
                "batch.num.messages": batch_num_messages,
                "queue.buffering.max.messages": 200_000,
                "enable.idempotence": True,
            }
        )

    def _delivery_callback(self, err: KafkaError | None, msg) -> None:
        if err is not None:
            logger.error("delivery failed for %s: %s", msg.topic(), err)

    def _produce(self, topic: str, key: str, value: bytes) -> None:
        while True:
            try:
                self._producer.produce(topic, key=key, value=value, callback=self._delivery_callback)
                return
            except BufferError:
                # librdkafka's outgoing queue is full — poll to drain delivery
                # reports and free space, i.e. back-pressure instead of buffering here.
                self._producer.poll(0.5)

    def send_telemetry(self, vin: str, message: dict) -> None:
        self._produce(self.telemetry_topic, key=vin, value=json.dumps(message, default=str).encode("utf-8"))

    def send_dlq(self, topic: str, raw_payload: bytes, reason: str, detail: str) -> None:
        envelope = {"source_topic": topic, "reason": reason, "detail": detail, "raw": raw_payload.decode("utf-8", errors="replace")}
        self._produce(self.dlq_topic, key=reason, value=json.dumps(envelope).encode("utf-8"))

    def poll(self, timeout: float = 0.0) -> None:
        self._producer.poll(timeout)

    def flush(self, timeout: float = 10.0) -> None:
        self._producer.flush(timeout)
