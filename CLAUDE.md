# FleetPulse — CLAUDE.md

Predictive maintenance POC for truck fleets. Solo hackathon build under Claude Pro usage limits.
Full context lives in `docs/PLAN.md` (the plan) and `docs/PROGRESS.md` (session-by-session status).
**Read both before starting work in a new session.** Do not rely on prior chat history — it will not be there.

## Session discipline
- One slice per session, matching a row in `docs/PLAN.md` §6.3 "Session schedule". Don't jump ahead.
- Keep output small: run tests with `-q`, pipe logs through `tail -50` / `grep ERROR`, never print huge JSON blobs.
- Write whole files at once; don't re-read files you just wrote.
- No subagents for build sessions — each one starts cold and re-reads everything, burning usage for nothing.
- At the end of a session: tick the relevant checklist row in `docs/PLAN.md`/PROGRESS, and append a 3-5 line note to `docs/PROGRESS.md` (what got built, what's next, any blockers). Then stop — don't keep chatting.

## Stack
- **Ingest:** MQTT 5 (Mosquitto, mTLS) → ingest-gateway (Python) → Kafka (KRaft) + Apicurio Schema Registry (Avro).
- **Stream:** Apache Flink SQL (dedup, windowed rules, MATCH_RECOGNIZE CEP) + a Python state-writer (Redis, Mongo twin).
- **Batch/ML:** PySpark feature jobs on Parquet/MinIO; scikit-learn HistGradientBoostingClassifier; pgvector for failure signatures / DTC KB.
- **Stores:** PostgreSQL 16 + pgvector (3NF core, RLS), TimescaleDB (separate instance, telemetry), MongoDB (twin docs + raw archive), Redis (latest state, rate limits, pub/sub), MinIO + Parquet (lake).
- **API:** FastAPI + SQLModel, Keycloak OIDC, RBAC + RLS, keyset pagination, Redis rate limiting, WebSocket alerts.
- **Copilot:** LangGraph + Claude + an MCP server of read-only fleet tools, plus a human-approval queue for work orders.
- **Web:** React + Vite + TS.
- **Observability:** OpenTelemetry → OTel Collector → Prometheus + Grafana.

Full architecture diagram and rationale: `docs/PLAN.md` §2. Trimmed-scope decisions: `docs/PLAN.md` §6.2.

## Repo layout
See `docs/PLAN.md` §4. Each service is hexagonal: `api → app → domain ← infra`, boundaries enforced with import-linter (Python) / equivalent lint rule (TS).

## Commands (Makefile)
- `make up` / `make down` — start/stop the `core` compose profile.
- `make seed` — seed 100K vehicles/drivers/depots into Postgres.
- `make simulate RATE=<events/s>` — run the truck simulator against MQTT.
- `make bench-ingest` — dedicated ingest throughput benchmark.
- `make burst` — 3x burst load test.
- `make batch` / `make train` — Spark feature job / sklearn training.
- `make test` — full test suite (unit + integration + contract + BDD).
- `make chaos` — kill a broker / gateway copy / Flink TM mid-load, verify zero-loss recovery via `seq`.

Compose profiles (`core`, `ai`, `batch`, `obs`, `chaos`) are defined in `docker-compose.yml`; see `docs/PLAN.md` §3.

## Conventions
- One universal JSON/Avro message format for every vehicle (no per-OEM formats, no schema versioning yet); schema lives in `libs/fleetcore/schemas`.
- Never invent a second ingestion path — every truck goes MQTT → Mosquitto → ingest-gateway → Kafka.
- Tenant/role always comes from the JWT server-side; the copilot never emits raw SQL.
- Don't add scope beyond the current session's slice in `docs/PLAN.md` §6.3 — trimmed items are listed in §6.2 and §6.4 and are intentional, not oversights.
