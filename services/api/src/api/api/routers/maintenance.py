from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from api.api.deps import get_session, rate_limited, require_action
from api.app import work_orders as work_orders_app
from api.domain import rbac
from api.infra.auth import CurrentUser
from api.infra.redis_client import get_redis

router = APIRouter(prefix="/v1/maintenance", tags=["maintenance"])


@router.get("/scheduled")
def list_scheduled(
    limit: int = Query(100, ge=1, le=500),
    session: Session = Depends(get_session),
    _rl: None = Depends(rate_limited),
    _user: CurrentUser = Depends(require_action(rbac.Action.VIEW_SCHEDULED)),
):
    return work_orders_app.list_scheduled(session, limit=limit)


@router.get("/status")
def status_board(
    limit: int = Query(200, ge=1, le=500),
    session: Session = Depends(get_session),
    _rl: None = Depends(rate_limited),
    _user: CurrentUser = Depends(require_action(rbac.Action.VIEW_SCHEDULED)),
):
    return work_orders_app.status_board(session, limit=limit)


@router.post("/schedule/{vehicle_id}", status_code=status.HTTP_201_CREATED)
def schedule(
    vehicle_id: str,
    hours: int = Query(work_orders_app.DEFAULT_BOOKING_HOURS, ge=1, le=72),
    session: Session = Depends(get_session),
    _rl: None = Depends(rate_limited),
    user: CurrentUser = Depends(require_action(rbac.Action.SCHEDULE_MAINTENANCE)),
):
    try:
        booking = work_orders_app.schedule_maintenance(
            session, get_redis(), vehicle_id, proposed_by=user.email, approver_user_id=user.sub, hours=hours
        )
    except work_orders_app.VehicleNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "vehicle not found")
    except work_orders_app.AlreadyScheduled:
        raise HTTPException(status.HTTP_409_CONFLICT, "vehicle already has maintenance scheduled")
    if booking is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "every depot is fully booked")
    return booking


@router.post("/{work_order_id}/start")
def start(
    work_order_id: str,
    session: Session = Depends(get_session),
    _rl: None = Depends(rate_limited),
    _user: CurrentUser = Depends(require_action(rbac.Action.START_MAINTENANCE)),
):
    if not work_orders_app.start(session, work_order_id):
        raise HTTPException(status.HTTP_409_CONFLICT, "work order not found or not waiting to start")
    return {"work_order_id": work_order_id, "status": "in_service"}


@router.post("/{work_order_id}/complete")
def complete(
    work_order_id: str,
    session: Session = Depends(get_session),
    _rl: None = Depends(rate_limited),
    _user: CurrentUser = Depends(require_action(rbac.Action.COMPLETE_MAINTENANCE)),
):
    if not work_orders_app.complete(session, work_order_id):
        raise HTTPException(status.HTTP_409_CONFLICT, "work order not found or not in progress")
    return {"work_order_id": work_order_id, "status": "completed"}
