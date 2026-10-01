from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from api.api.deps import get_session, rate_limited, require_action
from api.app import work_orders as work_orders_app
from api.domain import rbac
from api.infra.auth import CurrentUser

router = APIRouter(prefix="/v1/work-orders", tags=["work-orders"])


# Work orders are created by "Schedule service" (api/routers/maintenance.py, already approved) or proposed
# by the copilot's MCP tool, which waits here for a human to approve it.
@router.post("/{work_order_id}/approve")
def approve(
    work_order_id: str,
    session: Session = Depends(get_session),
    _rl: None = Depends(rate_limited),
    user: CurrentUser = Depends(require_action(rbac.Action.APPROVE_WORK_ORDER)),
):
    ok = work_orders_app.approve(session, work_order_id, approver_user_id=user.sub)
    if not ok:
        raise HTTPException(status.HTTP_409_CONFLICT, "work order not found or already decided")
    return {"work_order_id": work_order_id, "status": "approved"}
