Feature: Booking an at-risk vehicle moves it to "Maintenance Scheduled"
  A fleet_manager schedules service from the at-risk tab: the vehicle is booked into the nearest
  depot with a free bay and leaves the at-risk list for the scheduled list. Technicians can see the
  schedule and mark jobs serviced but not book; auditors are read-only.

  Scenario: A booked vehicle leaves at-risk and appears in maintenance scheduled
    Given a real vehicle from the demo tenant's at-risk list
    When "fleet_manager" schedules maintenance for that vehicle
    Then the booking is created at a depot
    And that vehicle is no longer in the at-risk list
    And that vehicle is in the maintenance scheduled list
    When "fleet_manager" schedules maintenance for that vehicle
    Then the request is rejected with status 409

  Scenario: Only managers and admins can schedule, and technicians can mark it serviced
    Given a real vehicle from the demo tenant's at-risk list
    When "technician" schedules maintenance for that vehicle
    Then the request is rejected with status 403
    When "auditor" schedules maintenance for that vehicle
    Then the request is rejected with status 403
    When "fleet_manager" schedules maintenance for that vehicle
    Then the booking is created at a depot
    When "technician" marks that maintenance serviced
    Then that vehicle is not in the maintenance scheduled list
