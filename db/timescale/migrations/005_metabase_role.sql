-- Same reporting role as db/postgres/migrations/008_metabase_role.sql, for
-- the separate TimescaleDB instance. No RLS exists here (session 3: Timescale
-- never held tenant-scoped PII to begin with), so this is a plain SELECT-only
-- grant — nothing to bypass, unlike the Postgres core's BYPASSRLS.
DO $$ BEGIN
    CREATE ROLE metabase_reporting LOGIN PASSWORD 'changeme' NOSUPERUSER;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

GRANT CONNECT ON DATABASE telemetry TO metabase_reporting;
GRANT USAGE ON SCHEMA public TO metabase_reporting;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO metabase_reporting;

ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO metabase_reporting;
