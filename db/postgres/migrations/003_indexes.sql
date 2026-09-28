-- FK lookup + tenant-scan indexes. The keyset-pagination and partial-index
-- optimisations for specific slow queries are session 9's EXPLAIN ANALYZE work
-- (PLAN §2 "SQL optimisation") — these are the baseline indexes every
-- tenant-scoped table needs regardless.
CREATE INDEX IF NOT EXISTS idx_depot_tenant ON depot (tenant_id);
CREATE INDEX IF NOT EXISTS idx_driver_tenant ON driver (tenant_id);
CREATE INDEX IF NOT EXISTS idx_driver_depot ON driver (depot_id);
CREATE INDEX IF NOT EXISTS idx_vehicle_tenant ON vehicle (tenant_id);
CREATE INDEX IF NOT EXISTS idx_vehicle_depot ON vehicle (depot_id);
CREATE INDEX IF NOT EXISTS idx_vehicle_model ON vehicle (vehicle_model_id);
CREATE INDEX IF NOT EXISTS idx_vehicle_driver ON vehicle (primary_driver_id);
CREATE INDEX IF NOT EXISTS idx_app_user_tenant ON app_user (tenant_id);
CREATE INDEX IF NOT EXISTS idx_subscription_tenant ON subscription (tenant_id);
CREATE INDEX IF NOT EXISTS idx_alert_tenant ON alert (tenant_id);
CREATE INDEX IF NOT EXISTS idx_alert_vehicle ON alert (vehicle_id);
CREATE INDEX IF NOT EXISTS idx_work_order_tenant ON work_order (tenant_id);
CREATE INDEX IF NOT EXISTS idx_work_order_vehicle ON work_order (vehicle_id);
CREATE INDEX IF NOT EXISTS idx_prediction_tenant ON prediction (tenant_id);
CREATE INDEX IF NOT EXISTS idx_prediction_vehicle ON prediction (vehicle_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_tenant ON audit_log (tenant_id);
