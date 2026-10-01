-- Real-time rules for failures 1-8 (PLAN §1 table, "Real-time rule" column;
-- 6-8 were trimmed per PLAN §6.2/§6.3 session 4 scope, then promoted and
-- built in session 10b once the deadline turned out to have slack). Each
-- view produces rows shaped like alerts_sink; 04_cep_misfire.sql adds
-- failure 4's MATCH_RECOGNIZE pattern and 05_pipeline.sql unions all of them.
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
-- Must check for an actual P030x code, not just mil_on = TRUE: mil_on just
-- means "some active_dtc is non-empty", and every failure type with a DTC
-- list sets it (session 10b's tyre/transmission/ev_battery additions turned
-- this from a latent bug into an observed one — an EV HV battery fault was
-- generating a bogus second "misfire" alert carrying its P0A80/P0AFA codes).
CREATE VIEW alert_misfire_mil AS
SELECT
    vin, tenant,
    'misfire' AS failure_type,
    'critical' AS severity,
    'realtime' AS source,
    payload.active_dtc AS dtc_codes,
    event_time AS detected_at
FROM telemetry_raw
WHERE msg_type = 'HEALTH' AND payload.mil_on = TRUE
  AND (
    ARRAY_CONTAINS(payload.active_dtc, 'P0300') OR ARRAY_CONTAINS(payload.active_dtc, 'P0301') OR
    ARRAY_CONTAINS(payload.active_dtc, 'P0302') OR ARRAY_CONTAINS(payload.active_dtc, 'P0303') OR
    ARRAY_CONTAINS(payload.active_dtc, 'P0304') OR ARRAY_CONTAINS(payload.active_dtc, 'P0305') OR
    ARRAY_CONTAINS(payload.active_dtc, 'P0306') OR ARRAY_CONTAINS(payload.active_dtc, 'P0307') OR
    ARRAY_CONTAINS(payload.active_dtc, 'P0308')
  );

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

-- Failure 6 — tyre slow leak: "fast pressure drop or temp spike" (PLAN §1),
-- checked per-tyre via UNNEST (same one-bad-axle-is-enough shape as brake
-- wear above) rather than joining the two arrays together — UNNESTing
-- tire_kpa and tire_c independently and cross-joining them would pair every
-- tyre's pressure with every tyre's temperature, not tyre[i] with tyre[i].
-- 'C0750' is a representative reference code for the alert row's dtc_codes
-- display column (PLAN's "C0750-series"), same as alert_brakes below cites
-- 'C0750' even though the simulator never plants it as a literal active_dtc
-- (Flink SQL's ARRAY[] constructor requires at least one element, so an
-- empty array isn't an option here the way Python's FAILURE_DTCS uses one).
CREATE VIEW alert_tyre_pressure AS
SELECT
    t.vin, t.tenant,
    'tyre' AS failure_type,
    'critical' AS severity,
    'realtime' AS source,
    CAST(ARRAY['C0750'] AS ARRAY<STRING>) AS dtc_codes,
    t.event_time AS detected_at
FROM telemetry_raw t
CROSS JOIN UNNEST(t.payload.tire_kpa) AS a (kpa)
WHERE t.msg_type = 'HEALTH' AND kpa < 550;

CREATE VIEW alert_tyre_temp AS
SELECT
    t.vin, t.tenant,
    'tyre' AS failure_type,
    'critical' AS severity,
    'realtime' AS source,
    CAST(ARRAY['C0750'] AS ARRAY<STRING>) AS dtc_codes,
    t.event_time AS detected_at
FROM telemetry_raw t
CROSS JOIN UNNEST(t.payload.tire_c) AS a (temp_c)
WHERE t.msg_type = 'HEALTH' AND temp_c > 60;

-- Failure 7 — transmission: fluid overheat, sustained (same HOP-window
-- reasoning as failure 1's cooling rule — a momentary spike under hard load
-- isn't a failure signature, a held-high reading is).
CREATE VIEW alert_transmission AS
SELECT
    vin, tenant,
    'transmission' AS failure_type,
    'critical' AS severity,
    'realtime' AS source,
    CAST(ARRAY['P0700', 'P0730'] AS ARRAY<STRING>) AS dtc_codes,
    window_end AS detected_at
FROM TABLE(
    HOP(TABLE telemetry_raw, DESCRIPTOR(event_time), INTERVAL '5' SECOND, INTERVAL '30' SECOND)
)
WHERE msg_type = 'FAST' AND payload.trans_c IS NOT NULL
GROUP BY vin, tenant, window_start, window_end
HAVING MIN(payload.trans_c) > 130;

-- Failure 8 — EV HV battery: cell over-temperature. HEALTH-only, same shape
-- as failure 3's charge_v rule.
CREATE VIEW alert_ev_hv_battery AS
SELECT
    vin, tenant,
    'ev_battery' AS failure_type,
    'critical' AS severity,
    'realtime' AS source,
    CAST(ARRAY['P0A80', 'P0AFA'] AS ARRAY<STRING>) AS dtc_codes,
    event_time AS detected_at
FROM telemetry_raw
WHERE msg_type = 'HEALTH' AND payload.cell_temp_max_c IS NOT NULL AND payload.cell_temp_max_c > 60;
