from api.app import work_orders


def test_book_nearest_depot_picks_depot_with_capacity(monkeypatch):
    depot_rows = [
        {"id": "full", "lat": 12.97, "lon": 77.60, "bays": 1, "active_bookings": 1},
        {"id": "open", "lat": 13.08, "lon": 80.27, "bays": 1, "active_bookings": 0},
    ]
    monkeypatch.setattr("api.infra.repositories.list_depots", lambda session: depot_rows)
    booked = {}

    def fake_book_depot(session, depot_id, vehicle_id, work_order_id, hours):
        booked.update(depot_id=depot_id, vehicle_id=vehicle_id, hours=hours)
        return "booking-1"

    monkeypatch.setattr("api.infra.repositories.book_depot", fake_book_depot)

    result = work_orders.book_nearest_depot(session=object(), vehicle_id="veh-1", vehicle_lat=12.9716, vehicle_lon=77.5946)

    assert result == {"booking_id": "booking-1", "depot_id": "open"}
    assert booked["depot_id"] == "open"
    assert booked["hours"] == work_orders.DEFAULT_BOOKING_HOURS


def test_book_nearest_depot_none_when_all_full(monkeypatch):
    depot_rows = [{"id": "full", "lat": 12.97, "lon": 77.60, "bays": 1, "active_bookings": 1}]
    monkeypatch.setattr("api.infra.repositories.list_depots", lambda session: depot_rows)

    result = work_orders.book_nearest_depot(session=object(), vehicle_id="veh-1", vehicle_lat=12.9716, vehicle_lon=77.5946)

    assert result is None
