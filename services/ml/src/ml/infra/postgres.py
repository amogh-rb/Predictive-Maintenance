"""Postgres access for the ML app layer — vehicle_id lookups, prediction
writes, and DTC KB / failure-signature writes. Same host-external connection
convention as `db/postgres/seed_fleet.py` (this runs on the host, not in a
container).
"""
from __future__ import annotations

import os
from typing import Iterable

import psycopg


def connect() -> psycopg.Connection:
    return psycopg.connect(
        host=os.getenv("POSTGRES_HOST_EXTERNAL", "localhost"),
        port=os.getenv("POSTGRES_PORT_EXTERNAL", "5434"),
        dbname=os.getenv("POSTGRES_DB", "fleetpulse"),
        user=os.getenv("POSTGRES_USER", "fleetpulse"),
        password=os.getenv("POSTGRES_PASSWORD", "changeme"),
    )


def tenant_id(conn: psycopg.Connection, tenant_name: str) -> str:
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM tenant WHERE name = %s", (tenant_name,))
        row = cur.fetchone()
        if row is None:
            raise RuntimeError(f"tenant {tenant_name!r} not found — run `make seed` first")
        return str(row[0])


def vehicle_ids_by_vin(conn: psycopg.Connection, tenant: str) -> dict[str, str]:
    """RLS-scoped: caller must have already set app.tenant_id on this connection."""
    with conn.cursor() as cur:
        cur.execute("SELECT vin, id FROM vehicle")
        return {vin: str(vid) for vin, vid in cur.fetchall()}


def set_tenant(conn: psycopg.Connection, tid: str) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT set_config('app.tenant_id', %s, false)", (tid,))


def write_predictions(conn: psycopg.Connection, tid: str, rows: Iterable[dict]) -> int:
    """Each row: vehicle_id, failure_type, risk_score, lead_days, model_version, feature_vector (list[float])."""
    n = 0
    with conn.cursor() as cur:
        for r in rows:
            cur.execute(
                "INSERT INTO prediction "
                "(tenant_id, vehicle_id, failure_type, risk_score, lead_days, model_version, feature_vector) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s::vector)",
                (
                    tid, r["vehicle_id"], r["failure_type"], r["risk_score"],
                    r.get("lead_days"), r["model_version"],
                    "[" + ",".join(f"{x:.6f}" for x in r["feature_vector"]) + "]",
                ),
            )
            n += 1
    conn.commit()
    return n


def write_dtc_kb(conn: psycopg.Connection, rows: Iterable[tuple[str, str, list[float]]]) -> int:
    n = 0
    with conn.cursor() as cur:
        for code, description, embedding in rows:
            cur.execute(
                "INSERT INTO dtc_kb (code, description, embedding) VALUES (%s, %s, %s::vector) "
                "ON CONFLICT (code) DO UPDATE SET description = EXCLUDED.description, embedding = EXCLUDED.embedding",
                (code, description, "[" + ",".join(f"{x:.6f}" for x in embedding) + "]"),
            )
            n += 1
    conn.commit()
    return n


def write_failure_signatures(conn: psycopg.Connection, rows: Iterable[tuple[str, str, list[float]]]) -> int:
    n = 0
    with conn.cursor() as cur:
        cur.execute("DELETE FROM failure_signature")  # small static table, safe to replace wholesale
        for failure_type, description, embedding in rows:
            cur.execute(
                "INSERT INTO failure_signature (failure_type, description, embedding) VALUES (%s, %s, %s::vector)",
                (failure_type, description, "[" + ",".join(f"{x:.6f}" for x in embedding) + "]"),
            )
            n += 1
    conn.commit()
    return n
