# Evidence — stream processing (PLAN §6.3 session 4)

Raw material for the solution document's stream-processing section (session 10).

## Screenshots

| File | Shows |
|---|---|
| `flink-job-graph.png` | Flink UI job graph of `fleetpulse-telemetry-pipeline`: one shared Kafka source fanning out (HASH) to the exact-dedup branch (→ Timescale `telemetry_fast`/`telemetry_health` JDBC sinks + the lake's `StreamingFileWriter` → `PartitionCommitter`), the cooling rule's two-phase HOP window (`LocalWindowAggregate` → `GlobalWindowAggregate`), and the misfire `MATCH_RECOGNIZE` (`Match`), all converging on `alerts_sink`; the stateless rules (lubrication, battery, MIL, brakes) forward straight to it. Taken while idle, hence 0% busy. |
| `flink-job-running.png` | Same job under `make simulate RATE=2000` traffic, ~11 minutes in: RUNNING, 1,627+ records sent, sub-tasks all RUNNING. Also shows the Source box at **100% backpressured (max)** — this was the OOM in `flink-job-oom-restarting.png` about to happen (the TaskManager's 1 GB heap couldn't keep up and back-pressure was the visible symptom seconds before the crash), not a healthy steady state; see the note below. |
| `flink-job-oom-restarting.png` | The job a few minutes later: `RESTARTING` (Flink's checkpoint-enabled default restart strategy trying to recover), the `Source` task in `FAILED`, everything else `CANCELED`. Kept as the record of the bug, not as "correct" evidence — see below. |

## Measured results (2026-09-28, local laptop stack, parallelism 1)

**Final, sustained 10-minute `make simulate RATE=2000` run** (after the memory fix below — this is the number that matters):
- 1,500,228 `telemetry_fast` rows, 25,724 `telemetry_health` rows (~2,500 rows/s combined, end to end: simulator → MQTT → gateway → Kafka → Flink → Timescale).
- 440 organic `brake_wear` alerts in Postgres `alert`, from simulated wear with **no fault injection** — the rule finding real degrading vehicles in a random 2,000-vehicle-active fleet.
- 19/19 checkpoints completed, 0 failed, 0 restored (first run since submission).
- 1.1 GB / 30 objects committed to the lake (`s3://fleetpulse-lake/telemetry/dt=2026-09-28/`).
- TaskManager stayed up the entire 10 minutes — no crash, no restart.

Earlier, smaller runs (45–90 s) used to sanity-check individual pieces: 82,041 / 89,426 `telemetry_fast` rows on two back-to-back 45 s runs (confirms the seq-restart fix below — see "Failure modes"); 3,497 `telemetry_health` rows with arrays (`tire_kpa`, `brake_pad_pct`, `active_dtc`) landing as native Postgres arrays on a 90 s run; a `lubrication` alert from one synthetic low-oil-pressure FAST message, used to test that rule deterministically before real wear-based alerts were confirmed.

## Failure modes found and fixed during verification (useful for the ADRs / lessons-learned)

Each of these killed or silently stalled the job at least once — see `docs/PROGRESS.md` session 4 for detail.

1. `ts` typed `TIMESTAMP(3)` couldn't parse the envelope's 'Z'-suffixed timestamps → null rowtime → window/CEP crash. Fix: `TIMESTAMP_LTZ(3)`.
2. JDBC connector supports neither `TIMESTAMP_LTZ` nor `ARRAY` for Postgres → cast to `TIMESTAMP(3)`; arrays sent as Postgres array literals with `stringtype=unspecified`.
3. Event-time dedup compiles to a changelog stream (needs sink PKs, loses rowtime) → proc-time dedup for sinks; rules read the raw stream.
4. Without checkpointing, the file sink never commits (files stuck as S3 multipart uploads) and any single bad record fails the job permanently.
5. Hadoop S3A + Garage: bulk-deleting directory markers returns NoSuchKey → infinite retry, job stuck INITIALIZING. Fix: `fs.s3a.directory.marker.retention: keep`.
6. Simulator restarted `seq` at 0 every run → ~40% of repeat-run traffic (352,358 of 896,505) dropped as duplicates by the gateway. Fix: per-run millisecond `seq` base.
7. **TaskManager OOM'd under sustained traffic** (`flink-job-oom-restarting.png`): 1 GB process size (PLAN §3's original budget) left too little task heap once the cooling rule's HOP window (30 s size / 5 s slide → 6 overlapping windows per key) and the dedup operator's keyed state grew under real load — `flink-job-running.png`'s 100% source backpressure was this happening in real time, moments before the crash. The TaskManager disappearing entirely (`{"taskmanagers":0}`) then stuck the job in `RESTARTING` forever (`NoResourceAvailableException` — no slots to restart into). Fix: `taskmanager.memory.process.size: 2048m`. Verified with a full 10-minute sustained run afterward (numbers above) — TaskManager never dropped.
