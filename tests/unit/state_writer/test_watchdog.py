import pytest

from state_writer.domain.watchdog import ConsumerStalled, StallWatchdog


def _clock():
    t = [0.0]

    def now():
        return t[0]

    def advance(seconds):
        t[0] += seconds

    return now, advance


def test_no_error_while_assigned():
    now, advance = _clock()
    watchdog = StallWatchdog(timeout_s=10.0, time_fn=now)
    for _ in range(5):
        watchdog.check(is_assigned=True)
        advance(100.0)  # even a long time is fine as long as it stays assigned


def test_no_error_for_a_brief_unassigned_gap():
    now, advance = _clock()
    watchdog = StallWatchdog(timeout_s=10.0, time_fn=now)
    watchdog.check(is_assigned=False)
    advance(5.0)
    watchdog.check(is_assigned=False)  # under the 10s threshold


def test_raises_once_unassigned_past_the_threshold():
    now, advance = _clock()
    watchdog = StallWatchdog(timeout_s=10.0, time_fn=now)
    watchdog.check(is_assigned=False)
    advance(11.0)
    with pytest.raises(ConsumerStalled):
        watchdog.check(is_assigned=False)


def test_regaining_assignment_resets_the_clock():
    now, advance = _clock()
    watchdog = StallWatchdog(timeout_s=10.0, time_fn=now)
    watchdog.check(is_assigned=False)
    advance(9.0)
    watchdog.check(is_assigned=True)  # reassigned just in time
    advance(9.0)
    watchdog.check(is_assigned=False)  # would have failed without the reset above
