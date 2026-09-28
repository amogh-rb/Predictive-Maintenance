from __future__ import annotations

from typing import Any

from redis import Redis
from sqlmodel import Session

from api.domain.masking import masked_location
from api.domain.pagination import RiskCursor, decode_cursor, encode_cursor
from api.infra import repositories as repo


def list_at_risk(session: Session, limit: int, cursor_str: str | None) -> dict[str, Any]:
    cursor: RiskCursor | None = decode_cursor(cursor_str) if cursor_str else None
    rows = repo.list_at_risk(session, limit=limit, cursor=cursor)
    next_cursor = None
    if len(rows) == limit:
        last = rows[-1]
        next_cursor = encode_cursor(float(last["risk_score"]), str(last["vehicle_id"]))
    return {"items": rows, "next_cursor": next_cursor}


def get_vehicle_detail(session: Session, redis_client: Redis, vehicle_id: str, role: str) -> dict[str, Any] | None:
    vehicle = repo.get_vehicle(session, vehicle_id)
    if vehicle is None:
        return None
    vehicle["depot_location"] = masked_location(vehicle.pop("depot_lat"), vehicle.pop("depot_lon"), role)

    twin = repo.get_vehicle_twin(redis_client, vehicle["vin"])
    if twin is not None and "lat" in twin and "lon" in twin:
        # The live GPS fix is the actually sensitive field here (PLAN §2
        # "Privacy": location masking by role) — depot_location above is a
        # fixed, non-secret address, this is where the truck is right now.
        twin["location"] = masked_location(twin.pop("lat"), twin.pop("lon"), role)
    vehicle["twin"] = twin
    return vehicle
