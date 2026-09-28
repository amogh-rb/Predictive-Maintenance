from api.domain.masking import masked_location


def test_fleet_admin_gets_exact_coordinates():
    result = masked_location(12.9716, 77.5946, "fleet_admin")
    assert result == {"lat": 12.9716, "lon": 77.5946}


def test_technician_gets_geohash_not_coordinates():
    result = masked_location(12.9716, 77.5946, "technician")
    assert "lat" not in result and "lon" not in result
    assert len(result["geohash"]) == 5
