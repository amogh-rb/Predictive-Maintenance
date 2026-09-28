"""Wires the MQTT subscriber to Kafka: validate -> Bloom-filter dedup
pre-filter -> produce to `telemetry`, or `dlq` for anything invalid.

The MQTT sink (`services/ingest-gateway/infra/mqtt_subscriber.py`) pushes
into a bounded queue; `Queue.put` blocking when full is the back-pressure
path back to the MQTT read loop. A single worker thread drains the queue so
validation and Kafka production never race with the MQTT network thread.
"""
from __future__ import annotations

import logging
import queue
import threading
from dataclasses import dataclass, field

from fleetcore.algorithms.bloom import BloomFilter
from ingest_gateway.domain.validation import validate
from ingest_gateway.infra.kafka_producer import TelemetryProducer

logger = logging.getLogger("ingest_gateway.gateway")


@dataclass
class GatewayStats:
    received: int = 0
    forwarded: int = 0
    duplicates_dropped: int = 0
    dlq: dict[str, int] = field(default_factory=dict)


class Gateway:
    def __init__(
        self,
        producer: TelemetryProducer,
        n_shards: int,
        queue_maxsize: int = 10_000,
        bloom_capacity: int = 2_000_000,
        bloom_fp_rate: float = 0.001,
    ):
        self.producer = producer
        self.n_shards = n_shards
        self._queue: queue.Queue[tuple[str, bytes]] = queue.Queue(maxsize=queue_maxsize)
        self._bloom = BloomFilter.for_capacity(bloom_capacity, bloom_fp_rate)
        self.stats = GatewayStats()
        self._stop = threading.Event()

    def sink(self, topic: str, payload: bytes) -> None:
        """Called on the MQTT thread; blocks (back-pressure) when the queue is full."""
        self._queue.put((topic, payload))

    def _process_one(self, topic: str, payload: bytes) -> None:
        self.stats.received += 1
        result = validate(topic, payload, self.n_shards)
        if not result.ok:
            self.producer.send_dlq(topic, payload, result.error, result.detail)
            self.stats.dlq[result.error] = self.stats.dlq.get(result.error, 0) + 1
            return

        message = result.message
        dedup_key = f"{message.vin}:{message.seq}"
        if dedup_key in self._bloom:
            self.stats.duplicates_dropped += 1
            return
        self._bloom.add(dedup_key)

        # tenant never rides in the wire envelope (fleetcore.domain.envelope) —
        # it's proven once, from the mTLS-authenticated topic segment, in
        # validate() above. Stamped onto the Kafka message here so Flink's
        # Timescale sink and the state-writer's Postgres/Mongo writes don't
        # have to re-derive or re-trust it downstream.
        keyed_message = {**message.model_dump(mode="json"), "tenant": result.tenant}
        self.producer.send_telemetry(message.vin, keyed_message)
        self.stats.forwarded += 1

    def run_forever(self) -> None:
        while not self._stop.is_set():
            try:
                topic, payload = self._queue.get(timeout=1.0)
            except queue.Empty:
                self.producer.poll(0)
                continue
            self._process_one(topic, payload)
            self.producer.poll(0)

    def stop(self) -> None:
        self._stop.set()
