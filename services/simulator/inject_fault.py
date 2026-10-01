#!/usr/bin/env python
"""One-shot fault injection for a single VIN, driving `make inject-fault`.

Publishes ~15s of FAST/HEALTH telemetry for one vehicle with an accelerated
failure ramp (onset "now", failure_at ~10s out) so the relevant PLAN §1
real-time threshold is crossed quickly enough to watch the downstream alert
pipeline fire (verification item 3: alert in the UI within 5s of the
breach — Flink side lands in session 4, this script covers the ingest half).

Usage: python services/simulator/inject_fault.py --vin <17-char VIN> --type overheat
Types: overheat (cooling), oil (lubrication), battery, misfire, brakes (brake_wear),
tyre (tyre_leak), transmission, ev_battery (EV_HV_BATTERY — publishes as an EV
vehicle, since the failure doesn't exist on an ICE powertrain)
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "services" / "simulator" / "src"))
sys.path.insert(0, str(REPO_ROOT / "libs"))

from dotenv import load_dotenv  # noqa: E402

from fleetcore.algorithms import vin as vin_algo  # noqa: E402
from simulator.app.simulate import build_envelope  # noqa: E402
from simulator.domain.failure import FailurePlan, FailureType  # noqa: E402
from simulator.domain.signals import SignalEngine  # noqa: E402
from simulator.domain.vehicle import DEPOTS, Vehicle, VehicleType  # noqa: E402
from simulator.infra.mqtt_publisher import ShardedMqttPublisher  # noqa: E402

TYPE_MAP = {
    "overheat": FailureType.COOLING,
    "oil": FailureType.LUBRICATION,
    "battery": FailureType.BATTERY,
    "misfire": FailureType.MISFIRE,
    "brakes": FailureType.BRAKE_WEAR,
    "tyre": FailureType.TYRE_LEAK,
    "transmission": FailureType.TRANSMISSION,
    "ev_battery": FailureType.EV_HV_BATTERY,
}
# EV_HV_BATTERY only shows up in payloads for EV/HYBRID vehicles (signals.py
# gates cell_v_delta_mv etc. on vehicle_type) — everything else runs fine as
# the default ICE truck.
_VEHICLE_TYPE_FOR_FAILURE = {FailureType.EV_HV_BATTERY: VehicleType.EV}


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    load_dotenv(REPO_ROOT / ".env")

    parser = argparse.ArgumentParser(description="Inject a rapid-onset failure for one VIN")
    parser.add_argument("--vin", required=True)
    parser.add_argument("--type", choices=sorted(TYPE_MAP), default="overheat")
    parser.add_argument("--tenant", default=os.environ.get("TENANT_DEFAULT", "demo"))
    parser.add_argument("--ramp-seconds", type=float, default=10.0)
    parser.add_argument("--tail-seconds", type=float, default=5.0, help="extra seconds at full severity")
    args = parser.parse_args(argv)

    vin = args.vin.upper()
    if not vin_algo.is_valid(vin):
        fixed = vin_algo.with_check_digit(vin.ljust(17, "0")[:17])
        logging.warning("VIN %s has an invalid check digit; using %s instead", vin, fixed)
        vin = fixed

    failure_type = TYPE_MAP[args.type]
    vehicle = Vehicle(
        vin=vin, tenant=args.tenant,
        vehicle_type=_VEHICLE_TYPE_FOR_FAILURE.get(failure_type, VehicleType.ICE),
        depot=DEPOTS[0], fw_version="1.0.0", driver_token="drv-injected",
    )
    now = datetime.now(timezone.utc)
    plan = FailurePlan(
        vin=vin,
        failure_type=failure_type,
        onset_at=now,
        failure_at=now + timedelta(seconds=args.ramp_seconds),
    )
    engine = SignalEngine(vehicle, plan)

    host = os.environ.get("MQTT_HOST_EXTERNAL", "localhost")
    port = int(os.environ.get("MQTT_PORT", 8883))
    ca_cert = REPO_ROOT / os.environ.get("MQTT_CA_CERT", "infra/certs/ca/ca.crt")
    shard_dir = REPO_ROOT / "infra" / "certs" / "issued" / "shards"
    n_shards = int(os.environ.get("MQTT_SHARD_COUNT", 32))
    publisher = ShardedMqttPublisher(
        host=host, port=port, ca_cert=ca_cert, shard_cert_dir=shard_dir,
        tenant=args.tenant, n_shards=n_shards,
    )

    total_seconds = args.ramp_seconds + args.tail_seconds
    logging.info("injecting %s failure on %s for %.0fs (onset now, failure_at +%.0fs)",
                 args.type, vin, total_seconds, args.ramp_seconds)
    try:
        seq = int(time.time() * 1000)  # monotonic across runs; see simulate.py
        for _ in range(int(total_seconds)):
            at = datetime.now(timezone.utc)
            engine.step(1.0)
            seq += 1
            publisher.publish(vin, build_envelope(vehicle, "FAST", seq, at, engine.fast_payload(at)))
            if engine.health_due():
                seq += 1
                publisher.publish(vin, build_envelope(vehicle, "HEALTH", seq, at, engine.health_payload(at)))
            for event_payload in engine.pending_events(at):
                seq += 1
                publisher.publish(vin, build_envelope(vehicle, "EVENT", seq, at, event_payload))
            time.sleep(1.0)
    finally:
        time.sleep(0.5)  # let paho's background thread flush in-flight publishes
        publisher.close()

    print(f"Done. Injected {args.type} failure on {vin}; severity reached 1.0 at +{args.ramp_seconds:.0f}s.")


if __name__ == "__main__":
    main()
