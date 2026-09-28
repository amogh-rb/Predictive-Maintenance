"""Geohash encode + precision truncation, used by the API to mask vehicle
location by role (PLAN §2 "Privacy": "location masking (geohash truncation)
by role"). A technician sees a coarse ~20 km cell instead of an exact
lat/lon; a fleet_admin/fleet_manager sees full precision.

Standard base32 geohash (Niemeyer's algorithm): interleave bits of lon/lat,
narrowing the lat/lon range at each bit, then pack 5 bits per base32 char.
"""
from __future__ import annotations

_BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz"


def encode(lat: float, lon: float, precision: int = 9) -> str:
    """Encode a (lat, lon) pair to a base32 geohash string of the given length."""
    if not (-90.0 <= lat <= 90.0):
        raise ValueError(f"lat {lat} out of range")
    if not (-180.0 <= lon <= 180.0):
        raise ValueError(f"lon {lon} out of range")

    lat_range = [-90.0, 90.0]
    lon_range = [-180.0, 180.0]
    geohash = []
    bit = 0
    ch = 0
    even_bit = True  # geohash interleaves starting with longitude

    while len(geohash) < precision:
        if even_bit:
            mid = (lon_range[0] + lon_range[1]) / 2
            if lon >= mid:
                ch = (ch << 1) | 1
                lon_range[0] = mid
            else:
                ch = ch << 1
                lon_range[1] = mid
        else:
            mid = (lat_range[0] + lat_range[1]) / 2
            if lat >= mid:
                ch = (ch << 1) | 1
                lat_range[0] = mid
            else:
                ch = ch << 1
                lat_range[1] = mid
        even_bit = not even_bit
        bit += 1
        if bit == 5:
            geohash.append(_BASE32[ch])
            bit = 0
            ch = 0

    return "".join(geohash)


# Role -> geohash precision (fewer chars = coarser cell). 5 chars is roughly
# a 4.9km x 4.9km cell, 9 is centimetre-precision (effectively exact).
ROLE_PRECISION = {
    "fleet_admin": 9,
    "fleet_manager": 9,
    "technician": 5,
    "auditor": 5,
}


def mask_for_role(lat: float, lon: float, role: str) -> str:
    """Return a geohash truncated to the precision allowed for `role`.

    Unknown roles get the most conservative (coarsest) precision rather than
    raising, since this sits on the response-serialisation path where a typo'd
    role should degrade privacy-safe, not leak exact coordinates.
    """
    precision = ROLE_PRECISION.get(role, min(ROLE_PRECISION.values()))
    return encode(lat, lon, precision)
