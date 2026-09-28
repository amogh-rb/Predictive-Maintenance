# PROGRESS

One entry per session. Newest first. 3-5 lines: what got built, what's next, any blockers.
Read this (not chat history) at the start of every new session.

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
