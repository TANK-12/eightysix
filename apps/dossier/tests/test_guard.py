"""The memory guard. This machine has no swap, so running out locks it up."""

import guard


def test_it_pauses_when_memory_runs_low():
    assert guard.decide(1500, paused_by_us=False) == "pause"


def test_it_does_not_pause_twice():
    assert guard.decide(1500, paused_by_us=True) == "hold"


def test_it_resumes_once_there_is_real_headroom():
    assert guard.decide(5000, paused_by_us=True) == "resume"


def test_it_will_not_flap_between_the_two_marks():
    """Resuming at the pause threshold would pause again immediately."""
    between = (guard.PAUSE_BELOW_MB + guard.RESUME_ABOVE_MB) // 2
    assert guard.decide(between, paused_by_us=True) == "hold"
    assert guard.decide(between, paused_by_us=False) == "hold"
    assert guard.RESUME_ABOVE_MB > guard.PAUSE_BELOW_MB


def test_a_healthy_machine_is_left_alone():
    assert guard.decide(12000, paused_by_us=False) == "hold"


def test_an_unreadable_reading_changes_nothing():
    assert guard.decide(-1, paused_by_us=False) == "hold"
    assert guard.decide(-1, paused_by_us=True) == "hold"


def test_it_reads_real_memory_from_the_kernel():
    mb = guard.available_mb()
    assert mb > 0, "MemAvailable could not be read"
