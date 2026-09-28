-- Failure 4, CEP half: "misfire codes recur with rising frequency" (PLAN §1)
-- is the predictive pattern proper, but two-or-more P0300-P0308 DTC_SET
-- events on the same truck inside a short window is exactly the kind of
-- multi-event pattern MATCH_RECOGNIZE exists for (a plain filter can't see
-- "recurs"; it only sees one row at a time) — so it's promoted to a
-- real-time critical alert here rather than waiting for the nightly batch
-- job (session 5) to catch it as a slope.
-- MATCH_RECOGNIZE can't navigate a nested ROW field (payload.dtc) through a
-- pattern variable — Calcite's column resolution for MEASURES/DEFINE only
-- works one level deep — so EVENT rows are flattened to top-level columns
-- first; the pattern then references `A.dtc`, not `A.payload.dtc`.
CREATE VIEW telemetry_events AS
SELECT vin, tenant, event_time, payload.event_type AS event_type, payload.dtc AS dtc
FROM telemetry_raw
WHERE msg_type = 'EVENT';

CREATE VIEW alert_misfire_recurrence AS
SELECT
    vin, tenant,
    'misfire' AS failure_type,
    'critical' AS severity,
    'realtime' AS source,
    CAST(ARRAY[last_dtc] AS ARRAY<STRING>) AS dtc_codes,
    match_end AS detected_at
FROM telemetry_events
MATCH_RECOGNIZE (
    PARTITION BY vin, tenant
    ORDER BY event_time
    MEASURES
        LAST(A.dtc) AS last_dtc,
        LAST(A.event_time) AS match_end,
        COUNT(A.event_time) AS occurrences
    -- Reluctant, not greedy (`A{2,}?`, not `A{2,}`): Flink disallows a greedy
    -- quantifier as a pattern's last element, and reluctant is the right
    -- semantics anyway — fire as soon as the 2nd matching DTC_SET lands,
    -- rather than holding the match open to swallow a 3rd, 4th, etc.
    PATTERN (A{2,}?) WITHIN INTERVAL '10' MINUTE
    DEFINE
        A AS A.event_type = 'DTC_SET'
             AND A.dtc IS NOT NULL
             AND A.dtc SIMILAR TO 'P030[0-8]'
);
