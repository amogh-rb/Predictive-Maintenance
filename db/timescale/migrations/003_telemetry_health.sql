-- HEALTH payload (60 s wear/state snapshot) — tyre, brake, 12V and HV-battery
-- signals that drive failures 2/3/5/6/8 (PLAN §1). Separate hypertable from
-- telemetry_fast because it's a different write rate (60 s vs 1 Hz) and
-- different consumers (wear-trend features, not real-time driving rules).
CREATE TABLE IF NOT EXISTS telemetry_health (
    ts                  timestamptz NOT NULL,
    vin                 char(17) NOT NULL,
    tenant              text NOT NULL,
    seq                 bigint NOT NULL,
    tire_kpa            double precision[],
    tire_c              double precision[],
    brake_pad_pct       double precision[],
    batt_12v_rest_v     double precision,
    crank_min_v         double precision,
    charge_v            double precision,
    engine_hours        double precision,
    idle_s              integer,
    mil_on              boolean,
    active_dtc          text[],
    cell_v_delta_mv     double precision,
    cell_temp_max_c     double precision,
    cell_temp_min_c     double precision,
    soh_pct             double precision
);

SELECT create_hypertable(
    'telemetry_health', 'ts',
    partitioning_column => 'vin',
    number_partitions => 8,
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS idx_telemetry_health_vin_ts ON telemetry_health (vin, ts DESC);

ALTER TABLE telemetry_health SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'vin'
);
SELECT add_compression_policy('telemetry_health', INTERVAL '7 days', if_not_exists => TRUE);
SELECT add_retention_policy('telemetry_health', INTERVAL '90 days', if_not_exists => TRUE);
