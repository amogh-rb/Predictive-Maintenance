# Connected Vehicle Intelligence Hackathon: Solution Document

**Submission format:** PDF (export of this document)
**To be submitted by:** [Team name]
**Team members and roles:** [Name, role, email]. Solo build.
**Problem space chosen:** Predictive maintenance for truck fleets
**Repository URL:** https://github.com/amogh-rb/Predictive-Maintenance
**Demo video URL (≤ 5 min):** [Link]
**Date of submission:** 01/10/2026

> Everything is a proof of concept on one laptop (16 cores, 13 GB to Docker) with simulated trucks. Measured numbers point at a file in `docs/evidence/`. Extrapolations are labelled. Items marked [TODO] are manual steps for the author.

---

## 1. Executive Summary
**Problem.** Fleet managers learn a truck is failing when it breaks down. Unplanned downtime hits the fleet manager, technicians, drivers and fleet finance.

**Solution.** FleetPulse ingests telemetry from every truck over one MQTT → Kafka path, raises streaming alerts for 8 failure types within seconds, and uses a per-failure ML model to rank which trucks will fail soon, why, and what to do. A manager can book the nearest depot with one click, or ask an agentic copilot that proposes work orders for human approval.

**Key results (all on simulated data, details in section 7):**
- Backtest: model trained only on data before 2026-09-19. Of 10,765 vehicles scored, 61 scored ≥ 0.5 and all 61 really failed. Top-113 precision 0.63, failure type right for 100% of hits, lead-time error 4.6 days mean absolute.
- Alerts about 1 s end to end for single-reading rules, 6-7 s for 30 s windowed rules. WebSocket push 0.7 s.
- Zero loss through a Flink TaskManager kill (27,408/27,408 messages) and a 3-broker Kafka broker kill (12,000/12,000).
- 100K vehicles seeded; local ingest measured at about 1K events/s (simulator-bound). **The 100K events/s target was not measured.**

**Distinctive work.** Tenant isolation in Postgres RLS with role and tenant taken only from the JWT; an MCP-tool copilot that cannot see or override its own tenant; MATCH_RECOGNIZE for recurring misfire codes; Dijkstra depot routing that skips full depots; location masking by role; an honest as-of backtest rather than a random split.

---

## 2. Problem Statement & Validation
### 2.1 Problem Statement
A fleet manager needs a way to know which trucks will break down in the coming days, and why, because an unplanned breakdown strands a load and costs far more than a planned inspection. The POC models this as ₹150,000 per breakdown vs ₹3,000 per inspection (an assumption, not a measured figure).

- **Primary user:** fleet manager.
- **Secondary:** technicians (work orders and bay slots), drivers (safety), fleet finance (cost), auditors (traceability).

### 2.2 Evidence & Validation
**Validation method: simulation and back-test only.** No interviews or published study were used, so the pain-size claims are assumptions.

| Evidence / Assumption | Source or method | What it shows | Confidence |
|---|---|---|---|
| Failures show multi-day drift in coolant, oil, voltage, pad wear, tyre and cell signals before the fault | Domain assumption, encoded in the simulator's severity ramp | A model can find early warning if real ramps look like the simulated ones | Low (unvalidated on real data) |
| Unplanned breakdown costs about 50x an inspection | Assumed ₹150,000 vs ₹3,000 | Drives the ₹-saved illustration only | Low |
| The model beats threshold alerting on lead time | As-of back-test, section 11 | Baseline (DTC or threshold breach) has about zero lead time by construction | Medium on simulated data |
| Pipeline survives component failure | Chaos tests, section 9 | Zero loss for TaskManager and broker kills | High for those scenarios |

**Existing alternatives** (aftermarket dongles, OEM portals, telematics suites): generally alert on thresholds or fault codes after the fact and are tied to one OEM or device. FleetPulse's angle is a single universal message, a forecast with lead time and failure type, and a ranked action list. We did not benchmark any of these products.

### 2.3 Impact & Success Metrics
| Metric | Baseline today | Target | How measured |
|---|---|---|---|
| Lead time before failure | about 0 days (threshold alert fires at failure) | several days | Backtest: estimate error 4.6 days MAE; horizon ≤ 10 days with this data |
| Precision of high-risk flags | n/a | high | Backtest: 61 of 61 flagged ≥ 0.5 truly failed |
| Recall of failures at top-113 | n/a | high | Top-113 precision 0.63; 113 vehicles truly failed |
| Critical alert latency | n/a | < 5 s | about 1 s single-reading rules; 6-7 s windowed rules |
| ₹ saved on test window | baseline −₹10.9 M | positive | Model +₹7.1 M (illustrative) |

**Scale of impact.** At 10K vehicles the 3-5% planted failure rate gives roughly 300-500 failures per month; at 100K, 3-5K. This is a simulation parameter, not a field statistic. **Wider impact:** safety (fewer roadside failures), cost, and reduced emissions from catching cooling and misfire faults earlier. Not quantified.

---

## 3. Solution Description
### 3.1 Overview & User Journey
**What it does.** Trucks publish telemetry; the platform detects faults in real time, forecasts failures, and gives managers a ranked at-risk list, live alerts, one-click service scheduling, a copilot and analytics.

**Journey.** Vehicle event → MQTT → gateway validation → Kafka → Flink rule fires → alert in Postgres and pushed over WebSocket → manager opens Live Alerts → opens the vehicle in At-Risk with failure type and lead days → **Schedule service** books the nearest depot with a free bay → vehicle moves to Maintenance Scheduled → technician marks it serviced.

**Screenshots:** [TODO: At-Risk, Vehicle Detail, Live Alerts, Maintenance Scheduled, Copilot, Grafana, Metabase]. Existing Flink screenshots: `docs/evidence/stream/*.png`.

### 3.2 Key Value Proposition
- **Customer job:** keep trucks running and plan maintenance before failures.
- **Pain relieved:** no more discovering faults at breakdown; the list is ranked and explained.
- **Gain created:** failure type, lead-time estimate and a booked bay in one flow; natural-language questions over fleet data with human approval for actions.
- **Differentiation:** one universal format (no per-OEM adapters in the POC), tenant-safe by construction, evaluated by backtest. Not yet proven on real vehicle data.

### 3.3 Innovative Ideas
1. **Tenant-blind copilot.** The agent's tool schema has no tenant or role field; the server injects them from the JWT, tools run under row-level security, and writes only create `proposed` records. Evidence: BDD tenant-isolation and work-order approval scenarios; unit tests for the role gate.
2. **As-of backtest.** Train only on what was knowable at a date, score that day, compare with what happened. This exposed that a last-day snapshot scored stale or healthy vehicles, and fixed the at-risk definition. Evidence: `docs/evidence/ml/report.md`.
3. **Routing that falls through full depots.** Dijkstra over a depot mesh finds the nearest depot with a free bay rather than the nearest by distance. Evidence: unit tests and live 201/409 paths.

These are small applied techniques, not novel research.

---

## 4. Feature List
Status: Done / Partial / Planned. Video timestamps: [TODO after recording].

| ID | Feature | Priority | Status | Code path | Video |
|---|---|---|---|---|---|
| F-01 | MQTT 5 + mTLS ingest with per-shard identity, validation, Bloom dedup, DLQ, back-pressure | Must | Done | `services/ingest-gateway/` | [TODO] |
| F-02 | Universal telemetry schema (FAST/HEALTH/EVENT) | Must | Done | `libs/fleetcore/schemas/`, `libs/fleetcore/domain/` | [TODO] |
| F-03 | Fleet simulator: 100K vehicles, failures, noise, bursts | Must | Done | `services/simulator/` | [TODO] |
| F-04 | Real-time rules for 8 failure types + MATCH_RECOGNIZE misfire CEP | Must | Done (windowed rules ~7 s) | `stream/flink/sql/` | [TODO] |
| F-05 | Vehicle twin in Redis and Mongo; alerts to Postgres | Must | Done | `services/state-writer/` | [TODO] |
| F-06 | Spark features + per-type sklearn models vs baseline | Must | Done | `batch/spark/`, `services/ml/` | [TODO] |
| F-07 | Secured API: OIDC, RBAC, RLS, keyset pagination, rate limit, audit | Must | Done | `services/api/` | [TODO] |
| F-08 | At-risk list, vehicle detail, live alerts (WebSocket) | Must | Done | `web/src/pages/` | [TODO] |
| F-09 | One-click Schedule service + Maintenance Scheduled tab | Should | Done | `services/api/.../routers/maintenance.py`, `web/src/pages/MaintenancePage.tsx` | [TODO] |
| F-10 | Copilot: LangGraph + MCP tools + approval + audit | Must | Done | `services/copilot/`, `services/mcp-server/` | [TODO] |
| F-11 | Location masking by role; driver erasure | Should | Done | `services/api/.../vehicles.py`, `routers/drivers.py` | [TODO] |
| F-12 | Grafana/Prometheus/OTel; Metabase analytics tab | Should | Partial (API metrics only; no Kafka lag or Flink throughput exporter) | `infra/compose/`, `routers/analytics.py` | [TODO] |
| F-13 | Helm chart (verified on kind), Terraform (validate only) | Could | Partial | `infra/helm/`, `infra/terraform/` | [TODO] |
| F-14 | UI for copilot approval queue | Should | Planned (API exists) | n/a | n/a |
| F-15 | Per-vehicle certificates, OEM-cloud connector | Won't (POC) | Planned | n/a | n/a |

---

## 5. Solution Architecture (High-Level Design)
### 5.1 Architecture Overview
C4 context and container diagrams, plus the flows, are in [docs/diagrams/c4-and-sequences.md](../diagrams/c4-and-sequences.md) [TODO: paste rendered images into the PDF].

**Data flow of one telemetry event, with measured or designed latency:**
1. Truck → Mosquitto, MQTT 5 QoS 1 over mTLS.
2. Mosquitto → ingest-gateway (shared subscription): validation and Bloom dedup, milliseconds.
3. Gateway → Kafka `telemetry` (key = VIN).
4. Kafka → Flink SQL rule → Kafka `alerts`. About 1 s end to end for single-reading rules; windowed rules fire 6-7 s after the 30 s window (5 s watermark bound).
5. `alerts` → state-writer → Postgres, and → API WebSocket → browser (0.7 s measured push).
6. Kafka → Flink → Timescale and lake; Spark nightly → features → sklearn → `prediction` in Postgres → API/UI.

Protocols: MQTT/mTLS (devices), Kafka (internal), JDBC (Flink to Timescale), HTTPS/REST and WebSocket (UI), SSE (copilot to MCP), OTLP (traces and metrics).

### 5.2 Technology Stack & Justification
| Layer | Choice | Why, and what was rejected |
|---|---|---|
| Ingestion / messaging | MQTT 5 + Mosquitto, custom gateway, Kafka KRaft | MQTT suits flaky cellular devices; gateway gives identity, validation and back-pressure (ADR 1). Kafka over RabbitMQ for replay and per-VIN ordering (ADR 2). Rejected: devices writing straight to Kafka; a broker-native Kafka bridge |
| Stream / batch | Flink SQL; Spark + sklearn | Latency vs throughput fit (ADR 5). Rejected: one engine for both |
| Stores | Postgres 16 + pgvector, TimescaleDB, MongoDB, Redis, S3-compatible lake (Garage) | Each fits its workload (ADR 3). MinIO replaced by Garage because MinIO CE was pulled. Rejected: Iceberg (catalogue cost), Elasticsearch |
| Backend / frontend | FastAPI + SQLModel; React + Vite + TS | Typed, fast to build; hexagonal layout |
| ML / AI | scikit-learn HistGradientBoosting; LangGraph + MCP + Gemini free tier | Small tabular data suits boosted trees. Gemini instead of Claude to avoid a paid key (ADR 6) |
| Infra / CI / observability | Docker Compose profiles, Helm, Terraform, GitHub Actions, OTel + Prometheus + Grafana, Metabase | Compose profiles split the stack to fit a laptop. Rejected: ELK and Vault (budget) |

### 5.3 Data Architecture
- **ER diagram:** [docs/diagrams/er-diagram.md](../diagrams/er-diagram.md). 3NF core; deliberate denormalisation: the `vehicle_latest_risk` materialised view (read speed) and Mongo twin documents.
- **Polyglot map and CAP:**

| Store | Data | CAP leaning |
|---|---|---|
| PostgreSQL + pgvector | tenants, vehicles, drivers, alerts, work orders, predictions, audit, DTC KB | CP |
| TimescaleDB | telemetry hypertables, daily aggregate | leans AP |
| MongoDB | twin docs, 7-day raw archive | AP-leaning |
| Redis | latest state, rate-limit buckets | AP |
| Lake (Garage, JSON/Parquet) | history for Spark | n/a |

- **Capacity estimate (extrapolation, not measured):** 100K vehicles at 100K events/s and about 1 KB per event is about 8.6 TB/day raw (about 3 PB/year); at 5-8x Parquet compression about 1-1.7 TB/day. Partition key: VIN. Retention: hot 7 days in Timescale, warm 90 days compressed, cold Parquet with S3 lifecycle to archive tiers. The 1 KB figure is the brief's; our message mix averages under that (FAST about 350 B, HEALTH about 600 B, EVENT about 250 B). No cloud bill was computed.
- **Query optimisation** (`docs/evidence/sql/report.md`; run on a small dataset, so most absolute gains are modest):

| Query | Before (ms) | After (ms) | Change made |
|---|---|---|---|
| At-risk list | 0.82 (OFFSET over the raw table; the N+1 lookups it replaced can't be captured as one plan) | 0.45 (index scan, no sort) | Materialised view + composite keyset index |
| Open alerts per tenant | 5.3 | 0.040 | Partial index on `alert(tenant_id, opened_at) WHERE closed_at IS NULL` |
| Fleet daily summary | 48 | 0.056 | Timescale continuous aggregate (parallel seq scan across 8 chunks → index scan) |

### 5.4 Deployment View
- **Local:** Docker Compose profiles `core`, `ai`, `batch`, `obs`, `chaos`; about 8 GB for `core`.
- **Kubernetes:** one generic Helm chart templated over a `services` map (Deployment, Service, HPA, PDB, NetworkPolicy per service; bitnami subcharts for Postgres, Redis, Mongo). Verified on a real `kind` cluster: `api` and Postgres 1/1 Running, `/healthz` answered through the Service (`docs/evidence/helm/`). Not deployed: Kafka (Strimzi), Flink operator, the rest of the services.
- **AWS:** Terraform with community modules (VPC, EKS, RDS, MSK, S3, KMS, Secrets Manager). `terraform validate` passes; `plan` stops at missing credentials (`docs/evidence/terraform/`). Never applied.
- **Cloud-agnostic:** `values-gcp.yaml` and `values-azure.yaml` overlays; every component is open source and container-based. The overlays were not deployed.
- **Secrets:** `.env` locally (a dev API key and passwords exist for demo users); AWS Secrets Manager in Terraform only.

---

## 6. Low-Level Design
### 6.1 Layering & Separation of Concerns
**Style:** hexagonal (ports and adapters), `api → app → domain ← infra`, so rules are testable without a database or broker. Used in `api`, `ingest-gateway`, `state-writer`, `ml`. Boundaries are a convention checked in review; **import-linter is not configured**, despite the plan.

| Layer | Responsibility | Must not |
|---|---|---|
| Presentation / API | HTTP, WebSocket, validation, auth, DTOs | contain business rules or SQL |
| Application | use cases, transactions | depend on a specific database or broker |
| Domain | entities, rules (e.g. RBAC, twin merge, lead-time, watchdog) | import framework or infra code |
| Infrastructure | repositories, Kafka/Redis/Mongo clients, JWT/JWKS | leak vendor types into the domain |

**Folder structure (two levels):**
```
services/{simulator,ingest-gateway,state-writer,api,copilot,mcp-server,ml}
stream/flink/sql      batch/spark      libs/fleetcore/{algorithms,domain,schemas}
web/src               db/{postgres,timescale}/migrations
infra/{compose,helm,terraform,keycloak,certs,k8s-local}
tests/{unit,integration,contract,bdd}     docs/{adr,diagrams,solution,evidence}
```
(`tests/load`, `tests/chaos`, `tests/security` exist as empty folders; load and chaos scripts live in `services/simulator/`.)

### 6.2 Design Principles Applied
- **SOLID:** domain logic separated from adapters (dependency inversion): `state_writer/domain/watchdog.py` takes a fake clock in tests; `api/domain/rbac.py` is a pure role-to-action table.
- **12-Factor:** config from environment (`.env.example`), stateless gateway and API, a disposable-process model (the state-writer exits when its consumer stalls and `restart: unless-stopped` recreates it).
- **Idempotency:** `seq` per vehicle and message type; the twin ignores older `seq`; the gateway Bloom filter drops redeliveries; scheduling is conditional (409 if already booked); metabase and Garage provisioning scripts are rerunnable.
- **Fail-fast:** the gateway rejects bad shard, VIN or DTC to a DLQ; the stall watchdog exits non-zero.
- **Least privilege:** API DB role is NOSUPERUSER NOBYPASSRLS; roles gate each action.
- **DRY:** the simulator, seeder and backfill share one fleet generator so VINs match across stores.

### 6.3 Design Patterns Used
| Pattern | Problem solved | Location |
|---|---|---|
| Repository | Keep SQL out of use cases | `services/api/src/api/infra/repositories.py` |
| Ports and adapters | Swap brokers/stores, test with fakes | each service's `domain` / `infra` split |
| Observer / pub-sub | Fan alerts out to WebSocket clients | `api/infra/ws_broadcaster.py` |
| Token bucket | Rate limiting, atomic via Redis Lua | `api/infra/rate_limit.py` |
| Watchdog / supervised restart | Detect a stuck Kafka consumer | `state_writer/domain/watchdog.py` |
| Strategy (role-based) | Location masking exact vs geohash | `api/app/vehicles.py` |
| Pipeline / state machine | Per-message-type twin merge | `state_writer/domain/twin.py` |

Not implemented: circuit breaker, outbox, saga. Retry exists only as client reconnect behaviour.

### 6.4 Interfaces, Contracts & Runtime Flows
- **API contract:** FastAPI generates OpenAPI at `/docs` and `/openapi.json` (live stack). Versioned `/v1`; keyset pagination on at-risk list; RFC 7807 `problem+json` errors; Redis token-bucket rate limit; a Pact contract for `GET /v1/vehicles/at-risk`.
- **Event schemas:** topics `telemetry` (key VIN), `alerts`, `dlq`. Wire format is JSON validated against a JSON Schema generated from the pydantic envelope (drift-checked in `tests/contract`). An Avro file exists in `libs/fleetcore/schemas/avro` and Apicurio runs, but producers and consumers do not use it yet. **No schema versioning**, by decision.
- **Sequence diagrams:** alert path, copilot, and scheduling in `docs/diagrams/c4-and-sequences.md`. **Failure paths with evidence:** (a) duplicate delivery, dropped by the gateway (BDD `duplicate_no_double_alert`); (b) Flink TaskManager kill and (c) Kafka broker kill, section 7. [TODO: add one explicit failure-path sequence diagram to the PDF.]

### 6.5 Algorithms & Data Structures
All in `libs/fleetcore/algorithms/` with unit tests. **Scale tested:** unit-level only; no dedicated runtime benchmark was recorded.

| Problem | Algorithm | Complexity | Why |
|---|---|---|---|
| VIN validation | ISO 3779 check digit (weighted sum mod 11) | O(17) | spec-defined |
| DTC parsing | regex | O(length) | fixed grammar |
| Duplicate pre-filter | Bloom filter | O(k) per op; O(m) bits; false positives possible | constant memory over 100K+ vehicles |
| Shard identity | hash of VIN → 32 shards | O(1) | shared by simulator and gateway so they never disagree |
| Location masking | geohash truncation | O(precision) | coarse cell for low-privilege roles |
| Nearest depot with a free bay | Dijkstra with a heap over a fully connected depot mesh (haversine weights) | O(E log V), E ≈ V² (5 depots) | falls through full depots |

```
nearest_free_depot(start):
    dist[start] = 0; heap = [(0, start)]
    while heap:
        d, u = pop(heap)
        if free_bays(u) > 0: return u
        for v in depots: relax(dist[u] + haversine(u, v))
    return None            # all full: API answers 409
```

Not implemented despite the original plan: Count-Min Sketch, sliding-window deque, trip segmentation.

---

## 7. Non-Functional Requirements & Performance Benchmarks
| NFR | Target | Achieved | How measured |
|---|---|---|---|
| Ingest throughput | 100K+ events/s | **Not met / not measured.** 937 events/s sustained 5 min (simulator-bound); 2,000/s for 10 min on the stream; burst 500→1,500/s | `make bench-ingest`; `docs/evidence/stream/README.md`; `docs/evidence/load/burst_test.txt` |
| End-to-end latency | < 2 s dashboard; < 5 s critical | Single-reading rules about 1 s, WebSocket push 0.7 s. Windowed rules (cooling, transmission) 6-7 s, **above target** | BDD `critical_alert_latency`; live checks |
| API latency | p95 < 200 ms; p99 < 500 ms | **Not measured** (k6 not run) | n/a |
| Resilience | recovers after broker / pod failure | TM kill: 27,408/27,408; broker kill: 12,000/12,000; gateway-copy kill: 18,441/18,664 delivered (1.19% loss) | `docs/evidence/chaos/` |
| Availability | 99.9%, no SPOF | **Not met.** Single Mosquitto, single Kafka broker in `core`, no Flink JobManager HA | architecture review |

- **Load test setup:** Python simulator (single process) → Mosquitto → one gateway → single-broker Kafka, on one laptop with Docker at 12 CPUs / 13 GB. Burst test: 3x step for about 48 s; consumer lag peaked at 24,039 and returned to 0 in 36 s; 1.97% of sent messages missing, attributed to the simulator's own MQTT client, not the pipeline.
- **Sustained run:** 10 min at 2,000/s: 1,500,228 FAST + 25,724 HEALTH rows, 19/19 checkpoints, TaskManager stayed up (after raising its memory from 1 GB to 2 GB).
- **Results graphs:** [TODO screenshots: Grafana, Flink UI]. The planned 1-hour soak is not in the evidence folder.

---

## 8. Security & Compliance
**Threat model (STRIDE, ingestion path and API):**

| Threat | Example | Control | Residual |
|---|---|---|---|
| Spoofing | device impersonates a VIN | mTLS shard certs, per-shard topic ACL, gateway VIN→shard check; OIDC JWT via JWKS | one shard cert can speak for any VIN in its shard |
| Tampering | forged telemetry | schema, VIN check digit, DTC validation, DLQ | no message signing |
| Repudiation | user denies an action | `audit_log` per request and per copilot tool call | same Postgres, not WORM |
| Information disclosure | cross-tenant read, location leak | RLS (FORCE), role masking, tenant from JWT only | Metabase role bypasses RLS by design; dev secrets in `.env` |
| Denial of service | flood | shared subscription, back-pressure, Kafka buffering, rate limit | no WAF; one Mosquitto thread |
| Elevation of privilege | copilot goes beyond role | server-injected tenant/role, no raw SQL, `proposed`-only writes, iteration cap | prompt injection mitigated, not eliminated |

**AuthN/Z.** Keycloak OIDC; roles fleet_admin, fleet_manager, technician, auditor; tenant isolation by Postgres RLS (a real incident: alerts were mis-filed across tenants for two days because a superuser role bypassed RLS; fixed and regression-tested, section 12).

**Device identity and encryption.** mTLS on MQTT with a dev CA and 32 shard certificates (not per vehicle). TLS to the API and web is **not** set up in the compose stack (the plan's ingress was not built). Encryption at rest: not configured for the stores; the pgcrypto extension is enabled but column-level encryption of PII was not verified. Secrets: `.env`; Secrets Manager only in Terraform.

**Privacy.** The message carries only a pseudonymous `driver_token`; no raw CAN, video or driver PII leaves the vehicle; PII lives in Postgres. Location is exact for admin/manager and a geohash cell for technician/auditor, applied to the live twin too. The erasure endpoint pseudonymises Postgres PII and deletes the driver's Mongo archive documents (9 ms after an index fix; 35 s before). A 7-day TTL covers the raw archive. We have not done a GDPR/DPDP compliance review; this is a technical foundation only.

**AI safety.** Tenant and role are injected server-side and absent from the tool schema; tools run under RLS; no raw SQL; `propose_work_order` writes only a `proposed` order needing human approval; at most 16 iterations and a token cap; every tool call is audited; tool output is treated as data. Failure of the LLM returns a stub reply.

---

## 9. Test Strategy
| Test type | Tools | No. of tests | Coverage / result | In CI? |
|---|---|---|---|---|
| Unit | pytest, coverage | 199 | 79% combined on fleetcore, ingest-gateway, api (fleetcore 98%, ingest-gateway 100%, api about 74%); no branch coverage reported | Yes |
| Integration | pytest + Testcontainers (Postgres RLS, Kafka, Redis, Mongo) | 8 | pass | Yes |
| Contract | Pact (web→API), JSON Schema drift check | 8 | pass | Yes |
| Acceptance (BDD) | behave against the live stack | 7 scenarios | 7/7 pass | Manual `workflow_dispatch` job only (stack too large for a hosted runner) |
| Performance / load / soak | custom simulator scripts | 3 runs (bench, burst, sustained) | see section 7; k6 and the 1 h soak not done | No |
| Security | Semgrep, Trivy (fs and image), pip-audit, npm audit | n/a | report-only; findings not triaged here; ZAP baseline not run | Yes (non-gating) |
| Compliance & chaos | custom scripts | 3 (TM, broker, gateway) + BDD erasure/tenant isolation | section 7 | Chaos: local only |

- **Edge cases covered:** duplicate events, out-of-order and bursty traffic (simulator noise), malformed messages to the DLQ, consumer stall, broker/TM/gateway outage, cross-tenant access, erasure.
- **Not covered:** an unknown OEM format (there is one format by design); the web UI has no unit tests (type-checked, linted, and driven with Playwright).
- **Report links:** `docs/evidence/` (chaos, load, ml, sql, stream, helm, terraform, analytics).

---

## 10. Observability
- **Built:** the API exports OpenTelemetry traces and metrics to an OTel Collector, Prometheus and a provisioned Grafana dashboard ("FleetPulse API: Overview": request rate and latency by route). Metabase shows fleet analytics (risk by failure type, 30-day alert trend, work-order approval time, daily telemetry health). Flink's own UI shows checkpoints and backpressure.
- **Not built:** Kafka consumer-lag and Flink throughput exporters; log aggregation (ELK dropped); traces through the stream path. The lag figures in section 7 were read from Kafka tooling, not a dashboard.
- **Dashboard screenshots:** [TODO].
- **Troubleshooting walk-through (how it was done in practice):** a latency spike or "alerts missing" is triaged as: (1) API dashboard for request latency; (2) `kafka-consumer-groups --describe` for lag and an active member (a stale group showed "Up" containers but no consumption); (3) Flink UI for job state, backpressure and checkpoint age, plus `curl :8081/jobs` (job drops on JobManager restart); (4) `docker logs` of gateway and state-writer for DLQ and reconnects; (5) Kafka GC log for pauses over a second (this found 14 s pauses at a 512 MB heap).

---

## 11. AI / ML Component
- **Purpose.** Rank which vehicles will fail and why, with lead time. Rules alone fire at the threshold (about zero lead time); the model uses multi-day trends. The copilot answers fleet questions through tools and proposes work orders.
- **Data & features.** Simulated history: backfill reached 11,006 of 20,000 planned vehicles over 30 days (about 95M FAST and 32M HEALTH rows) before the disk limit; trained on the committed part. Spark builds daily per-vehicle features: 7-day slopes of coolant, oil pressure, charge voltage, pad wear; DTC recurrence; tyre sibling delta; slip ratio; cell temperature. Ground truth sits in a CSV never loaded into an online store. **Leakage checks:** time-based split; as-of training that drops rows after the as-of date and vehicles whose failure is still ahead; the backtest scores a snapshot. A weakness: per-type labels mark every pre-failure row of a planted vehicle positive, not only a 7-day window.
- **Model.** One HistGradientBoostingClassifier per failure type (8), shallow (depth 3), L2, early stopping, Platt calibration. Lead time is extrapolated from the 7-day slope to the rule threshold. Embeddings for the DTC knowledge base and failure signatures use a hashing trick in pgvector (a pragmatic stand-in for a sentence-transformer).
- **Agent.** LangGraph ReAct agent, Gemini (`gemini-flash-lite-latest`), MCP tools `get_fleet_risk`, `get_vehicle_health`, `list_alerts`, `search_dtc_kb`, `find_nearest_depot` (read-only) and `propose_work_order` (role-gated).
- **Evaluation** (`docs/evidence/ml/report.md`):
  - **Backtest, the number to quote:** 10,765 vehicles scored as of 2026-09-19; 113 really failed afterwards. Risk ≥ 0.5: 61 flagged, 61 failed. Risk ≥ 0.2: 69 flagged, 66 failed. Top-113 precision 0.63. Failure type correct for all hits. Lead-time MAE 4.6 days.
  - **Per-type test metrics are noise:** 2 to 15 positives per type, so values such as PR-AUC 1.000 are not evidence. precision@100 is 0.51.
  - **Baseline** (DTC or threshold breach): precision about 0.001-0.002, lead time about zero; ₹ saved on the test window −₹10.9 M vs +₹7.1 M for the model (a rough illustration).
  - **Caveats:** simulated, clean ramps, so scores are bimodal; horizon at most about 10 days; EV battery and transmission have the fewest positives.
- **Guardrails & cost.** LLM failure → stub; iteration cap 16; token cap; human approval; audit. Hallucination control is by design rather than measured: risk percentages are formatted by the tool and the prompt says to present them as-is. Cost and latency: free tier, about 20 requests/day on one tier tried earlier (each question costs one request per tool call plus the answer); a multi-tool answer can take tens of seconds (proxy timeout 90 s). No per-request cost was measured.

---

## 12. Architecture Decisions, Risks & Future Enhancements
**ADRs** (full text in `docs/adr/`):
1. MQTT + custom gateway over devices writing straight to Kafka or a broker bridge. Consequence: shard-level not per-vehicle identity.
2. Kafka (KRaft) over RabbitMQ: replay and per-VIN ordering; needed a 1 GB heap and a persistent data dir.
3. Polyglot storage: Postgres (CP), Timescale, Mongo, Redis, lake; Metabase BYPASSRLS trade-off.
4. Delivery semantics and CAP/PACELC: at-least-once at the edges with idempotent keys; exactly-once only inside Flink; rules read the raw topic so a checkpoint replay can double-emit.
5. Flink for real time, Spark for batch.
6. Human-in-the-loop copilot over MCP tools.

**Risks and technical debt.**
- Simulated data only; model quality on real fleets is unknown.
- 100K events/s, API p95/p99, availability and the 1-hour soak are unproven.
- Single Mosquitto and single Kafka broker; no Flink JobManager HA (`make flink-submit` after restart).
- No TLS on the web/API in compose; no encryption at rest; secrets in `.env`.
- Windowed alerts take 6-7 s, above the 5 s target.
- Gateway Bloom filter can drop a non-duplicate (false positive).
- Copilot proposals have an approval endpoint but no UI queue; free-tier LLM quota.
- Import-boundary linting is not enforced; some planned algorithms (Count-Min Sketch, sliding window, trip segmentation) were not built.
- CI security scans are report-only; BDD runs only manually.
- **Incident:** between 2026-09-29 and 10-01, alerts were filed under the wrong tenant because the state-writer's superuser role bypassed RLS and its tenant lookup relied on it. Fixed with an explicit tenant filter and a regression test; 1,200 rows repaired.
- Timescale compression can peg the CPU for about 1.5 h after a large backfill.

**Future enhancements.**
1. Per-vehicle certificates, a sharded or EMQX broker tier, and a measured 100K events/s run on Kubernetes with k6 for the API.
2. Validate on real or public vehicle telemetry; add ambiguity and a longer horizon to the simulation; add a work-order approval queue UI.
3. Kafka lag and Flink exporters, Avro with a schema registry plus versioning, TLS and encryption at rest, a Flink HA setup, and an OEM-cloud connector.

---

## 13. Demo Video (5 minutes maximum)
| Time | Segment | Plan |
|---|---|---|
| 0:00-0:30 | Problem | Fleet manager, unplanned breakdowns, the ₹150,000 vs ₹3,000 assumption |
| 0:30-1:00 | Solution | One-line pitch |
| 1:00-3:00 | Live demo | Log in as manager → At-Risk → vehicle → **Schedule service** → Maintenance Scheduled; `make inject-fault TYPE=oil` → Live Alerts in about 1 s; ask the copilot |
| 3:00-4:15 | Under the hood | Architecture, Flink UI, Grafana; kill the Flink TaskManager and show recovery |
| 4:15-5:00 | Impact and next steps | Backtest numbers, honest gaps, roadmap |

**Video link:** [TODO]

---

## 14. Repository Checklist
| Item | Status |
|---|---|
| README with problem, quickstart, test commands, known issues | Done; architecture image [TODO] |
| One-command run | `make up` starts the core stack; seeding, Flink submission and the simulator are separate commands (see README), so it is not a single command |
| Structure: services, `/docs`, `/infra`, `/tests` | Done |
| CI: build, lint, tests, security scans | Done (ruff, eslint, unit, integration, contract, web build, Semgrep, Trivy, pip-audit, npm audit, image builds); BDD manual; ZAP not run |
| Hygiene: no secrets, `.env.example` | `.env.example` provided; [TODO: scan the history for secrets before submitting, since a real LLM key was used locally in `.env`]; commits from one author (solo) |
| Tag `v1.0-submission` | [TODO] |

---

## 15. Conclusion
**Learnings.** Most failures were in the plumbing, not the rules: an idle Kafka partition stalled the watermark, GC pauses outlasted a session timeout, data wasn't on a volume, a superuser role silently bypassed RLS. Live end-to-end checks caught what unit tests did not.

**Strengths.** One ingestion path and one message format; a full path from simulator to UI; tenant isolation tested at the database; a copilot with real guardrails; evidence for every claim and plain statements of gaps; an as-of backtest.

**Challenges solved.** Flink windowing and MATCH_RECOGNIZE edge cases, JDBC array and timestamp types, TaskManager memory, Kafka persistence, long-uptime consumer stalls (watchdog), multi-copy gateway client IDs, mis-filed alerts, a misleading last-day scoring snapshot.

---

## 16. Declarations
- **Open-source components** (licence from upstream projects; confirm against an SBOM [TODO: generate]): Mosquitto (EPL/EDL), Apache Kafka, Flink, Spark (Apache 2.0), PostgreSQL (PostgreSQL licence), pgvector (PostgreSQL), TimescaleDB (Timescale licence, Apache-2/TSL split), MongoDB (SSPL), Redis (licence depends on version), Garage (AGPL-3.0), Keycloak (Apache 2.0), Apicurio (Apache 2.0), Grafana (AGPL-3.0), Prometheus and OpenTelemetry (Apache 2.0), Metabase (AGPL-3.0 / commercial), FastAPI (MIT), SQLModel (MIT), scikit-learn (BSD-3), LangGraph, LangChain, MCP SDK (MIT), React and Vite (MIT), keycloak-js (Apache 2.0).
- **AI tools used:** Claude Code (Sonnet) assisted with writing code, tests, infrastructure and this document, under the author's direction and review of the live results. Gemini via the Google API is the copilot's runtime LLM.
- **Data:** all data is synthetic, generated by the simulator. No real personal data, no real vehicles. Driver names and PII in Postgres are generated.

---

## 17. Appendix
- C4, sequence and ER diagrams: `docs/diagrams/`
- ADRs: `docs/adr/`
- Evidence: `docs/evidence/` (chaos, load, ml, sql, stream, helm, terraform, analytics)
- Session log with every bug found and fixed: `docs/PROGRESS.md`
- Plan: `docs/PLAN.md`
