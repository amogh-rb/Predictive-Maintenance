# FleetPulse: Solution Document

Predictive maintenance for truck fleets. *Which trucks will break down soon, why, and what should the fleet manager do?*
Solo entry, Talenciaglobal/SRM "Connected Vehicle Intelligence" hackathon. Repo: https://github.com/amogh-rb/Predictive-Maintenance

> Everything here is a POC on one laptop (16 cores, 13 GB to Docker) with simulated trucks. Where a number is measured it points at a file in `docs/evidence/`; where it is an extrapolation it says so.

## 1. Problem and users
Primary user: the fleet manager, who needs a ranked at-risk list with a reason and a next action. Secondary: technicians (work orders), auditors (audit log), admins. Drivers' PII is pseudonymised outside Postgres.

## 2. What it detects
Eight failure types, each on two timescales: a streaming rule for the critical alert, and a per-type sklearn model for the early warning.

| # | Failure | Real-time rule (Flink) |
|---|---|---|
| 1 | Cooling | coolant > 110 °C sustained 30 s (HOP window) |
| 2 | Lubrication | oil pressure below minimum while running |
| 3 | 12V battery/alternator | charge voltage < 12.5 V while driving |
| 4 | Ignition misfire | MATCH_RECOGNIZE on recurring P030x DTCs |
| 5 | Brake wear | pad % below legal minimum |
| 6 | Tyre slow leak | pressure/temperature threshold |
| 7 | Transmission | fluid overheat (HOP window) |
| 8 | EV HV battery | cell over-temperature |

One universal message format (FAST 1 Hz, HEALTH 60 s, EVENT on occurrence) with an envelope of vin, msg_type, seq, ts, fw_version, schema_ver, driver_token. No raw CAN, video or driver PII leaves the vehicle.

## 3. Architecture
See `docs/diagrams/c4-and-sequences.md` for C4 and sequence diagrams, `docs/diagrams/er-diagram.md` for the schema.

Single ingestion path: simulator → Mosquitto (mTLS) → ingest-gateway → Kafka → Flink SQL and state-writer → Timescale / Postgres / Mongo / Redis / lake → Spark → sklearn → Postgres → FastAPI → React, plus a LangGraph copilot over an MCP server. Observability: OTel → Prometheus → Grafana; Metabase for fleet analytics.

Decisions and trade-offs: ADRs 1-6 in `docs/adr/`. Each service is hexagonal (`api → app → domain ← infra`).

## 4. ML
- One HistGradientBoostingClassifier per failure type, shallow and L2-regularised, Platt-calibrated, trained on a time split. Baseline: "active DTC or threshold breach", which by construction has about zero lead time.
- **Honest evaluation is the backtest** (`docs/evidence/ml/report.md`): trained only on data before 2026-09-19, then scored every vehicle that day. 10,765 vehicles scored, 113 really failed afterwards. 61 scored ≥ 0.5 and all 61 failed; top-113 precision 0.63; failure type right for 100% of hits; lead-time MAE 4.6 days.
- Caveats, stated plainly: the data is simulated and the ramp is clean, so scores are bimodal (clearly drifting or clearly healthy). Per-type test sets have 2-15 positives, so per-type PR-AUC (many 1.000) is noise; quote the backtest instead. The horizon is at most about 10 days because all planted failures sit inside the 30-day history. The backfill reached 11,006 of a planned 20,000 vehicles (disk) and was trained on as-is. The ₹ savings figure is a rough illustration (breakdown ₹150,000 vs inspection ₹3,000), not a costed study.
- The at-risk list is defined as predicted to fail within 30 days and not yet past threshold; already-failed vehicles belong in Live Alerts.

## 5. API, security and privacy
- FastAPI `/v1`: keyset pagination, RFC 7807 errors, Redis token-bucket rate limit, WebSocket alerts, audit row per authenticated request.
- Keycloak OIDC, JWKS validation; roles fleet_admin, fleet_manager, technician, auditor. Tenant and role come only from the JWT.
- Postgres RLS (FORCE) driven by `app.tenant_id`; the API role is NOSUPERUSER NOBYPASSRLS.
- Location masking by role (exact for admin/manager, geohash cell for technician/auditor), applied to the vehicle's live twin too (a leak found and fixed in session 6).
- Erasure endpoint pseudonymises Postgres PII and deletes the driver's Mongo archive docs (9 ms after adding an index; 35 s before).
- mTLS on MQTT with per-shard certificates (see ADR 1 for the deviation from per-vehicle certs).

### STRIDE
| Threat | Example | Mitigation | Residual |
|---|---|---|---|
| Spoofing | Device impersonates another vehicle | mTLS shard cert, per-shard topic ACL, gateway VIN→shard re-check; JWT via JWKS for users | A compromised shard cert can speak for any VIN in that shard; per-vehicle certs needed |
| Tampering | Forged or malformed telemetry | Schema, VIN check digit and DTC validation; DLQ; Kafka ACL not configured in POC | No message signing |
| Repudiation | User denies an action | audit_log row per request and per copilot tool call | Audit table is in the same Postgres; no WORM storage |
| Information disclosure | Cross-tenant read; location leak | RLS, role masking, tenant from JWT only (pgcrypto is enabled, but column-level PII encryption was not verified) | Metabase role bypasses RLS by design (documented); dev secrets in `.env`; Vault dropped (AWS Secrets Manager in Terraform only) |
| Denial of service | Flood from devices or API | MQTT shared subscription plus gateway back-pressure, Kafka buffering, Redis rate limit | No WAF; one Mosquitto thread is a ceiling |
| Elevation of privilege | Copilot induced to act beyond role | Tenant/role injected server-side and absent from tool schema; no raw SQL; write tool only creates `proposed`; iteration cap; tool output as data | Prompt injection through data fields is mitigated, not eliminated |

## 6. Measured results
| Check | Result | Evidence |
|---|---|---|
| Ingest throughput (5 min, simulator-limited) | 937 events/s end to end, 98.4% of attempted | PROGRESS session 2 |
| Burst 3x (500→1500/s) | lag peaked at 24,039, back to 0 in 36 s; 1.97% simulator-side delta | `docs/evidence/load/burst_test.txt` |
| Sustained stream, 10 min at 2,000/s | 1.5 M FAST rows, 19/19 checkpoints, no TM loss | `docs/evidence/stream/README.md` |
| TaskManager kill | 27,408/27,408 `(vin, seq)` landed | `docs/evidence/chaos/taskmanager_kill.txt` |
| Kafka broker kill (3 brokers, acks=all) | 12,000/12,000 | `.../broker_kill.txt` |
| Gateway-copy kill | 18,441/18,664 delivered (1.19% loss) | `.../gateway_kill.txt` |
| Alert latency | ~1 s single-reading rules; ~6-7 s windowed rules; 0.7 s WebSocket push | PLAN open items, PROGRESS 11 |
| SQL optimisation | at-risk list via keyset + materialised view; open alerts via partial index; daily aggregate 48 ms → 0.056 ms | `docs/evidence/sql/report.md` |
| Tests | 199 unit, 8 integration, 8 contract, 7 BDD scenarios; combined coverage 79% on fleetcore/ingest-gateway/api (target was 80%) | PROGRESS sessions 9, 11 |
| Deploy | `helm install` on kind: api and Postgres 1/1 Running; `terraform validate` passes, `plan` stops at missing AWS credentials | `docs/evidence/helm`, `terraform` |

**Not achieved, stated plainly:** the 100K events/s target. The local ingest benchmark is bound by the single-process Python simulator at about 1K/s, and the burst test ran at 1.5K/s; we never measured the 10-25K/s demo target or the 100K/s ceiling. The 1-hour soak was not saved as evidence. Zero loss is shown for the TaskManager and broker kills only. A full 100K-vehicle history was not generated. CI runs unit, integration and contract tests and report-only security scans; the full-stack BDD job is manual because it does not fit a hosted runner. The OWASP ZAP baseline is not run.

## 7. Scale and cost (extrapolation, not measured)
100K vehicles at about 1 KB per event and 100K events/s is about 8.6 TB/day raw. With roughly 5-8x Parquet compression that is about 1-1.7 TB/day to the lake. Hot data stays 7 days in Timescale, warm 90 days compressed, cold in Parquet under an S3 lifecycle to archive tiers. Every stateless piece (gateway, state-writer, Flink task slots) scales horizontally; Kafka partitions by VIN; Mosquitto shards by VIN hash. The Helm chart carries HPA, PDB, probes and NetworkPolicy, and `values-gcp.yaml` / `values-azure.yaml` show the second cloud. No cloud bill was computed; storage at S3 Standard list prices of roughly $0.023/GB-month for the warm tier would dominate, so pricing the tier split is the first step before committing.

## 8. Trade-offs and deviations
| Plan | Built | Why |
|---|---|---|
| MinIO | Garage | MinIO CE pulled from registries |
| Claude in copilot | Gemini free tier | avoid a paid key |
| Per-vehicle mTLS certs | per-shard certs | scope |
| Avro via Schema Registry (Apicurio runs; `.avsc` exists) | gateway/Flink use JSON validated against schema generated from pydantic | scope |
| Iceberg | Spark Parquet + JSON lake sink | catalogue setup cost |
| ELK, Vault | dropped | Pro budget; Secrets Manager path documented |
| Sentence-transformer embeddings | hashing trick | ~2 GB dependency |
| Manual propose/approve/book UI | one-click "Schedule service" | managers are the users; copilot proposals still need approval |
| Pact message contract | JSON-Schema contract test | scope |

## 9. Known issues
- Alerts were mis-filed to the wrong tenant between 09-29 and 10-01 (state-writer role bypassed RLS and the tenant lookup relied on it). Fixed with an explicit tenant filter and a regression test; the 1,200 affected rows were repaired.
- Flink has no JobManager HA; resubmit after a restart.
- No UI for the approval queue of copilot proposals.
- Browser look-and-feel was exercised with a scripted Playwright run in Chromium, not a formal usability test.
- The Timescale compression policy can peg the CPU for about 1.5 h after a large backfill.

## 10. Demo path
1. `make up`, `make flink-submit`, open the web UI, log in as `manager@demo` (password in the repo's README).
2. At-Risk tab, open a vehicle, **Schedule service**; see it move to Maintenance Scheduled.
3. `make inject-fault VIN=<vin> TYPE=oil`; the alert appears in Live Alerts within about a second.
4. Ask the copilot about the riskiest trucks at a depot; check the audit log as `admin@demo`.
5. Grafana and Metabase for operations and fleet analytics.

*Screenshots, video timestamps and the PDF export are manual steps for the author.*
