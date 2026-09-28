-- PLAN §2 "SQL optimisation" items 1-2 (item 3, the fleet daily summary,
-- was already covered by session 3's `telemetry_fast_daily` continuous
-- aggregate on the Timescale side).

-- 1. The at-risk list: was OFFSET pagination plus an N+1 "latest prediction
-- per vehicle" lookup. `vehicle_latest_risk` pre-computes one row per
-- vehicle (its single highest-risk open prediction) so the API's keyset
-- query is a plain indexed range scan, no OFFSET, no per-row lookup.
-- Refreshed after every `make train` run (`make refresh-risk`), and once
-- here so it exists (empty) before the first training run.
CREATE MATERIALIZED VIEW IF NOT EXISTS vehicle_latest_risk AS
SELECT DISTINCT ON (p.vehicle_id)
    p.tenant_id,
    p.vehicle_id,
    p.failure_type,
    p.risk_score,
    p.lead_days,
    p.model_version,
    p.created_at
FROM prediction p
ORDER BY p.vehicle_id, p.created_at DESC, p.risk_score DESC
WITH NO DATA;

-- Composite index backs both the DISTINCT ON refresh and, more importantly,
-- the API's keyset page: `WHERE tenant_id = :t AND (risk_score, vehicle_id)
-- < (:last_risk, :last_id) ORDER BY risk_score DESC, vehicle_id DESC LIMIT :n`.
CREATE UNIQUE INDEX IF NOT EXISTS idx_vehicle_latest_risk_pk
    ON vehicle_latest_risk (vehicle_id);
CREATE INDEX IF NOT EXISTS idx_vehicle_latest_risk_keyset
    ON vehicle_latest_risk (tenant_id, risk_score DESC, vehicle_id DESC);

GRANT SELECT ON vehicle_latest_risk TO fleetpulse_api;

-- REFRESH ... CONCURRENTLY (used by `make refresh-risk`) requires the view
-- to already be populated once with a plain refresh first.
REFRESH MATERIALIZED VIEW vehicle_latest_risk;

-- 2. Open alerts per fleet: a partial index on the common "still open" case
-- (closed_at IS NULL is a constant predicate, so unlike migration 006's
-- now()-based filter this one *is* a valid IMMUTABLE partial-index predicate).
CREATE INDEX IF NOT EXISTS idx_alert_open_by_tenant
    ON alert (tenant_id, opened_at DESC)
    WHERE closed_at IS NULL;
