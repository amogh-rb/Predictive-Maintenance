-- Wraps every sink INSERT into one STATEMENT SET so they share a single
-- JobGraph (and, since table.optimizer.reuse-source-enabled defaults to
-- true, a single scan of the `telemetry` Kafka topic) instead of each INSERT
-- becoming its own job with its own consumer group re-reading the topic.
-- run-jobs.sh concatenates 00-05 in order and submits the result once.
BEGIN STATEMENT SET;

INSERT INTO telemetry_fast_sink
SELECT
    CAST(event_time AS TIMESTAMP(3)), vin, tenant, seq,
    payload.lat, payload.lon, payload.heading, payload.gps_hdop,
    payload.speed_kmh, payload.odo_km, payload.accel_long_g, payload.accel_lat_g,
    payload.ambient_c, payload.rpm, payload.load_pct, payload.throttle_pct,
    payload.coolant_c, payload.oil_c, payload.oil_kpa, payload.trans_c, payload.gear,
    payload.fuel_pct, payload.fuel_rate_lph, payload.soc_pct, payload.hv_v, payload.hv_a
FROM telemetry_dedup
WHERE msg_type = 'FAST';

INSERT INTO telemetry_health_sink
SELECT
    CAST(event_time AS TIMESTAMP(3)), vin, tenant, seq,
    -- JSON '[..]' -> Postgres array literal '{..}' (see telemetry_health_sink).
    REPLACE(REPLACE(JSON_STRING(payload.tire_kpa), '[', '{'), ']', '}'),
    REPLACE(REPLACE(JSON_STRING(payload.tire_c), '[', '{'), ']', '}'),
    REPLACE(REPLACE(JSON_STRING(payload.brake_pad_pct), '[', '{'), ']', '}'),
    payload.batt_12v_rest_v, payload.crank_min_v, payload.charge_v,
    payload.engine_hours, payload.idle_s, payload.mil_on,
    REPLACE(REPLACE(JSON_STRING(payload.active_dtc), '[', '{'), ']', '}'),
    payload.cell_v_delta_mv, payload.cell_temp_max_c, payload.cell_temp_min_c, payload.soh_pct
FROM telemetry_dedup
WHERE msg_type = 'HEALTH';

INSERT INTO telemetry_lake_sink
SELECT
    vin, msg_type, seq, event_time, tenant, payload,
    DATE_FORMAT(event_time, 'yyyy-MM-dd') AS dt
FROM telemetry_dedup;

INSERT INTO alerts_sink
SELECT vin, tenant, failure_type, severity, source, dtc_codes, detected_at FROM alert_cooling
UNION ALL
SELECT vin, tenant, failure_type, severity, source, dtc_codes, detected_at FROM alert_lubrication
UNION ALL
SELECT vin, tenant, failure_type, severity, source, dtc_codes, detected_at FROM alert_battery
UNION ALL
SELECT vin, tenant, failure_type, severity, source, dtc_codes, detected_at FROM alert_misfire_mil
UNION ALL
SELECT vin, tenant, failure_type, severity, source, dtc_codes, detected_at FROM alert_misfire_recurrence
UNION ALL
SELECT vin, tenant, failure_type, severity, source, dtc_codes, detected_at FROM alert_brakes;

END;
