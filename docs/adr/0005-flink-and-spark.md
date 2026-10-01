# ADR 5: Flink for real time, Spark for batch

**Status:** accepted

**Decision.** Flink SQL handles dedup, windowed rules and MATCH_RECOGNIZE (recurring misfire DTCs). Spark computes daily per-vehicle features (7-day slopes, DTC recurrence, tyre sibling delta, slip ratio) for sklearn.

**Why two engines.** Alerts need seconds of latency; model features need large scans. One engine would be a poor fit for one of them.

**Consequences.**
- Single-reading rules (lubrication, 12V, MIL, brakes, tyre, EV cell temperature) alert in about 1 s end to end. Sustained-window rules (cooling, transmission) alert about 6-7 s after the 30 s window closes, because the watermark needs a 5 s out-of-orderness bound. The "under 5 s" target holds for the first group only.
- Idle Kafka partitions pinned the watermark; `table.exec.source.idle-timeout` is 10 s.
- TaskManager needed 2 GB (1 GB OOM'd under sustained load). Flink has no JobManager HA here, so `make flink-submit` is required after a JM restart.
