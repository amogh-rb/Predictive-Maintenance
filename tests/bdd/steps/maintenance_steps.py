from __future__ import annotations

import psycopg
from behave import then, when

from util import api_get, api_post

PG = dict(host="localhost", port=5434, dbname="fleetpulse", user="fleetpulse", password="changeme")


def _cleanup_vehicle_bookings(vehicle_id: str) -> None:
    """Remove the work orders/bookings this scenario made, so the vehicle returns to the at-risk list
    for the other scenarios (and the demo). Bookings are only ever created by these steps for the
    vehicle picked in the scenario's Given step."""
    with psycopg.connect(**PG, autocommit=True) as conn:
        conn.execute(
            "DELETE FROM depot_booking WHERE vehicle_id = %s AND created_at > now() - interval '10 minutes'",
            (vehicle_id,),
        )
        conn.execute(
            "DELETE FROM work_order WHERE vehicle_id = %s AND created_at > now() - interval '10 minutes' "
            "AND proposed_by LIKE 'manager@%%'",
            (vehicle_id,),
        )


def _ids(context, path: str, role: str = "fleet_manager") -> set[str]:
    resp = api_get(context, path, role=role)
    assert resp.status_code == 200, resp.text
    return {i["vehicle_id"] for i in resp.json()["items"]}


@when('"{role}" schedules maintenance for that vehicle')
def step_schedule(context, role):
    context.add_cleanup(_cleanup_vehicle_bookings, context.vehicle_id)
    context.response = api_post(context, f"/v1/maintenance/schedule/{context.vehicle_id}", role=role)
    if context.response.status_code == 201:
        context.scheduled_work_order_id = context.response.json()["work_order_id"]


@then("the booking is created at a depot")
def step_booking_created(context):
    assert context.response.status_code == 201, context.response.text
    body = context.response.json()
    assert body["depot_id"] and body["booking_id"] and body["work_order_id"], body


@then("that vehicle is no longer in the at-risk list")
def step_not_in_at_risk(context):
    assert context.vehicle_id not in _ids(context, "/v1/vehicles/at-risk?limit=200")


@then("that vehicle is in the maintenance scheduled list")
def step_in_scheduled(context):
    assert context.vehicle_id in _ids(context, "/v1/maintenance/scheduled?limit=500")


@when('"{role}" marks that maintenance serviced')
def step_mark_serviced(context, role):
    context.response = api_post(
        context, f"/v1/maintenance/{context.scheduled_work_order_id}/complete", role=role
    )
    assert context.response.status_code == 200, context.response.text


@then("that vehicle is not in the maintenance scheduled list")
def step_not_in_scheduled(context):
    assert context.vehicle_id not in _ids(context, "/v1/maintenance/scheduled?limit=500")
