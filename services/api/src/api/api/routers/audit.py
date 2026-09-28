from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from api.api.deps import get_session, rate_limited, require_action
from api.domain import rbac
from api.infra import repositories as repo
from api.infra.auth import CurrentUser

router = APIRouter(prefix="/v1/audit", tags=["audit"])


@router.get("")
def list_audit_log(
    limit: int = Query(100, ge=1, le=1000),
    session: Session = Depends(get_session),
    _rl: None = Depends(rate_limited),
    _user: CurrentUser = Depends(require_action(rbac.Action.VIEW_AUDIT_LOG)),
):
    return repo.list_audit_log(session, limit=limit)
