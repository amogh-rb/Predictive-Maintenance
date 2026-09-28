"""MQTT 5 + mTLS subscriber using a shared subscription, so N gateway copies
split the load of every shard's telemetry between them (PLAN §2: "Stateless
and horizontally scaled via MQTT 5 shared subscriptions").

Back-pressure: `on_message` calls `sink(topic, payload)` synchronously on
paho's network thread. If `sink` blocks (the gateway's bounded queue is
full because Kafka can't keep up), paho stops reading further bytes off the
socket until it returns — the standard way to turn a slow consumer into
actual TCP-level back-pressure on the MQTT connection, rather than an
unbounded in-memory buffer.
"""
from __future__ import annotations

import logging
import ssl
from pathlib import Path
from typing import Callable

import paho.mqtt.client as mqtt

logger = logging.getLogger("ingest_gateway.mqtt")

Sink = Callable[[str, bytes], None]


class GatewaySubscriber:
    def __init__(
        self,
        host: str,
        port: int,
        ca_cert: str | Path,
        client_cert: str | Path,
        client_key: str | Path,
        sink: Sink,
        share_group: str = "gateway",
        topic_filter: str = "fleet/+/+/+/telemetry",
        client_id: str = "ingest-gateway",
    ):
        self.host = host
        self.port = port
        self.sink = sink
        self.topic = f"$share/{share_group}/{topic_filter}"

        self.client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
            protocol=mqtt.MQTTv5,
        )
        self.client.tls_set(
            ca_certs=str(ca_cert), certfile=str(client_cert), keyfile=str(client_key), cert_reqs=ssl.CERT_REQUIRED,
        )
        self.client.tls_insecure_set(True)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            client.subscribe(self.topic, qos=1)
            logger.info("connected, subscribed to %s", self.topic)
        else:
            logger.error("MQTT connect failed: %s", reason_code)

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        logger.warning("MQTT disconnected: %s", reason_code)

    def _on_message(self, client, userdata, message):
        try:
            self.sink(message.topic, message.payload)
        except Exception:
            logger.exception("sink raised while handling message on %s", message.topic)

    def run_forever(self) -> None:
        self.client.connect(self.host, self.port, keepalive=30)
        self.client.loop_forever()

    def stop(self) -> None:
        self.client.disconnect()
