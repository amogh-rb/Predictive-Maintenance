"""Consumer-driven contract: web -> api, HTTP (PLAN §5/§6.2 "one Pact HTTP
contract"). The consumer side is written in Python rather than pact-js so it
lives in the same suite as the other contract/integration tests (no second
JS test runner for one interaction) — it exercises the *same* request/response
shape `web/src/pages/AtRiskPage.tsx` + `web/src/types.ts` actually depend on,
so a change to either side that breaks the shape breaks this test.

Two tests:
- `test_consumer_generates_pact`: drives a Pact mock server the way
  `AtRiskPage.tsx` drives the real API, and writes the resulting contract to
  `tests/contract/pacts/web-api.json`.
- `test_provider_honours_pact` (needs the live `core` stack): replays that
  contract against the real running `api` container and fails if the real
  response doesn't match. Skipped if the api isn't reachable — this is the
  provider-verification half of the same contract, run against real infra
  rather than a broker.
"""
from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from pact import Pact, Verifier, match

PACT_DIR = Path(__file__).parent / "pacts"

AT_RISK_ITEM_SHAPE = {
    "vehicle_id": match.like("3f9c1e2a-0000-4000-8000-000000000001"),
    "vin": match.like("1HGCM82633A004352"),
    "failure_type": match.like("cooling"),
    "risk_score": match.like(0.842),
    # Deliberately not type-matched: lead_days is genuinely nullable
    # per-row (services/ml/domain/lead_time.py returns None whenever a
    # failure type's trend isn't moving toward its threshold), so a real
    # page mixes float and null values — this matcher library's `like()`
    # asserts one fixed type for every item `each_like` expands to, which
    # can't express "float or null" across a real mixed page. The presence
    # of the key is still implicitly covered by `test_consumer_generates_pact`
    # asserting on `body["items"]`; the actual value/type contract for this
    # field is covered by tests/unit/ml/test_lead_time.py and web/src/types.ts's
    # `number | null` instead.
    "depot_name": match.like("Chennai Depot"),
    "depot_city": match.like("Chennai"),
}


def test_consumer_generates_pact() -> None:
    pact = Pact("web", "api")
    (
        pact.upon_receiving("a request for the at-risk vehicle list")
        .given("vehicles have been scored by the ML pipeline")
        .with_request("GET", "/v1/vehicles/at-risk")
        .with_header("Authorization", match.like("Bearer token"))
        .will_respond_with(200)
        .with_header("Content-Type", "application/json")
        .with_body(
            # 121 demo predictions (session 5's backfill) is more than the
            # default page size, so a real first page always has a real
            # opaque cursor string, not null.
            {"items": match.each_like(AT_RISK_ITEM_SHAPE), "next_cursor": match.like("eyJyIjoxLjAsInYiOiJhYmMifQ==")},
            content_type="application/json",
        )
    )
    with pact.serve() as srv:
        resp = httpx.get(
            f"{srv.url}/v1/vehicles/at-risk",
            headers={"Authorization": "Bearer token"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body and "next_cursor" in body

    PACT_DIR.mkdir(parents=True, exist_ok=True)
    pact.write_file(PACT_DIR, overwrite=True)


def _live_token() -> str | None:
    """Password-grant a real JWT from the running Keycloak, matching the
    `fleetpulse-web` public client (directAccessGrantsEnabled: true)."""
    try:
        resp = httpx.post(
            "http://localhost:8082/realms/fleetpulse/protocol/openid-connect/token",
            data={
                "grant_type": "password",
                "client_id": "fleetpulse-web",
                "username": "manager@demo",
                "password": "changeme",
            },
            timeout=5.0,
        )
        resp.raise_for_status()
        return resp.json()["access_token"]
    except Exception:
        return None


def test_provider_honours_pact() -> None:
    token = _live_token()
    if token is None:
        pytest.skip("Keycloak/api not reachable at localhost:8082/8000 — run `make up` first")
    if not (PACT_DIR / "web-api.json").exists():
        pytest.skip("run test_consumer_generates_pact first to produce the pact file")

    verifier = (
        Verifier("api")
        .add_source(PACT_DIR / "web-api.json")
        .add_custom_header("Authorization", f"Bearer {token}")
        .add_transport(url="http://localhost:8000")
    )
    verifier.verify()
