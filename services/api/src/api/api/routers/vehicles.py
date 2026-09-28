from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from api.api.deps import get_session, rate_limited, require_action
from api.app import vehicles as vehicles_app
from api.domain import rbac
from api.infra.auth import CurrentUser
from api.infra.redis_client import get_redis

router = APIRouter(prefix="/v1/vehicles", tags=["vehicles"])


@router.get("/at-risk")
def list_at_risk(
    limit: int = Query(20, ge=1, le=200),
    cursor: str | None = None,
    session: Session = Depends(get_session),
    _rl: None = Depends(rate_limited),
    _user: CurrentUser = Depends(require_action(rbac.Action.VIEW_AT_RISK)),
):
    return vehicles_app.list_at_risk(session, limit=limit, cursor_str=cursor)


@router.get("/{vehicle_id}")
def get_vehicle(
    vehicle_id: str,
    session: Session = Depends(get_session),
    _rl: None = Depends(rate_limited),
    user: CurrentUser = Depends(require_action(rbac.Action.VIEW_VEHICLE)),
):
    role = rbac.highest_precision_role(user.roles)
    vehicle = vehicles_app.get_vehicle_detail(session, get_redis(), vehicle_id, role)
    if vehicle is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "vehicle not found")
    return vehicle
