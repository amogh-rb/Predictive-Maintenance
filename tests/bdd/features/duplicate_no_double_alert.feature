Feature: A retransmitted duplicate reading never reaches Kafka twice
  PLAN §2 "ingest-gateway": a Bloom-filter dedup pre-filter on (vin, seq)
  drops an exact duplicate before it ever reaches Kafka — the realistic case
  being an MQTT QoS-1 redelivery after an unacknowledged publish.

  Scoped to the ingest-gateway boundary, not the full alerting path: the
  realtime rules (03_realtime_rules.sql) deliberately read `telemetry_raw`
  directly rather than the exactly-once dedup view (session 4's own
  trade-off, "trading exact-dedup for a live watermark chain" — see
  docs/PROGRESS.md session 4/7), so Flink's *own* at-least-once checkpoint
  replay can still emit more than one alert for a single Kafka message, with
  or without a duplicate MQTT publish. That's a separate, already-documented
  gap, not something this scenario re-litigates.

  Scenario: The same FAST reading published twice over MQTT lands on telemetry once
    Given a real seeded vehicle from the demo tenant
    When the same FAST reading with oil_kpa 50 and rpm 1800 is published twice for it over MQTT
    Then exactly one copy of that reading appears on the telemetry topic
