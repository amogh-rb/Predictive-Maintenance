# PostgreSQL 3NF core — ER diagram

Source of truth: `db/postgres/migrations/002_core_schema.sql`. Telemetry itself
lives in TimescaleDB (`db/timescale/migrations`), not here — see PLAN §2 for
the OLTP/telemetry split rationale. `vehicle_model`, `dtc_kb` and
`failure_signature` are shared catalogues with no `tenant_id`; every other
table carries `tenant_id` and is RLS-scoped (`004_rls.sql`).

```mermaid
erDiagram
    TENANT ||--o{ DEPOT : owns
    TENANT ||--o{ DRIVER : employs
    TENANT ||--o{ VEHICLE : owns
    TENANT ||--o{ APP_USER : has
    TENANT ||--o{ SUBSCRIPTION : has
    TENANT ||--o{ ALERT : scopes
    TENANT ||--o{ WORK_ORDER : scopes
    TENANT ||--o{ PREDICTION : scopes
    TENANT ||--o{ AUDIT_LOG : scopes

    DEPOT ||--o{ DRIVER : "based at"
    DEPOT ||--o{ VEHICLE : "based at"

    VEHICLE_MODEL ||--o{ VEHICLE : "is a"
    DRIVER ||--o{ VEHICLE : "primary driver of"

    VEHICLE ||--o{ ALERT : raises
    VEHICLE ||--o{ WORK_ORDER : "gets"
    VEHICLE ||--o{ PREDICTION : "scored for"

    ALERT ||--o{ WORK_ORDER : "proposes"
    APP_USER ||--o{ WORK_ORDER : approves

    TENANT {
        uuid id PK
        text name UK
        timestamptz created_at
    }
    DEPOT {
        uuid id PK
        uuid tenant_id FK
        text name
        text city
        double lat
        double lon
    }
    VEHICLE_MODEL {
        int id PK
        text make
        text model
        enum vehicle_type "ICE | EV | HYBRID"
        smallint tyre_count "4 | 6"
    }
    DRIVER {
        uuid id PK
        uuid tenant_id FK
        text driver_token UK "pseudonymous, on the wire"
        text full_name "PII, PG-only"
        text phone "PII, PG-only"
        text license_no "PII, PG-only"
        uuid depot_id FK
    }
    VEHICLE {
        uuid id PK
        uuid tenant_id FK
        char17 vin UK
        uuid depot_id FK
        int vehicle_model_id FK
        text fw_version
        uuid primary_driver_id FK
        enum status "active | maintenance | retired"
    }
    APP_USER {
        uuid id PK
        uuid tenant_id FK
        text email UK
        enum role "fleet_admin | fleet_manager | technician | auditor"
    }
    SUBSCRIPTION {
        uuid id PK
        uuid tenant_id FK
        text plan
        int seats
        date renews_at
    }
    ALERT {
        uuid id PK
        uuid tenant_id FK
        uuid vehicle_id FK
        text failure_type
        enum severity "info | warning | critical"
        enum source "realtime | predictive"
        text_array dtc_codes
        timestamptz opened_at
        timestamptz closed_at
    }
    WORK_ORDER {
        uuid id PK
        uuid tenant_id FK
        uuid vehicle_id FK
        uuid alert_id FK
        enum status "proposed | approved | rejected | completed"
        text proposed_by
        uuid approved_by FK
    }
    PREDICTION {
        uuid id PK
        uuid tenant_id FK
        uuid vehicle_id FK
        text failure_type
        numeric risk_score
        numeric lead_days
        text model_version
        vector feature_vector "384-dim, pgvector"
    }
    AUDIT_LOG {
        uuid id PK
        uuid tenant_id FK
        text actor
        text action
        text resource
        jsonb details
    }
    DTC_KB {
        text code PK
        text description
        vector embedding "384-dim, pgvector"
    }
    FAILURE_SIGNATURE {
        uuid id PK
        text failure_type
        text description
        vector embedding "384-dim, pgvector"
    }
```
