"""VIN (Vehicle Identification Number) validation: ISO 3779 / SAE J853 check digit.

A VIN is 17 characters, positions 1-17, using only digits and uppercase letters
excluding I, O, Q (they're too easily confused with 1, 0, 0). Position 9 is a
check digit computed from the other 16 characters, letting a reader reject a
mis-transcribed VIN without a database lookup — exactly what the ingest-gateway
needs to do at line rate before a message reaches Kafka.

Algorithm (SAE J853 / ISO 3779 Annex):
1. Transliterate each character to a digit (letters map to 1-9, repeating after
   skipping multiples of 10; digits map to themselves).
2. Multiply each of the 17 positions by its fixed weight and sum.
3. remainder = sum % 11. The check digit is '0'-'9' for 0-9, or 'X' for 10.
"""
from __future__ import annotations

VIN_LENGTH = 17
CHECK_DIGIT_POSITION = 8  # 0-indexed; VIN position 9

_TRANSLITERATION = {
    "A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6, "G": 7, "H": 8,
    "J": 1, "K": 2, "L": 3, "M": 4, "N": 5, "P": 7, "R": 9,
    "S": 2, "T": 3, "U": 4, "V": 5, "W": 6, "X": 7, "Y": 8, "Z": 9,
}
_INVALID_LETTERS = {"I", "O", "Q"}

# Weight per position 1-17; position 9 (the check digit itself) carries weight 0.
_WEIGHTS = [8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2]

_VALID_CHARS = set("0123456789") | set(_TRANSLITERATION)


class InvalidVinError(ValueError):
    """Raised when a VIN has an invalid length or characters."""


def _transliterate(char: str) -> int:
    if char.isdigit():
        return int(char)
    if char in _TRANSLITERATION:
        return _TRANSLITERATION[char]
    raise InvalidVinError(f"character {char!r} is not a valid VIN character")


def _check_structure(vin: str) -> None:
    if len(vin) != VIN_LENGTH:
        raise InvalidVinError(f"VIN must be {VIN_LENGTH} characters, got {len(vin)}")
    bad = set(vin) - _VALID_CHARS - {"X"}
    if bad:
        raise InvalidVinError(f"VIN contains invalid characters: {sorted(bad)}")
    if set(vin) & _INVALID_LETTERS:
        raise InvalidVinError("VIN must not contain I, O, or Q")


def compute_check_digit(vin: str) -> str:
    """Return the correct check digit ('0'-'9' or 'X') for a 17-char VIN.

    The character already at position 9 is ignored — this computes what it
    *should* be, so callers can both generate and validate with one function.
    """
    _check_structure(vin)
    total = sum(_transliterate(c) * w for c, w in zip(vin, _WEIGHTS))
    remainder = total % 11
    return "X" if remainder == 10 else str(remainder)


def is_valid(vin: str) -> bool:
    """True if `vin` is structurally valid and its check digit matches."""
    try:
        _check_structure(vin)
    except InvalidVinError:
        return False
    return vin[CHECK_DIGIT_POSITION] == compute_check_digit(vin)


def with_check_digit(vin: str) -> str:
    """Return `vin` with position 9 replaced by its correct check digit."""
    digit = compute_check_digit(vin)
    return vin[:CHECK_DIGIT_POSITION] + digit + vin[CHECK_DIGIT_POSITION + 1 :]
