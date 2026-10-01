"""Fans the `alerts` Kafka topic (Flink's sink, session 4) out to connected
WebSocket clients, filtered per-connection by tenant (PLAN §2 "API":
WebSocket alerts). confluent-kafka's Consumer is synchronous, so it runs on
a dedicated background thread; each message is handed to the asyncio event
loop via `run_coroutine_threadsafe` rather than sharing the loop directly.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import threading

from confluent_kafka import OFFSET_END, Consumer, TopicPartition
from fastapi import WebSocket

logger = logging.getLogger("api.ws")


class AlertBroadcaster:
    def __init__(self) -> None:
        self._connections: dict[WebSocket, str] = {}  # ws -> tenant name
        self._lock = asyncio.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    async def register(self, ws: WebSocket, tenant: str) -> None:
        async with self._lock:
            self._connections[ws] = tenant

    async def unregister(self, ws: WebSocket) -> None:
        async with self._lock:
            self._connections.pop(ws, None)

    def start(self) -> None:
        self._loop = asyncio.get_event_loop()
        self._thread = threading.Thread(target=self._consume_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _consume_loop(self) -> None:
        # Each API process wants every alert (it fans out to its own sockets), so there is nothing to
        # share with other consumers: assign the partitions directly from the end instead of joining a
        # consumer group. No group means no rebalances or session timeouts, which under load left the
        # feed silent for minutes (a group join stuck behind a busy broker).
        consumer = Consumer({
            "bootstrap.servers": os.environ.get("KAFKA_BROKERS", "localhost:9092"),
            "group.id": "api-ws-broadcaster",
            "enable.auto.commit": False,
            "auto.offset.reset": "latest",
        })
        try:
            while not self._stop.is_set():
                try:
                    partitions = consumer.list_topics("alerts", timeout=10).topics["alerts"].partitions
                    consumer.assign([TopicPartition("alerts", p, OFFSET_END) for p in partitions])
                    break
                except Exception:
                    logger.warning("alerts topic not reachable yet, retrying")
                    self._stop.wait(3)
            while not self._stop.is_set():
                msg = consumer.poll(1.0)
                if msg is None or msg.error():
                    continue
                try:
                    alert = json.loads(msg.value())
                except (json.JSONDecodeError, TypeError):
                    continue
                if self._loop:
                    asyncio.run_coroutine_threadsafe(self._broadcast(alert), self._loop)
        finally:
            consumer.close()

    async def _broadcast(self, alert: dict) -> None:
        tenant = alert.get("tenant")
        async with self._lock:
            targets = [ws for ws, t in self._connections.items() if t == tenant]
        for ws in targets:
            try:
                await ws.send_json(alert)
            except Exception:
                logger.warning("dropping a WS connection that failed to send")
                await self.unregister(ws)


broadcaster = AlertBroadcaster()
