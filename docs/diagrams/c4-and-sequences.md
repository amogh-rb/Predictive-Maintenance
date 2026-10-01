# C4 and sequence diagrams

Mermaid; renders on GitHub.

## C4 level 1: system context

```mermaid
flowchart LR
  truck["Trucks / e-vans<br/>(simulated, 100K)"]
  mgr["Fleet manager / admin"]
  tech["Technician"]
  aud["Auditor"]
  fp["FleetPulse<br/>predictive maintenance"]
  kc["Keycloak (OIDC)"]
  llm["LLM provider<br/>(Gemini free tier)"]
  truck -- "MQTT 5 + mTLS" --> fp
  mgr -- "web UI / REST" --> fp
  tech -- "web UI" --> fp
  aud -- "audit view" --> fp
  fp -- "JWT validation" --> kc
  fp -- "copilot prompts (tool output as data)" --> llm
```

## C4 level 2: containers

```mermaid
flowchart TB
  sim["simulator"] -->|"MQTT, topic fleet/{tenant}/shard-N/{vin}/telemetry"| mq["Mosquitto (mTLS, per-shard ACL)"]
  mq --> gw["ingest-gateway<br/>validate, Bloom dedup, back-pressure, DLQ"]
  gw --> kafka[("Kafka KRaft<br/>telemetry / alerts / dlq")]
  kafka --> flink["Flink SQL<br/>dedup, windows, CEP"]
  kafka --> sw["state-writer"]
  flink --> ts[("TimescaleDB")]
  flink --> lake[("Parquet / JSON lake<br/>S3-compatible (Garage)")]
  flink -->|alerts| kafka
  sw --> redis[("Redis")]
  sw --> mongo[("MongoDB<br/>twin + raw archive")]
  sw --> pg[("PostgreSQL 16 + pgvector<br/>RLS")]
  lake --> spark["Spark feature job"]
  ts --> spark
  spark --> ml["sklearn training / scoring"]
  ml --> pg
  api["FastAPI<br/>RBAC, RLS, WebSocket"] --> pg
  api --> redis
  api --> mongo
  api --> kafka
  web["React UI"] --> api
  api --> cop["copilot (LangGraph)"]
  cop --> mcp["MCP server<br/>read-only tools + propose_work_order"]
  mcp --> pg
  api -.OTel.-> otel["OTel Collector"] --> prom["Prometheus"] --> graf["Grafana"]
  meta["Metabase"] --> pg
  meta --> ts
```

## Sequence: critical alert, fault to screen

```mermaid
sequenceDiagram
  participant T as Truck (simulator)
  participant M as Mosquitto
  participant G as ingest-gateway
  participant K as Kafka
  participant F as Flink SQL
  participant S as state-writer
  participant P as Postgres
  participant A as API (WebSocket)
  participant U as Browser
  T->>M: FAST/HEALTH msg (QoS 1, mTLS)
  M->>G: shared subscription
  G->>G: shard/VIN/DTC/schema check, Bloom dedup
  G->>K: telemetry (key = VIN)
  K->>F: consume
  F->>K: alerts (rule fired)
  K->>S: alerts
  S->>P: INSERT alert (tenant resolved from vehicle)
  K->>A: alerts (background consumer)
  A-->>U: WebSocket push, filtered by JWT tenant
```

## Sequence: copilot with human approval

```mermaid
sequenceDiagram
  participant U as Manager (browser)
  participant A as API
  participant C as copilot (LangGraph)
  participant L as LLM
  participant X as MCP server
  participant P as Postgres (RLS)
  U->>A: POST /v1/copilot/ask (JWT)
  A->>A: tenant + role from JWT, resolve tenant uuid
  A->>C: question + tenant/role (server-injected)
  loop up to 16 iterations
    C->>L: messages
    L-->>C: tool call (no tenant/role argument exposed)
    C->>X: tool + injected tenant/role
    X->>P: SET LOCAL app.tenant_id; query
    X->>P: audit_log row
    X-->>C: data (treated as data, not instructions)
  end
  C-->>A: answer
  A-->>U: reply
  Note over X,P: propose_work_order writes status=proposed.<br/>A human with approve rights must approve it.
```

## Sequence: schedule service from the at-risk list

```mermaid
sequenceDiagram
  participant U as Manager
  participant A as API
  participant R as Redis twin
  participant P as Postgres
  U->>A: POST /v1/maintenance/schedule/{vehicle_id}
  A->>R: truck position (server side only)
  A->>A: Dijkstra over depot mesh, skip full depots
  A->>P: one transaction: work order approved + bay booked
  alt every depot full
    A-->>U: 409, nothing written
  else booked
    A-->>U: 201, vehicle moves to Maintenance Scheduled tab
  end
```
