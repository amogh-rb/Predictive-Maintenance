#!/usr/bin/env python
"""ingest-gateway entrypoint: MQTT (shared subscription) -> validate -> Kafka.

Reads connection details from the environment (set by docker-compose from
`.env`, or exported directly for a local run): MQTT_HOST, MQTT_PORT,
MQTT_CA_CERT, MQTT_SHARD_COUNT, KAFKA_BROKERS.
"""
from __future__ import annotations

import logging
import os
import signal
import sys
import threading
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "services" / "ingest-gateway" / "src"))
sys.path.insert(0, str(REPO_ROOT / "libs"))

from ingest_gateway.app.gateway import Gateway  # noqa: E402
from ingest_gateway.infra.kafka_producer import TelemetryProducer  # noqa: E402
from ingest_gateway.infra.mqtt_subscriber import GatewaySubscriber  # noqa: E402


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logger = logging.getLogger("ingest_gateway.main")

    mqtt_host = os.environ.get("MQTT_HOST", "mosquitto")
    mqtt_port = int(os.environ.get("MQTT_PORT", 8883))
    ca_cert = REPO_ROOT / os.environ.get("MQTT_CA_CERT", "infra/certs/ca/ca.crt")
    gateway_cert = REPO_ROOT / "infra" / "certs" / "issued" / "ingest-gateway.crt"
    gateway_key = REPO_ROOT / "infra" / "certs" / "issued" / "ingest-gateway.key"
    n_shards = int(os.environ.get("MQTT_SHARD_COUNT", 32))
    kafka_brokers = os.environ.get("KAFKA_BROKERS", "kafka:9092")

    producer = TelemetryProducer(bootstrap_servers=kafka_brokers)
    gateway = Gateway(producer=producer, n_shards=n_shards)
    subscriber = GatewaySubscriber(
        host=mqtt_host, port=mqtt_port, ca_cert=ca_cert,
        client_cert=gateway_cert, client_key=gateway_key, sink=gateway.sink,
    )

    mqtt_thread = threading.Thread(target=subscriber.run_forever, daemon=True)
    mqtt_thread.start()

    def _shutdown(signum, frame):
        logger.info("shutting down (received signal %s)", signum)
        gateway.stop()
        subscriber.stop()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        gateway.run_forever()
    finally:
        producer.flush()
        logger.info(
            "final stats: received=%d forwarded=%d duplicates_dropped=%d dlq=%s",
            gateway.stats.received, gateway.stats.forwarded,
            gateway.stats.duplicates_dropped, gateway.stats.dlq,
        )


if __name__ == "__main__":
    main()
