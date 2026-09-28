-- Real-time rules for failures 1-5 (PLAN §1 table, "Real-time rule" column;
-- 6-8 are trimmed per PLAN §6.2/§6.3 session 4 scope). Each view produces
-- rows shaped like alerts_sink; 04_cep_misfire.sql adds failure 4's
-- MATCH_RECOGNIZE pattern and 05_pipeline.sql unions all of them.
--
-- Reads from telemetry_raw, not telemetry_dedup (01_dedup.sql) — that view's
-- proc-time dedup operator (see its comment) doesn't carry a live rowtime/
-- watermark attribute forward, which the HOP window below and the CEP
-- pattern in 04_cep_misfire.sql both need. Real-time alerting can tolerate
-- the rare exact duplicate ingest-gateway's Bloom pre-filter doesn't catch —
-- every rule here keys off a sustained or recurring condition, not a single
-- reading — so skipping the exact-dedup pass for this branch only is a
-- deliberate trade, not an oversight.

-- Failure 1 — cooling: coolant > 110C for >= 30s. A HOP (sliding) window,
-- via the windowing table-valued function (the non-deprecated form since
-- Flink 1.13; the old `GROUP BY HOP(...)` aggregate-function syntax is
-- legacy), because the rule is about *sustained* heat, not one hot reading
-- (a single spike can be sensor noise or a momentary load event) — MIN()
-- over the window only clears 110C if every sample in it did.
CREATE VIEW alert_cooling AS
SELECT
    vin, tenant,
    'cooling' AS failure_type,
    'critical' AS severity,
    'realtime' AS source,
    CAST(ARRAY['P0128', 'P0217'] AS ARRAY<STRING>) AS dtc_codes,
    window_end AS detected_at
FROM TABLE(
    HOP(TABLE telemetry_raw, DESCRIPTOR(event_time), INTERVAL '5' SECOND, INTERVAL '30' SECOND)
)
WHERE msg_type = 'FAST' AND payload.coolant_c IS NOT NULL
GROUP BY vin, tenant, window_start, window_end
HAVING MIN(payload.coolant_c) > 110;

-- Failure 2 — lubrication: oil pressure below the safe minimum while the
-- engine is turning. 100 kPa is a placeholder "safe minimum" threshold (the
-- PLAN table doesn't pin an exact figure); tune once real oil-pressure
-- distributions are visible in the seeded fleet.
CREATE VIEW alert_lubrication AS
SELECT
    vin, tenant,
    'lubrication' AS failure_type,
    'critical' AS severity,
    'realtime' AS source,
    CAST(ARRAY['P0520', 'P0521', 'P0522', 'P0523', 'P0524'] AS ARRAY<STRING>) AS dtc_codes,
    event_time AS detected_at
FROM telemetry_raw
WHERE msg_type = 'FAST'
  AND payload.oil_kpa IS NOT NULL AND payload.oil_kpa < 100
  AND payload.rpm IS NOT NULL AND payload.rpm > 0;

-- Failure 3 — 12V/starter/alternator: charge voltage below the alternator's
-- healthy floor. charge_v only rides on HEALTH (60s cadence, not FAST), and
-- the alternator only drives it once the engine is running, so no join
-- against FAST's speed is needed to establish "while driving" here.
CREATE VIEW alert_battery AS
SELECT
    vin, tenant,
    '12v_battery' AS failure_type,
    'critical' AS severity,
    'realtime' AS source,
    CAST(ARRAY['P0562', 'P0615'] AS ARRAY<STRING>) AS dtc_codes,
    event_time AS detected_at
FROM telemetry_raw
WHERE msg_type = 'HEALTH' AND payload.charge_v IS NOT NULL AND payload.charge_v < 12.5;

-- Failure 4 — ignition misfire, "flashing MIL" half of PLAN's rule (the
-- recurring-DTC half is the MATCH_RECOGNIZE pattern in 04_cep_misfire.sql).
CREATE VIEW alert_misfire_mil AS
SELECT
    vin, tenant,
    'misfire' AS failure_type,
    'critical' AS severity,
    'realtime' AS source,
    payload.active_dtc AS dtc_codes,
    event_time AS detected_at
FROM telemetry_raw
WHERE msg_type = 'HEALTH' AND payload.mil_on = TRUE;

-- Failure 5 — brake wear: any single axle's pad below the legal minimum.
-- 20% is the placeholder "legal min" (PLAN table names it without a figure);
-- UNNEST turns the per-axle array into rows so one worn axle is enough,
-- not an average across all of them.
CREATE VIEW alert_brakes AS
SELECT
    t.vin, t.tenant,
    'brake_wear' AS failure_type,
    'critical' AS severity,
    'realtime' AS source,
    CAST(ARRAY['C0750'] AS ARRAY<STRING>) AS dtc_codes,
    t.event_time AS detected_at
FROM telemetry_raw t
CROSS JOIN UNNEST(t.payload.brake_pad_pct) AS a (pad_pct)
WHERE t.msg_type = 'HEALTH' AND pad_pct < 20;
