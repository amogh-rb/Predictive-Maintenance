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
    PROPOSE_WORK_ORDER = "propose_work_order"
    APPROVE_WORK_ORDER = "approve_work_order"
    BOOK_DEPOT = "book_depot"
    VIEW_AUDIT_LOG = "view_audit_log"
    ERASE_DRIVER = "erase_driver"


_ROLE_ACTIONS: dict[str, set[Action]] = {
    "fleet_admin": {
        Action.VIEW_AT_RISK, Action.VIEW_VEHICLE, Action.VIEW_ALERTS,
        Action.PROPOSE_WORK_ORDER, Action.APPROVE_WORK_ORDER, Action.BOOK_DEPOT,
        Action.VIEW_AUDIT_LOG, Action.ERASE_DRIVER,
    },
    "fleet_manager": {
        Action.VIEW_AT_RISK, Action.VIEW_VEHICLE, Action.VIEW_ALERTS,
        Action.PROPOSE_WORK_ORDER, Action.APPROVE_WORK_ORDER, Action.BOOK_DEPOT,
    },
    "technician": {
        Action.VIEW_VEHICLE, Action.VIEW_ALERTS, Action.PROPOSE_WORK_ORDER,
    },
    "auditor": {
        Action.VIEW_AT_RISK, Action.VIEW_VEHICLE, Action.VIEW_ALERTS, Action.VIEW_AUDIT_LOG,
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
