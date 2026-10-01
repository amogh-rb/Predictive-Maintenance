"""Detects the "Up but not actually consuming" failure mode sessions 5 and 9
both hit: a Kafka consumer group loses its partition assignment (a broker
heartbeat blip) and the rejoin never completes. `docker compose ps` still
shows the container healthy, so nothing else notices — a real deployment
needs *some* signal to force a restart, since `restart: unless-stopped`
only helps once the process actually exits.
"""
from __future__ import annotations

import time
from typing import Callable


class ConsumerStalled(RuntimeError):
    pass


class StallWatchdog:
    def __init__(self, timeout_s: float = 120.0, time_fn: Callable[[], float] = time.monotonic):
        self._timeout_s = timeout_s
        self._time_fn = time_fn
        self._unassigned_since: float | None = None

    def check(self, is_assigned: bool) -> None:
        """Call once per poll loop iteration with the consumer's current
        assignment state. Raises `ConsumerStalled` once unassigned for
        longer than `timeout_s` — the caller lets that propagate and exit
        the process rather than catching it."""
        now = self._time_fn()
        if is_assigned:
            self._unassigned_since = None
            return
        if self._unassigned_since is None:
            self._unassigned_since = now
            return
        stalled_for = now - self._unassigned_since
        if stalled_for > self._timeout_s:
            raise ConsumerStalled(
                f"Kafka consumer group unassigned for {stalled_for:.0f}s "
                f"(> {self._timeout_s:.0f}s threshold) — exiting for a clean restart"
            )
