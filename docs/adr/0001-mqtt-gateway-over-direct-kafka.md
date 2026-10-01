# ADR 1: MQTT plus a custom ingest-gateway, not devices writing to Kafka

**Status:** accepted

**Context.** 100K vehicles on cellular links need a lightweight, flaky-network-tolerant protocol. Kafka clients are heavy and give us no per-device identity or edge validation. A broker-native Kafka bridge would forward anything.

**Decision.** Every truck publishes over MQTT 5 (QoS 1, mTLS) to Mosquitto. A stateless Python ingest-gateway reads via shared subscription, validates, dedups and writes to Kafka. There is no second ingestion path.

**Consequences.**
- Kafka is shielded from device traffic; bad messages go to a DLQ.
- Validation (schema, VIN ISO 3779 check digit, DTC regex, shard match) and back-pressure are unit-testable code.
- Scales horizontally; scaling exposed a real bug (hardcoded MQTT client_id kicked the first copy off), fixed in session 10a.
- **Deviation:** 100K per-vehicle certificates was out of scope, so identity is checked per VIN-hash shard (32 shard certs, one ACL entry each). The gateway re-derives the shard from the VIN and rejects mismatches. Per-vehicle certs are the production step.
- A single Mosquitto thread is a throughput ceiling; sharding or EMQX is the next move.
