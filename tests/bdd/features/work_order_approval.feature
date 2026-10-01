Feature: Copilot work-order proposals need human approval
  PLAN §2 "Agentic AI" guardrail: the copilot's `propose_work_order` tool only ever creates a
  "proposed" work order, and only a fleet_admin or fleet_manager can approve it. Managers book
  service directly with "Schedule service" (see maintenance_scheduling.feature); this is the
  approval queue for what the copilot proposes.

  Scenario: A technician cannot approve a copilot-proposed work order
    Given a real vehicle from the demo tenant's at-risk list
    And the copilot has proposed a work order for that vehicle
    When "technician" tries to approve that work order
    Then the request is rejected with status 403

  Scenario: An auditor cannot approve a copilot-proposed work order
    Given a real vehicle from the demo tenant's at-risk list
    And the copilot has proposed a work order for that vehicle
    When "auditor" tries to approve that work order
    Then the request is rejected with status 403

  Scenario: A fleet_admin approval moves the work order out of the queue
    Given a real vehicle from the demo tenant's at-risk list
    And the copilot has proposed a work order for that vehicle
    When "fleet_admin" approves that work order
    Then the work order status becomes "approved"
