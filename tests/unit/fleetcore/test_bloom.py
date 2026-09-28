import pytest

from fleetcore.algorithms.bloom import BloomFilter


def test_no_false_negatives():
    bf = BloomFilter.for_capacity(expected_items=1000, false_positive_rate=0.01)
    items = [f"VIN{i}-seq{i}" for i in range(1000)]
    for item in items:
        bf.add(item)
    for item in items:
        assert item in bf


def test_unseen_item_usually_absent():
    bf = BloomFilter.for_capacity(expected_items=1000, false_positive_rate=0.01)
    for i in range(1000):
        bf.add(f"seen-{i}")
    false_positives = sum(1 for i in range(1000) if f"unseen-{i}" in bf)
    # generous slack over the configured 1% target so the test isn't flaky
    assert false_positives < 50


def test_len_counts_additions_not_capacity():
    bf = BloomFilter(size_bits=64, num_hashes=3)
    assert len(bf) == 0
    bf.add("a")
    bf.add("b")
    assert len(bf) == 2


def test_for_capacity_rejects_bad_inputs():
    with pytest.raises(ValueError):
        BloomFilter.for_capacity(expected_items=0, false_positive_rate=0.01)
    with pytest.raises(ValueError):
        BloomFilter.for_capacity(expected_items=100, false_positive_rate=1.5)


def test_dedup_use_case_vin_seq_pair():
    bf = BloomFilter.for_capacity(expected_items=10_000, false_positive_rate=0.001)
    key = "1HGCM82633A004352:42"
    assert key not in bf
    bf.add(key)
    assert key in bf
