# FleetPulse: Predictive Maintenance POC (Motorq Hackathon, solo build)

## Status checklist
Tick a row when its "Done when" condition is met. This is the source of truth for where the build stands — update it at the end of every session, alongside a note in `PROGRESS.md`.

| # | Session | Status | Done when |
|---|---|---|---|
| 0 | Manual prep | [x] | Docker running, repo URL ready |
| 1 | Repo skeleton, CLAUDE.md, PLAN/PROGRESS, core docker-compose, Makefile, .env.example, CI stub | [x] | All infra healthy; first commit pushed |
| 2 | fleetcore + simulator + ingest-gateway | [x] | Validated events in Kafka `telemetry`; throughput number known (937 events/s end-to-end at RATE=1000, see PROGRESS) |
| 3 | Postgres 3NF + Timescale + seed | [x] | 100K vehicles in PG |
| 4 | Flink SQL jobs + state-writer | [x] | Alerts in PG within seconds |
| 5 | Backfill + Spark features + sklearn model | [x] | Risk scores + `docs/evidence/ml/report.md` |
| 6 | FastAPI + Keycloak + RBAC/RLS + WebSocket | [x] | Secured API passes tests |
| 7 | React UI (4 screens + audit) | [ ] | Full journey in the browser |
| 8 | Copilot (LangGraph + MCP) + OTel/Prometheus/Grafana | [ ] | Copilot answers; Grafana shows throughput/lag/latency |
| 9 | Integration/contract/BDD/CI security; Helm; Terraform; SQL EXPLAIN | [ ] | Evidence folder complete |
| 10 | Solution document, ADRs, diagrams, README | [ ] | Doc ready |

---

## Context
This is a solo entry for the Talenciaglobal/SRM "Connected Vehicle Intelligence" hackathon, due **Thu 1 Oct 2026, 20:00**. Laptop: 16 cores, 16 GB RAM, 66 GB free disk. Docker Desktop is installed. Also available: Python 3.13, Node 22, git and the Claude API.

**Problem:** predictive maintenance for truck fleets: *"Which trucks will break down in the next 7 days, why, and what should I do?"* The primary user is the fleet manager. Secondary stakeholders are technicians, drivers and fleet finance.

**Decisions made with the user:**
- Keep the 8-failure list and the signal design below.
- No Scania real-data validation for now; it is parked.
- **Single ingestion path:** every truck publishes over MQTT → Mosquitto → ingest-gateway → Kafka. There is no direct OEM-cloud-to-Kafka path; an OEM-cloud connector is listed as a future enhancement.
- **One universal message format** for every truck, with no per-OEM formats and no schema versioning for now. Versioning can be added later if needed. The **normalizer service is removed**: the gateway validates and writes straight to the `telemetry` topic.
- **Use the reference architecture from the problem statement** (MQTT, Kafka, Flink/Spark, Postgres/Timescale, a NoSQL store, Redis, pgvector, OpenTelemetry, LangGraph/MCP, Prometheus/Grafana, K8s/Helm/Terraform), built as a POC. The laptop can't run everything at full scale at once, so compose profiles split the stack. Full-rate throughput is proven per component and extrapolated, and the numbers achieved are reported honestly.

---

## 1. Failures detected, and the data that detects them

Each failure is detected on two timescales: **predictive** (the ML model forecasts a failure within 7 days from multi-day trends) and **real-time** (a streaming rule raises a critical alert in under 5 s).

| # | Failure | Signals used | Early-warning pattern (predictive) | Real-time rule | DTCs |
|---|---|---|---|---|---|
| 1 | Cooling (pump/thermostat/leak) | coolant_c, ambient_c, load_pct, rpm, speed | coolant temperature relative to load and ambient creeps up over days; slower cool-down | coolant > 110 °C for ≥30 s | P0128, P0217 |
| 2 | Lubrication | oil_kpa, oil_c, rpm | oil pressure at the same rpm band falls | oil pressure < min while running | P0520–P0524 |
| 3 | 12V battery / starter / alternator | batt_12v_rest_v, crank_min_v, charge_v | cranking dip deepens daily; overnight drain | charge_v < 12.5 V while driving | P0562, P0615 |
| 4 | Ignition misfire | dtc events, rpm, fuel_rate_lph | misfire codes recur with rising frequency; fuel per km rises | flashing MIL | P0300–P0308 |
| 5 | Brake wear | brake_pad_pct per axle, harsh-brake events, route type | wear rate × driving style projects the date pads hit the minimum | pads < legal min | C-codes |
| 6 | Tyre slow leak | tire_kpa[], tire_c[] | one tyre drifts away from its siblings (weather cancels out) | fast pressure drop or temp spike | C0750-series |
| 7 | Transmission | trans_c, gear, rpm vs speed | fluid temperature creeps; slip (rpm rises while speed doesn't) | trans fluid overheat | P0700, P0730 |
| 8 | EV HV battery (e-vans) | cell_v_delta_mv, cell_temp_max/min, soh_pct, soc, hv_v/a | cell imbalance widens; one cell runs hotter; range per full charge shrinks | cell over-temperature | P0A80, P0AFA |

**Build order:** failures 1–5 are Must; 6–8 are Should.

### Message types (average event under the brief's ~1 KB)
| Type | Rate | ~Size | Content |
|---|---|---|---|
| FAST | 1 Hz with ignition on; every 5 min parked | 350 B | lat, lon, heading, gps_hdop, speed_kmh, odo_km, accel_long_g, accel_lat_g, rpm, load_pct, throttle_pct, coolant_c, oil_c, oil_kpa, trans_c, gear, fuel_pct, fuel_rate_lph (ICE) / soc_pct, hv_v, hv_a (EV), ambient_c |
| HEALTH | 60 s, plus at ignition on/off | 600 B | tire_kpa[], tire_c[], brake_pad_pct[], batt_12v_rest_v, crank_min_v, charge_v, cell_v_delta_mv, cell_temp_max/min_c, soh_pct, engine_hours, idle_s, mil_on, active_dtc[] |
| EVENT | when it happens | 250 B | DTC_SET/CLEARED (+ freeze frame), HARSH_BRAKE/ACCEL/CORNER, IGNITION_ON/OFF, CHARGE_START/END, OVERSPEED |

**Envelope on every message:** vin, msg_type, seq, ts, fw_version, schema_ver, driver_token (pseudonymous; PII lives only in Postgres).

**Not sent:** raw CAN, video, driver PII. This is the edge-filtering and privacy argument.

### Format
One universal JSON format for all trucks: flat, metric units, ISO-8601 UTC timestamps, defined once as a JSON Schema / Avro schema in `libs/fleetcore/schemas`. Vehicle make and model live in Postgres, not in the message.

**Fleet mix:** 70% diesel, 20% EV vans, 10% hybrid; depots in 5 cities. About 3–5% of vehicles have a planted failure per 30 days, each with a hidden failure date that is used only for labels.

---

## 2. Architecture (reference stack from the problem statement)

```
 TRUCKS (simulator; one universal format; single ingestion path)
   MQTT 5 + mTLS, topic fleet/{tenant}/{vin}/telemetry, QoS 1
          |
   [Mosquitto x2-3, sharded by VIN hash] --> [ingest-gateway (Py) xN, MQTT 5 shared subscription]
                   cert↔VIN check, schema + VIN + DTC        |
                   validation, batching, back-pressure, DLQ  v
                                                   [Apache Kafka, KRaft (1 broker dev / 3 chaos)]
                                                  + Apicurio Schema Registry (Avro)
                                                  topics: telemetry (key=VIN), alerts, dlq, predictions
                                                             |
                                             +---------------+-------------------------------+
                                             v                                               v
                                 [Apache Flink (Flink SQL jobs)]                     [state-writer (Py)]
                                                  dedup (keyed state + TTL),          latest state -> Redis
                                                  HOP/TUMBLE windows,                 vehicle twin doc ->
                                                  MATCH_RECOGNIZE CEP -> alerts,      MongoDB; raw payload
                                                  JDBC sink -> TimescaleDB,           archive -> MongoDB (TTL)
                                                  Parquet/Iceberg sink -> MinIO (S3)
                                                             |
   [Apache Spark batch (PySpark)] on Iceberg/MinIO + Timescale -> daily features -> scikit-learn model
                                                             -> predictions -> Postgres + pgvector
   [api: FastAPI + SQLModel] REST + WebSocket, OAuth2/OIDC via Keycloak, RBAC + RLS, keyset, Redis rate limit
   [copilot: LangGraph + Claude + MCP server of fleet tools] guardrails, approval queue, audit
   [web: React + Vite + TS]
   Observability: OpenTelemetry -> OTel Collector -> Prometheus + Grafana (ELK dropped for Pro budget, see 6.2)
   Secrets: .env / Docker secrets locally; AWS Secrets Manager + KMS in k8s (Vault dropped, see 6.2)
```

### Data stores
| Store | Holds | CAP | Why |
|---|---|---|---|
| **PostgreSQL 16** (+ pgvector) | 3NF core: tenant, fleet, depot, vehicle, vehicle_model, driver, subscription, user/role, alert, work_order, prediction, audit_log; vectors for the DTC knowledge base and failure signatures | CP | ACID for ownership, billing and audit; RLS for tenant isolation |
| **TimescaleDB** (a separate instance) | Telemetry hypertable, partitioned by time and space-partitioned by VIN hash; continuous aggregates for daily features; compression and retention | leans AP (async replica) | Isolates the telemetry write/scan workload from the OLTP core, which is the brief's §4.1 "mixed workloads" point |
| **MongoDB** | Vehicle digital-twin documents (current health, open DTCs, component wear, recent events; nested shape differs for ICE/EV/hybrid and 4- or 6-tyre trucks); raw message archive (TTL 7 d, for replay/audit) | AP-leaning (tunable write concern) | Document shape varies by vehicle type and grows over time, with no migrations; the NoSQL document store |
| **Redis** | Latest state, rate-limit buckets, pub/sub for WebSocket fan-out, cache | AP | Sub-millisecond reads for live views |
| **MinIO (S3) + Iceberg/Parquet** | Warm/cold telemetry lake used by Spark batch jobs | – | Cheap, cloud-agnostic object storage; the "billions of rows" tier |

**Lifecycle:** hot data (Timescale, 7 d raw) → warm (Timescale compressed and aggregated, 90 d; Iceberg) → cold (Parquet on S3 lifecycle to Glacier-class storage). The solution document includes a cost estimate at 8.6 TB/day.

**Disk budget:** with 66 GB free, the backfilled history is capped at about 300M rows, spread across Timescale (compressed) and Iceberg. Billion-row behaviour is shown by extrapolation plus a Spark benchmark on generated Parquet.

### Stream processing responsibilities
- **ingest-gateway (Python):** checks the certificate against the VIN, then validates schema, VIN check digit and DTC regex. Batches valid messages to `telemetry`; invalid ones go to the DLQ. Stateless and horizontally scaled via MQTT 5 shared subscriptions; back-pressure by slowing MQTT reads when Kafka is slow.
- **Flink SQL:**
  - dedup using `ROW_NUMBER() OVER (PARTITION BY vin, seq)` with state TTL;
  - real-time rules (windowed aggregates, plus MATCH_RECOGNIZE for patterns such as a repeated misfire DTC);
  - sinks to TimescaleDB (JDBC), the alerts topic and Iceberg on MinIO;
  - checkpointing to MinIO, giving exactly-once from Kafka through Flink state to Kafka.
- **Spark batch:** nightly feature engineering over history (7/14-day slopes, operating-condition-normalised signals, DTC recurrence, tyre sibling deltas) → training/scoring.

### ML
- **Model:** scikit-learn HistGradientBoostingClassifier.
- **Label:** planted failure within 7 days.
- **Split:** time-based, with ground truth kept out of feature tables to prevent leakage.
- **Baseline:** "active DTC or threshold breach".
- **Metrics:** PR-AUC, precision@100, recall at ≥5 days' lead, and ₹ saved (cost of breakdown vs inspection).
- **Explanations:** per-vehicle feature contributions via permutation importance or SHAP.
- **Vectors:** failure signatures stored in pgvector for "similar past failures".

### Agentic AI
LangGraph agent using Claude (model configurable; load the `claude-api` skill before building). It calls tools through an **MCP server**:
- `get_fleet_risk`, `get_vehicle_health`, `list_alerts`, `search_dtc_kb` (pgvector RAG), `find_nearest_depot` (Dijkstra) — all read-only;
- `propose_work_order` — goes to a human approval queue.

Guardrails:
- The tenant and role come from the JWT and are injected server-side.
- There is no raw SQL.
- Tool output is treated as data.
- Iterations and tokens are capped.
- Everything is written to the audit log.

### API and security
- **API:** FastAPI + SQLModel, `/v1`, keyset pagination, RFC 7807 errors, Redis token-bucket rate limit, OpenAPI.
- **Auth:** **Keycloak** OIDC (realm export committed), JWT validation via JWKS.
- **Roles:** fleet_admin, fleet_manager, technician, auditor; Postgres RLS on tenant_id.
- **Privacy:** location masking (geohash truncation) by role; audit middleware; erasure endpoint (pseudonymise driver PII in PG, delete that driver's rows in Timescale, Mongo and Iceberg).
- **Transport and secrets:** mTLS on Mosquitto (a dev CA generated by script); TLS via a Caddy/nginx ingress; pgcrypto AES-256 for PII columns; secrets in .env locally and AWS Secrets Manager in k8s.

### Algorithms (`libs/fleetcore/algorithms`, each with complexity analysis and a benchmark)
VIN ISO 3779 check digit, DTC regex parsing, Bloom filter (a pre-filter in the ingest-gateway), Count-Min Sketch plus heap top-K DTCs, geohash, monotonic-deque sliding windows, Dijkstra/A* to the nearest depot with a free slot, and trip/stop segmentation (state machine plus DP smoothing).

### SQL optimisation (EXPLAIN ANALYZE before and after)
1. The at-risk list: OFFSET plus N+1 lookups, replaced by keyset pagination with a composite index and a join.
2. Open alerts per fleet: replaced by a partial index.
3. The fleet daily summary: replaced by a materialised view / Timescale continuous aggregate.

---

## 3. Running it on this laptop
- **Prerequisite:** create `%USERPROFILE%\.wslconfig` with `memory=13GB`, `processors=12`, `swap=8GB`. Start Docker Desktop.
- **Compose profiles** (so not everything runs at once):
  - `core`: mosquitto, kafka, schema-registry, ingest-gateway, flink-jm/tm, postgres, timescaledb, redis, mongodb, minio, api, web, keycloak — about 8 GB;
  - `ai`: copilot + MCP server;
  - `batch`: spark (run on demand);
  - `obs`: otel-collector, prometheus, grafana — about 1 GB;
  - `chaos`: 3-broker Kafka.
- JVM heaps are tuned small (Kafka 512 MB, Flink TM 1 GB, Keycloak 512 MB).
- **Throughput:** the local demo runs at 10–25K events/s end to end. A dedicated ingest benchmark (simulator → sharded Mosquitto → gateway copies → Kafka, with other services stopped) pushes toward 100K/s. If Mosquitto's single thread is the bottleneck, add shards or swap in EMQX, and record that decision in the ADR. A 3x burst test measures lag and zero loss. Horizontal-scaling numbers per component support the extrapolation to 100K/s on k8s. The document states all of this honestly.

## 4. Repo layout
```
/services/{simulator,ingest-gateway,state-writer,api,copilot,mcp-server,ml}
/stream/flink/sql            /batch/spark
/libs/fleetcore              (domain + algorithms + schemas: avro/, proto/)
/web
/db/{postgres,timescale}/migrations
/infra/{compose,helm/fleetpulse,terraform/aws,k8s-local,keycloak,certs}
/tests/{integration,contract,bdd,load,chaos,security}
/docs/{adr,diagrams,solution,evidence}   .github/workflows
docker-compose.yml  Makefile  .env.example  README.md
```
Each service uses hexagonal internals: api → app → domain ← infra. Layer boundaries are enforced with import-linter.

## 5. Testing, DevOps
| Suite | Tooling |
|---|---|
| Unit (≥80% on fleetcore/ingest-gateway/api) | pytest + coverage, vitest |
| Integration | Testcontainers (Kafka, Postgres, Timescale, Redis, Mongo) |
| Contract | Pact: web→api (HTTP), ingest-gateway→Flink telemetry schema (message pact) |
| BDD | behave: critical alert < 5 s, duplicate doesn't double-alert, tenant isolation, erasure, copilot proposal needs approval |
| Load / soak | simulator as load generator + k6 (API p95/p99) + consumer-lag metrics; 1 h soak overnight Wed |
| Security | Semgrep, Trivy (fs + images), pip-audit/npm audit, OWASP ZAP baseline |
| Chaos / compliance | kill a Kafka broker (3-broker profile), an ingest-gateway copy and a Flink TM mid-load, then reconcile by `seq` for zero loss; audit and erasure tests |

- **CI** (GitHub Actions): lint → unit/coverage → images → integration/contract/BDD → Semgrep/Trivy/ZAP; artefacts are uploaded. Heavy load and chaos tests run locally and their evidence is committed.
- **Deploy:**
  - Helm chart (HPA, PDB, probes, NetworkPolicy) verified on **kind**, using Strimzi (Kafka), the Flink operator and bitnami charts for the stores.
  - Terraform for AWS (VPC, EKS, MSK, RDS, S3, KMS, Secrets Manager); `validate` and `plan` are the evidence unless cloud credit appears.
  - `values-gcp.yaml` / `values-azure.yaml` show the second cloud without code changes.

## 6. Build plan under Claude Pro usage limits

### 6.1 How Pro limits shape the work
Pro usage resets on a rolling window of about 5 hours from your first message, and there is also a **weekly cap**. Every message resends the whole conversation, so long chats and big file or log dumps burn usage fastest. Opus uses the allowance several times faster than Sonnet. Check `/usage` at the start of each session. Treat the numbers below as estimates and adjust after the first session.

**Budget assumption:** about 3 Claude windows a day, each good for one focused build session. Monday has about 2 left, Tuesday and Wednesday 3 each, Thursday 2 (up to 16:00). That makes **about 10 sessions**. The weekly cap may bite first, so the hardest code goes early and the repo is **always runnable** at the end of every session. If usage runs out, what exists still demos.

**Rules for every session:**
1. **Start fresh.** Open a new chat, not this one; it is already very long. Run `/model sonnet`, and switch to Opus only to untangle a hard bug.
2. **Context comes from files, not chat.** `CLAUDE.md` (project rules, stack, commands) and `docs/PLAN.md` (this plan with a status checklist) are loaded automatically. At the end of each session, tick the checklist and add a 3–5 line note to `docs/PROGRESS.md`. The next session reads that, not history.
3. **One slice per session**, asked for in one precise message, for example: "Session 4: build the Flink SQL jobs per PLAN §2; tests; update PROGRESS." Avoid many small back-and-forths.
4. **Keep output small.**
   - Tests run with `-q`, logs go through `tail -50` or `grep ERROR`, and huge JSON is never printed.
   - Claude writes whole files at once and does not re-read them.
   - No subagents: each starts cold and re-reads everything.
5. **`/compact`** if a session runs long; **`/clear`** between slices.
6. **You do the token-free work:**
   - installs and `docker compose pull`;
   - GitHub repo and secrets;
   - running long benchmarks, soak and chaos tests, and pasting back only their summary lines;
   - screenshots, the video, and exporting the PDF.
7. **When a limit hits mid-session,** commit what works, write PROGRESS.md, and use the wait for manual tasks (listed per session below).

### 6.2 Scope trimmed for Pro (all still satisfy the brief's "pick any" tool lists)
| Keep | Trimmed / dropped | Why this is OK |
|---|---|---|
| OTel + Prometheus + Grafana (metrics, logs via Grafana dashboards) | Elasticsearch + Kibana dropped | The brief lists "Splunk **or** ELK, OpenTelemetry, Prometheus + Grafana" as examples; this saves config work and about 2 GB of RAM |
| Docker secrets / .env with a documented Vault/Secrets Manager path in k8s | Vault container dropped | Documented in Security §8 and set up in Terraform (AWS Secrets Manager) |
| Failures 1–5 | Failures 6–8 become Could | Depth over breadth |
| One Pact HTTP contract (web→api) + JSON-Schema contract test for the `telemetry` message | Pact message contract dropped | Covers the "contract tests between services" row |
| Iceberg → **plain Parquet** on MinIO | Iceberg dropped | Parquet is listed; Iceberg adds catalogue setup |
| One generic Helm chart reused per service via values | Per-service charts | Cheap to generate |
| Terraform using community AWS modules (vpc, eks, rds, msk, s3) | Hand-written modules | Short files; `plan` output as evidence |
| React UI: 4 screens (at-risk list, vehicle detail, live alerts, copilot) + a small audit view | Extra admin screens | Covers the main user journey |

### 6.3 Session schedule
The "You" column is manual work done between sessions, often while the limit resets.

| # | When | Claude builds (one slice) | You (no tokens) | Done when |
|---|---|---|---|---|
| **0** | Mon, now | *Nothing more in this chat.* | Create `.wslconfig` (memory=13GB, processors=12, swap=8GB), `wsl --shutdown`, start Docker. Create the empty GitHub repo. Run `/usage`. | Docker running, repo URL ready |
| **1** | Mon | Repo skeleton, `CLAUDE.md`, `docs/PLAN.md` + PROGRESS.md, `docker-compose.yml` (core infra: Mosquitto with mTLS certs script, Kafka KRaft + schema registry, Postgres+pgvector, TimescaleDB, Redis, MongoDB, MinIO), Makefile, `.env.example`, CI stub | `docker compose pull`, `make up`, paste back only the `docker compose ps` result | All infra healthy; first commit pushed |
| **2** | Mon | `fleetcore` (universal schema, VIN check digit, DTC regex, Bloom filter) + tests; simulator (100K trucks, failures 1–5, noise/duplicates/out-of-order/bursts, MQTT); ingest-gateway (cert↔VIN, validation, batching, back-pressure, DLQ) + tests | Run `make bench-ingest` for 5 min and paste the summary line (events/s) | Validated events in Kafka `telemetry`; throughput number known |
| **3** | Tue AM | Postgres 3NF migrations + RLS; Timescale hypertable + continuous aggregate; seed 100K vehicles/drivers/depots; ER diagram (Mermaid) | Run the seed, spot-check counts | 100K vehicles in PG |
| **4** | Tue PM | Flink SQL jobs (dedup, windowed rules for failures 1–5, CEP misfire pattern, sinks to Timescale/Parquet/alerts) + state-writer (Redis, PG alerts, Mongo twin) | Run the stream for 10 min; screenshot the Flink UI | Alerts in PG within seconds |
| **5** | Tue eve | History backfill script; Spark feature job; sklearn model vs baseline with metrics report; scoring to PG; pgvector DTC KB + failure signatures | Run the backfill overnight | Risk scores + `docs/evidence/ml/report.md` |
| **6** | Wed AM | FastAPI: Keycloak realm export, JWT/RBAC, RLS session tenant, keyset pagination, Redis rate limit, masking, audit, erasure, WebSocket alerts, Dijkstra depot booking + tests | Click through Keycloak login once | Secured API passes tests |
| **7** | Wed PM | React UI (4 screens + audit view) | Use the app; note visual bugs in one list for the next session | Full journey in the browser |
| **8** | Wed eve | Copilot (LangGraph + MCP server + Claude, approval queue, audit, stub fallback); OTel + Prometheus + Grafana dashboards | Add `ANTHROPIC_API_KEY` locally; start the 1 h soak test overnight | Copilot answers; Grafana shows throughput/lag/latency |
| **9** | Thu AM | Integration (Testcontainers), Pact, behave BDD, CI with Semgrep/Trivy/ZAP; Helm chart + kind; Terraform; EXPLAIN before/after for 3 queries; UI fixes from your list | Run burst + chaos scripts and k6; save outputs to `docs/evidence/`; verify CI is green | Evidence folder complete |
| **10** | Thu PM (by 16:00) | Solution Document drafted from PLAN/PROGRESS/evidence; 5 ADRs; STRIDE; C4 and sequence diagrams (Mermaid); README | Add screenshots and video timestamps, proofread, export PDF | Doc ready |
| — | Thu 16:00–19:45 | *(buffer; only small fixes)* | Record and upload the video; tag `v1.0-submission`; submit | Submitted |

### 6.4 If usage runs out early
- **Behind by 1 session:** fold session 8's observability into session 9, and keep the copilot minimal (3 read-only tools + approval).
- **Behind by 2:** move Helm/Terraform to "Planned" in the doc with the chart skeleton only; the UI becomes 3 screens.
- **Weekly cap hit:** you finish from the repo using PROGRESS.md. The doc gets written by you from the evidence folder; the template sections map one-to-one to PLAN sections.

**Never cut:** simulator at 100K, MQTT → gateway → Kafka, Flink alerts, Spark + ML vs baseline, the polyglot stores, the secure API + UI, the copilot with audit, tests in CI, doc + video.

## 7. ADRs
0. (Could become ADR 6) MQTT + custom ingest-gateway over devices writing straight to Kafka, or a broker's built-in Kafka bridge: protects Kafka from device traffic, gives a per-device identity check, and makes validation and back-pressure testable code.
1. Kafka (KRaft) over RabbitMQ: replay, partitioned per-VIN ordering, ecosystem.
2. Polyglot storage: PG core (CP) + Timescale telemetry (separate instance) + Mongo twin/raw + Redis + pgvector + S3 lake.
3. Delivery semantics: exactly-once inside Flink (checkpoints + transactional sink); at-least-once plus idempotent keys at the edges. This is the CAP/PACELC entry.
4. Flink for real time, Spark for batch, over a single engine: latency vs throughput fit.
5. Human-in-the-loop agent over MCP tools: no SQL, tenant injected server-side.

## Verification
1. `docker compose --profile core up -d && make seed && make simulate RATE=20000` → Grafana shows ingest, consumer lag and Flink throughput, and Timescale rows grow.
2. `make bench-ingest` (100K/s target) and `make burst` (3x for 5 min) → lag recovers, and the `seq` reconciliation reports 0 lost.
3. `make inject-fault VIN=… TYPE=overheat` → the alert appears in the UI in under 5 s (traced).
4. `make batch && make train` → report of model vs baseline in `docs/evidence/ml/`.
5. Tenant-A manager can't read tenant-B data; a technician sees masked locations.
6. Copilot question → MCP tool calls, proposed work order waits for approval, audit rows written.
7. `make test` → ≥80% coverage; CI green with security artefacts.
8. `make chaos` → kill a broker/gateway copy/TM mid-load, then it recovers with zero loss.
9. `helm install` on kind → pods healthy; `terraform plan` succeeds.

## Open items for the user
- A GitHub repo URL (needed for CI) and `ANTHROPIC_API_KEY`.
- Team name for the cover page.
- Allow me to create `.wslconfig` (this restarts WSL and Docker).
