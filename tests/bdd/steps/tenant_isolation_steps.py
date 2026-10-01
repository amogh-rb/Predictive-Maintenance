from __future__ import annotations

import uuid

import psycopg
from behave import given, then, when

from util import api_get

PG = dict(host="localhost", port=5434, dbname="fleetpulse", user="fleetpulse", password="changeme")


def _remove_rogue_tenant(tenant_id, model_id) -> None:
    """Undo everything the Given step created. Left behind, each run adds a tenant, and the state-writer
    can then file real alerts under it (see AlertStore._load_vin_index)."""
    with psycopg.connect(**PG, autocommit=True) as conn:
        conn.execute("DELETE FROM alert WHERE tenant_id = %s", (tenant_id,))
        conn.execute("DELETE FROM vehicle WHERE tenant_id = %s", (tenant_id,))
        conn.execute("DELETE FROM depot WHERE tenant_id = %s", (tenant_id,))
        conn.execute("DELETE FROM tenant WHERE id = %s", (tenant_id,))
        conn.execute("DELETE FROM vehicle_model WHERE id = %s", (model_id,))


@given("a rogue alert planted for a brand-new second tenant")
def step_plant_rogue_alert(context):
    context.rogue_vin = "1" + uuid.uuid4().hex[:16].upper()
    with psycopg.connect(**PG, autocommit=True) as conn:
        tenant_id = conn.execute(
            "INSERT INTO tenant (name) VALUES (%s) RETURNING id", (f"rogue-{uuid.uuid4().hex[:8]}",)
        ).fetchone()[0]
        depot_id = conn.execute(
            "INSERT INTO depot (tenant_id, name, city, lat, lon) VALUES (%s, 'Rogue Depot', 'Nowhere', 0, 0) "
            "RETURNING id",
            (tenant_id,),
        ).fetchone()[0]
        model_id = conn.execute(
            "INSERT INTO vehicle_model (make, model, vehicle_type, tyre_count) "
            "VALUES ('Rogue', %s, 'ICE', 6) RETURNING id",
            (uuid.uuid4().hex,),
        ).fetchone()[0]
        vehicle_id = conn.execute(
            "INSERT INTO vehicle (tenant_id, vin, vehicle_model_id, depot_id, fw_version, status) "
            "VALUES (%s, %s, %s, %s, '1.0.0', 'active') RETURNING id",
            (tenant_id, context.rogue_vin, model_id, depot_id),
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO alert (tenant_id, vehicle_id, failure_type, severity, source, dtc_codes) "
            "VALUES (%s, %s, 'cooling', 'critical', 'realtime', ARRAY['P0128'])",
            (tenant_id, vehicle_id),
        )
    context.add_cleanup(_remove_rogue_tenant, tenant_id, model_id)


@when('"{role}" lists open alerts')
def step_list_alerts(context, role):
    context.response = api_get(context, "/v1/alerts", role=role)


@then("none of the returned alerts belong to the rogue tenant")
def step_check_not_leaked(context):
    assert context.response.status_code == 200, context.response.text
    vins = {row["vin"] for row in context.response.json()}
    assert context.rogue_vin not in vins
