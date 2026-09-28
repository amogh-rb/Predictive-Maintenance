from __future__ import annotations

from sqlmodel import Session

from fleetcore.algorithms.depot_routing import Depot, find_nearest_depot_with_capacity
from api.infra import repositories as repo

DEFAULT_BOOKING_HOURS = 4


def propose(session: Session, vehicle_id: str, alert_id: str | None, proposed_by: str) -> str:
    return repo.propose_work_order(session, vehicle_id, alert_id, proposed_by)


def approve(session: Session, work_order_id: str, approver_user_id: str) -> bool:
    return repo.approve_work_order(session, work_order_id, approver_user_id)


def book_nearest_depot(
    session: Session, vehicle_id: str, vehicle_lat: float, vehicle_lon: float,
    work_order_id: str | None = None, hours: int = DEFAULT_BOOKING_HOURS,
) -> dict | None:
    """Dijkstra over the depot mesh (fleetcore.algorithms.depot_routing) picks
    the nearest depot that currently has a free bay, then books it.
    """
    depot_rows = repo.list_depots(session)
    depots = [
        Depot(id=str(r["id"]), lat=r["lat"], lon=r["lon"], bays=r["bays"], active_bookings=r["active_bookings"])
        for r in depot_rows
    ]
    chosen = find_nearest_depot_with_capacity(vehicle_lat, vehicle_lon, depots)
    if chosen is None:
        return None
    booking_id = repo.book_depot(session, chosen.id, vehicle_id, work_order_id, hours)
    return {"booking_id": booking_id, "depot_id": chosen.id}
