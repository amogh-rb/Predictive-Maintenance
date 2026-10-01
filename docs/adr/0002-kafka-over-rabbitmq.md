# ADR 2: Kafka (KRaft) over RabbitMQ

**Status:** accepted

**Context.** Telemetry needs replay (reprocess after a rule change), per-vehicle ordering, and several independent consumers (Flink, state-writer, WebSocket fan-out).

**Decision.** Apache Kafka in KRaft mode, `telemetry` keyed by VIN, with `alerts` and `dlq` topics. Apicurio Schema Registry is in the stack; the wire format is JSON validated against a schema generated from the pydantic envelope.

**Consequences.**
- Partition-per-VIN ordering and offset replay; consumers are independent.
- Operational cost: the 512 MB heap caused 14 s GC pauses that exceeded the KRaft session timeout; heap raised to 1 GB, and the data dir moved onto the volume (session 10c).
- Consumers can go stale after long uptime; state-writer now has a stall watchdog that exits so the container restarts.
