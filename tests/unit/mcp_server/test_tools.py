from contextlib import contextmanager
from decimal import Decimal

from mcp_server.app import tools
from mcp_server.app.tools import _CAN_PROPOSE_WORK_ORDER, _to_vector_literal, propose_work_order


def test_propose_work_order_rejects_disallowed_role():
    # 'auditor' can view but never propose (mirrors api/domain/rbac.py) — this
    # must be rejected before any DB call, so no Postgres connection is needed
    # for this test.
    result = propose_work_order(
        tenant_id="t1", role="auditor", proposed_by="a@demo", vehicle_id="v1"
    )
    assert result == {"proposed": False, "error": "role 'auditor' cannot propose a work order"}


def test_can_propose_work_order_roles_match_api_rbac():
    assert _CAN_PROPOSE_WORK_ORDER == {"fleet_admin", "fleet_manager", "technician"}


def test_to_vector_literal_format():
    assert _to_vector_literal([1.0, -0.5, 0.0]) == "[1.0,-0.5,0.0]"


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, *args, **kwargs):
        return _FakeResult(self._rows)


def test_get_fleet_risk_formats_risk_score_as_percent(monkeypatch):
    # web/src/pages/AtRiskPage.tsx formats risk_score the same way
    # ((item.risk_score * 100).toFixed(1) + '%') — the copilot's data must
    # match, since an LLM won't reliably do this conversion itself (confirmed
    # live: it initially echoed the raw 0-1 fraction as if it were already a
    # percentage).
    rows = [
        {"vehicle_id": "v1", "vin": "VIN1", "failure_type": "cooling", "risk_score": Decimal("1.00000"),
         "lead_days": None, "depot_name": "chennai", "depot_city": "Chennai"},
        {"vehicle_id": "v2", "vin": "VIN2", "failure_type": "brake_wear", "risk_score": Decimal("0.84436"),
         "lead_days": 3, "depot_name": "chennai", "depot_city": "Chennai"},
    ]

    @contextmanager
    def fake_tenant_session(tenant_id):
        yield _FakeSession(rows)

    monkeypatch.setattr(tools.postgres, "tenant_session", fake_tenant_session)

    result = tools.get_fleet_risk(tenant_id="t1", limit=2)

    assert result[0]["risk_percent"] == "100.0%"
    assert result[1]["risk_percent"] == "84.4%"
    assert "risk_score" not in result[0]
