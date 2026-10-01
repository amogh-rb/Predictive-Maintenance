-- The at-risk list means "predicted to fail within the next 30 days". A vehicle already past
-- its threshold has failed (that is a live alert, not a prediction), and one with no projected
-- crossing inside the horizon is not at risk yet. Both have a NULL `lead_days` (see
-- services/ml/src/ml/domain/lead_time.py), so the view keeps only rows with 0 < lead_days <= 30.
-- It also reads only each tenant's latest model run: the previous definition took the newest row
-- per vehicle across every model_version, so a vehicle the new model no longer flagged kept
-- showing an old model's score.
DROP MATERIALIZED VIEW IF EXISTS vehicle_latest_risk;

CREATE MATERIALIZED VIEW vehicle_latest_risk AS
SELECT DISTINCT ON (p.vehicle_id)
    p.tenant_id,
    p.vehicle_id,
    p.failure_type,
    p.risk_score,
    p.lead_days,
    p.model_version,
    p.created_at
FROM prediction p
WHERE p.lead_days > 0
  AND p.lead_days <= 30
  AND p.model_version = (
      SELECT p2.model_version FROM prediction p2
      WHERE p2.tenant_id = p.tenant_id
      ORDER BY p2.created_at DESC LIMIT 1
  )
ORDER BY p.vehicle_id, p.risk_score DESC, p.created_at DESC;

CREATE UNIQUE INDEX idx_vehicle_latest_risk_pk ON vehicle_latest_risk (vehicle_id);
CREATE INDEX idx_vehicle_latest_risk_keyset
    ON vehicle_latest_risk (tenant_id, risk_score DESC, vehicle_id DESC);

GRANT SELECT ON vehicle_latest_risk TO fleetpulse_api;
