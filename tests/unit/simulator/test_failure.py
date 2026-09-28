from datetime import datetime, timedelta, timezone

from simulator.domain.failure import FailureType, FailurePlan, plan_failures
from simulator.domain.vehicle import generate_fleet


def test_plants_failures_in_the_3_to_5_percent_range():
    fleet = generate_fleet(size=10_000, seed=1)
    now = datetime.now(timezone.utc)
    plans = plan_failures([v.vin for v in fleet], now, seed=1)
    rate = len(plans) / len(fleet)
    assert 0.02 < rate < 0.06


def test_onset_precedes_failure_and_is_not_before_now():
    fleet = generate_fleet(size=2_000, seed=2)
    now = datetime.now(timezone.utc)
    plans = plan_failures([v.vin for v in fleet], now, seed=2)
    assert plans, "expected at least one planted failure"
    for plan in plans.values():
        assert plan.onset_at <= plan.failure_at
        assert plan.onset_at >= now


def test_failure_at_falls_within_window():
    fleet = generate_fleet(size=2_000, seed=3)
    now = datetime.now(timezone.utc)
    plans = plan_failures([v.vin for v in fleet], now, window_days=30, seed=3)
    for plan in plans.values():
        assert now <= plan.failure_at <= now + timedelta(days=30)


def test_severity_ramps_from_0_to_1():
    now = datetime.now(timezone.utc)
    plan = FailurePlan(
        vin="X", failure_type=FailureType.COOLING,
        onset_at=now, failure_at=now + timedelta(seconds=100),
    )
    assert plan.severity(now) == 0.0
    assert plan.severity(now + timedelta(seconds=50)) == 0.5
    assert plan.severity(now + timedelta(seconds=100)) == 1.0
    assert plan.severity(now + timedelta(seconds=200)) == 1.0  # held, not exceeded


def test_severity_before_onset_is_zero():
    now = datetime.now(timezone.utc)
    plan = FailurePlan(
        vin="X", failure_type=FailureType.BATTERY,
        onset_at=now + timedelta(seconds=10), failure_at=now + timedelta(seconds=20),
    )
    assert plan.severity(now) == 0.0
