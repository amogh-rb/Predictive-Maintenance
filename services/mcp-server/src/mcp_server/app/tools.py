"""Business logic behind each MCP tool (PLAN.md §2 "Agentic AI"). Each
function is deliberately thin and reuses tables/views earlier sessions
already built (`vehicle_latest_risk` — session 6, `alert`/`work_order` —
session 3/6, `dtc_kb`/`failure_signature` — session 5, the Redis twin —
session 4, `depot_routing`'s Dijkstra — session 6). No function here accepts
a caller-supplied tenant value from free text: `tenant_id` is always passed
in by `server.py` from the value the copilot already resolved server-side
from the user's JWT, never parsed out of the LLM's own output.

Every tool call writes one `audit_log` row (PLAN §2 guardrail: "everything is
written to the audit log"), same shape as `api/infra/repositories.write_audit_log`.
"""
from __future__ import annotations

import json
from typing import Any

from fleetcore.algorithms.depot_routing import Depot, find_nearest_depot_with_capacity
from sqlmodel import text

from mcp_server.domain.embeddings import embed_text
from mcp_server.infra import postgres, redis_store

# Roles whose copilot session may propose a work order (it still waits for a human approver via the
# API's approve endpoint). Kept here, not imported: mcp-server and api are separate packages, each
# owning its own thin logic against the shared tables.
_CAN_PROPOSE_WORK_ORDER = {"fleet_admin", "fleet_manager", "technician"}


def _audit(session, actor: str, action: str, resource: str, details: dict) -> None:
    session.execute(
        text("""
            INSERT INTO audit_log (tenant_id, actor, action, resource, details)
            VALUES (current_setting('app.tenant_id')::uuid, :actor, :action, :resource, :details)
        """),
        {"actor": actor, "action": action, "resource": resource, "details": json.dumps(details)},
    )


def get_fleet_risk(tenant_id: str, limit: int = 10) -> list[dict[str, Any]]:
    with postgres.tenant_session(tenant_id) as session:
        rows = session.execute(
            text("""
                SELECT r.vehicle_id, v.vin, r.failure_type, r.risk_score, r.lead_days,
                       d.name AS depot_name, d.city AS depot_city
                FROM vehicle_latest_risk r
                JOIN vehicle v ON v.id = r.vehicle_id
                JOIN depot d ON d.id = v.depot_id
                WHERE NOT EXISTS (  -- same rule as the At-Risk tab: already booked since this score
                    SELECT 1 FROM depot_booking b WHERE b.vehicle_id = r.vehicle_id AND b.created_at > r.created_at
                )
                ORDER BY r.risk_score DESC
                LIMIT :limit
            """),
            {"limit": limit},
        ).mappings().all()
        # Formatted the same way the web UI's At-Risk Fleet screen does
        # (web/src/pages/AtRiskPage.tsx: `(item.risk_score * 100).toFixed(1)}%`)
        # rather than leaving the raw 0-1 fraction for the model to reformat
        # itself — confirmed live that an LLM won't reliably do this
        # conversion the same way every time.
        result = []
        for r in rows:
            row = dict(r)
            risk_score = row.pop("risk_score")
            row["risk_percent"] = f"{float(risk_score) * 100:.1f}%"
            result.append(row)
        _audit(session, "copilot", "get_fleet_risk", "vehicle_latest_risk", {"limit": limit, "n": len(result)})
        return result


def get_vehicle_health(tenant_id: str, vin: str) -> dict[str, Any]:
    with postgres.tenant_session(tenant_id) as session:
        vehicle = session.execute(
            text("""
                SELECT v.id, v.vin, v.status, vm.make, vm.model, vm.vehicle_type,
                       d.name AS depot_name, d.city AS depot_city
                FROM vehicle v
                JOIN vehicle_model vm ON vm.id = v.vehicle_model_id
                JOIN depot d ON d.id = v.depot_id
                WHERE v.vin = :vin
            """),
            {"vin": vin},
        ).mappings().first()
        if vehicle is None:
            _audit(session, "copilot", "get_vehicle_health", vin, {"found": False})
            return {"found": False, "vin": vin}

        alerts = session.execute(
            text("""
                SELECT failure_type, severity, dtc_codes, opened_at
                FROM alert
                WHERE vehicle_id = :vid AND closed_at IS NULL
                ORDER BY opened_at DESC
            """),
            {"vid": vehicle["id"]},
        ).mappings().all()

        twin = redis_store.get_vehicle_twin(vin)
        result = {
            "found": True,
            **dict(vehicle),
            "open_alerts": [dict(a) for a in alerts],
            "twin": twin,
        }
        _audit(session, "copilot", "get_vehicle_health", vin, {"open_alerts": len(alerts)})
        return result


def list_alerts(tenant_id: str, open_only: bool = True, limit: int = 20) -> list[dict[str, Any]]:
    clause = "AND a.closed_at IS NULL" if open_only else ""
    with postgres.tenant_session(tenant_id) as session:
        rows = session.execute(
            text(f"""
                SELECT a.id, a.vehicle_id, v.vin, a.failure_type, a.severity, a.dtc_codes, a.opened_at, a.closed_at
                FROM alert a
                JOIN vehicle v ON v.id = a.vehicle_id
                WHERE true {clause}
                ORDER BY a.opened_at DESC
                LIMIT :limit
            """),
            {"limit": limit},
        ).mappings().all()
        result = [dict(r) for r in rows]
        _audit(session, "copilot", "list_alerts", "alert", {"open_only": open_only, "n": len(result)})
        return result


def _to_vector_literal(vec: list[float]) -> str:
    return "[" + ",".join(repr(x) for x in vec) + "]"


def search_dtc_kb(tenant_id: str, query: str, k: int = 5) -> dict[str, Any]:
    """Cosine-nearest DTCs and failure signatures (session 5's pgvector KB).
    Shared, un-RLS'd catalogues (migration 004) — `tenant_id` is only used
    for the audit row, not for scoping the search itself.
    """
    qvec = _to_vector_literal(embed_text(query))
    with postgres.shared_session() as session:
        dtcs = session.execute(
            text("""
                SELECT code, description, embedding <=> (:q)::vector AS distance
                FROM dtc_kb
                ORDER BY distance
                LIMIT :k
            """),
            {"q": qvec, "k": k},
        ).mappings().all()
        signatures = session.execute(
            text("""
                SELECT failure_type, description, embedding <=> (:q)::vector AS distance
                FROM failure_signature
                ORDER BY distance
                LIMIT :k
            """),
            {"q": qvec, "k": k},
        ).mappings().all()

    with postgres.tenant_session(tenant_id) as audit_session:
        _audit(audit_session, "copilot", "search_dtc_kb", query[:200], {"k": k})

    return {
        "dtcs": [{"code": r["code"], "description": r["description"], "distance": r["distance"]} for r in dtcs],
        "failure_signatures": [
            {"failure_type": r["failure_type"], "description": r["description"], "distance": r["distance"]}
            for r in signatures
        ],
    }


def find_nearest_depot(tenant_id: str, vehicle_lat: float, vehicle_lon: float) -> dict[str, Any] | None:
    with postgres.tenant_session(tenant_id) as session:
        depot_rows = session.execute(
            text("""
                SELECT d.id, d.name, d.city, d.lat, d.lon, d.bays, COALESCE(active.n, 0) AS active_bookings
                FROM depot d
                LEFT JOIN (
                    SELECT depot_id, count(*) AS n FROM depot_booking
                    WHERE booked_until > now() GROUP BY depot_id
                ) active ON active.depot_id = d.id
            """)
        ).mappings().all()
        depots = [
            Depot(id=str(r["id"]), lat=r["lat"], lon=r["lon"], bays=r["bays"], active_bookings=r["active_bookings"])
            for r in depot_rows
        ]
        chosen = find_nearest_depot_with_capacity(vehicle_lat, vehicle_lon, depots)
        _audit(session, "copilot", "find_nearest_depot", "depot", {"found": chosen is not None})
        if chosen is None:
            return None
        by_id = {str(r["id"]): r for r in depot_rows}
        row = by_id[chosen.id]
        return {"depot_id": chosen.id, "name": row["name"], "city": row["city"], "free_bays": chosen.free_bays}


def propose_work_order(
    tenant_id: str, role: str, proposed_by: str, vehicle_id: str, alert_id: str | None = None
) -> dict[str, Any]:
    if role not in _CAN_PROPOSE_WORK_ORDER:
        return {"proposed": False, "error": f"role {role!r} cannot propose a work order"}

    with postgres.tenant_session(tenant_id) as session:
        row = session.execute(
            text("""
                INSERT INTO work_order (tenant_id, vehicle_id, alert_id, status, proposed_by)
                VALUES (current_setting('app.tenant_id')::uuid, :vehicle_id, :alert_id, 'proposed', :proposed_by)
                RETURNING id
            """),
            {"vehicle_id": vehicle_id, "alert_id": alert_id, "proposed_by": proposed_by},
        ).first()
        work_order_id = str(row[0])
        _audit(
            session, "copilot", "propose_work_order", work_order_id,
            {"vehicle_id": vehicle_id, "alert_id": alert_id, "proposed_by": proposed_by},
        )
        return {"proposed": True, "work_order_id": work_order_id, "status": "proposed"}
