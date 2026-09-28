"""MQTT 5 + mTLS publisher, one connection per active VIN-hash shard.

A shard's client cert is only allowed (by the Mosquitto ACL generated in
`infra/certs/issue-shard-certs.py`) to publish under its own
`fleet/{tenant}/shard-{n}/+/telemetry` topic segment, so this class keeps one
`paho.mqtt.Client` per shard and lazily connects a shard's client the first
time a vehicle hashing to it needs to publish — most runs only touch a
handful of the configured shards.
"""
from __future__ import annotations

import json
import ssl
from pathlib import Path

import paho.mqtt.client as mqtt
import paho.mqtt.properties as mqtt_props
from paho.mqtt.packettypes import PacketTypes

from fleetcore.algorithms.sharding import shard_for_vin


class ShardedMqttPublisher:
    def __init__(
        self,
        host: str,
        port: int,
        ca_cert: str | Path,
        shard_cert_dir: str | Path,
        tenant: str,
        n_shards: int,
        qos: int = 1,
    ):
        self.host = host
        self.port = port
        self.ca_cert = str(ca_cert)
        self.shard_cert_dir = Path(shard_cert_dir)
        self.tenant = tenant
        self.n_shards = n_shards
        self.qos = qos
        self._clients: dict[int, mqtt.Client] = {}

    def _connect_shard(self, shard: int) -> mqtt.Client:
        crt = self.shard_cert_dir / f"shard-{shard}.crt"
        key = self.shard_cert_dir / f"shard-{shard}.key"
        client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"sim-shard-{shard}",
            protocol=mqtt.MQTTv5,
        )
        client.tls_set(ca_certs=self.ca_cert, certfile=str(crt), keyfile=str(key), cert_reqs=ssl.CERT_REQUIRED)
        client.tls_insecure_set(True)  # dev CA / dev certs carry no SAN for "localhost"
        client.connect(self.host, self.port, keepalive=30)
        client.loop_start()
        return client

    def _client_for_shard(self, shard: int) -> mqtt.Client:
        client = self._clients.get(shard)
        if client is None:
            client = self._connect_shard(shard)
            self._clients[shard] = client
        return client

    def topic_for(self, vin: str) -> tuple[int, str]:
        shard = shard_for_vin(vin, self.n_shards)
        return shard, f"fleet/{self.tenant}/shard-{shard}/{vin}/telemetry"

    def publish(self, vin: str, message: dict) -> None:
        shard, topic = self.topic_for(vin)
        client = self._client_for_shard(shard)
        properties = mqtt_props.Properties(PacketTypes.PUBLISH)
        properties.MessageExpiryInterval = 60
        client.publish(topic, json.dumps(message, default=str), qos=self.qos, properties=properties)

    def close(self) -> None:
        for client in self._clients.values():
            client.loop_stop()
            client.disconnect()
        self._clients.clear()
