"""The account usage bars follow the real account usage, not only the panel's
own conversations: every terminal session on the account uses the same window."""

import time
from pathlib import Path

import runner

LIVE = {
    "five_hour": {"utilization": 35.0, "resets_at": "2026-09-25T18:19:59+00:00"},
    "seven_day": {"utilization": 54.0, "resets_at": "2026-09-29T08:59:59+00:00"},
    "seven_day_opus": None,
}


def test_live_numbers_become_the_same_shape_the_stream_gives():
    got = runner.usage_from_live(LIVE)
    assert got["five_hour"]["used"] == 0.35
    assert got["seven_day"]["used"] == 0.54
    assert got["five_hour"]["resets_at"] == 1790360399
    assert got["source"] == "live"


def test_usage_is_polled_in_the_background_and_not_too_often(tmp_path):
    profiles = runner.Profiles(tmp_path / "data", main_dir=tmp_path / "main")
    calls: list[Path] = []

    def fetch(config: Path) -> dict:
        calls.append(config)
        return LIVE

    profiles.usage_fetch = fetch
    assert profiles.poll_usage("default", wait=True)
    assert calls == [tmp_path / "main"]
    stored = profiles._read()["usage"]["default"]
    assert stored["five_hour"]["used"] == 0.35 and stored["seen"] > time.time() - 5
    assert not profiles.poll_usage("default", wait=True)  # too soon: no second call
    assert len(calls) == 1


def test_a_failed_poll_keeps_the_last_numbers(tmp_path):
    profiles = runner.Profiles(tmp_path / "data", main_dir=tmp_path / "main")
    profiles.note_usage(
        "default",
        {"unifiedWindows": {"five_hour": {"utilization": 0.2, "resetsAt": 1}}},
    )

    def broken(config: Path) -> dict:
        raise OSError("offline")

    profiles.usage_fetch = broken
    profiles.poll_usage("default", wait=True)
    assert profiles._read()["usage"]["default"]["five_hour"]["used"] == 0.2


def too_many(retry_after=None):
    import email.message
    import urllib.error

    headers = email.message.Message()
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)
    return urllib.error.HTTPError("https://x", 429, "Too Many Requests", headers, None)


def test_a_rate_limited_check_backs_off_and_says_so(tmp_path):
    # A32: the usage endpoint answers 429 when checked too often; the bar keeps
    # its last good reading, says why it is old, and waits before asking again.
    profiles = runner.Profiles(tmp_path / "data", main_dir=tmp_path / "main")
    profiles.usage_fetch = lambda config: LIVE
    profiles.poll_usage("default", wait=True)
    calls = []

    def limited(config: Path) -> dict:
        calls.append(config)
        raise too_many(retry_after=600)

    profiles.usage_fetch = limited
    profiles._usage_polled["default"] = 0  # the normal interval has passed
    assert profiles.poll_usage("default", wait=True)
    stored = profiles._read()["usage"]["default"]
    assert stored["five_hour"]["used"] == 0.35  # the last good numbers stay
    assert "busy" in stored["check"]["error"]
    profiles._usage_polled["default"] = 0
    assert not profiles.poll_usage("default", wait=True)  # still backing off
    assert len(calls) == 1
    assert profiles._usage_retry["default"] >= time.time() + 590


def test_backoff_doubles_without_retry_after_and_clears_on_success(tmp_path):
    profiles = runner.Profiles(tmp_path / "data", main_dir=tmp_path / "main")

    def limited(config: Path) -> dict:
        raise too_many()

    profiles.usage_fetch = limited
    profiles.poll_usage("default", wait=True)
    first = profiles._usage_retry["default"] - time.time()
    profiles._usage_polled["default"] = profiles._usage_retry["default"] = 0
    profiles.poll_usage("default", wait=True)
    second = profiles._usage_retry["default"] - time.time()
    assert 100 < first < second <= runner.USAGE_MAX_BACKOFF + 1
    profiles.usage_fetch = lambda config: LIVE
    profiles._usage_polled["default"] = profiles._usage_retry["default"] = 0
    assert profiles.poll_usage("default", wait=True)
    stored = profiles._read()["usage"]["default"]
    assert "check" not in stored and stored["five_hour"]["used"] == 0.35
    assert profiles._usage_retry.get("default", 0) == 0


def test_a_stream_event_without_numbers_keeps_the_bars(tmp_path):
    # S26 (Emerson, 2026-09-28): "the Forge usage bars are not reliable and
    # keep breaking". Most rate_limit_events carry a status and no windows;
    # each one used to replace the stored usage, so the bar vanished until the
    # next live check (2 to 15 minutes).
    profiles = runner.Profiles(tmp_path / "data", main_dir=tmp_path / "main")
    profiles.usage_fetch = lambda config: LIVE
    profiles.poll_usage("default", wait=True)
    seen = profiles._read()["usage"]["default"]["seen"]
    profiles.note_usage(
        "default", {"status": "allowed", "rateLimitType": "five_hour", "resetsAt": 5}
    )
    stored = profiles._read()["usage"]["default"]
    assert stored["five_hour"]["used"] == 0.35
    assert stored["seven_day"]["used"] == 0.54
    assert stored["status"] == "allowed"
    assert stored["seen"] == seen  # no new numbers: the age stays honest


def test_a_stream_event_with_one_window_keeps_the_other(tmp_path):
    profiles = runner.Profiles(tmp_path / "data", main_dir=tmp_path / "main")
    profiles.usage_fetch = lambda config: LIVE
    profiles.poll_usage("default", wait=True)
    profiles.note_usage(
        "default",
        {
            "status": "allowed",
            "unifiedWindows": {"seven_day": {"utilization": 0.6, "resetsAt": 9}},
        },
    )
    stored = profiles._read()["usage"]["default"]
    assert stored["seven_day"]["used"] == 0.6
    assert stored["five_hour"]["used"] == 0.35
    assert stored["source"] == "stream"


def test_a_window_without_a_number_is_not_stored_as_one(tmp_path):
    profiles = runner.Profiles(tmp_path / "data", main_dir=tmp_path / "main")
    profiles.usage_fetch = lambda config: LIVE
    profiles.poll_usage("default", wait=True)
    profiles.note_usage("default", {"unifiedWindows": {"five_hour": {"resetsAt": 3}}})
    assert profiles._read()["usage"]["default"]["five_hour"]["used"] == 0.35


def test_a_reused_live_reading_is_dated_by_its_age():
    # usage.py hands back its last reading with "_age" when the server says wait
    got = runner.usage_from_live({**LIVE, "_age": 240})
    assert time.time() - 250 < got["seen"] < time.time() - 230


def test_a_live_answer_missing_a_window_keeps_the_old_one(tmp_path):
    profiles = runner.Profiles(tmp_path / "data", main_dir=tmp_path / "main")
    profiles.usage_fetch = lambda config: LIVE
    profiles.poll_usage("default", wait=True)
    profiles.usage_fetch = lambda config: {
        "five_hour": {"utilization": 40.0, "resets_at": None}
    }
    profiles._usage_polled["default"] = 0
    profiles.poll_usage("default", wait=True)
    stored = profiles._read()["usage"]["default"]
    assert stored["five_hour"]["used"] == 0.4
    assert stored["seven_day"]["used"] == 0.54
    assert "check" not in stored


def test_an_older_live_reading_never_replaces_newer_stream_numbers(tmp_path):
    """Emerson, 2026-10-07: "the usage bar keeps showing the actual usage and
    then changing back to 98 hours ago". usage.py hands back a 4-day-old cached
    reading while the endpoint answers 429; it must not overwrite the fresher
    numbers a conversation's rate_limit_event gave."""
    profiles = runner.Profiles(tmp_path / "data", main_dir=tmp_path / "main")
    profiles.note_usage(
        "default",
        {
            "unifiedWindows": {
                "five_hour": {"utilization": 0.61, "resetsAt": 111},
                "seven_day": {"utilization": 0.4, "resetsAt": 222},
            }
        },
    )
    before = profiles._read()["usage"]["default"]
    profiles.usage_fetch = lambda config: {**LIVE, "_age": 345600}
    assert profiles.poll_usage("default", wait=True)
    after = profiles._read()["usage"]["default"]
    assert after["five_hour"]["used"] == 0.61 and after["seven_day"]["used"] == 0.4
    assert after["seen"] == before["seen"] and after["source"] == "stream"
    assert "rate-limiting" in after["check"]["error"]
    # a fresh live reading still wins over the stream's
    profiles._usage_polled.clear()
    profiles.usage_fetch = lambda config: LIVE
    assert profiles.poll_usage("default", wait=True)
    fresh = profiles._read()["usage"]["default"]
    assert fresh["five_hour"]["used"] == 0.35 and fresh["source"] == "live"
    assert fresh["seen"] >= before["seen"] and "check" not in fresh


def test_each_window_keeps_its_newest_reading(tmp_path):
    """A live answer that is newer overall but older for one window (the
    stream gave a newer five-hour number since) keeps that window."""
    profiles = runner.Profiles(tmp_path / "data", main_dir=tmp_path / "main")
    profiles.usage_fetch = lambda config: {**LIVE, "_age": 600}
    profiles.poll_usage("default", wait=True)
    profiles.note_usage(
        "default",
        {"unifiedWindows": {"five_hour": {"utilization": 0.7, "resetsAt": 1}}},
    )
    profiles._usage_polled.clear()
    profiles.usage_fetch = lambda config: {**LIVE, "_age": 300}
    profiles.poll_usage("default", wait=True)
    got = profiles._read()["usage"]["default"]
    assert got["five_hour"]["used"] == 0.7  # the stream's, newer than 300 s ago
    assert got["seven_day"]["used"] == 0.54  # live, newer than its last one
