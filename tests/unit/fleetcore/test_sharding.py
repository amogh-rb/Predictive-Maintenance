import pytest

from fleetcore.algorithms.sharding import shard_for_vin, shard_topic


def test_shard_is_deterministic():
    assert shard_for_vin("1M8GDM9AXKP042788", 32) == shard_for_vin("1M8GDM9AXKP042788", 32)


def test_shard_within_range():
    for i in range(200):
        assert 0 <= shard_for_vin(f"VIN{i}", 16) < 16


def test_different_vins_spread_across_shards():
    shards = {shard_for_vin(f"VIN{i}", 8) for i in range(200)}
    assert len(shards) > 1  # not degenerate: doesn't collapse to a single shard


def test_rejects_non_positive_shard_count():
    with pytest.raises(ValueError):
        shard_for_vin("X", 0)


def test_shard_topic_embeds_tenant_shard_and_vin():
    topic = shard_topic("demo", "1M8GDM9AXKP042788", 32)
    shard = shard_for_vin("1M8GDM9AXKP042788", 32)
    assert topic == f"fleet/demo/shard-{shard}/1M8GDM9AXKP042788/telemetry"
