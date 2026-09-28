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
-- The four array columns are STRING here, not ARRAY: the JDBC connector's
-- Postgres converter throws "Writing ARRAY type is not yet supported" on the
-- first HEALTH row (it killed a job that had otherwise run for 1h42m).
-- 05_pipeline.sql renders each array as a Postgres array literal
-- ('{90.5,91.2}', '{"P0300"}') and `stringtype=unspecified` below makes the
-- driver send it untyped, so Postgres parses it straight into the table's
-- native double precision[] / text[] columns — no schema change needed.
CREATE TABLE telemetry_health_sink (
    ts                  TIMESTAMP(3),
    vin                 STRING,
    tenant              STRING,
    seq                 BIGINT,
    tire_kpa            STRING,
    tire_c              STRING,
    brake_pad_pct       STRING,
    batt_12v_rest_v     DOUBLE,
    crank_min_v         DOUBLE,
    charge_v            DOUBLE,
    engine_hours        DOUBLE,
    idle_s              INT,
    mil_on              BOOLEAN,
    active_dtc          STRING,
    cell_v_delta_mv     DOUBLE,
    cell_temp_max_c     DOUBLE,
    cell_temp_min_c     DOUBLE,
    soh_pct             DOUBLE
) WITH (
    'connector' = 'jdbc',
    'url' = 'jdbc:postgresql://timescaledb:5432/telemetry?stringtype=unspecified',
    'table-name' = 'telemetry_health',
    'username' = 'fleetpulse',
    'password' = 'changeme',
    'sink.buffer-flush.max-rows' = '200',
    'sink.buffer-flush.interval' = '1s'
);

-- Warm/cold lake (PLAN §2 lifecycle), partitioned by day so a day's data is
-- one prefix. JSON-per-line for now; PLAN §6.2 says Parquet — switching needs
-- flink-sql-parquet added to infra/compose/flink/Dockerfile plus 'format' =
-- 'parquet' here. Either format only commits files on a checkpoint, which
-- run-jobs.sh enables (every 30 s).
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
