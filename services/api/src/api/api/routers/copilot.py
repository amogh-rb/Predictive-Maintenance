"""Proxies to the `copilot` service (LangGraph + MCP + Gemini, PLAN §6.3
session 8), which only runs under the `ai` compose profile. `web/src/pages/
CopilotPage.tsx` (session 7) already expects a 404 here to mean "not
deployed yet" and shows a banner instead of breaking, so a *connection*
failure to `copilot` (core profile running without ai) is mapped to a 404 —
same contract the frontend already ships against. A real request that's just
slow (a multi-tool-call Gemini exchange, confirmed live to take 30-60s+ when
the model spends part of its budget on reasoning tokens) is a different
failure and must not show the misleading "not deployed" banner, so a
read timeout is surfaced as a 504 instead.
"""
from __future__ import annotations

import os

import httpx
from fastapi import APIRouter, Depends, HTTPException, status

from api.api.deps import get_current_user, rate_limited
from api.api.schemas import CopilotAskRequest, CopilotAskResponse
from api.infra import db
from api.infra.auth import CurrentUser

router = APIRouter(prefix="/v1/copilot", tags=["copilot"])

COPILOT_URL = os.environ.get("COPILOT_URL", "http://copilot:9100")


@router.post("/ask", response_model=CopilotAskResponse)
async def ask(
    body: CopilotAskRequest,
    _rl: None = Depends(rate_limited),
    user: CurrentUser = Depends(get_current_user),
) -> CopilotAskResponse:
    # The MCP tools' `SET LOCAL app.tenant_id` (mcp_server/infra/postgres.py)
    # expects the tenant's uuid, same as api/api/deps.py:get_session — the
    # JWT's `tenant` claim is the tenant *name* ("demo"), not the id. Sending
    # the name through unresolved fails every RLS-scoped query with
    # `invalid input syntax for type uuid` (caught live).
    tenant_id = db.resolve_tenant_id(user.tenant)
    if tenant_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"unknown tenant {user.tenant!r}")

    payload = {
        "message": body.message,
        "tenant": tenant_id,
        "role": user.roles[0] if user.roles else "",
        "proposed_by": user.email,
    }
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(f"{COPILOT_URL}/ask", json=payload)
            resp.raise_for_status()
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status.HTTP_504_GATEWAY_TIMEOUT, "copilot took too long to answer, try again"
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "copilot service is not deployed (ai profile not running)"
        ) from exc

    return CopilotAskResponse(**resp.json())
