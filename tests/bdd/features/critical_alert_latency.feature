Feature: A critical real-time alert appears within 5 seconds
  PLAN §2 "Real-time rule" / verification item 3: a threshold-breach
  telemetry reading (no window needed for the lubrication rule — a single
  FAST reading with oil_kpa < 100 while running) must surface as a Postgres
  `alert` row within 5 seconds of publish, end to end: MQTT -> mTLS Mosquitto
  -> ingest-gateway -> Kafka -> Flink -> alerts topic -> state-writer -> Postgres.

  Scenario: A low-oil-pressure reading for a real vehicle raises an alert fast
    Given a real seeded vehicle from the demo tenant
    When a FAST reading with oil_kpa 50 and rpm 1800 is published for it over MQTT
    Then a "lubrication" alert for that vehicle appears in Postgres within 5 seconds
