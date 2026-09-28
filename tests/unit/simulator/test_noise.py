from simulator.infra.noise import NoiseConfig, NoiseInjector


def test_no_noise_passes_message_through_once():
    cfg = NoiseConfig(duplicate_rate=0, reorder_rate=0, burst_rate=0)
    injector = NoiseInjector(config=cfg, seed=1)
    out = injector.offer({"seq": 1}, now=0.0)
    assert out == [{"seq": 1}]


def test_always_duplicate_sends_message_twice():
    cfg = NoiseConfig(duplicate_rate=1.0, reorder_rate=0, burst_rate=0)
    injector = NoiseInjector(config=cfg, seed=1)
    out = injector.offer({"seq": 1}, now=0.0)
    assert out == [{"seq": 1}, {"seq": 1}]


def test_always_burst_sends_multiple_copies():
    cfg = NoiseConfig(duplicate_rate=0, reorder_rate=0, burst_rate=1.0, burst_size_range=(5, 5))
    injector = NoiseInjector(config=cfg, seed=1)
    out = injector.offer({"seq": 1}, now=0.0)
    assert len(out) == 5


def test_always_reorder_delays_the_message():
    cfg = NoiseConfig(duplicate_rate=0, reorder_rate=1.0, burst_rate=0, reorder_delay_range=(2.0, 2.0))
    injector = NoiseInjector(config=cfg, seed=1)
    out = injector.offer({"seq": 1}, now=0.0)
    assert out == []  # held back, not sent immediately
    assert injector.drain_due(now=1.0) == []  # not due yet
    assert injector.drain_due(now=2.0) == [{"seq": 1}]


def test_drain_due_releases_multiple_in_shuffled_order_deterministically():
    cfg = NoiseConfig(duplicate_rate=0, reorder_rate=1.0, burst_rate=0, reorder_delay_range=(1.0, 1.0))
    injector = NoiseInjector(config=cfg, seed=99)
    for i in range(10):
        injector.offer({"seq": i}, now=0.0)
    released = injector.drain_due(now=1.0)
    assert sorted(m["seq"] for m in released) == list(range(10))
