"""One consumer subscribed to both `telemetry` and `alerts` (PLAN §2's
state-writer box forks off the same `telemetry` topic Flink reads
independently, and also drains the `alerts` topic Flink's rule pipeline
produces to). A single consumer keeps startup/shutdown and offset commits in
one place; the app layer dispatches by topic.
"""
from __future__ import annotations

import json
import logging

from confluent_kafka import Consumer

logger = logging.getLogger("state_writer.kafka")


class MessageConsumer:
    def __init__(self, bootstrap_servers: str, topics: list[str], group_id: str = "state-writer"):
        self._consumer = Consumer(
            {
                "bootstrap.servers": bootstrap_servers,
                "group.id": group_id,
                # "latest", not "earliest": state-writer, like the Flink job
                # (stream/flink/sql/00_source.sql), is the real-time layer —
                # it shouldn't replay sessions 2-3's historical backlog,
                # some of which predates this session's envelope/tenant
                # field and isn't guaranteed to still parse.
                "auto.offset.reset": "latest",
                "enable.auto.commit": True,
            }
        )
        self._consumer.subscribe(topics)

    def poll(self, timeout: float = 1.0) -> tuple[str, dict] | None:
        msg = self._consumer.poll(timeout)
        if msg is None:
            return None
        if msg.error():
            logger.error("consumer error: %s", msg.error())
            return None
        try:
            return msg.topic(), json.loads(msg.value())
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            logger.error("unparseable message on %s: %s", msg.topic(), exc)
            return None

    def close(self) -> None:
        self._consumer.close()
