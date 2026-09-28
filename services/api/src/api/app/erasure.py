"""Driver erasure (PLAN §2 "Privacy": "erasure endpoint (pseudonymise driver
PII in PG, delete that driver's rows in Timescale, Mongo and Iceberg)").

Scoped to what actually holds driver PII, per fleetcore's envelope design
(PLAN §1: "Not sent: ... driver PII"): Postgres `driver` (pseudonymised, not
deleted — vehicle.primary_driver_id and any work_order history still need
the row to exist) and Mongo `raw_archive` (deleted by driver_token). Neither
Timescale nor the Mongo `vehicle_twin` document ever stored a driver_token,
so there is nothing to erase there — see infra/mongo_client.py.
"""
from __future__ import annotations

from sqlmodel import Session

from api.infra import mongo_client, repositories as repo


class DriverNotFound(Exception):
    pass


def erase_driver(session: Session, driver_id: str) -> dict:
    driver = repo.get_driver(session, driver_id)
    if driver is None:
        raise DriverNotFound(driver_id)

    repo.pseudonymize_driver(session, driver_id)
    archived_deleted = mongo_client.erase_driver_archive(driver["driver_token"])

    return {
        "driver_id": driver_id,
        "postgres_pii_pseudonymized": True,
        "mongo_raw_archive_deleted": archived_deleted,
        "timescale": "not applicable — telemetry carries no driver PII",
    }
