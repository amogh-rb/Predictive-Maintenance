"""DTC (Diagnostic Trouble Code) parsing per the SAE J2012 / ISO 15031-6 format.

A DTC is 5 characters: `<system><origin><specific:3>`.
- system: P (Powertrain), C (Chassis), B (Body), U (Network/communication).
- origin: 0-3. Even (0, 2) is SAE-generic (defined by the standard, portable
  across OEMs); odd (1, 3) is manufacturer-specific.
- specific: 3 hex characters (0-9, A-F) — plain OBD-II codes only use 0-9, but
  newer HV-battery/EV codes (e.g. P0A80) use hex, so this parser accepts both.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

_DTC_RE = re.compile(r"^(?P<system>[PCBU])(?P<origin>[0-3])(?P<specific>[0-9A-F]{3})$")


class DtcSystem(str, Enum):
    POWERTRAIN = "P"
    CHASSIS = "C"
    BODY = "B"
    NETWORK = "U"


class DtcOrigin(str, Enum):
    GENERIC = "generic"
    MANUFACTURER = "manufacturer"


_GENERIC_ORIGINS = {"0", "2"}


@dataclass(frozen=True)
class ParsedDtc:
    code: str
    system: DtcSystem
    origin: DtcOrigin
    specific: str


def is_valid(code: str) -> bool:
    return bool(_DTC_RE.match(code))


def parse(code: str) -> ParsedDtc:
    match = _DTC_RE.match(code)
    if not match:
        raise ValueError(f"{code!r} is not a valid DTC (expected [PCBU][0-3][0-9A-F]{{3}})")
    origin = DtcOrigin.GENERIC if match["origin"] in _GENERIC_ORIGINS else DtcOrigin.MANUFACTURER
    return ParsedDtc(
        code=code,
        system=DtcSystem(match["system"]),
        origin=origin,
        specific=match["specific"],
    )


def in_range(code: str, start: str, end: str) -> bool:
    """True if `code` falls within an inclusive DTC range sharing the same system.

    Used to match ranges like the misfire codes P0300-P0308 against an
    incoming DTC without enumerating every code in the range.
    """
    parsed, lo, hi = parse(code), parse(start), parse(end)
    if not (parsed.system == lo.system == hi.system):
        return False
    return lo.specific <= parsed.specific <= hi.specific
