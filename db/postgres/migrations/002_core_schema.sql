-- 3NF core (PLAN §2 "Data stores" / §4): tenant, fleet ownership, drivers,
-- vehicles, users/roles, alerts, work orders, predictions, audit, and the
-- pgvector-backed DTC/failure-signature knowledge base.
-- Vehicle telemetry itself lives in TimescaleDB (db/timescale/migrations),
-- not here — this is the OLTP/ownership side of the split described there.

DO $$ BEGIN
    CREATE TYPE drivetrain_type AS ENUM ('ICE', 'EV', 'HYBRID');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE vehicle_status AS ENUM ('active', 'maintenance', 'retired');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE app_role AS ENUM ('fleet_admin', 'fleet_manager', 'technician', 'auditor');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE alert_severity AS ENUM ('info', 'warning', 'critical');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE alert_source AS ENUM ('realtime', 'predictive');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE work_order_status AS ENUM ('proposed', 'approved', 'rejected', 'completed');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS tenant (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name        text UNIQUE NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS depot (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   uuid NOT NULL REFERENCES tenant(id),
    name        text NOT NULL,
    city        text NOT NULL,
    lat         double precision NOT NULL,
    lon         double precision NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, name)
);

-- Shared catalogue, not tenant-scoped: make/model/drivetrain determine
-- which optional telemetry fields are meaningful (PLAN §1 FastPayload).
CREATE TABLE IF NOT EXISTS vehicle_model (
    id              serial PRIMARY KEY,
    make            text NOT NULL,
    model           text NOT NULL,
    vehicle_type    drivetrain_type NOT NULL,
    tyre_count      smallint NOT NULL CHECK (tyre_count IN (4, 6)),
    UNIQUE (make, model)
);

-- Real PII lives here only; the wire-level driver_token (envelope.py) is the
-- pseudonymous identifier trucks actually publish (PLAN §1 "Not sent: ... driver PII").
CREATE TABLE IF NOT EXISTS driver (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL REFERENCES tenant(id),
    driver_token    text UNIQUE NOT NULL,
    full_name       text NOT NULL,
    phone           text NOT NULL,
    license_no      text NOT NULL,
    depot_id        uuid NOT NULL REFERENCES depot(id),
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS vehicle (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           uuid NOT NULL REFERENCES tenant(id),
    vin                 char(17) UNIQUE NOT NULL,
    depot_id            uuid NOT NULL REFERENCES depot(id),
    vehicle_model_id    integer NOT NULL REFERENCES vehicle_model(id),
    fw_version          text NOT NULL,
    primary_driver_id   uuid REFERENCES driver(id),
    status              vehicle_status NOT NULL DEFAULT 'active',
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS app_user (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   uuid NOT NULL REFERENCES tenant(id),
    email       text UNIQUE NOT NULL,
    role        app_role NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS subscription (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   uuid NOT NULL REFERENCES tenant(id),
    plan        text NOT NULL,
    seats       integer NOT NULL CHECK (seats > 0),
    renews_at   date NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS alert (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL REFERENCES tenant(id),
    vehicle_id      uuid NOT NULL REFERENCES vehicle(id),
    failure_type    text NOT NULL,
    severity        alert_severity NOT NULL,
    source          alert_source NOT NULL,
    dtc_codes       text[] NOT NULL DEFAULT '{}',
    opened_at       timestamptz NOT NULL DEFAULT now(),
    closed_at       timestamptz
);

CREATE TABLE IF NOT EXISTS work_order (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL REFERENCES tenant(id),
    vehicle_id      uuid NOT NULL REFERENCES vehicle(id),
    alert_id        uuid REFERENCES alert(id),
    status          work_order_status NOT NULL DEFAULT 'proposed',
    proposed_by     text NOT NULL,
    approved_by     uuid REFERENCES app_user(id),
    created_at      timestamptz NOT NULL DEFAULT now(),
    approved_at     timestamptz
);

CREATE TABLE IF NOT EXISTS prediction (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL REFERENCES tenant(id),
    vehicle_id      uuid NOT NULL REFERENCES vehicle(id),
    failure_type    text NOT NULL,
    risk_score      numeric(6, 5) NOT NULL CHECK (risk_score BETWEEN 0 AND 1),
    lead_days       numeric(4, 1),
    model_version   text NOT NULL,
    feature_vector  vector(384),
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_log (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   uuid NOT NULL REFERENCES tenant(id),
    actor       text NOT NULL,
    action      text NOT NULL,
    resource    text NOT NULL,
    details     jsonb NOT NULL DEFAULT '{}',
    created_at  timestamptz NOT NULL DEFAULT now()
);

-- DTC knowledge base + failure signatures for the copilot's `search_dtc_kb`
-- RAG tool (PLAN §2 "Agentic AI") — shared across tenants, not RLS-scoped.
CREATE TABLE IF NOT EXISTS dtc_kb (
    code        text PRIMARY KEY,
    description text NOT NULL,
    embedding   vector(384)
);

CREATE TABLE IF NOT EXISTS failure_signature (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    failure_type    text NOT NULL,
    description     text NOT NULL,
    embedding       vector(384),
    created_at      timestamptz NOT NULL DEFAULT now()
);
