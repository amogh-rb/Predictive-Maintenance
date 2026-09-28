import pytest

from api.domain.pagination import decode_cursor, encode_cursor


def test_roundtrip():
    cursor = encode_cursor(0.873, "abc-123")
    decoded = decode_cursor(cursor)
    assert decoded.risk_score == 0.873
    assert decoded.vehicle_id == "abc-123"


def test_cursor_is_opaque_not_plaintext():
    cursor = encode_cursor(0.5, "vehicle-1")
    assert "vehicle-1" not in cursor
    assert "0.5" not in cursor


def test_malformed_cursor_raises_value_error():
    with pytest.raises(ValueError):
        decode_cursor("not-valid-base64!!!")


def test_truncated_json_raises_value_error():
    import base64

    bad = base64.urlsafe_b64encode(b'{"r": 1.0}').decode()  # missing "v"
    with pytest.raises(ValueError):
        decode_cursor(bad)
