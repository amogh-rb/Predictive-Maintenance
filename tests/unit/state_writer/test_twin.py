from state_writer.domain.twin import merge_twin


def _fast(vin="VIN1", tenant="demo", seq=1, coolant_c=90, speed_kmh=50):
    return {
        "vin": vin, "tenant": tenant, "msg_type": "FAST", "seq": seq,
        "ts": "2026-09-28T12:00:00Z",
        "payload": {"coolant_c": coolant_c, "speed_kmh": speed_kmh, "rpm": None},
    }


def _health(vin="VIN1", tenant="demo", seq=1, charge_v=13.5):
    return {
        "vin": vin, "tenant": tenant, "msg_type": "HEALTH", "seq": seq,
        "ts": "2026-09-28T12:01:00Z",
        "payload": {"charge_v": charge_v, "mil_on": False},
    }


def test_first_message_creates_twin():
    doc = merge_twin(None, _fast())
    assert doc["vin"] == "VIN1"
    assert doc["tenant"] == "demo"
    assert doc["coolant_c"] == 90
    assert "rpm" not in doc  # None-valued fields are dropped, not stored as null


def test_a_later_none_does_not_clobber_an_earlier_value():
    doc = merge_twin(None, _fast(seq=1, coolant_c=90))
    doc = merge_twin(doc, {**_fast(seq=2), "payload": {"coolant_c": None, "speed_kmh": 60}})
    assert doc["coolant_c"] == 90
    assert doc["speed_kmh"] == 60


def test_exact_retry_seq_is_dropped():
    doc = merge_twin(None, _fast(seq=5))
    assert merge_twin(doc, _fast(seq=5)) is None


def test_out_of_order_seq_is_dropped():
    doc = merge_twin(None, _fast(seq=5))
    assert merge_twin(doc, _fast(seq=3)) is None


def test_seq_counters_are_independent_per_msg_type():
    doc = merge_twin(None, _fast(seq=100))
    doc = merge_twin(doc, _health(seq=1))  # HEALTH's own counter, unaffected by FAST's seq=100
    assert doc is not None
    assert doc["charge_v"] == 13.5


def test_fields_from_different_msg_types_coexist_in_one_twin():
    doc = merge_twin(None, _fast(coolant_c=95))
    doc = merge_twin(doc, _health(charge_v=12.1))
    assert doc["coolant_c"] == 95
    assert doc["charge_v"] == 12.1
