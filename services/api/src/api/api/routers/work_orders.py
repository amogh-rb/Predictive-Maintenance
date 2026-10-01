from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from api.api.deps import get_session, rate_limited, require_action
from api.app import work_orders as work_orders_app
from api.domain import rbac
from api.infra.auth import CurrentUser
from api.infra.redis_client import get_redis

router = APIRouter(prefix="/v1/work-orders", tags=["work-orders"])


# Work orders are created by "Schedule service" (api/routers/maintenance.py, already approved) or proposed
# by the copilot's MCP tool, which waits here for a human to approve (booking a depot bay) or reject it.
@router.post("/{work_order_id}/approve")
def approve(
    work_order_id: str,
    session: Session = Depends(get_session),
    _rl: None = Depends(rate_limited),
    user: CurrentUser = Depends(require_action(rbac.Action.APPROVE_WORK_ORDER)),
):
    try:
        booking = work_orders_app.approve(session, get_redis(), work_order_id, approver_user_id=user.sub)
    except work_orders_app.NoDepotCapacity:
        raise HTTPException(status.HTTP_409_CONFLICT, "every depot is fully booked; the proposal stays pending")
    if booking is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "work order not found or already decided")
    return booking


@router.post("/{work_order_id}/reject")
def reject(
    work_order_id: str,
    session: Session = Depends(get_session),
    _rl: None = Depends(rate_limited),
    _user: CurrentUser = Depends(require_action(rbac.Action.APPROVE_WORK_ORDER)),
):
    if not work_orders_app.reject(session, work_order_id):
        raise HTTPException(status.HTTP_409_CONFLICT, "work order not found or already decided")
    return {"work_order_id": work_order_id, "status": "rejected"}
