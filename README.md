# FleetPulse

Predictive maintenance POC for truck fleets: *which trucks will break down soon, why, and what should I do?*
Built for the Talenciaglobal/SRM "Connected Vehicle Intelligence" hackathon (solo).

**Start here:** [Solution document](docs/solution/SOLUTION.md), [ADRs](docs/adr/), [C4 and sequence diagrams](docs/diagrams/c4-and-sequences.md), [ER diagram](docs/diagrams/er-diagram.md), [evidence](docs/evidence/).
Plan and session log: [docs/PLAN.md](docs/PLAN.md), [docs/PROGRESS.md](docs/PROGRESS.md).

## What it does
- Simulated trucks publish one universal message over MQTT 5 + mTLS to an ingest-gateway, then Kafka.
- Flink SQL raises real-time alerts for 8 failure types; a Spark + scikit-learn pipeline forecasts failures and ranks an at-risk list.
- Secured FastAPI (Keycloak, RBAC, Postgres RLS), React UI (At-Risk, Vehicle Detail, Live Alerts, Maintenance Scheduled, Audit Log, Copilot, Analytics), and a LangGraph copilot over an MCP server with human approval for work-order proposals.

## Quickstart
Requires Docker (about 13 GB), Python 3.13, Node 22.
```bash
cp .env.example .env         # fill in secrets (GOOGLE_API_KEY optional, for the copilot)
make up                      # dev mTLS certs + core compose profile
make migrate && make seed    # schema + 100K vehicles
make lake-init && make flink-submit
make simulate RATE=500       # live telemetry
```
Web UI `http://localhost:5173`. Keycloak realm `fleetpulse`, demo users `admin@demo`, `manager@demo`, `tech@demo`, `audit@demo` (password `changeme`, dev only).

Other targets: `make test`, `make backfill`, `make batch`, `make train`, `make refresh-risk`, `make burst`, `make chaos`, `make inject-fault VIN=... TYPE=oil`, `make explain`. Compose profiles: `core`, `ai`, `batch`, `obs`, `chaos`.

## Honest status
All planned slices are built and verified against the running stack, with these limits: simulated data only; local ingest benchmark is about 1K events/s (simulator-bound), not the 100K/s target; zero-loss shown for TaskManager and broker kills; CI security scans are report-only. Full list in section 6 and 9 of the solution document.
