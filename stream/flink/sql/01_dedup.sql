-- Exact dedup on (vin, seq) (PLAN §2's "dedup using ROW_NUMBER() OVER
-- (PARTITION BY vin, seq) with state TTL"). ingest-gateway already runs an
-- approximate Bloom-filter pre-filter (session 2), which is reset on
-- restart and only catches exact-retry duplicates seen since the last
-- restart; this is the exact, stateful pass everything downstream in this
-- job relies on. State TTL (table.exec.state.ttl, set at job submission —
-- see stream/flink/run-jobs.sh) bounds how long a (vin, seq) key is kept so
-- state doesn't grow unbounded over a long-running job.
--
-- ORDER BY proc_time, deliberately, not event_time: this needs to compile to
-- Flink's *proc-time* "keep first row" dedup operator, which is append-only
-- (first-seen wins, permanently). The event-time variant instead compiles to
-- an upsert/changelog operator (a later-arriving-but-earlier-event-time row
-- can revise "first"), which (a) demands every downstream sink declare a
-- primary key, including the two JDBC telemetry sinks and the Kafka alerts
-- sink, and (b) strips the rowtime/watermark metadata a Window TVF or
-- MATCH_RECOGNIZE downstream of it needs — confirmed by hitting both a
-- sink-primary-key error and (with the fix half-applied) a NullPointerException
-- in StreamRecordTimestampInserter the first time this was run end-to-end.
-- Consequence: 03_realtime_rules.sql and 04_cep_misfire.sql read from
-- telemetry_raw, not this view, so their windowing keeps a live watermark
-- chain — real-time alerting can tolerate the rare exact duplicate
-- ingest-gateway's Bloom pre-filter already thins out (PLAN §1's rules all
-- key off sustained/recurring conditions, not single readings), whereas the
-- Timescale/lake sinks below, which this view does feed, need the exact
-- pass so stored history has no double-counted rows.
CREATE VIEW telemetry_dedup AS
SELECT vin, msg_type, seq, event_time, fw_version, schema_ver, driver_token, tenant, payload
FROM (
    SELECT
        *,
        ROW_NUMBER() OVER (PARTITION BY vin, seq ORDER BY proc_time ASC) AS row_num
    FROM telemetry_raw
)
WHERE row_num = 1;
