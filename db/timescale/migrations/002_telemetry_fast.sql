-- FAST payload (libs/fleetcore/domain/envelope.py, 1 Hz driving telemetry),
-- flattened for column-store efficiency. Written by the Flink JDBC sink
-- (session 4) — this migration only lays down the shape. Hypertable
-- partitioned by time and space-partitioned by VIN hash (PLAN §2) so a
-- single vehicle's history stays in one chunk per time range while writes
-- spread across chunks instead of hammering one partition.
CREATE TABLE IF NOT EXISTS telemetry_fast (
    ts              timestamptz NOT NULL,
    vin             char(17) NOT NULL,
    tenant          text NOT NULL,
    seq             bigint NOT NULL,
    lat             double precision,
    lon             double precision,
    heading         double precision,
    gps_hdop        double precision,
    speed_kmh       double precision,
    odo_km          double precision,
    accel_long_g    double precision,
    accel_lat_g     double precision,
    ambient_c       double precision,
    rpm             double precision,
    load_pct        double precision,
    throttle_pct    double precision,
    coolant_c       double precision,
    oil_c           double precision,
    oil_kpa         double precision,
    trans_c         double precision,
    gear            integer,
    fuel_pct        double precision,
    fuel_rate_lph   double precision,
    soc_pct         double precision,
    hv_v            double precision,
    hv_a            double precision
);

SELECT create_hypertable(
    'telemetry_fast', 'ts',
    partitioning_column => 'vin',
    number_partitions => 8,
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS idx_telemetry_fast_vin_ts ON telemetry_fast (vin, ts DESC);

-- Compress cold chunks, drop raw rows past 90 d (PLAN §2 lifecycle:
-- hot 7 d raw -> warm 90 d compressed+aggregated -> cold Parquet on S3).
ALTER TABLE telemetry_fast SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'vin'
);
SELECT add_compression_policy('telemetry_fast', INTERVAL '7 days', if_not_exists => TRUE);
SELECT add_retention_policy('telemetry_fast', INTERVAL '90 days', if_not_exists => TRUE);
