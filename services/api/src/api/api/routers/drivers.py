from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from api.api.deps import get_session, rate_limited, require_action
from api.app import erasure
from api.domain import rbac
from api.infra.auth import CurrentUser

router = APIRouter(prefix="/v1/drivers", tags=["drivers"])


@router.post("/{driver_id}/erase")
def erase_driver(
    driver_id: str,
    session: Session = Depends(get_session),
    _rl: None = Depends(rate_limited),
    _user: CurrentUser = Depends(require_action(rbac.Action.ERASE_DRIVER)),
):
    try:
        return erasure.erase_driver(session, driver_id)
    except erasure.DriverNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "driver not found") from None
