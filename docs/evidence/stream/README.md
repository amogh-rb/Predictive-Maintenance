# Evidence — stream processing (PLAN §6.3 session 4)

Raw material for the solution document's stream-processing section (session 10).

## Screenshots

| File | Shows |
|---|---|
| `flink-job-graph.png` | Flink UI job graph of `fleetpulse-telemetry-pipeline`: one shared Kafka source fanning out (HASH) to the exact-dedup branch (→ Timescale `telemetry_fast`/`telemetry_health` JDBC sinks + the lake's `StreamingFileWriter` → `PartitionCommitter`), the cooling rule's two-phase HOP window (`LocalWindowAggregate` → `GlobalWindowAggregate`), and the misfire `MATCH_RECOGNIZE` (`Match`), all converging on `alerts_sink`; the stateless rules (lubrication, battery, MIL, brakes) forward straight to it. Taken while idle, hence 0% busy. |
| `flink-job-running.png` | *(to add)* Same job under `make simulate RATE=2000` traffic: RUNNING, records flowing, checkpoints completing. |

## Measured results (2026-09-28, local laptop stack, parallelism 1)

- **Throughput landed in Timescale:** two back-to-back 45 s `make simulate RATE=2000` runs → 82,041 and 89,426 `telemetry_fast` rows (~1,800–2,000 rows/s end to end, simulator → MQTT → gateway → Kafka → Flink → Timescale).
- **HEALTH path:** 3,497 `telemetry_health` rows from a 90 s run, arrays (`tire_kpa`, `brake_pad_pct`, `active_dtc`) stored as native Postgres arrays.
- **Checkpointing:** every 30 s to `s3://fleetpulse-lake/checkpoints` (Garage); 5/5 completed, 0 failed in the first run.
- **Lake:** day-partitioned JSON part files + `_SUCCESS` markers under `s3://fleetpulse-lake/telemetry/dt=YYYY-MM-DD/`, committed on checkpoint.
- **Real-time alerts, organically from simulated wear (no injection):** 90 `brake_wear` rows in Postgres `alert` via Flink → `alerts` topic → state-writer, tenant-scoped under RLS (plus a `lubrication` alert from one synthetic low-oil-pressure FAST message, used to test that rule deterministically); 2,000 Mongo twins (one per active vehicle) + Redis latest-state.

## Failure modes found and fixed during verification (useful for the ADRs / lessons-learned)

Each of these killed or silently stalled the job at least once — see `docs/PROGRESS.md` session 4 for detail.

1. `ts` typed `TIMESTAMP(3)` couldn't parse the envelope's 'Z'-suffixed timestamps → null rowtime → window/CEP crash. Fix: `TIMESTAMP_LTZ(3)`.
2. JDBC connector supports neither `TIMESTAMP_LTZ` nor `ARRAY` for Postgres → cast to `TIMESTAMP(3)`; arrays sent as Postgres array literals with `stringtype=unspecified`.
3. Event-time dedup compiles to a changelog stream (needs sink PKs, loses rowtime) → proc-time dedup for sinks; rules read the raw stream.
4. Without checkpointing, the file sink never commits (files stuck as S3 multipart uploads) and any single bad record fails the job permanently.
5. Hadoop S3A + Garage: bulk-deleting directory markers returns NoSuchKey → infinite retry, job stuck INITIALIZING. Fix: `fs.s3a.directory.marker.retention: keep`.
6. Simulator restarted `seq` at 0 every run → ~40% of repeat-run traffic (352,358 of 896,505) dropped as duplicates by the gateway. Fix: per-run millisecond `seq` base.
