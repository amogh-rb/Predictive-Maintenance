import pytest

from fleetcore.algorithms import vin


def test_known_valid_vin():
    # Real-world reference VIN with a known-correct check digit (widely cited example).
    assert vin.is_valid("1M8GDM9AXKP042788")


def test_with_check_digit_round_trips():
    candidate = "1M8GDM9A0KP042788"
    fixed = vin.with_check_digit(candidate)
    assert vin.is_valid(fixed)
    assert fixed[: vin.CHECK_DIGIT_POSITION] == candidate[: vin.CHECK_DIGIT_POSITION]


def test_flipped_character_is_rejected():
    fixed = vin.with_check_digit("1M8GDM9A0KP042788")
    tampered = fixed[:5] + ("9" if fixed[5] != "9" else "8") + fixed[6:]
    assert not vin.is_valid(tampered)


@pytest.mark.parametrize("bad_letter", ["I", "O", "Q"])
def test_rejects_confusable_letters(bad_letter):
    vin17 = "1M8GDM9A0KP04278" + bad_letter
    assert not vin.is_valid(vin17)


@pytest.mark.parametrize("length", [16, 18])
def test_rejects_wrong_length(length):
    assert not vin.is_valid("1" * length)


def test_compute_check_digit_raises_on_invalid_structure():
    with pytest.raises(vin.InvalidVinError):
        vin.compute_check_digit("short")
