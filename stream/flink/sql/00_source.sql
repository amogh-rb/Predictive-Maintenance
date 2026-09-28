-- Kafka source over the `telemetry` topic (PLAN §2). Messages are plain JSON
-- (ingest-gateway writes json.dumps, not Avro — see kafka_producer.py), keyed
-- by VIN. `payload` covers the union of FAST/HEALTH/EVENT fields as nullable
-- columns: Flink's JSON format leaves a column NULL when the source dict
-- doesn't have that key, which is exactly the union-by-msg_type shape
-- fleetcore.domain.envelope encodes as three separate pydantic models.
CREATE TABLE telemetry_raw (
    vin             STRING,
    msg_type        STRING,
    seq             BIGINT,
    -- TIMESTAMP_LTZ(3), not TIMESTAMP(3): fleetcore's envelope (envelope.py)
    -- serializes `ts` as a 'Z'-suffixed (zoned) ISO-8601 instant via
    -- pydantic. Flink's JSON format silently nulls a field it can't parse
    -- (json.ignore-parse-errors below) rather than failing loudly, and
    -- TIMESTAMP(3) — a zone-less "local" timestamp type — couldn't parse
    -- that 'Z' suffix, so every single row's event_time came out null,
    -- crashing the HOP window and MATCH_RECOGNIZE operators downstream
    -- (both require a non-null rowtime) the first three times this was run
    -- end-to-end. TIMESTAMP_LTZ(3) is the type Flink documents for exactly
    -- this shape of value: a zoned instant, which is what `ts` actually is.
    ts              TIMESTAMP_LTZ(3),
    fw_version      STRING,
    schema_ver      INT,
    driver_token    STRING,
    tenant          STRING,
    payload         ROW<
        lat DOUBLE, lon DOUBLE, heading DOUBLE, gps_hdop DOUBLE, speed_kmh DOUBLE, odo_km DOUBLE,
        accel_long_g DOUBLE, accel_lat_g DOUBLE, ambient_c DOUBLE,
        rpm DOUBLE, load_pct DOUBLE, throttle_pct DOUBLE, coolant_c DOUBLE, oil_c DOUBLE, oil_kpa DOUBLE,
        trans_c DOUBLE, gear INT, fuel_pct DOUBLE, fuel_rate_lph DOUBLE,
        soc_pct DOUBLE, hv_v DOUBLE, hv_a DOUBLE,
        tire_kpa ARRAY<DOUBLE>, tire_c ARRAY<DOUBLE>, brake_pad_pct ARRAY<DOUBLE>,
        batt_12v_rest_v DOUBLE, crank_min_v DOUBLE, charge_v DOUBLE,
        engine_hours DOUBLE, idle_s INT, mil_on BOOLEAN, active_dtc ARRAY<STRING>,
        cell_v_delta_mv DOUBLE, cell_temp_max_c DOUBLE, cell_temp_min_c DOUBLE, soh_pct DOUBLE,
        event_type STRING, dtc STRING, freeze_frame MAP<STRING, DOUBLE>, `value` DOUBLE
    >,
    proc_time   AS PROCTIME(),
    event_time  AS ts,
    WATERMARK FOR event_time AS event_time - INTERVAL '5' SECOND
) WITH (
    'connector' = 'kafka',
    'topic' = 'telemetry',
    'properties.bootstrap.servers' = 'kafka:9092',
    'properties.group.id' = 'flink-telemetry-jobs',
    -- 'latest-offset', not 'earliest-offset': this job is the real-time
    -- (speed) layer — it should only ever see the live tail, not replay
    -- sessions 2-3's historical bench-ingest/simulate backlog (some of which
    -- predates this session's envelope/tenant changes and isn't guaranteed
    -- to parse cleanly). Full-history reprocessing is the batch layer's job
    -- (session 5's Spark backfill), a standard lambda-architecture split.
    'scan.startup.mode' = 'latest-offset',
    'format' = 'json',
    'json.ignore-parse-errors' = 'true',
    'json.timestamp-format.standard' = 'ISO-8601'
);
