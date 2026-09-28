from fleetcore.algorithms.geohash import encode, mask_for_role


def test_encode_known_vector():
    # Jutland, Denmark — a well-known geohash.org test vector.
    assert encode(57.64911, 10.40744, precision=11) == "u4pruydqqvj"


def test_encode_precision_controls_length():
    gh = encode(12.9716, 77.5946, precision=6)
    assert len(gh) == 6


def test_encode_out_of_range_raises():
    import pytest

    with pytest.raises(ValueError):
        encode(200.0, 0.0)
    with pytest.raises(ValueError):
        encode(0.0, -200.0)


def test_mask_for_role_precision():
    lat, lon = 12.9716, 77.5946
    admin_hash = mask_for_role(lat, lon, "fleet_admin")
    tech_hash = mask_for_role(lat, lon, "technician")
    assert len(admin_hash) == 9
    assert len(tech_hash) == 5
    assert admin_hash.startswith(tech_hash)


def test_mask_for_role_unknown_role_gets_coarsest():
    lat, lon = 12.9716, 77.5946
    unknown_hash = mask_for_role(lat, lon, "totally-unknown-role")
    assert len(unknown_hash) == min(5, 9)
