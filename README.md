# FleetPulse

Predictive maintenance POC for truck fleets — *"Which trucks will break down in the next 7 days, why, and what should I do?"*
Built for the Talenciaglobal/SRM "Connected Vehicle Intelligence" hackathon.

Full plan, architecture and session-by-session status: [docs/PLAN.md](docs/PLAN.md) and [docs/PROGRESS.md](docs/PROGRESS.md).
Build/session rules for contributors (including Claude): [CLAUDE.md](CLAUDE.md).

## Quickstart
```bash
cp .env.example .env         # fill in secrets
make up                      # generates dev mTLS certs, starts the core compose profile
make ps                      # check container health
```

Compose profiles: `core` (default infra), `ai` (copilot + MCP server), `batch` (Spark, on demand), `obs` (OTel/Prometheus/Grafana), `chaos` (3-broker Kafka). See `docs/PLAN.md` §3.

## Status
Repo skeleton and core infra only (session 1 of 10). See [docs/PLAN.md](docs/PLAN.md) status checklist for what's built.
