#!/usr/bin/env python
"""state-writer entrypoint (PLAN §6.3 session 4): telemetry -> Redis (latest
state) + MongoDB (vehicle twin, raw archive); alerts -> Postgres `alert`.

Reads connection details from the environment (set by docker-compose from
`.env`): KAFKA_BROKERS, TELEMETRY_TOPIC, ALERTS_TOPIC, REDIS_HOST, REDIS_PORT,
MONGO_URI, MONGO_DB, POSTGRES_HOST/PORT/DB/USER/PASSWORD.
"""
from __future__ import annotations

import logging
import os
import signal
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "services" / "state-writer" / "src"))
sys.path.insert(0, str(REPO_ROOT / "libs"))

from state_writer.app.writer import StateWriter  # noqa: E402
from state_writer.domain.watchdog import ConsumerStalled  # noqa: E402
from state_writer.infra.kafka_consumer import MessageConsumer  # noqa: E402
from state_writer.infra.mongo_store import TwinStore  # noqa: E402
from state_writer.infra.postgres_store import AlertStore  # noqa: E402
from state_writer.infra.redis_store import LatestStateStore  # noqa: E402


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logger = logging.getLogger("state_writer.main")

    kafka_brokers = os.environ.get("KAFKA_BROKERS", "kafka:9092")
    telemetry_topic = os.environ.get("TELEMETRY_TOPIC", "telemetry")
    alerts_topic = os.environ.get("ALERTS_TOPIC", "alerts")

    consumer = MessageConsumer(kafka_brokers, [telemetry_topic, alerts_topic])
    latest_store = LatestStateStore(
        host=os.environ.get("REDIS_HOST", "redis"), port=int(os.environ.get("REDIS_PORT", 6379))
    )
    twin_store = TwinStore(
        uri=os.environ.get("MONGO_URI", "mongodb://fleetpulse:changeme@mongodb:27017"),
        db_name=os.environ.get("MONGO_DB", "fleetpulse"),
    )
    alert_store = AlertStore(
        host=os.environ.get("POSTGRES_HOST", "postgres"),
        port=int(os.environ.get("POSTGRES_PORT", 5432)),
        dbname=os.environ.get("POSTGRES_DB", "fleetpulse"),
        user=os.environ.get("POSTGRES_USER", "fleetpulse"),
        password=os.environ.get("POSTGRES_PASSWORD", "changeme"),
    )

    writer = StateWriter(consumer, latest_store, twin_store, alert_store, telemetry_topic, alerts_topic)

    def _shutdown(signum, frame):
        logger.info("shutting down (received signal %s)", signum)
        writer.stop()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        writer.run_forever()
    except ConsumerStalled as exc:
        # Sessions 5 and 9: docker compose ps stays "Up" while the consumer
        # group silently stops consuming after a broker heartbeat blip. Exit
        # non-zero so `restart: unless-stopped` recreates the container with
        # a fresh consumer instead of limping indefinitely.
        logger.error("stalled, exiting for restart: %s", exc)
        raise SystemExit(1) from exc
    finally:
        consumer.close()
        logger.info(
            "final stats: telemetry=%d stale_dropped=%d alerts=%d alerts_unknown_vin=%d",
            writer.stats.telemetry_processed, writer.stats.telemetry_stale_dropped,
            writer.stats.alerts_processed, writer.stats.alerts_unknown_vin,
        )


if __name__ == "__main__":
    main()
