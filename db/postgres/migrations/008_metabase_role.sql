-- Metabase (analytics refinement, before session 10) connects with pooled,
-- long-lived connections and can't `SET LOCAL app.tenant_id` per request the
-- way api/infra/db.py does (api/api/deps.py:get_session) — an RLS-bound role
-- would see zero rows through every tenant_isolation policy 004_rls.sql
-- defined. Rather than silently working around RLS, this is a deliberate,
-- documented trade-off (same spirit as 005_api_role.sql's own comment):
-- BYPASSRLS, SELECT-only, for a single-tenant hackathon demo's cross-tenant
-- fleet analytics. RLS enforcement is untouched for every other read/write
-- path (the API, the copilot/MCP tools) — only this reporting role bypasses
-- it, and only for SELECT.
DO $$ BEGIN
    CREATE ROLE metabase_reporting LOGIN PASSWORD 'changeme' NOSUPERUSER BYPASSRLS;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

GRANT CONNECT ON DATABASE fleetpulse TO metabase_reporting;
GRANT USAGE ON SCHEMA public TO metabase_reporting;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO metabase_reporting;

ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO metabase_reporting;
