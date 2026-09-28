"""Injects duplicates, out-of-order delivery, and bursts into the outgoing
message stream (PLAN §6.3 session 2: "noise/duplicates/out-of-order/bursts").

Real trucks retry unacked QoS-1 publishes (duplicates), reconnect after a
signal gap and flush a backlog (bursts), and don't guarantee send order
across a reconnect (out-of-order) — this is what downstream dedup (a Bloom
filter pre-filter here, Flink's exact `ROW_NUMBER()` dedup later) and
sequence-based reconciliation (`make chaos`, session 9) exist to handle. A
message is a plain dict; this module doesn't know or care about its shape.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field


@dataclass
class NoiseConfig:
    duplicate_rate: float = 0.01
    reorder_rate: float = 0.02
    reorder_delay_range: tuple[float, float] = (1.0, 5.0)
    burst_rate: float = 0.0005
    burst_size_range: tuple[int, int] = (5, 20)


@dataclass(order=True)
class _Delayed:
    release_at: float
    seq: int = field(compare=False)
    message: dict = field(compare=False)


class NoiseInjector:
    """Wraps a clean message stream with duplicate/reorder/burst effects.

    Call `offer(message, now)` for every message the simulator produces; it
    returns the messages to publish immediately. Call `drain_due(now)` each
    tick to release any delayed (reordered) messages whose time has come.
    `now` is a float seconds virtual clock, supplied by the caller, so this
    class is deterministic and doesn't sleep.
    """

    def __init__(self, config: NoiseConfig | None = None, seed: int | None = None):
        self.config = config or NoiseConfig()
        self.rng = random.Random(seed)
        self._delayed: list[_Delayed] = []
        self._seq_counter = 0

    def offer(self, message: dict, now: float) -> list[dict]:
        out: list[dict] = []
        c = self.config

        if self.rng.random() < c.burst_rate:
            size = self.rng.randint(*c.burst_size_range)
            out.extend(message for _ in range(size))
        else:
            out.append(message)

        if self.rng.random() < c.duplicate_rate:
            out.append(message)

        if self.rng.random() < c.reorder_rate:
            delay = self.rng.uniform(*c.reorder_delay_range)
            self._seq_counter += 1
            self._delayed.append(_Delayed(release_at=now + delay, seq=self._seq_counter, message=message))
            out = out[:-1] if out and out[-1] is message else out  # don't send twice this tick

        return out

    def drain_due(self, now: float) -> list[dict]:
        due = [d for d in self._delayed if d.release_at <= now]
        if not due:
            return []
        self._delayed = [d for d in self._delayed if d.release_at > now]
        # Shuffle so releases don't happen in original send order — that's the point.
        self.rng.shuffle(due)
        return [d.message for d in due]
