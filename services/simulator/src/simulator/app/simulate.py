"""Orchestrates the simulator: build a fleet, plan failures, then publish
FAST/HEALTH/EVENT telemetry over MQTT at a target aggregate rate.

One wall-clock tick == one second. Each tick, up to `RATE` active vehicles
each advance their `SignalEngine` by the elapsed time and emit a FAST
message; HEALTH is emitted per vehicle every 60s (or on ignition edges, via
`SignalEngine.health_due`); EVENTs are emitted whenever `pending_events`
returns any. Every outgoing message passes through the `NoiseInjector`
before publishing, so duplicates/reordering/bursts are indistinguishable
downstream from what a real fleet would produce.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from simulator.domain.failure import plan_failures
from simulator.domain.signals import SignalEngine
from simulator.domain.vehicle import Vehicle, generate_fleet
from simulator.infra.mqtt_publisher import ShardedMqttPublisher
from simulator.infra.noise import NoiseInjector

logger = logging.getLogger("simulator")


@dataclass
class SimulationStats:
    fast_sent: int = 0
    health_sent: int = 0
    event_sent: int = 0

    @property
    def total_sent(self) -> int:
        return self.fast_sent + self.health_sent + self.event_sent


def build_envelope(vehicle: Vehicle, msg_type: str, seq: int, at: datetime, payload: dict) -> dict:
    return {
        "vin": vehicle.vin,
        "msg_type": msg_type,
        "seq": seq,
        "ts": at.isoformat(),
        "fw_version": vehicle.fw_version,
        "schema_ver": 1,
        "driver_token": vehicle.driver_token,
        "payload": payload,
    }


def run_simulation(
    publisher: ShardedMqttPublisher,
    rate_eps: int,
    duration_s: float | None,
    fleet_size: int = 100_000,
    active_vehicles: int | None = None,
    tenant: str = "demo",
    seed: int | None = None,
    stats: SimulationStats | None = None,
) -> SimulationStats:
    stats = stats or SimulationStats()
    fleet = generate_fleet(size=fleet_size, tenant=tenant, seed=seed)
    now0 = datetime.now(timezone.utc)
    failure_plans = plan_failures(fleet, now0, seed=seed)

    n_active = min(active_vehicles or rate_eps, len(fleet))
    active = fleet[:n_active]
    engines = {v.vin: SignalEngine(v, failure_plans.get(v.vin)) for v in active}
    # A per-run millisecond base, not 0: a real device's seq survives reboots,
    # and restarting at 0 made every repeat run's vin:seq pairs look like
    # duplicates to the gateway's Bloom filter, Flink's dedup state and the
    # state-writer's seq guard (~40% of one session's traffic was dropped).
    # ~1 msg/s per vehicle can never catch up with a 1000/s clock.
    seq_base = int(time.time() * 1000)
    seq_counters = {v.vin: seq_base for v in active}
    noise = NoiseInjector(seed=seed)

    logger.info("simulating %d active vehicles (%d in fleet, %d with planted failures) at ~%d events/s",
                n_active, len(fleet), len(failure_plans), rate_eps)

    start = time.monotonic()
    tick = 0
    while duration_s is None or (time.monotonic() - start) < duration_s:
        tick_start = time.monotonic()
        at = datetime.now(timezone.utc)
        virtual_clock = time.monotonic() - start

        for vehicle in active:
            engine = engines[vehicle.vin]
            engine.step(1.0)
            seq_counters[vehicle.vin] += 1
            seq = seq_counters[vehicle.vin]

            fast_msg = build_envelope(vehicle, "FAST", seq, at, engine.fast_payload(at))
            for msg in noise.offer(fast_msg, virtual_clock):
                publisher.publish(vehicle.vin, msg)
                stats.fast_sent += 1

            if engine.health_due():
                seq_counters[vehicle.vin] += 1
                seq = seq_counters[vehicle.vin]
                health_msg = build_envelope(vehicle, "HEALTH", seq, at, engine.health_payload(at))
                for msg in noise.offer(health_msg, virtual_clock):
                    publisher.publish(vehicle.vin, msg)
                    stats.health_sent += 1

            for event_payload in engine.pending_events(at):
                seq_counters[vehicle.vin] += 1
                seq = seq_counters[vehicle.vin]
                event_msg = build_envelope(vehicle, "EVENT", seq, at, event_payload)
                for msg in noise.offer(event_msg, virtual_clock):
                    publisher.publish(vehicle.vin, msg)
                    stats.event_sent += 1

        for msg in noise.drain_due(virtual_clock):
            publisher.publish(msg["vin"], msg)
            stats.fast_sent += 1

        tick += 1
        if tick % 10 == 0:
            logger.info("tick %d: %d messages sent so far", tick, stats.total_sent)

        elapsed = time.monotonic() - tick_start
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)

    return stats
