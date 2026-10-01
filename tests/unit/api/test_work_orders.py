from api.app import work_orders


def _patch_schedule(monkeypatch, depots, *, open_booking=False, twin=None):
    calls = []
    vehicle = {"id": "veh-1", "vin": "VIN1", "depot_lat": 12.97, "depot_lon": 77.60}
    monkeypatch.setattr("api.infra.repositories.get_vehicle", lambda s, vid: vehicle if vid == "veh-1" else None)
    monkeypatch.setattr("api.infra.repositories.has_open_booking", lambda s, vid: open_booking)
    monkeypatch.setattr("api.infra.repositories.get_vehicle_twin", lambda r, vin: twin)
    monkeypatch.setattr("api.infra.repositories.list_depots", lambda s: depots)
    monkeypatch.setattr(
        "api.infra.repositories.propose_work_order", lambda s, v, a, by: calls.append("propose") or "wo-1"
    )
    monkeypatch.setattr(
        "api.infra.repositories.approve_work_order", lambda s, wo, who: calls.append("approve") or True
    )
    monkeypatch.setattr(
        "api.infra.repositories.book_depot", lambda s, d, v, wo, h: calls.append(f"book:{d}") or "booking-1"
    )
    return calls


def test_schedule_maintenance_books_nearest_free_depot_and_approves(monkeypatch):
    depots = [
        {"id": "full", "name": "bengaluru", "city": "Bengaluru", "lat": 12.97, "lon": 77.60, "bays": 1, "active_bookings": 1},
        {"id": "open", "name": "chennai", "city": "Chennai", "lat": 13.08, "lon": 80.27, "bays": 1, "active_bookings": 0},
    ]
    calls = _patch_schedule(monkeypatch, depots)

    result = work_orders.schedule_maintenance(object(), object(), "veh-1", "mgr@demo", "sub-1")

    assert calls == ["propose", "approve", "book:open"]
    assert result["depot_city"] == "Chennai"
    assert result["work_order_id"] == "wo-1" and result["booking_id"] == "booking-1"


def test_schedule_maintenance_uses_live_position_over_home_depot(monkeypatch):
    # Truck is parked in Chennai although its home depot is Bengaluru: Chennai wins.
    depots = [
        {"id": "blr", "name": "bengaluru", "city": "Bengaluru", "lat": 12.97, "lon": 77.60, "bays": 4, "active_bookings": 0},
        {"id": "maa", "name": "chennai", "city": "Chennai", "lat": 13.08, "lon": 80.27, "bays": 4, "active_bookings": 0},
    ]
    calls = _patch_schedule(monkeypatch, depots, twin={"lat": 13.09, "lon": 80.28})

    work_orders.schedule_maintenance(object(), object(), "veh-1", "mgr@demo", "sub-1")

    assert calls[-1] == "book:maa"


def test_schedule_maintenance_writes_nothing_when_every_depot_is_full(monkeypatch):
    depots = [{"id": "full", "name": "x", "city": "X", "lat": 12.97, "lon": 77.60, "bays": 1, "active_bookings": 1}]
    calls = _patch_schedule(monkeypatch, depots)

    assert work_orders.schedule_maintenance(object(), object(), "veh-1", "mgr@demo", "sub-1") is None
    assert calls == []


def test_schedule_maintenance_rejects_unknown_vehicle_and_double_booking(monkeypatch):
    import pytest

    _patch_schedule(monkeypatch, [])
    with pytest.raises(work_orders.VehicleNotFound):
        work_orders.schedule_maintenance(object(), object(), "nope", "mgr@demo", "sub-1")

    _patch_schedule(monkeypatch, [], open_booking=True)
    with pytest.raises(work_orders.AlreadyScheduled):
        work_orders.schedule_maintenance(object(), object(), "veh-1", "mgr@demo", "sub-1")


def _patch_approve(monkeypatch, depots, *, status="proposed"):
    calls = []
    monkeypatch.setattr(
        "api.infra.repositories.get_work_order",
        lambda s, wo: {"id": wo, "vehicle_id": "veh-1", "status": status} if wo == "wo-1" else None,
    )
    monkeypatch.setattr(
        "api.infra.repositories.get_vehicle",
        lambda s, vid: {"id": "veh-1", "vin": "VIN1", "depot_lat": 12.97, "depot_lon": 77.60},
    )
    monkeypatch.setattr("api.infra.repositories.get_vehicle_twin", lambda r, vin: None)
    monkeypatch.setattr("api.infra.repositories.list_depots", lambda s: depots)
    monkeypatch.setattr(
        "api.infra.repositories.approve_work_order", lambda s, wo, who: calls.append("approve") or True
    )
    monkeypatch.setattr(
        "api.infra.repositories.book_depot", lambda s, d, v, wo, h: calls.append(f"book:{d}") or "booking-1"
    )
    return calls


_OPEN_DEPOT = [{"id": "d1", "name": "blr", "city": "Bengaluru", "lat": 12.97, "lon": 77.60, "bays": 2, "active_bookings": 0}]


def test_approving_a_proposal_books_the_nearest_free_depot(monkeypatch):
    calls = _patch_approve(monkeypatch, _OPEN_DEPOT)
    result = work_orders.approve(object(), object(), "wo-1", "sub-1")
    assert calls == ["approve", "book:d1"]
    assert result["status"] == "approved" and result["depot_city"] == "Bengaluru"


def test_approving_leaves_the_proposal_pending_when_every_depot_is_full(monkeypatch):
    import pytest

    full = [{**_OPEN_DEPOT[0], "bays": 1, "active_bookings": 1}]
    calls = _patch_approve(monkeypatch, full)
    with pytest.raises(work_orders.NoDepotCapacity):
        work_orders.approve(object(), object(), "wo-1", "sub-1")
    assert calls == []


def test_approving_something_already_decided_or_unknown_returns_none(monkeypatch):
    calls = _patch_approve(monkeypatch, _OPEN_DEPOT, status="approved")
    assert work_orders.approve(object(), object(), "wo-1", "sub-1") is None
    assert work_orders.approve(object(), object(), "nope", "sub-1") is None
    assert calls == []


def test_status_board_groups_each_stage(monkeypatch):
    monkeypatch.setattr("api.infra.repositories.list_pending_proposals", lambda s, n: ["p"])
    monkeypatch.setattr(
        "api.infra.repositories.list_scheduled", lambda s, n, statuses=("approved",): list(statuses)
    )
    monkeypatch.setattr("api.infra.repositories.list_recent_closed", lambda s, n: ["r"])
    board = work_orders.status_board(object())
    assert board == {"pending": ["p"], "scheduled": ["approved"], "in_service": ["in_service"], "recent": ["r"]}
