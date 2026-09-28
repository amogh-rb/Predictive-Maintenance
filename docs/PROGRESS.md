# PROGRESS

One entry per session. Newest first. 3-5 lines: what got built, what's next, any blockers.
Read this (not chat history) at the start of every new session.

---

## Session 2 — 2026-09-28
Built `fleetcore` (VIN ISO 3779 check digit, DTC regex, Bloom filter, the universal FAST/HEALTH/EVENT pydantic schema + matching Avro file, 51 tests), the simulator (100K-vehicle fleet gen, failures 1-5 with a severity ramp, duplicate/reorder/burst noise injection, MQTT publisher, `make simulate`/`make inject-fault`/`make bench-ingest`, 25 tests), and ingest-gateway (shard-consistency + schema/VIN/DTC validation, Bloom dedup pre-filter, bounded-queue back-pressure, Kafka producer with DLQ routing, 13 tests — 85 total, all green). Verified live end-to-end against the running `core` stack: simulator → Mosquitto (mTLS) → ingest-gateway → Kafka `telemetry` (325 sent, 320 forwarded, 5 noise-duplicates correctly deduped, 0 DLQ), and `inject-fault --type overheat` drove coolant_c from 88°C to 119°C, crossing the 110°C real-time threshold, confirming the failure-ramp mechanism for session 4's alerting.

**Engineering decision (documented, not silent — same spirit as session 1's MinIO→Garage swap):** 100K live per-vehicle mTLS certs isn't a one-session build, so "cert↔VIN check" is implemented at VIN-hash **shard** granularity instead: 32 shard client certs (`infra/certs/issue-shard-certs.py`), one Mosquitto ACL entry per shard restricting it to its own `fleet/{tenant}/shard-N/+/telemetry` topic segment, and the gateway re-derives each message's expected shard from its VIN and rejects mismatches. Same VIN→shard function (`fleetcore.algorithms.sharding`) is shared by simulator and gateway so they never disagree. Also fixed two pre-existing session-1 issues hit along the way: `generate-dev-certs.sh`'s `-subj` args were being mangled by Git Bash's path conversion (fixed with a doubled leading slash, the standard workaround, plus made the script idempotent), and Kafka only advertised `kafka:9092` with no host-reachable listener (added an `EXTERNAL` listener on `29092` so host tools like `bench_ingest.py` can read topic offsets).

**Next:** Session 3 — Postgres 3NF migrations + RLS, Timescale hypertable + continuous aggregate, seed 100K vehicles/drivers/depots, ER diagram.

**Blockers:** none. Also worth a look when convenient: `minio` (Garage) shows `unhealthy` in `docker compose ps` — not touched this session, pre-existing from session 1's swap.

**`make bench-ingest` result (5 min, RATE=1000, the Makefile default):** 311,697 messages attempted (952 events/s — the simulator itself is the bottleneck at this rate, not Mosquitto/Kafka: a single Python process paces to wall-clock ticks and per-tick JSON/paho overhead eats a little headroom), 306,715 delivered end-to-end to Kafka's `telemetry` topic (937 events/s, 98.4% of attempted — the gap is expected duplicate-drop from noise injection plus in-flight messages not yet landed at measurement time, not loss). PLAN §6.3 row 2 is now fully ticked. Higher RATE values (e.g. `make bench-ingest RATE=20000`) haven't been tried yet — worth doing in a later session to find where the local ceiling actually is, per PLAN §3's 10-25K events/s local-demo target.

---

## Session 1 — 2026-09-28
Built the repo skeleton per PLAN §4 (services/, stream/, batch/, libs/fleetcore/, web/, db/, infra/, tests/, docs/), `CLAUDE.md`, `docs/PLAN.md` with a status checklist, this file, `.env.example`, `docker-compose.yml` for the `core`/`ai`/`batch`/`obs`/`chaos` profiles, a `Makefile` with the targets CLAUDE.md documents, and a CI stub workflow (lint job only, rest are TODO markers for session 9). Initialized git, first commit pushed to https://github.com/amogh-rb/Predictive-Maintenance.git.

All 11 `core` containers came up healthy after three fixes, applied by the user directly against the running stack:
- **MinIO → Garage.** MinIO Community Edition was pulled/deprecated from registries between when the compose file was written and when it was run. Swapped for `dxflrs/garage:v1.0.1` (S3-compatible, single-node). `infra/compose/garage.toml` added. I then found and fixed a persistence bug in that config: `metadata_dir` wasn't under the mounted volume, so bucket/key config would be lost on container restart — moved both `metadata_dir` and `data_dir` under `/var/lib/garage/data`. Also corrected `.env.example`: internal (container-to-container) traffic must hit Garage's S3 API on port **3900**, not the host-mapped 9000; Garage credentials are provisioned via `garage key new` / `garage bucket allow`, not env vars like the old MinIO image — bucket + key creation is a **TODO for session 2** (state-writer needs it for the raw archive / lake writes).
- **Keycloak port conflict.** flink-jobmanager already held 8081; Keycloak moved to host port 8082.
- **Healthchecks.** Mosquitto, Apicurio (path changed to `/health/ready`), and Garage healthchecks were fixed to match what each image actually exposes.

Also: `.wslconfig` created, Docker confirmed at 12 CPUs / 13 GB RAM; mTLS dev certs generated (had to run via Anaconda's openssl since Git Bash routing failed).

**Next:** Session 2 — `fleetcore` (universal schema, VIN check digit, DTC regex, Bloom filter) + tests; simulator (100K trucks, failures 1-5, noise/duplicates/out-of-order/bursts, MQTT); ingest-gateway (cert↔VIN, validation, batching, back-pressure, DLQ) + tests. Remember the Garage bucket/key TODO above before anything tries to write to the lake.

**Blockers:** none.
