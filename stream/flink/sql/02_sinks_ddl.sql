-- Sink table DDLs (PLAN §2: "sinks to TimescaleDB (JDBC), the alerts topic
-- and Iceberg on MinIO" — Iceberg trimmed to plain Parquet per PLAN §6.2).
-- The two JDBC (Postgres/Timescale) sinks below use plain TIMESTAMP(3), not
-- TIMESTAMP_LTZ(3) like the source (00_source.sql): Flink's JDBC connector
-- (flink-connector-jdbc 3.2.0-1.19)'s Postgres row converter has no case for
-- TIMESTAMP_LTZ ("Unsupported type" at job startup) even though Postgres's
-- own `timestamptz` is the better semantic match for a zoned instant.
-- 05_pipeline.sql casts `event_time` down to TIMESTAMP(3) for these two
-- INSERTs only; the Kafka/filesystem sinks further down keep TIMESTAMP_LTZ(3)
-- since their JSON writers have no such limitation.

-- Column order/names match db/timescale/migrations/002_telemetry_fast.sql.
CREATE TABLE telemetry_fast_sink (
    ts              TIMESTAMP(3),
    vin             STRING,
    tenant          STRING,
    seq             BIGINT,
    lat             DOUBLE, lon DOUBLE, heading DOUBLE, gps_hdop DOUBLE,
    speed_kmh       DOUBLE, odo_km DOUBLE, accel_long_g DOUBLE, accel_lat_g DOUBLE,
    ambient_c       DOUBLE, rpm DOUBLE, load_pct DOUBLE, throttle_pct DOUBLE,
    coolant_c       DOUBLE, oil_c DOUBLE, oil_kpa DOUBLE, trans_c DOUBLE, gear INT,
    fuel_pct        DOUBLE, fuel_rate_lph DOUBLE, soc_pct DOUBLE, hv_v DOUBLE, hv_a DOUBLE
) WITH (
    'connector' = 'jdbc',
    'url' = 'jdbc:postgresql://timescaledb:5432/telemetry',
    'table-name' = 'telemetry_fast',
    'username' = 'fleetpulse',
    'password' = 'changeme',
    'sink.buffer-flush.max-rows' = '500',
    'sink.buffer-flush.interval' = '1s'
);

-- Column order/names match db/timescale/migrations/003_telemetry_health.sql.
CREATE TABLE telemetry_health_sink (
    ts                  TIMESTAMP(3),
    vin                 STRING,
    tenant              STRING,
    seq                 BIGINT,
    tire_kpa            ARRAY<DOUBLE>,
    tire_c              ARRAY<DOUBLE>,
    brake_pad_pct       ARRAY<DOUBLE>,
    batt_12v_rest_v     DOUBLE,
    crank_min_v         DOUBLE,
    charge_v            DOUBLE,
    engine_hours        DOUBLE,
    idle_s              INT,
    mil_on              BOOLEAN,
    active_dtc          ARRAY<STRING>,
    cell_v_delta_mv     DOUBLE,
    cell_temp_max_c     DOUBLE,
    cell_temp_min_c     DOUBLE,
    soh_pct             DOUBLE
) WITH (
    'connector' = 'jdbc',
    'url' = 'jdbc:postgresql://timescaledb:5432/telemetry',
    'table-name' = 'telemetry_health',
    'username' = 'fleetpulse',
    'password' = 'changeme',
    'sink.buffer-flush.max-rows' = '200',
    'sink.buffer-flush.interval' = '1s'
);

-- Warm/cold lake (PLAN §2 lifecycle) — plain JSON-per-line rather than
-- Parquet for this session's slice: the flink-sql-parquet writer needs a
-- bulk/rolling file sink whose part files only become visible on checkpoint
-- (default 3-minute interval here), so JSON keeps `docker compose exec
-- flink-jobmanager` verification and the 10-minute manual smoke run in
-- PLAN §6.3 session 4 able to see files land quickly; swapping 'format' to
-- 'parquet' later is a one-line change once a longer soak (session 9) is
-- driving it. Partitioned by day so a day's data is one prefix.
-- `payload` keeps its nested ROW type rather than being pre-serialized to a
-- STRING: Flink SQL has no ROW-to-STRING cast, but the JSON format writer
-- serializes a ROW column to a nested JSON object natively, so passing it
-- through as-is is both the only option and the simplest one.
CREATE TABLE telemetry_lake_sink (
    vin             STRING,
    msg_type        STRING,
    seq             BIGINT,
    event_time      TIMESTAMP_LTZ(3),
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
    dt              STRING
) PARTITIONED BY (dt) WITH (
    'connector' = 'filesystem',
    'path' = 's3://fleetpulse-lake/telemetry/',
    'format' = 'json',
    'sink.partition-commit.trigger' = 'process-time',
    'sink.partition-commit.delay' = '0s',
    'sink.partition-commit.policy.kind' = 'success-file',
    'sink.rolling-policy.rollover-interval' = '2min',
    'sink.rolling-policy.check-interval' = '30s'
);

-- Real-time alerts (PLAN §2: Flink sinks to the `alerts` topic; the
-- state-writer, running in parallel off the same `telemetry` topic per the
-- architecture diagram, consumes this to write Postgres `alert` rows).
CREATE TABLE alerts_sink (
    vin             STRING,
    tenant          STRING,
    failure_type    STRING,
    severity        STRING,
    source          STRING,
    dtc_codes       ARRAY<STRING>,
    detected_at     TIMESTAMP_LTZ(3)
) WITH (
    'connector' = 'kafka',
    'topic' = 'alerts',
    'properties.bootstrap.servers' = 'kafka:9092',
    'format' = 'json',
    'json.timestamp-format.standard' = 'ISO-8601'
);
