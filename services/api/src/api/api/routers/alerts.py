from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from api.api.deps import get_session, rate_limited, require_action
from api.app import alerts as alerts_app
from api.domain import rbac
from api.infra.auth import CurrentUser

router = APIRouter(prefix="/v1/alerts", tags=["alerts"])


@router.get("")
def list_alerts(
    open_only: bool = True,
    limit: int = Query(50, ge=1, le=500),
    session: Session = Depends(get_session),
    _rl: None = Depends(rate_limited),
    _user: CurrentUser = Depends(require_action(rbac.Action.VIEW_ALERTS)),
):
    return alerts_app.list_alerts(session, open_only=open_only, limit=limit)
