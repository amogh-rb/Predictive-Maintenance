from __future__ import annotations

from redis import Redis
from sqlmodel import Session

from fleetcore.algorithms.depot_routing import Depot, find_nearest_depot_with_capacity
from api.infra import repositories as repo

DEFAULT_BOOKING_HOURS = 4


class VehicleNotFound(Exception):
    pass


class AlreadyScheduled(Exception):
    pass


class NoDepotCapacity(Exception):
    pass


def _choose_depot(session: Session, redis_client: Redis, vehicle: dict):
    """Nearest depot with a free bay for this vehicle: (Depot, depot row) or (None, None). The truck's
    exact position is read server-side from its live twin (falling back to its home depot) and never
    returned to the client."""
    twin = repo.get_vehicle_twin(redis_client, vehicle["vin"]) or {}
    lat = twin.get("lat", vehicle["depot_lat"])
    lon = twin.get("lon", vehicle["depot_lon"])
    depot_rows = repo.list_depots(session)
    depots = [
        Depot(id=str(r["id"]), lat=r["lat"], lon=r["lon"], bays=r["bays"], active_bookings=r["active_bookings"])
        for r in depot_rows
    ]
    chosen = find_nearest_depot_with_capacity(float(lat), float(lon), depots)
    if chosen is None:
        return None, None
    return chosen, next(r for r in depot_rows if str(r["id"]) == chosen.id)


def approve(
    session: Session, redis_client: Redis, work_order_id: str, approver_user_id: str,
    hours: int = DEFAULT_BOOKING_HOURS,
) -> dict | None:
    """Approving a proposal also books the nearest depot with a free bay, so it lands in "Scheduled".
    Returns None if the work order isn't a pending proposal; raises NoDepotCapacity (nothing written)
    when every depot is full, leaving the proposal pending."""
    wo = repo.get_work_order(session, work_order_id)
    if wo is None or wo["status"] != "proposed":
        return None
    vehicle = repo.get_vehicle(session, str(wo["vehicle_id"]))
    if vehicle is None:
        return None
    chosen, depot = _choose_depot(session, redis_client, vehicle)
    if chosen is None:
        raise NoDepotCapacity(work_order_id)
    if not repo.approve_work_order(session, work_order_id, approver_user_id):
        return None
    booking_id = repo.book_depot(session, chosen.id, str(wo["vehicle_id"]), work_order_id, hours)
    return {
        "work_order_id": work_order_id, "booking_id": booking_id, "depot_id": chosen.id,
        "depot_name": depot["name"], "depot_city": depot["city"], "status": "approved",
    }


def reject(session: Session, work_order_id: str) -> bool:
    return repo.reject_work_order(session, work_order_id)


def start(session: Session, work_order_id: str) -> bool:
    return repo.start_work_order(session, work_order_id)


def schedule_maintenance(
    session: Session, redis_client: Redis, vehicle_id: str, proposed_by: str, approver_user_id: str,
    hours: int = DEFAULT_BOOKING_HOURS,
) -> dict | None:
    """One step from the at-risk tab: pick the nearest depot with a free bay, then open + approve a
    work order and book that bay. Returns None (and writes nothing) when every depot is full.

    The truck's exact position is read server-side from its live twin (falling back to its home depot);
    role-based masking only applies to what is returned to the client, and none of it is returned here.
    """
    vehicle = repo.get_vehicle(session, vehicle_id)
    if vehicle is None:
        raise VehicleNotFound(vehicle_id)
    if repo.has_open_booking(session, vehicle_id):
        raise AlreadyScheduled(vehicle_id)

    chosen, depot = _choose_depot(session, redis_client, vehicle)
    if chosen is None:
        return None

    work_order_id = repo.propose_work_order(session, vehicle_id, None, proposed_by)
    repo.approve_work_order(session, work_order_id, approver_user_id)
    booking_id = repo.book_depot(session, chosen.id, vehicle_id, work_order_id, hours)
    return {
        "work_order_id": work_order_id, "booking_id": booking_id, "depot_id": chosen.id,
        "depot_name": depot["name"], "depot_city": depot["city"], "hours": hours,
    }


def list_scheduled(session: Session, limit: int = 100) -> dict:
    return {"items": repo.list_scheduled(session, limit)}


def status_board(session: Session, limit: int = 200) -> dict:
    """Everything a manager tracks on one page: proposals awaiting a decision, booked vehicles,
    vehicles being serviced now, and what closed in the last week."""
    return {
        "pending": repo.list_pending_proposals(session, limit),
        "scheduled": repo.list_scheduled(session, limit, ("approved",)),
        "in_service": repo.list_scheduled(session, limit, ("in_service",)),
        "recent": repo.list_recent_closed(session, limit),
    }


def complete(session: Session, work_order_id: str) -> bool:
    return repo.complete_work_order(session, work_order_id)
