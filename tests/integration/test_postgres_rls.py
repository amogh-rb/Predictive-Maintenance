"""Integration test: real Postgres, real RLS (PLAN §5 "Integration:
Testcontainers"). Session 3 verified this by hand once against the running
`core` stack; this automates the same proof — a non-superuser,
NOBYPASSRLS role genuinely cannot read another tenant's rows, and can read
its own once `app.tenant_id` is set — so a future migration change that
weakens a policy fails CI instead of waiting to be caught by hand again.

Spins an ephemeral `pgvector/pgvector:pg16` container (same image as the
real `postgres` service), applies migrations 001-005 in order, then proves
RLS the same way `db/postgres/seed_fleet.py` / `services/state-writer`'s
`AlertStore` do it: `SELECT set_config('app.tenant_id', ..., false)` inside
each transaction.
"""
from __future__ import annotations

from pathlib import Path

import psycopg
import pytest
from testcontainers.community.postgres import PostgresContainer

MIGRATIONS_DIR = Path(__file__).parents[2] / "db" / "postgres" / "migrations"
MIGRATION_FILES = [
    "001_extensions.sql",
    "002_core_schema.sql",
    "003_indexes.sql",
    "004_rls.sql",
    "005_api_role.sql",
    "008_metabase_role.sql",
]


@pytest.fixture(scope="module")
def pg_conn_params():
    with PostgresContainer("pgvector/pgvector:pg16", username="fleetpulse", password="changeme", dbname="fleetpulse") as pg:
        params = dict(
            host=pg.get_container_host_ip(),
            port=int(pg.get_exposed_port(5432)),
            dbname="fleetpulse",
            user="fleetpulse",
            password="changeme",
        )
        with psycopg.connect(**params, autocommit=True) as conn:
            for filename in MIGRATION_FILES:
                sql = (MIGRATIONS_DIR / filename).read_text()
                conn.execute(sql)
        yield params


@pytest.fixture(scope="module")
def two_tenants_one_vehicle_each(pg_conn_params):
    """Seeds two tenants as the superuser connection (bypasses RLS, same as
    `POSTGRES_USER` in docker-compose.yml — session 3's note on why the API's
    own DB role must not be that user)."""
    with psycopg.connect(**pg_conn_params, autocommit=True) as conn:
        tenant_ids = {}
        vins = {"tenant-a": "1HGCM82633A00001", "tenant-b": "1HGCM82633A00002"}
        for name in ("tenant-a", "tenant-b"):
            row = conn.execute(
                "INSERT INTO tenant (name) VALUES (%s) RETURNING id", (name,)
            ).fetchone()
            tenant_ids[name] = row[0]
            depot = conn.execute(
                "INSERT INTO depot (tenant_id, name, city, lat, lon) "
                "VALUES (%s, 'Depot', 'City', 0, 0) RETURNING id",
                (tenant_ids[name],),
            ).fetchone()[0]
            model = conn.execute(
                "INSERT INTO vehicle_model (make, model, vehicle_type, tyre_count) "
                "VALUES ('Acme', %s, 'ICE', 6) RETURNING id",
                (f"T1-{name}",),
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO vehicle (tenant_id, vin, vehicle_model_id, depot_id, fw_version, status) "
                "VALUES (%s, %s, %s, %s, '1.0.0', 'active')",
                (tenant_ids[name], vins[name], model, depot),
            )
        return {"ids": tenant_ids, "vins": vins}


def _as_role(pg_conn_params, tenant_id: str | None):
    """Connects as `fleetpulse_api` (session 6's NOSUPERUSER NOBYPASSRLS
    role, created by migration 005) — the same role the real API and
    state-writer use, never the superuser."""
    conn = psycopg.connect(
        host=pg_conn_params["host"], port=pg_conn_params["port"],
        dbname=pg_conn_params["dbname"], user="fleetpulse_api", password="changeme",
        autocommit=True,
    )
    if tenant_id is not None:
        conn.execute("SELECT set_config('app.tenant_id', %s, false)", (str(tenant_id),))
    return conn


def test_no_tenant_context_sees_nothing(pg_conn_params, two_tenants_one_vehicle_each):
    with _as_role(pg_conn_params, tenant_id=None) as conn:
        rows = conn.execute("SELECT * FROM vehicle").fetchall()
    assert rows == []


def test_tenant_a_cannot_see_tenant_b(pg_conn_params, two_tenants_one_vehicle_each):
    tenant_a = two_tenants_one_vehicle_each["ids"]["tenant-a"]
    with _as_role(pg_conn_params, tenant_id=tenant_a) as conn:
        seen_vins = {row[0].rstrip() for row in conn.execute("SELECT vin FROM vehicle").fetchall()}
    assert seen_vins == {two_tenants_one_vehicle_each["vins"]["tenant-a"]}


def test_tenant_sees_only_its_own_row_count(pg_conn_params, two_tenants_one_vehicle_each):
    for name, tenant_id in two_tenants_one_vehicle_each["ids"].items():
        with _as_role(pg_conn_params, tenant_id=tenant_id) as conn:
            count = conn.execute("SELECT count(*) FROM vehicle").fetchone()[0]
        assert count == 1, f"{name} should see exactly its own 1 vehicle"


def test_metabase_reporting_bypasses_rls_by_design(pg_conn_params, two_tenants_one_vehicle_each):
    """The inverse of the tests above: db/postgres/migrations/008_metabase_role.sql
    grants `metabase_reporting` BYPASSRLS specifically so Metabase's pooled
    connections (no per-request `SET LOCAL app.tenant_id`) can read
    cross-tenant. Asserting that here pins it as documented, intentional
    behavior — a future change that accidentally drops BYPASSRLS should fail
    this test, not silently break the analytics dashboard.
    """
    conn = psycopg.connect(
        host=pg_conn_params["host"], port=pg_conn_params["port"],
        dbname=pg_conn_params["dbname"], user="metabase_reporting", password="changeme",
        autocommit=True,
    )
    with conn:
        # No app.tenant_id set at all — an RLS-bound role would see zero rows
        # (test_no_tenant_context_sees_nothing above proves that for
        # fleetpulse_api); metabase_reporting must see both tenants' vehicles.
        seen_vins = {row[0].rstrip() for row in conn.execute("SELECT vin FROM vehicle").fetchall()}
    assert seen_vins == set(two_tenants_one_vehicle_each["vins"].values())
