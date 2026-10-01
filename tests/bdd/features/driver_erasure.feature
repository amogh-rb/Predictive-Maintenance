Feature: Driver erasure (right to be forgotten)
  PLAN §2 "Privacy": erasure endpoint pseudonymises driver PII in Postgres
  and deletes that driver's raw-archive rows in MongoDB by driver_token.

  Scenario: fleet_admin erases a driver; a technician cannot
    Given a freshly seeded driver with archived raw telemetry in Mongo
    When "technician" tries to erase that driver
    Then the request is rejected with status 403
    When "fleet_admin" erases that driver
    Then the driver's PII is pseudonymised in Postgres
    And the driver's raw archive is gone from Mongo
