"""Seed 100K vehicles/drivers/depots into Postgres (PLAN §6.3 session 3).

Reuses the simulator's `generate_fleet(seed=42)` so the VIN, tenant, depot
and driver_token on each Postgres row line up with what `make simulate`
actually publishes over MQTT — session 4+ can join telemetry by VIN and find
a matching vehicle here.

Idempotent: truncates the tenant-scoped tables it owns (vehicle, driver, and
depot/vehicle_model, which are cheap to regenerate) before reseeding, so
`make seed` can be re-run after a schema change without manual cleanup.

Run via `make seed` (applies migrations first, then this).
"""
from __future__ import annotations

import os
import random
import sys
import uuid
from pathlib import Path

import psycopg
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "services" / "simulator" / "src"))

from simulator.domain.vehicle import DEPOTS, VehicleType, generate_fleet  # noqa: E402

FLEET_SIZE = 100_000
FLEET_SEED = 42
TENANT_NAME = "demo"

# city, lat, lon — enough for `find_nearest_depot` (Dijkstra/A*, PLAN §2) to
# have real coordinates to route between.
DEPOT_COORDS = {
    "mumbai": ("Mumbai", 19.0760, 72.8777),
    "delhi": ("Delhi", 28.7041, 77.1025),
    "bengaluru": ("Bengaluru", 12.9716, 77.5946),
    "chennai": ("Chennai", 13.0827, 80.2707),
    "kolkata": ("Kolkata", 22.5726, 88.3639),
}

# A handful of representative models per drivetrain, tyre count per PLAN §1
# ("4- or 6-tyre trucks") — vans are 4-tyre, rigid/heavy trucks are 6-tyre.
VEHICLE_MODELS = [
    ("Tata", "Prima 2830", VehicleType.ICE, 6),
    ("Ashok Leyland", "1616 IL", VehicleType.ICE, 6),
    ("BharatBenz", "1617R", VehicleType.ICE, 6),
    ("Tata", "Ace Gold", VehicleType.ICE, 4),
    ("Mahindra", "eSupro Cargo", VehicleType.EV, 4),
    ("Tata", "Ace EV", VehicleType.EV, 4),
    ("Ashok Leyland", "1616 IL Hybrid", VehicleType.HYBRID, 6),
    ("Tata", "Prima Hybrid", VehicleType.HYBRID, 6),
]


def _driver_fields(rng: random.Random, i: int) -> tuple[str, str, str]:
    full_name = f"Driver {i:06d}"
    phone = f"+91-9{rng.randrange(100000000, 999999999)}"
    license_no = f"DL-{rng.randrange(1000000000, 9999999999)}"
    return full_name, phone, license_no


def main() -> None:
    load_dotenv(REPO_ROOT / ".env")

    host = os.getenv("POSTGRES_HOST_EXTERNAL", "localhost")
    port = os.getenv("POSTGRES_PORT_EXTERNAL", "5432")
    db = os.getenv("POSTGRES_DB", "fleetpulse")
    user = os.getenv("POSTGRES_USER", "fleetpulse")
    password = os.getenv("POSTGRES_PASSWORD", "changeme")

    conn = psycopg.connect(host=host, port=port, dbname=db, user=user, password=password)
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO tenant (name) VALUES (%s) "
                "ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name "
                "RETURNING id",
                (TENANT_NAME,),
            )
            tenant_id = cur.fetchone()[0]
            # RLS (004_rls.sql) is FORCE'd even for the seeding role, so every
            # statement in this session needs the tenant it's writing as.
            # set_config (not `SET ... = %s`, which can't take a bind param)
            # with is_local=false so it survives across this connection's
            # transaction commits.
            cur.execute("SELECT set_config('app.tenant_id', %s, false)", (str(tenant_id),))

            cur.execute("TRUNCATE vehicle, driver, depot RESTART IDENTITY CASCADE")
            cur.execute("TRUNCATE vehicle_model RESTART IDENTITY CASCADE")

            depot_ids: dict[str, uuid.UUID] = {}
            for name in DEPOTS:
                city, lat, lon = DEPOT_COORDS[name]
                cur.execute(
                    "INSERT INTO depot (tenant_id, name, city, lat, lon) "
                    "VALUES (%s, %s, %s, %s, %s) RETURNING id",
                    (tenant_id, name, city, lat, lon),
                )
                depot_ids[name] = cur.fetchone()[0]

            model_ids: dict[VehicleType, list[int]] = {t: [] for t in VehicleType}
            for make, model, vtype, tyres in VEHICLE_MODELS:
                cur.execute(
                    "INSERT INTO vehicle_model (make, model, vehicle_type, tyre_count) "
                    "VALUES (%s, %s, %s, %s) RETURNING id",
                    (make, model, vtype.value, tyres),
                )
                model_ids[vtype].append(cur.fetchone()[0])

        print(f"tenant={tenant_id} depots={len(depot_ids)} vehicle_models={len(VEHICLE_MODELS)}")

        fleet = generate_fleet(size=FLEET_SIZE, tenant=TENANT_NAME, seed=FLEET_SEED)
        rng = random.Random(FLEET_SEED)

        with conn.cursor() as cur:
            with cur.copy(
                "COPY driver (id, tenant_id, driver_token, full_name, phone, license_no, depot_id) "
                "FROM STDIN"
            ) as copy:
                for i, v in enumerate(fleet):
                    full_name, phone, license_no = _driver_fields(rng, i)
                    copy.write_row(
                        (
                            uuid.uuid4(),
                            tenant_id,
                            v.driver_token,
                            full_name,
                            phone,
                            license_no,
                            depot_ids[v.depot],
                        )
                    )

            cur.execute(
                "SELECT driver_token, id FROM driver WHERE tenant_id = %s", (tenant_id,)
            )
            driver_id_by_token = dict(cur.fetchall())

            with cur.copy(
                "COPY vehicle (id, tenant_id, vin, depot_id, vehicle_model_id, "
                "fw_version, primary_driver_id) FROM STDIN"
            ) as copy:
                for v in fleet:
                    model_id = rng.choice(model_ids[v.vehicle_type])
                    copy.write_row(
                        (
                            uuid.uuid4(),
                            tenant_id,
                            v.vin,
                            depot_ids[v.depot],
                            model_id,
                            v.fw_version,
                            driver_id_by_token[v.driver_token],
                        )
                    )

        conn.commit()

        with conn.cursor() as cur:
            cur.execute("SELECT set_config('app.tenant_id', %s, false)", (str(tenant_id),))
            cur.execute("SELECT count(*) FROM vehicle")
            vehicle_count = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM driver")
            driver_count = cur.fetchone()[0]

    print(f"seeded vehicles={vehicle_count} drivers={driver_count}")
    conn.close()


if __name__ == "__main__":
    main()
