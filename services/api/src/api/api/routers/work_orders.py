from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from api.api.deps import get_session, rate_limited, require_action
from api.api.schemas import BookDepotRequest, ProposeWorkOrderRequest
from api.app import work_orders as work_orders_app
from api.domain import rbac
from api.infra.auth import CurrentUser

router = APIRouter(prefix="/v1/work-orders", tags=["work-orders"])


@router.post("", status_code=status.HTTP_201_CREATED)
def propose(
    body: ProposeWorkOrderRequest,
    session: Session = Depends(get_session),
    _rl: None = Depends(rate_limited),
    user: CurrentUser = Depends(require_action(rbac.Action.PROPOSE_WORK_ORDER)),
):
    work_order_id = work_orders_app.propose(session, body.vehicle_id, body.alert_id, proposed_by=user.email)
    return {"work_order_id": work_order_id, "status": "proposed"}


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


@router.post("/{work_order_id}/book-depot")
def book_depot(
    work_order_id: str,
    body: BookDepotRequest,
    vehicle_id: str,
    session: Session = Depends(get_session),
    _rl: None = Depends(rate_limited),
    _user: CurrentUser = Depends(require_action(rbac.Action.BOOK_DEPOT)),
):
    booking = work_orders_app.book_nearest_depot(
        session, vehicle_id, body.vehicle_lat, body.vehicle_lon, work_order_id, body.hours
    )
    if booking is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "every depot is fully booked")
    return booking
