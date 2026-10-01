"""Shared helpers for step defs — not a step file itself (no @given/@when),
so behave won't try to load decorators from it; steps import it directly.
"""
from __future__ import annotations

import httpx

DEMO_USERS = {
    "fleet_admin": "admin@demo",
    "fleet_manager": "manager@demo",
    "technician": "tech@demo",
    "auditor": "audit@demo",
}
DEMO_PASSWORD = "changeme"


def token_for(context, role: str) -> str:
    if role in context._token_cache:
        return context._token_cache[role]
    resp = httpx.post(
        f"{context.keycloak_url}/realms/fleetpulse/protocol/openid-connect/token",
        data={
            "grant_type": "password",
            "client_id": "fleetpulse-web",
            "username": DEMO_USERS[role],
            "password": DEMO_PASSWORD,
        },
        timeout=10.0,
    )
    resp.raise_for_status()
    token = resp.json()["access_token"]
    context._token_cache[role] = token
    return token


def api_get(context, path: str, role: str, **kwargs) -> httpx.Response:
    return httpx.get(
        f"{context.api_url}{path}",
        headers={"Authorization": f"Bearer {token_for(context, role)}"},
        timeout=10.0,
        **kwargs,
    )


def api_post(context, path: str, role: str, json: dict | None = None, **kwargs) -> httpx.Response:
    return httpx.post(
        f"{context.api_url}{path}",
        headers={"Authorization": f"Bearer {token_for(context, role)}"},
        json=json,
        timeout=10.0,
        **kwargs,
    )
