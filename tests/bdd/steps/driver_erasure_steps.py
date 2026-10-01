from __future__ import annotations

import uuid
from datetime import datetime, timezone

import psycopg
import pymongo
from behave import given, then, when

from util import api_post

PG = dict(host="localhost", port=5434, dbname="fleetpulse", user="fleetpulse", password="changeme")
MONGO_URI = "mongodb://fleetpulse:changeme@localhost:27018/?authSource=admin"


@given("a freshly seeded driver with archived raw telemetry in Mongo")
def step_seed_driver(context):
    context.driver_token = f"bdd-{uuid.uuid4().hex[:12]}"
    with psycopg.connect(**PG, autocommit=True) as conn:
        tenant_id, depot_id = conn.execute(
            "SELECT id, (SELECT id FROM depot WHERE tenant_id = tenant.id LIMIT 1) FROM tenant WHERE name = 'demo'"
        ).fetchone()
        row = conn.execute(
            "INSERT INTO driver (tenant_id, driver_token, full_name, phone, license_no, depot_id) "
            "VALUES (%s, %s, 'BDD Test Driver', '+91-0000000000', 'DLBDD0001', %s) RETURNING id",
            (tenant_id, context.driver_token, depot_id),
        ).fetchone()
        context.driver_id = str(row[0])

    with pymongo.MongoClient(MONGO_URI) as client:
        client["fleetpulse"]["raw_archive"].insert_one(
            {
                "vin": "1HGCM82633A00099",
                "driver_token": context.driver_token,
                "msg_type": "FAST",
                "ts": datetime.now(timezone.utc).isoformat(),
                "archived_at": datetime.now(timezone.utc),
            }
        )


@when('"{role}" tries to erase that driver')
@when('"{role}" erases that driver')
def step_erase(context, role):
    context.response = api_post(context, f"/v1/drivers/{context.driver_id}/erase", role=role)


@then("the driver's PII is pseudonymised in Postgres")
def step_check_pg_pseudonymised(context):
    assert context.response.status_code == 200, context.response.text
    with psycopg.connect(**PG, autocommit=True) as conn:
        full_name, phone, license_no = conn.execute(
            "SELECT full_name, phone, license_no FROM driver WHERE id = %s", (context.driver_id,)
        ).fetchone()
    assert full_name != "BDD Test Driver"
    assert phone != "+91-0000000000"
    assert license_no != "DLBDD0001"


@then("the driver's raw archive is gone from Mongo")
def step_check_mongo_gone(context):
    with pymongo.MongoClient(MONGO_URI) as client:
        remaining = client["fleetpulse"]["raw_archive"].count_documents({"driver_token": context.driver_token})
    assert remaining == 0
