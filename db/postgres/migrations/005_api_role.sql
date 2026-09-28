-- The FastAPI service (session 6) must connect as a role that is NEITHER
-- superuser NOR BYPASSRLS, since Postgres exempts both from RLS regardless
-- of FORCE (session 3's PROGRESS note). The default POSTGRES_USER docker
-- creates *is* a superuser, so the API gets its own least-privilege role.
DO $$ BEGIN
    CREATE ROLE fleetpulse_api LOGIN PASSWORD 'changeme' NOSUPERUSER NOBYPASSRLS;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

GRANT CONNECT ON DATABASE fleetpulse TO fleetpulse_api;
GRANT USAGE ON SCHEMA public TO fleetpulse_api;

-- SELECT everywhere (including shared catalogues), row-level write access
-- only on the tables the API actually mutates; predictions/audit_log stay
-- SELECT + INSERT (never UPDATE/DELETE — append-only history).
GRANT SELECT ON ALL TABLES IN SCHEMA public TO fleetpulse_api;
GRANT INSERT, UPDATE ON depot, driver, vehicle, work_order TO fleetpulse_api;
GRANT INSERT ON alert, audit_log TO fleetpulse_api;
GRANT UPDATE (closed_at) ON alert TO fleetpulse_api;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO fleetpulse_api;

ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO fleetpulse_api;
