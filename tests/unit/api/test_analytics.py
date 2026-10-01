"""api/api/routers/analytics.py: signed Metabase embed-url endpoint. RBAC
(fleet_admin/fleet_manager only), the connection-failure-maps-to-404
contract (same as test_copilot.py's), and that the returned URL is actually
signed with MB_EMBEDDING_SECRET_KEY rather than leaking a raw dashboard link.
"""
import jwt
from fastapi.testclient import TestClient

from api.api import deps
from api.api.app import app
from api.api.routers import analytics
from api.infra.auth import CurrentUser


def _client_as(roles: list[str]) -> TestClient:
    app.dependency_overrides[deps.get_current_user] = lambda: CurrentUser(
        sub="user-1", email="manager@demo", tenant="demo", roles=roles
    )
    app.dependency_overrides[deps.rate_limited] = lambda: None
    return TestClient(app)


def teardown_function(_fn) -> None:
    app.dependency_overrides.clear()
    analytics._dashboard_id_cache.clear()


def test_embed_url_requires_auth_when_no_token():
    client = TestClient(app)
    resp = client.get("/v1/analytics/embed-url")
    assert resp.status_code in (401, 403)


def test_technician_forbidden_from_analytics():
    client = _client_as(["technician"])
    resp = client.get("/v1/analytics/embed-url")
    assert resp.status_code == 403


def test_returns_404_when_embedding_secret_not_configured(monkeypatch):
    monkeypatch.setattr(analytics, "MB_EMBEDDING_SECRET_KEY", "")
    client = _client_as(["fleet_manager"])
    resp = client.get("/v1/analytics/embed-url")
    assert resp.status_code == 404


def test_returns_404_when_metabase_unreachable(monkeypatch):
    # metabase (obs profile) genuinely isn't running in a unit test, so this
    # exercises the real connection-failure -> 404 mapping, same contract as
    # test_copilot.py's equivalent test.
    monkeypatch.setattr(analytics, "MB_EMBEDDING_SECRET_KEY", "test-secret")
    client = _client_as(["fleet_manager"])
    resp = client.get("/v1/analytics/embed-url")
    assert resp.status_code == 404


def test_returns_signed_embed_url(monkeypatch):
    monkeypatch.setattr(analytics, "MB_EMBEDDING_SECRET_KEY", "test-secret")
    monkeypatch.setattr(analytics, "METABASE_SITE_URL", "http://localhost:3002")
    monkeypatch.setattr(analytics, "_resolve_dashboard_id", lambda name: 7)

    client = _client_as(["fleet_admin"])
    resp = client.get("/v1/analytics/embed-url")

    assert resp.status_code == 200
    embed_url = resp.json()["embed_url"]
    assert embed_url.startswith("http://localhost:3002/embed/dashboard/")

    token = embed_url.split("/embed/dashboard/")[1].split("#")[0]
    claims = jwt.decode(token, "test-secret", algorithms=["HS256"])
    assert claims["resource"] == {"dashboard": 7}


def test_unknown_dashboard_name_returns_404(monkeypatch):
    monkeypatch.setattr(analytics, "MB_EMBEDDING_SECRET_KEY", "test-secret")
    client = _client_as(["fleet_manager"])
    resp = client.get("/v1/analytics/embed-url", params={"dashboard": "not-a-real-one"})
    assert resp.status_code == 404
