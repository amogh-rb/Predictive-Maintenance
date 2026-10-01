from api.domain.rbac import Action, can, highest_precision_role


def test_fleet_admin_can_erase_driver():
    assert can(["fleet_admin"], Action.ERASE_DRIVER)


def test_technician_cannot_erase_driver():
    assert not can(["technician"], Action.ERASE_DRIVER)


def test_technician_cannot_view_at_risk_list():
    assert not can(["technician"], Action.VIEW_AT_RISK)


def test_auditor_can_view_audit_log_but_not_approve():
    assert can(["auditor"], Action.VIEW_AUDIT_LOG)
    assert not can(["auditor"], Action.APPROVE_WORK_ORDER)


def test_union_of_multiple_roles():
    # A user tagged both technician and auditor gets both sets' permissions.
    assert can(["technician", "auditor"], Action.VIEW_AUDIT_LOG)
    assert can(["technician", "auditor"], Action.COMPLETE_MAINTENANCE)


def test_unknown_role_grants_nothing():
    assert not can(["made-up-role"], Action.VIEW_VEHICLE)


def test_highest_precision_role_prefers_admin():
    assert highest_precision_role(["technician", "fleet_admin"]) == "fleet_admin"


def test_highest_precision_role_defaults_to_auditor():
    assert highest_precision_role(["made-up-role"]) == "auditor"


def test_maintenance_scheduled_permissions():
    assert can(["fleet_manager"], Action.SCHEDULE_MAINTENANCE)
    assert can(["fleet_admin"], Action.SCHEDULE_MAINTENANCE)
    # technicians see the schedule and mark jobs serviced, but don't book
    assert can(["technician"], Action.VIEW_SCHEDULED)
    assert can(["technician"], Action.COMPLETE_MAINTENANCE)
    assert not can(["technician"], Action.SCHEDULE_MAINTENANCE)
    # auditors are read-only
    assert can(["auditor"], Action.VIEW_SCHEDULED)
    assert not can(["auditor"], Action.SCHEDULE_MAINTENANCE)
    assert not can(["auditor"], Action.COMPLETE_MAINTENANCE)


def test_start_maintenance_is_for_admin_manager_and_technician_only():
    assert all(can([r], Action.START_MAINTENANCE) for r in ("fleet_admin", "fleet_manager", "technician"))
    assert not can(["auditor"], Action.START_MAINTENANCE)
