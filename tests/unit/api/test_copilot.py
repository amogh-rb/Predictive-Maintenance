"""api/api/routers/copilot.py: proxies to the `copilot` service and maps any
connection failure to 404, matching what web/src/pages/CopilotPage.tsx
(session 7) already treats as "not deployed yet"; a slow-but-live request
maps to 504 instead, so a real multi-tool-call Gemini exchange (confirmed
live to sometimes take 30-60s+) isn't shown as "not deployed".
"""
import httpx
from fastapi.testclient import TestClient

from api.api import deps
from api.api.app import app
from api.infra.auth import CurrentUser


FAKE_TENANT_ID = "6fce1e9a-406c-4a3d-92d6-076de1e80b5e"


def _client_as(roles: list[str], monkeypatch) -> TestClient:
    app.dependency_overrides[deps.get_current_user] = lambda: CurrentUser(
        sub="user-1", email="manager@demo", tenant="demo", roles=roles
    )
    app.dependency_overrides[deps.rate_limited] = lambda: None
    # copilot.py resolves the JWT's tenant *name* to a uuid itself (it isn't
    # behind get_session, so that dependency's own resolution doesn't apply
    # here) — mocked so these tests don't need a real Postgres connection.
    monkeypatch.setattr("api.api.routers.copilot.db.resolve_tenant_id", lambda name: FAKE_TENANT_ID)
    return TestClient(app)


def teardown_function(_fn) -> None:
    app.dependency_overrides.clear()


def test_ask_requires_auth_when_no_token():
    client = TestClient(app)
    resp = client.post("/v1/copilot/ask", json={"message": "hi"})
    assert resp.status_code in (401, 403)


def test_ask_returns_404_when_copilot_unreachable(monkeypatch):
    # httpx.AsyncClient itself isn't mocked: copilot's compose service (ai
    # profile) isn't running in a unit test, so this exercises the real
    # connection-failure -> 404 mapping.
    client = _client_as(["fleet_manager"], monkeypatch)
    resp = client.post("/v1/copilot/ask", json={"message": "which trucks are at risk?"})
    assert resp.status_code == 404


def test_ask_returns_504_on_timeout_not_404(monkeypatch):
    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, json):
            raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr("api.api.routers.copilot.httpx.AsyncClient", FakeAsyncClient)

    client = _client_as(["fleet_manager"], monkeypatch)
    resp = client.post("/v1/copilot/ask", json={"message": "which trucks are at risk?"})

    assert resp.status_code == 504


def test_ask_forwards_tenant_role_and_returns_reply(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"reply": "3 trucks at risk in Chennai"}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, json):
            captured["url"] = url
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr("api.api.routers.copilot.httpx.AsyncClient", FakeAsyncClient)

    client = _client_as(["fleet_manager"], monkeypatch)
    resp = client.post("/v1/copilot/ask", json={"message": "which trucks are at risk?"})

    assert resp.status_code == 200
    assert resp.json() == {"reply": "3 trucks at risk in Chennai"}
    assert captured["json"]["tenant"] == FAKE_TENANT_ID  # resolved uuid, not the JWT's tenant name
    assert captured["json"]["role"] == "fleet_manager"
    assert captured["json"]["proposed_by"] == "manager@demo"
