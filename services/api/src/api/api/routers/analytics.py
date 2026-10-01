"""Signed Metabase dashboard embedding (analytics refinement, before session
10). Metabase's `MB_EMBEDDING_SECRET_KEY` must never reach the browser, so
this router — not the web app — signs the iframe URL server-side, keeping
CLAUDE.md's "tenant/role always comes from the JWT server-side" convention
even though the underlying Metabase connection (metabase_reporting,
db/postgres/migrations/008_metabase_role.sql) is itself cross-tenant: access
to *this endpoint* is still RBAC-gated (VIEW_ANALYTICS, fleet_admin/
fleet_manager only, api/domain/rbac.py).

Mirrors routers/copilot.py's shape: a connection failure to `metabase` (obs
profile not running) maps to 404, the same "not deployed yet" contract the
web app already understands from the copilot screen.
"""
from __future__ import annotations

import os
import time

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.api.deps import rate_limited, require_action
from api.api.schemas import AnalyticsEmbedResponse
from api.domain import rbac
from api.infra.auth import CurrentUser

router = APIRouter(prefix="/v1/analytics", tags=["analytics"])

METABASE_INTERNAL_URL = os.environ.get("METABASE_INTERNAL_URL", "http://metabase:3000")
METABASE_SITE_URL = os.environ.get("METABASE_SITE_URL", "http://localhost:3002")
METABASE_ADMIN_EMAIL = os.environ.get("METABASE_ADMIN_EMAIL", "admin@demo.fleetpulse")
METABASE_ADMIN_PASSWORD = os.environ.get("METABASE_ADMIN_PASSWORD", "changeme123")
MB_EMBEDDING_SECRET_KEY = os.environ.get("MB_EMBEDDING_SECRET_KEY", "")
EMBED_TTL_SECONDS = 600

# Dashboard-name -> id, resolved lazily against Metabase's own admin API
# (infra/compose/metabase-provision.py creates it, but doesn't pin an id —
# Metabase assigns one). Cached for the process lifetime: re-provisioning
# would only happen alongside a service restart in this POC.
_dashboard_id_cache: dict[str, int] = {}


def _metabase_session_id(client: httpx.Client) -> str:
    resp = client.post(
        "/api/session",
        json={"username": METABASE_ADMIN_EMAIL, "password": METABASE_ADMIN_PASSWORD},
    )
    resp.raise_for_status()
    return resp.json()["id"]


def _resolve_dashboard_id(name: str) -> int:
    if name in _dashboard_id_cache:
        return _dashboard_id_cache[name]

    with httpx.Client(base_url=METABASE_INTERNAL_URL, timeout=10.0) as client:
        session_id = _metabase_session_id(client)
        resp = client.get("/api/dashboard", headers={"X-Metabase-Session": session_id})
        resp.raise_for_status()
        for dash in resp.json():
            if dash["name"] == name:
                _dashboard_id_cache[name] = dash["id"]
                return dash["id"]
    raise HTTPException(status.HTTP_404_NOT_FOUND, f"no metabase dashboard named {name!r}")


_DASHBOARD_NAMES = {"fleet-overview": "Fleet Overview"}


@router.get("/embed-url", response_model=AnalyticsEmbedResponse)
def get_embed_url(
    dashboard: str = Query("fleet-overview"),
    _rl: None = Depends(rate_limited),
    _user: CurrentUser = Depends(require_action(rbac.Action.VIEW_ANALYTICS)),
) -> dict:
    name = _DASHBOARD_NAMES.get(dashboard)
    if name is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown dashboard {dashboard!r}")

    if not MB_EMBEDDING_SECRET_KEY:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "analytics is not deployed (obs profile not running, or metabase-init not run yet)",
        )

    try:
        dashboard_id = _resolve_dashboard_id(name)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "analytics is not deployed (obs profile not running)"
        ) from exc

    payload = {
        "resource": {"dashboard": dashboard_id},
        "params": {},
        "exp": round(time.time()) + EMBED_TTL_SECONDS,
    }
    token = jwt.encode(payload, MB_EMBEDDING_SECRET_KEY, algorithm="HS256")
    return {"embed_url": f"{METABASE_SITE_URL}/embed/dashboard/{token}#bordered=true&titled=true"}
