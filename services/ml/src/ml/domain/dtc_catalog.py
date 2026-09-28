"""Static DTC + failure-signature descriptions for the pgvector KB (PLAN §1, §2).

Source of truth for the DTC list is `simulator.domain.failure.FAILURE_DTCS`
for failures 1-5 (Must, already simulated); 6-8's DTCs are the ones PLAN §1's
table lists for the two Should/Could failures that use single codes (7, 8) —
6's "C0750-series" has no single code to register, so it's skipped here, same
as `FAILURE_DTCS` skips brake_wear's threshold-only detection. Populating this
KB is this session's deliverable regardless of whether 6-8's simulation/rules
exist yet (PLAN §6.3 session 5) — it's reference data, not detection logic.
"""
from __future__ import annotations

# code -> short human description (standard OBD-II/SAE J2012 meanings).
DTC_DESCRIPTIONS: dict[str, str] = {
    "P0128": "Coolant thermostat: engine coolant below thermostat regulating temperature",
    "P0217": "Engine coolant over-temperature condition",
    "P0520": "Engine oil pressure sensor/switch circuit malfunction",
    "P0521": "Engine oil pressure sensor/switch range/performance problem",
    "P0522": "Engine oil pressure sensor/switch circuit low voltage",
    "P0523": "Engine oil pressure sensor/switch circuit high voltage",
    "P0524": "Engine oil pressure too low",
    "P0562": "System voltage low (12V battery/alternator undercharge)",
    "P0615": "Starter relay circuit malfunction",
    "P0300": "Random/multiple cylinder misfire detected",
    "P0301": "Cylinder 1 misfire detected",
    "P0302": "Cylinder 2 misfire detected",
    "P0303": "Cylinder 3 misfire detected",
    "P0304": "Cylinder 4 misfire detected",
    "P0305": "Cylinder 5 misfire detected",
    "P0306": "Cylinder 6 misfire detected",
    "P0307": "Cylinder 7 misfire detected",
    "P0308": "Cylinder 8 misfire detected",
    "P0700": "Transmission control system malfunction",
    "P0730": "Incorrect gear ratio",
    "P0A80": "Replace hybrid/EV battery pack",
    "P0AFA": "Hybrid/EV battery pack performance deteriorated",
}

# failure_type -> (description, dtc codes). Description is the PLAN §1
# "early-warning pattern" column, phrased as the signature a similarity
# search should match against.
FAILURE_SIGNATURES: dict[str, tuple[str, list[str]]] = {
    "cooling": (
        "Coolant temperature creeps up relative to load and ambient over "
        "several days, with slower cool-down after stops, preceding a "
        "cooling-system failure (pump, thermostat, or leak).",
        ["P0128", "P0217"],
    ),
    "lubrication": (
        "Oil pressure at the same RPM band falls gradually over days, "
        "indicating pump wear or bearing wear ahead of a lubrication failure.",
        ["P0520", "P0521", "P0522", "P0523", "P0524"],
    ),
    "battery": (
        "Cranking voltage dip deepens daily and overnight drain increases, "
        "preceding a 12V battery, starter, or alternator failure.",
        ["P0562", "P0615"],
    ),
    "misfire": (
        "Ignition misfire DTCs recur with rising frequency and fuel "
        "consumption per kilometre rises ahead of a confirmed misfire.",
        ["P0300", "P0301", "P0302", "P0303", "P0304", "P0305", "P0306", "P0307", "P0308"],
    ),
    "brake_wear": (
        "Brake pad wear rate, combined with driving style and route type, "
        "projects the date pads reach the legal minimum thickness.",
        [],
    ),
    "tyre": (
        "One tyre's pressure or temperature drifts away from its siblings "
        "after weather effects are cancelled out, indicating a slow leak.",
        [],
    ),
    "transmission": (
        "Transmission fluid temperature creeps up and slip appears as RPM "
        "rises while road speed does not, ahead of a transmission failure.",
        ["P0700", "P0730"],
    ),
    "ev_battery": (
        "High-voltage cell imbalance widens, one cell runs hotter than the "
        "rest, and range per full charge shrinks ahead of an EV HV battery failure.",
        ["P0A80", "P0AFA"],
    ),
}
