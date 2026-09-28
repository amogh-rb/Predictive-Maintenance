from fleetcore.algorithms import vin as vin_algo
from simulator.domain.vehicle import VehicleType, generate_fleet


def test_generates_requested_size_with_unique_vins():
    fleet = generate_fleet(size=500, seed=1)
    assert len(fleet) == 500
    assert len({v.vin for v in fleet}) == 500


def test_all_vins_are_check_digit_valid():
    fleet = generate_fleet(size=200, seed=2)
    assert all(vin_algo.is_valid(v.vin) for v in fleet)


def test_deterministic_for_same_seed():
    fleet_a = generate_fleet(size=100, seed=7)
    fleet_b = generate_fleet(size=100, seed=7)
    assert [v.vin for v in fleet_a] == [v.vin for v in fleet_b]


def test_fleet_mix_is_roughly_70_20_10():
    fleet = generate_fleet(size=20_000, seed=3)
    counts = {t: sum(1 for v in fleet if v.vehicle_type == t) for t in VehicleType}
    assert 0.65 < counts[VehicleType.ICE] / len(fleet) < 0.75
    assert 0.15 < counts[VehicleType.EV] / len(fleet) < 0.25
    assert 0.05 < counts[VehicleType.HYBRID] / len(fleet) < 0.15


def test_depots_are_from_the_five_cities():
    from simulator.domain.vehicle import DEPOTS
    fleet = generate_fleet(size=200, seed=4)
    assert all(v.depot in DEPOTS for v in fleet)
    assert len(DEPOTS) == 5
