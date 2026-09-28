"""Writes Flink's real-time alerts (`alerts` Kafka topic) into Postgres
`alert` rows (PLAN §2). RLS on `alert` is FORCE'd
(db/postgres/migrations/004_rls.sql) — every insert needs `app.tenant_id` set
for that alert's tenant first, the same pattern db/postgres/seed_fleet.py
uses for seeding.
"""
from __future__ import annotations

from typing import Any

import psycopg


class AlertStore:
    def __init__(self, host: str, port: int, dbname: str, user: str, password: str):
        self._conn = psycopg.connect(
            host=host, port=port, dbname=dbname, user=user, password=password, autocommit=True
        )
        # vin -> (tenant_id, vehicle_id), loaded once at startup: 100K rows is
        # cheap to hold in memory and avoids a per-alert Postgres round trip
        # just to resolve which vehicle an alert belongs to.
        self._vin_index: dict[str, tuple[str, str]] = {}
        self._load_vin_index()

    def _load_vin_index(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute("SELECT id FROM tenant")
            tenant_ids = [row[0] for row in cur.fetchall()]
            for tenant_id in tenant_ids:
                cur.execute("SELECT set_config('app.tenant_id', %s, false)", (str(tenant_id),))
                cur.execute("SELECT vin, id FROM vehicle")
                for vin, vehicle_id in cur.fetchall():
                    self._vin_index[vin] = (str(tenant_id), str(vehicle_id))

    def insert_alert(self, alert: dict[str, Any]) -> bool:
        """Returns False (and skips the insert) for a VIN the loaded index
        doesn't know — e.g. simulator traffic ahead of `make seed`."""
        entry = self._vin_index.get(alert["vin"])
        if entry is None:
            return False
        tenant_id, vehicle_id = entry
        with self._conn.cursor() as cur:
            cur.execute("SELECT set_config('app.tenant_id', %s, false)", (tenant_id,))
            cur.execute(
                "INSERT INTO alert (tenant_id, vehicle_id, failure_type, severity, source, dtc_codes, opened_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (
                    tenant_id, vehicle_id, alert["failure_type"], alert["severity"],
                    alert["source"], alert["dtc_codes"], alert["detected_at"],
                ),
            )
        return True
