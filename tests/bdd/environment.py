"""behave environment for FleetPulse's BDD suite (PLAN §5). Every scenario
here exercises the real, already-running `core` compose stack (localhost
ports from `.env.example`) rather than mocks — same "live verification"
style every session's own manual checks have used. If the stack isn't up,
scenarios are skipped with a clear reason instead of failing, so `make test`
still works on a machine that hasn't run `make up`.
"""
from __future__ import annotations

import httpx

API_URL = "http://localhost:8000"
KEYCLOAK_URL = "http://localhost:8082"


def _stack_is_up() -> bool:
    try:
        resp = httpx.get(f"{API_URL}/healthz", timeout=3.0)
        return resp.status_code == 200
    except httpx.HTTPError:
        return False


def before_all(context) -> None:
    context.stack_up = _stack_is_up()
    context.api_url = API_URL
    context.keycloak_url = KEYCLOAK_URL
    context._token_cache: dict[str, str] = {}


def before_scenario(context, scenario) -> None:
    if not context.stack_up:
        scenario.skip("core compose stack not reachable at localhost:8000 — run `make up` first")
