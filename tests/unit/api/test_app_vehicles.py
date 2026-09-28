from api.app import vehicles as vehicles_app
from api.domain.pagination import encode_cursor


def test_list_at_risk_returns_next_cursor_when_page_full(monkeypatch):
    rows = [{"vehicle_id": f"v{i}", "risk_score": 0.9 - i * 0.01} for i in range(3)]
    monkeypatch.setattr("api.infra.repositories.list_at_risk", lambda session, limit, cursor: rows)

    result = vehicles_app.list_at_risk(session=object(), limit=3, cursor_str=None)

    assert result["items"] == rows
    assert result["next_cursor"] == encode_cursor(rows[-1]["risk_score"], rows[-1]["vehicle_id"])


def test_list_at_risk_no_next_cursor_on_short_page(monkeypatch):
    rows = [{"vehicle_id": "v0", "risk_score": 0.9}]
    monkeypatch.setattr("api.infra.repositories.list_at_risk", lambda session, limit, cursor: rows)

    result = vehicles_app.list_at_risk(session=object(), limit=20, cursor_str=None)

    assert result["next_cursor"] is None


def test_list_at_risk_decodes_incoming_cursor(monkeypatch):
    captured = {}

    def fake_list_at_risk(session, limit, cursor):
        captured["cursor"] = cursor
        return []

    monkeypatch.setattr("api.infra.repositories.list_at_risk", fake_list_at_risk)
    vehicles_app.list_at_risk(session=object(), limit=5, cursor_str=encode_cursor(0.5, "v9"))

    assert captured["cursor"].risk_score == 0.5
    assert captured["cursor"].vehicle_id == "v9"


def test_get_vehicle_detail_masks_depot_location(monkeypatch):
    vehicle_row = {
        "id": "veh-1", "vin": "1FT7W2BT0DEA00001", "depot_lat": 12.97, "depot_lon": 77.59,
    }
    monkeypatch.setattr("api.infra.repositories.get_vehicle", lambda session, vid: dict(vehicle_row))
    monkeypatch.setattr("api.infra.repositories.get_vehicle_twin", lambda redis_client, vin: {"speed_kmh": 60})

    result = vehicles_app.get_vehicle_detail(session=object(), redis_client=object(), vehicle_id="veh-1", role="technician")

    assert "depot_lat" not in result and "depot_lon" not in result
    assert "geohash" in result["depot_location"]
    assert result["twin"] == {"speed_kmh": 60}


def test_get_vehicle_detail_masks_live_twin_gps(monkeypatch):
    vehicle_row = {
        "id": "veh-1", "vin": "1FT7W2BT0DEA00001", "depot_lat": 12.97, "depot_lon": 77.59,
    }
    monkeypatch.setattr("api.infra.repositories.get_vehicle", lambda session, vid: dict(vehicle_row))
    monkeypatch.setattr(
        "api.infra.repositories.get_vehicle_twin",
        lambda redis_client, vin: {"lat": 12.9716, "lon": 77.5946, "speed_kmh": 40},
    )

    result = vehicles_app.get_vehicle_detail(session=object(), redis_client=object(), vehicle_id="veh-1", role="technician")

    assert "lat" not in result["twin"] and "lon" not in result["twin"]
    assert "geohash" in result["twin"]["location"]
    assert result["twin"]["speed_kmh"] == 40


def test_get_vehicle_detail_returns_none_when_not_found(monkeypatch):
    monkeypatch.setattr("api.infra.repositories.get_vehicle", lambda session, vid: None)
    result = vehicles_app.get_vehicle_detail(session=object(), redis_client=object(), vehicle_id="missing", role="fleet_admin")
    assert result is None
