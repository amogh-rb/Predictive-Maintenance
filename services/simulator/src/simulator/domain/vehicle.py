"""Fleet composition: vehicle identities for the simulated 100K-truck fleet.

Vehicle make/model/ownership live in Postgres (session 3), not here or on the
wire — the simulator only needs enough identity to publish a valid envelope
and to drive type-appropriate signal generation (ICE vs EV vs hybrid).
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum

from fleetcore.algorithms import vin as vin_algo

DEPOTS = ["mumbai", "delhi", "bengaluru", "chennai", "kolkata"]

# 70% diesel (ICE), 20% EV, 10% hybrid — PLAN §1 fleet mix.
_TYPE_WEIGHTS = [("ICE", 0.70), ("EV", 0.20), ("HYBRID", 0.10)]

_VIN_CHARS = "0123456789ABCDEFGHJKLMNPRSTUVWXYZ"  # excludes I, O, Q


class VehicleType(str, Enum):
    ICE = "ICE"
    EV = "EV"
    HYBRID = "HYBRID"


@dataclass(frozen=True)
class Vehicle:
    vin: str
    tenant: str
    vehicle_type: VehicleType
    depot: str
    fw_version: str
    driver_token: str


def _random_vin(rng: random.Random) -> str:
    body = "".join(rng.choice(_VIN_CHARS) for _ in range(vin_algo.VIN_LENGTH))
    return vin_algo.with_check_digit(body)


def _weighted_type(rng: random.Random) -> VehicleType:
    roll = rng.random()
    cumulative = 0.0
    for name, weight in _TYPE_WEIGHTS:
        cumulative += weight
        if roll <= cumulative:
            return VehicleType(name)
    return VehicleType(_TYPE_WEIGHTS[-1][0])


def generate_fleet(
    size: int = 100_000,
    tenant: str = "demo",
    seed: int | None = None,
    fw_version: str = "1.0.0",
) -> list[Vehicle]:
    """Generate `size` vehicles with unique, check-digit-valid VINs.

    Deterministic for a given `seed`, so a session can regenerate the same
    fleet (e.g. to line up with a later Postgres seed) without persisting it.
    """
    rng = random.Random(seed)
    seen_vins: set[str] = set()
    fleet: list[Vehicle] = []
    while len(fleet) < size:
        vin = _random_vin(rng)
        if vin in seen_vins:
            continue
        seen_vins.add(vin)
        fleet.append(
            Vehicle(
                vin=vin,
                tenant=tenant,
                vehicle_type=_weighted_type(rng),
                depot=rng.choice(DEPOTS),
                fw_version=fw_version,
                driver_token=f"drv-{rng.getrandbits(48):012x}",
            )
        )
    return fleet
