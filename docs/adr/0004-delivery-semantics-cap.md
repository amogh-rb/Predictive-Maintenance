# ADR 4: Delivery semantics and CAP/PACELC

**Status:** accepted

**Decision.** At-least-once at the edges with idempotent keys; exactly-once only where Flink controls the whole path.
- MQTT QoS 1 can redeliver. The gateway Bloom filter drops duplicates (false positives are possible by design, so `seq` starts from a per-run base to avoid dropping new runs).
- Flink checkpoints every 30 s to the lake bucket; a killed TaskManager recovers on its own.
- Real-time rules read the raw topic, not the dedup view, so a checkpoint replay can double-emit an alert. Accepted trade-off: the dedup view's changelog semantics would strip the watermark the windows need.

**CAP/PACELC.** Postgres is CP (alerts, work orders, audit must not diverge). Telemetry and Redis/Mongo lean AP and favour latency over consistency (PA/EL).

**Evidence.** TaskManager kill: 27,408/27,408 `(vin, seq)` pairs landed. Broker kill (3-broker, acks=all): 12,000/12,000. Gateway-copy kill: 1.19% loss, which is QoS-1 settling noise, not zero. Burst 3x: lag 24,039 recovered to 0 in 36 s, 1.97% simulator-side delta. We do not claim zero loss for the gateway-kill or burst runs.
