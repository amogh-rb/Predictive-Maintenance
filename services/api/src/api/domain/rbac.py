"""Role -> allowed actions (PLAN §2 "Roles": fleet_admin, fleet_manager,
technician, auditor). Pure logic, no I/O — the tenant and role themselves
always come from the validated JWT (CLAUDE.md conventions), never a request
body or query param; this module only decides what a role may *do* once
`api/deps.py` has already extracted it.
"""
from __future__ import annotations

from enum import Enum


class Action(str, Enum):
    VIEW_AT_RISK = "view_at_risk"
    VIEW_VEHICLE = "view_vehicle"
    VIEW_ALERTS = "view_alerts"
    APPROVE_WORK_ORDER = "approve_work_order"
    VIEW_AUDIT_LOG = "view_audit_log"
    ERASE_DRIVER = "erase_driver"
    VIEW_ANALYTICS = "view_analytics"
    VIEW_SCHEDULED = "view_scheduled"
    SCHEDULE_MAINTENANCE = "schedule_maintenance"
    COMPLETE_MAINTENANCE = "complete_maintenance"


_ROLE_ACTIONS: dict[str, set[Action]] = {
    "fleet_admin": {
        Action.VIEW_AT_RISK, Action.VIEW_VEHICLE, Action.VIEW_ALERTS,
        Action.APPROVE_WORK_ORDER,
        Action.VIEW_AUDIT_LOG, Action.ERASE_DRIVER, Action.VIEW_ANALYTICS,
        Action.VIEW_SCHEDULED, Action.SCHEDULE_MAINTENANCE, Action.COMPLETE_MAINTENANCE,
    },
    "fleet_manager": {
        Action.VIEW_AT_RISK, Action.VIEW_VEHICLE, Action.VIEW_ALERTS,
        Action.APPROVE_WORK_ORDER,
        Action.VIEW_ANALYTICS,
        Action.VIEW_SCHEDULED, Action.SCHEDULE_MAINTENANCE, Action.COMPLETE_MAINTENANCE,
    },
    "technician": {
        Action.VIEW_VEHICLE, Action.VIEW_ALERTS,
        Action.VIEW_SCHEDULED, Action.COMPLETE_MAINTENANCE,
    },
    "auditor": {
        Action.VIEW_AT_RISK, Action.VIEW_VEHICLE, Action.VIEW_ALERTS, Action.VIEW_AUDIT_LOG,
        Action.VIEW_SCHEDULED,
    },
}


def can(roles: list[str], action: Action) -> bool:
    """True if any of the JWT's roles grants `action`. A user with multiple
    realm roles gets the union of their permissions.
    """
    return any(action in _ROLE_ACTIONS.get(role, set()) for role in roles)


def highest_precision_role(roles: list[str]) -> str:
    """Which role's location-masking precision applies, for a user with
    several roles: the most permissive one wins (an admin who is also
    tagged technician still sees exact coordinates).
    """
    for preferred in ("fleet_admin", "fleet_manager", "technician", "auditor"):
        if preferred in roles:
            return preferred
    return "auditor"
