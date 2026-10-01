"""AlertStore's VIN -> tenant index must not depend on row-level security: the state-writer's DB role
bypasses RLS, so a bare `SELECT ... FROM vehicle` returns every tenant's vehicles on each pass."""
from state_writer.infra import postgres_store

VEHICLES = {  # tenant -> [(vin, vehicle_id)]
    "tenant-a": [("VIN-A1", "veh-a1"), ("VIN-A2", "veh-a2")],
    "tenant-b": [("VIN-B1", "veh-b1")],
}


class FakeCursor:
    """Behaves like a role that bypasses RLS: ignores app.tenant_id and only honours an explicit filter."""

    def __init__(self):
        self._rows = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        if sql.startswith("SELECT id FROM tenant"):
            self._rows = [(t,) for t in VEHICLES]
        elif "FROM vehicle" in sql:
            if "WHERE tenant_id" in sql:
                self._rows = list(VEHICLES[params[0]])
            else:
                self._rows = [row for rows in VEHICLES.values() for row in rows]
        else:
            self._rows = []

    def fetchall(self):
        return self._rows


class FakeConnection:
    def cursor(self):
        return FakeCursor()


def test_vin_index_maps_each_vin_to_its_own_tenant(monkeypatch):
    monkeypatch.setattr(postgres_store.psycopg, "connect", lambda **kw: FakeConnection())

    store = postgres_store.AlertStore("h", 5432, "db", "u", "p")

    assert store._vin_index["VIN-A1"] == ("tenant-a", "veh-a1")
    assert store._vin_index["VIN-A2"] == ("tenant-a", "veh-a2")
    assert store._vin_index["VIN-B1"] == ("tenant-b", "veh-b1")
