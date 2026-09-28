"""Wires the Kafka consumer to Redis/Mongo/Postgres (PLAN §2's state-writer
box): `telemetry` -> twin merge -> Redis + Mongo twin + Mongo raw archive;
`alerts` -> Postgres `alert`. One consumer, dispatched by topic, matching the
architecture diagram's state-writer forking off `telemetry` independently of
Flink rather than reading Flink's output.

The in-memory `_twins` cache (not a Mongo read-before-merge per message) is
reset on restart, same documented tradeoff as the ingest-gateway's Bloom
filter (session 2): a duplicate/out-of-order message straddling a restart
can slip past the seq guard once. Acceptable for a POC; a real deployment
would seed the cache from Mongo on startup.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from state_writer.domain.twin import merge_twin

logger = logging.getLogger("state_writer.writer")


@dataclass
class WriterStats:
    telemetry_processed: int = 0
    telemetry_stale_dropped: int = 0
    alerts_processed: int = 0
    alerts_unknown_vin: int = 0


class StateWriter:
    def __init__(
        self,
        consumer,
        latest_store,
        twin_store,
        alert_store,
        telemetry_topic: str,
        alerts_topic: str,
    ):
        self._consumer = consumer
        self._latest_store = latest_store
        self._twin_store = twin_store
        self._alert_store = alert_store
        self._telemetry_topic = telemetry_topic
        self._alerts_topic = alerts_topic
        self._twins: dict[str, dict[str, Any]] = {}
        self.stats = WriterStats()
        self._stop = False

    def _handle_telemetry(self, message: dict[str, Any]) -> None:
        vin = message["vin"]
        updated = merge_twin(self._twins.get(vin), message)
        if updated is None:
            self.stats.telemetry_stale_dropped += 1
            return
        self._twins[vin] = updated
        self._latest_store.set_latest(vin, updated)
        self._twin_store.upsert_twin(vin, updated)
        self._twin_store.archive_raw(message)
        self.stats.telemetry_processed += 1

    def _handle_alert(self, alert: dict[str, Any]) -> None:
        if self._alert_store.insert_alert(alert):
            self.stats.alerts_processed += 1
        else:
            self.stats.alerts_unknown_vin += 1

    def run_forever(self) -> None:
        while not self._stop:
            result = self._consumer.poll(1.0)
            if result is None:
                continue
            topic, payload = result
            try:
                if topic == self._telemetry_topic:
                    self._handle_telemetry(payload)
                elif topic == self._alerts_topic:
                    self._handle_alert(payload)
                else:
                    logger.warning("message on unexpected topic %s", topic)
            except (KeyError, TypeError) as exc:
                # A malformed/unexpected-shape message (e.g. pre-session-4
                # historical data missing the `tenant` field this session
                # added) should drop that one record, not take the whole
                # consumer loop down — matching ingest-gateway's own
                # validate-and-route-bad-input-aside pattern (session 2).
                logger.error("dropping unprocessable message on %s: %s", topic, exc)

    def stop(self) -> None:
        self._stop = True
