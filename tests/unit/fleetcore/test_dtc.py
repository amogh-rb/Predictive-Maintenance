import pytest

from fleetcore.algorithms import dtc


@pytest.mark.parametrize(
    "code",
    ["P0128", "P0217", "P0520", "P0524", "P0562", "P0615", "P0300", "P0308", "P0700", "P0730", "P0A80", "P0AFA"],
)
def test_known_codes_from_the_failure_table_are_valid(code):
    assert dtc.is_valid(code)


@pytest.mark.parametrize("code", ["Z0128", "P4128", "P012", "P01288", "p0128", ""])
def test_malformed_codes_are_invalid(code):
    assert not dtc.is_valid(code)


def test_parse_generic_powertrain_code():
    parsed = dtc.parse("P0128")
    assert parsed.system == dtc.DtcSystem.POWERTRAIN
    assert parsed.origin == dtc.DtcOrigin.GENERIC
    assert parsed.specific == "128"


def test_parse_manufacturer_specific_code():
    parsed = dtc.parse("P1234")
    assert parsed.origin == dtc.DtcOrigin.MANUFACTURER


def test_parse_hex_specific_digits():
    parsed = dtc.parse("P0AFA")
    assert parsed.specific == "AFA"


def test_parse_invalid_raises():
    with pytest.raises(ValueError):
        dtc.parse("nope")


def test_in_range_matches_misfire_codes():
    for n in range(300, 309):
        assert dtc.in_range(f"P0{n}", "P0300", "P0308")
    assert not dtc.in_range("P0310", "P0300", "P0308")


def test_in_range_requires_same_system():
    assert not dtc.in_range("C0300", "P0300", "P0308")
