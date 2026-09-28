from fleetcore.algorithms.depot_routing import Depot, find_nearest_depot_with_capacity, haversine_km


def test_haversine_zero_for_same_point():
    assert haversine_km(12.97, 77.59, 12.97, 77.59) == 0.0


def test_haversine_known_distance_bangalore_chennai():
    # ~290 km as the crow flies; allow generous tolerance for a POC check.
    km = haversine_km(12.9716, 77.5946, 13.0827, 80.2707)
    assert 280 < km < 300


def test_picks_nearest_depot_when_all_have_capacity():
    depots = [
        Depot(id="near", lat=12.97, lon=77.60, bays=2, active_bookings=0),
        Depot(id="far", lat=13.08, lon=80.27, bays=2, active_bookings=0),
    ]
    chosen = find_nearest_depot_with_capacity(12.9716, 77.5946, depots)
    assert chosen.id == "near"


def test_falls_through_to_next_depot_when_nearest_is_full():
    depots = [
        Depot(id="near", lat=12.97, lon=77.60, bays=2, active_bookings=2),  # full
        Depot(id="far", lat=13.08, lon=80.27, bays=2, active_bookings=0),
    ]
    chosen = find_nearest_depot_with_capacity(12.9716, 77.5946, depots)
    assert chosen.id == "far"


def test_none_when_every_depot_is_full():
    depots = [Depot(id="a", lat=12.97, lon=77.60, bays=1, active_bookings=1)]
    assert find_nearest_depot_with_capacity(12.9716, 77.5946, depots) is None


def test_empty_depot_list():
    assert find_nearest_depot_with_capacity(12.9716, 77.5946, []) is None
