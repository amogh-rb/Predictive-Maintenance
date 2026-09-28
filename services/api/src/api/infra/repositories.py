"""SQL against the RLS-scoped session (`db.tenant_session`) plus the Redis
mirror of each vehicle's live twin (session 4's state-writer,
`vehicle:latest:{vin}`). One query per use case, no ORM mapped classes —
these tables are owned by earlier sessions' raw-SQL migrations, and keeping
the queries explicit makes it obvious exactly which columns cross the
RLS/masking boundary into a response.
"""
from __future__ import annotations

import json
from typing import Any

from redis import Redis
from sqlmodel import Session, text

from api.domain.pagination import RiskCursor


def list_at_risk(session: Session, limit: int, cursor: RiskCursor | None) -> list[dict[str, Any]]:
    """Keyset page over `vehicle_latest_risk` (migration 007): a plain
    indexed range scan, no OFFSET, no per-row N+1 lookup — the join to
    vehicle/depot happens once, in this one query.
    """
    where_cursor = ""
    params: dict[str, Any] = {"limit": limit}
    if cursor is not None:
        where_cursor = "AND (r.risk_score, r.vehicle_id) < (:c_risk, :c_vid)"
        params["c_risk"] = cursor.risk_score
        params["c_vid"] = cursor.vehicle_id

    rows = session.execute(
        text(f"""
            SELECT r.vehicle_id, v.vin, r.failure_type, r.risk_score, r.lead_days,
                   d.name AS depot_name, d.city AS depot_city
            FROM vehicle_latest_risk r
            JOIN vehicle v ON v.id = r.vehicle_id
            JOIN depot d ON d.id = v.depot_id
            WHERE true {where_cursor}
            ORDER BY r.risk_score DESC, r.vehicle_id DESC
            LIMIT :limit
        """),
        params,
    ).mappings().all()
    return [dict(r) for r in rows]


def get_vehicle(session: Session, vehicle_id: str) -> dict[str, Any] | None:
    row = session.execute(
        text("""
            SELECT v.id, v.vin, v.status, v.fw_version,
                   vm.make, vm.model, vm.vehicle_type,
                   d.id AS depot_id, d.name AS depot_name, d.city AS depot_city,
                   d.lat AS depot_lat, d.lon AS depot_lon,
                   dr.full_name AS driver_name
            FROM vehicle v
            JOIN vehicle_model vm ON vm.id = v.vehicle_model_id
            JOIN depot d ON d.id = v.depot_id
            LEFT JOIN driver dr ON dr.id = v.primary_driver_id
            WHERE v.id = :id
        """),
        {"id": vehicle_id},
    ).mappings().first()
    return dict(row) if row else None


def get_vehicle_twin(redis_client: Redis, vin: str) -> dict[str, Any] | None:
    raw = redis_client.get(f"vehicle:latest:{vin}")
    return json.loads(raw) if raw else None


def list_alerts(session: Session, open_only: bool, limit: int) -> list[dict[str, Any]]:
    # Uses migration 007's partial index (tenant_id, opened_at DESC)
    # WHERE closed_at IS NULL for the open_only=True case.
    clause = "AND a.closed_at IS NULL" if open_only else ""
    rows = session.execute(
        text(f"""
            SELECT a.id, a.vehicle_id, v.vin, a.failure_type, a.severity, a.source,
                   a.dtc_codes, a.opened_at, a.closed_at
            FROM alert a
            JOIN vehicle v ON v.id = a.vehicle_id
            WHERE true {clause}
            ORDER BY a.opened_at DESC
            LIMIT :limit
        """),
        {"limit": limit},
    ).mappings().all()
    return [dict(r) for r in rows]


def list_depots(session: Session) -> list[dict[str, Any]]:
    rows = session.execute(
        text("""
            SELECT d.id, d.name, d.lat, d.lon, d.bays,
                   COALESCE(active.n, 0) AS active_bookings
            FROM depot d
            LEFT JOIN (
                SELECT depot_id, count(*) AS n
                FROM depot_booking
                WHERE booked_until > now()
                GROUP BY depot_id
            ) active ON active.depot_id = d.id
        """)
    ).mappings().all()
    return [dict(r) for r in rows]


def propose_work_order(
    session: Session, vehicle_id: str, alert_id: str | None, proposed_by: str
) -> str:
    row = session.execute(
        text("""
            INSERT INTO work_order (tenant_id, vehicle_id, alert_id, status, proposed_by)
            VALUES (current_setting('app.tenant_id')::uuid, :vehicle_id, :alert_id, 'proposed', :proposed_by)
            RETURNING id
        """),
        {"vehicle_id": vehicle_id, "alert_id": alert_id, "proposed_by": proposed_by},
    ).first()
    return str(row[0])


def approve_work_order(session: Session, work_order_id: str, approver_user_id: str) -> bool:
    row = session.execute(
        text("""
            UPDATE work_order
            SET status = 'approved', approved_by = :approver, approved_at = now()
            WHERE id = :id AND status = 'proposed'
            RETURNING id
        """),
        {"id": work_order_id, "approver": approver_user_id},
    ).first()
    return row is not None


def book_depot(session: Session, depot_id: str, vehicle_id: str, work_order_id: str | None, hours: int) -> str:
    row = session.execute(
        text("""
            INSERT INTO depot_booking (tenant_id, depot_id, vehicle_id, work_order_id, booked_until)
            VALUES (current_setting('app.tenant_id')::uuid, :depot_id, :vehicle_id, :wo_id,
                    now() + (:hours || ' hours')::interval)
            RETURNING id
        """),
        {"depot_id": depot_id, "vehicle_id": vehicle_id, "wo_id": work_order_id, "hours": hours},
    ).first()
    return str(row[0])


def get_driver(session: Session, driver_id: str) -> dict[str, Any] | None:
    row = session.execute(
        text("SELECT id, driver_token, full_name FROM driver WHERE id = :id"),
        {"id": driver_id},
    ).mappings().first()
    return dict(row) if row else None


def pseudonymize_driver(session: Session, driver_id: str) -> None:
    session.execute(
        text("""
            UPDATE driver
            SET full_name = '[erased]', phone = '[erased]', license_no = '[erased]'
            WHERE id = :id
        """),
        {"id": driver_id},
    )


def list_audit_log(session: Session, limit: int) -> list[dict[str, Any]]:
    rows = session.execute(
        text("""
            SELECT id, actor, action, resource, details, created_at
            FROM audit_log
            ORDER BY created_at DESC
            LIMIT :limit
        """),
        {"limit": limit},
    ).mappings().all()
    return [dict(r) for r in rows]


def write_audit_log(session: Session, actor: str, action: str, resource: str, details: dict) -> None:
    session.execute(
        text("""
            INSERT INTO audit_log (tenant_id, actor, action, resource, details)
            VALUES (current_setting('app.tenant_id')::uuid, :actor, :action, :resource, :details)
        """),
        {"actor": actor, "action": action, "resource": resource, "details": json.dumps(details)},
    )
