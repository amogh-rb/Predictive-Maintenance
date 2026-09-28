from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session

from api.domain import rbac
from api.infra import db
from api.infra.auth import CurrentUser, decode_token
from api.infra.rate_limit import default_limiter
from api.infra.redis_client import get_redis

_bearer = HTTPBearer(auto_error=True)


def get_current_user(
    request: Request, creds: HTTPAuthorizationCredentials = Depends(_bearer)
) -> CurrentUser:
    user = decode_token(creds.credentials)
    request.state.user = user  # picked up by the audit middleware after the response
    return user


def require_action(action: rbac.Action):
    def _check(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not rbac.can(user.roles, action):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"role(s) {user.roles} cannot {action.value}")
        return user

    return _check


def rate_limited(user: CurrentUser = Depends(get_current_user)) -> None:
    limiter = default_limiter(get_redis())
    if not limiter.allow(f"{user.tenant}:{user.sub}"):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "rate limit exceeded")


def get_session(user: CurrentUser = Depends(get_current_user)) -> Iterator[Session]:
    tenant_id = db.resolve_tenant_id(user.tenant)
    if tenant_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"unknown tenant {user.tenant!r}")
    with db.tenant_session(tenant_id) as session:
        yield session
