"""Nearest depot with a free bay (PLAN §2 algorithms: "Dijkstra/A* to the
nearest depot with a free slot").

There is no real road-network graph in this POC, so depots form a fully
connected mesh weighted by haversine great-circle distance (a defensible
stand-in for road distance at fleet scale), and the vehicle attaches to that
mesh via a single edge to its nearest depot ("last-mile onramp"). Plain
nearest-neighbour-by-distance would pick a full depot; Dijkstra over the mesh
is what lets the search fall through to the next-nearest depot *that has
capacity* instead, which is the actual routing problem being solved.
"""
from __future__ import annotations

import heapq
import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Depot:
    id: str
    lat: float
    lon: float
    bays: int
    active_bookings: int

    @property
    def free_bays(self) -> int:
        return self.bays - self.active_bookings


EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def _dijkstra(source: str, adjacency: dict[str, dict[str, float]]) -> dict[str, float]:
    """Standard Dijkstra shortest-path, O((V + E) log V) via a binary heap."""
    dist: dict[str, float] = {source: 0.0}
    visited: set[str] = set()
    heap: list[tuple[float, str]] = [(0.0, source)]

    while heap:
        d, node = heapq.heappop(heap)
        if node in visited:
            continue
        visited.add(node)
        for neighbour, weight in adjacency.get(node, {}).items():
            nd = d + weight
            if nd < dist.get(neighbour, math.inf):
                dist[neighbour] = nd
                heapq.heappush(heap, (nd, neighbour))

    return dist


def find_nearest_depot_with_capacity(
    vehicle_lat: float, vehicle_lon: float, depots: list[Depot]
) -> Depot | None:
    """Return the depot reachable at lowest total (great-circle) distance
    from the vehicle that currently has a free bay, or None if every depot
    listed is full.
    """
    if not depots:
        return None

    by_id = {d.id: d for d in depots}
    source = "__vehicle__"

    adjacency: dict[str, dict[str, float]] = {source: {}, **{d.id: {} for d in depots}}
    for d in depots:
        w = haversine_km(vehicle_lat, vehicle_lon, d.lat, d.lon)
        adjacency[source][d.id] = w
        adjacency[d.id][source] = w
    for i, a in enumerate(depots):
        for b in depots[i + 1 :]:
            w = haversine_km(a.lat, a.lon, b.lat, b.lon)
            adjacency[a.id][b.id] = w
            adjacency[b.id][a.id] = w

    distances = _dijkstra(source, adjacency)

    best_id, best_dist = None, math.inf
    for depot_id, dist in distances.items():
        if depot_id == source:
            continue
        depot = by_id[depot_id]
        if depot.free_bays > 0 and dist < best_dist:
            best_id, best_dist = depot_id, dist

    return by_id[best_id] if best_id is not None else None
