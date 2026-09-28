"""Route-level wiring: JWT auth is required, RBAC is enforced per-route, and
the DB/rate-limit dependencies are swappable. `get_current_user`/`get_session`/
`rate_limited` are overridden with fakes; `require_action(...)` is left real,
so this is exercising the actual RBAC decision, not a mock of it.
"""
from fastapi.testclient import TestClient

from api.api import deps
from api.api.app import app
from api.infra.auth import CurrentUser

FAKE_TENANT_ID = "11111111-1111-1111-1111-111111111111"


def _client_as(roles: list[str]) -> TestClient:
    app.dependency_overrides[deps.get_current_user] = lambda: CurrentUser(
        sub="user-1", email="user@demo", tenant="demo", roles=roles
    )
    app.dependency_overrides[deps.get_session] = lambda: iter([object()]).__next__()
    app.dependency_overrides[deps.rate_limited] = lambda: None
    return TestClient(app)


def teardown_function(_fn) -> None:
    app.dependency_overrides.clear()


def test_at_risk_requires_auth_when_no_token():
    client = TestClient(app)  # no overrides: real bearer-token check
    resp = client.get("/v1/vehicles/at-risk")
    assert resp.status_code in (401, 403)  # HTTPBearer 403s on a fully missing header


def test_technician_forbidden_from_at_risk_list(monkeypatch):
    client = _client_as(["technician"])
    resp = client.get("/v1/vehicles/at-risk")
    assert resp.status_code == 403


def test_fleet_manager_allowed_on_at_risk_list(monkeypatch):
    monkeypatch.setattr("api.infra.repositories.list_at_risk", lambda session, limit, cursor: [])
    client = _client_as(["fleet_manager"])
    resp = client.get("/v1/vehicles/at-risk")
    assert resp.status_code == 200
    assert resp.json() == {"items": [], "next_cursor": None}


def test_technician_forbidden_from_erasure():
    client = _client_as(["technician"])
    resp = client.post("/v1/drivers/some-driver/erase")
    assert resp.status_code == 403


def test_fleet_admin_allowed_on_erasure(monkeypatch):
    monkeypatch.setattr(
        "api.infra.repositories.get_driver",
        lambda session, did: {"id": did, "driver_token": "t1", "full_name": "x"},
    )
    monkeypatch.setattr("api.infra.repositories.pseudonymize_driver", lambda session, did: None)
    monkeypatch.setattr("api.infra.mongo_client.erase_driver_archive", lambda token: 0)

    client = _client_as(["fleet_admin"])
    resp = client.post("/v1/drivers/some-driver/erase")
    assert resp.status_code == 200
    assert resp.json()["postgres_pii_pseudonymized"] is True


def test_error_response_is_rfc7807_problem_json():
    client = _client_as(["technician"])
    resp = client.get("/v1/vehicles/at-risk")
    assert resp.headers["content-type"] == "application/problem+json"
    body = resp.json()
    assert body["status"] == 403
    assert "detail" in body
