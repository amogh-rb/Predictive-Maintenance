-- Daily per-vehicle features, continuously refreshed. This is what Spark's
-- nightly feature job (session 5) reads instead of scanning raw telemetry_fast,
-- and it's the "fleet daily summary" materialised-view story for PLAN §2's
-- SQL-optimisation section.
CREATE MATERIALIZED VIEW IF NOT EXISTS telemetry_fast_daily
WITH (timescaledb.continuous) AS
SELECT
    vin,
    time_bucket('1 day', ts)   AS day,
    avg(coolant_c)             AS avg_coolant_c,
    max(coolant_c)             AS max_coolant_c,
    avg(ambient_c)             AS avg_ambient_c,
    avg(load_pct)              AS avg_load_pct,
    avg(rpm)                   AS avg_rpm,
    avg(oil_kpa)               AS avg_oil_kpa,
    min(oil_kpa)               AS min_oil_kpa,
    avg(trans_c)               AS avg_trans_c,
    max(trans_c)               AS max_trans_c,
    max(speed_kmh)             AS max_speed_kmh,
    sum(fuel_rate_lph)         AS fuel_rate_sum,
    count(*)                   AS sample_count
FROM telemetry_fast
GROUP BY vin, day
WITH NO DATA;

SELECT add_continuous_aggregate_policy('telemetry_fast_daily',
    start_offset => INTERVAL '3 days',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists => TRUE
);
