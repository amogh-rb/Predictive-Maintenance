"""Response-shaping rules that depend only on role, no I/O (PLAN §2
"Privacy": location masking by role). Wraps fleetcore's geohash algorithm.
"""
from __future__ import annotations

from fleetcore.algorithms.geohash import mask_for_role


def masked_location(lat: float, lon: float, role: str) -> dict:
    """A coarse geohash cell for technician/auditor, exact lat/lon for
    fleet_admin/fleet_manager. Returning a geohash (not truncated
    lat/lon numbers) means a technician genuinely cannot reconstruct the
    original coordinates to better than the cell's ~5km resolution.
    """
    if role in ("fleet_admin", "fleet_manager"):
        return {"lat": lat, "lon": lon}
    return {"geohash": mask_for_role(lat, lon, role)}
