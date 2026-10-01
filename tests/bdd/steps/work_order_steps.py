from __future__ import annotations

import psycopg
from behave import given, then, when

from util import api_get, api_post

PG = dict(host="localhost", port=5434, dbname="fleetpulse", user="fleetpulse", password="changeme")


@given("a real vehicle from the demo tenant's at-risk list")
def step_pick_vehicle(context):
    resp = api_get(context, "/v1/vehicles/at-risk?limit=1", role="fleet_manager")
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert items, "no at-risk vehicles scored — run `make train` against a real backfill first"
    context.vehicle_id = items[0]["vehicle_id"]


def _delete_work_order(work_order_id: str) -> None:
    with psycopg.connect(**PG, autocommit=True) as conn:
        conn.execute("DELETE FROM work_order WHERE id = %s", (work_order_id,))


@given("the copilot has proposed a work order for that vehicle")
def step_copilot_proposes(context):
    # Same row the MCP server's `propose_work_order` tool writes: status 'proposed', proposed_by the
    # copilot's user. There is no REST endpoint for proposing any more; this is the only source.
    with psycopg.connect(**PG, autocommit=True) as conn:
        row = conn.execute(
            "INSERT INTO work_order (tenant_id, vehicle_id, status, proposed_by) "
            "SELECT tenant_id, id, 'proposed', 'copilot' FROM vehicle WHERE id = %s RETURNING id",
            (context.vehicle_id,),
        ).fetchone()
    context.work_order_id = str(row[0])
    context.add_cleanup(_delete_work_order, context.work_order_id)


@when('"{role}" tries to approve that work order')
@when('"{role}" approves that work order')
def step_approve(context, role):
    context.response = api_post(context, f"/v1/work-orders/{context.work_order_id}/approve", role=role)


@then('the work order status becomes "{expected}"')
def step_final_status(context, expected):
    assert context.response.status_code == 200, context.response.text
    assert context.response.json()["status"] == expected
