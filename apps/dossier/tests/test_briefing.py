"""Briefs must be written on a cadence and kept, not overwritten."""

from datetime import date, timedelta

import briefing
import store


def payload(generated, events=10, summary="Something happened [E0]."):
    return {
        "generated": generated,
        "window_days": 2,
        "events_total": events,
        "subjects_in_library": 5,
        "coverage_by_type": {"person": 5},
        "event_kinds": {"coverage": events},
        "countries": [
            {
                "country": "Germany",
                "events": events,
                "subjects": ["A", "B"],
                "latest": generated,
                "sample": [{"title": "x"} for _ in range(6)],
            }
        ],
        "summary": summary,
        "summary_points_dropped": 0,
        "cited_events": [
            {
                "date": generated,
                "subject": "A",
                "country": "Germany",
                "title": "A thing",
                "url": "u",
                "kind": "coverage",
                "detail": "d",
            }
        ],
        "jan_available": True,
    }


def test_a_brief_is_archived_under_its_kind_and_date(tmp_path):
    briefing.save(payload("2026-09-10"), kind="daily", root=tmp_path)
    written = list((tmp_path / "briefings" / "daily").glob("*.json"))
    assert [p.name for p in written] == ["2026-09-10.json"]


def test_briefs_accumulate_rather_than_overwrite(tmp_path):
    for day in ("2026-09-08", "2026-09-09", "2026-09-10"):
        briefing.save(payload(day), kind="daily", root=tmp_path)
    kept = sorted(p.stem for p in (tmp_path / "briefings" / "daily").glob("*.json"))
    assert kept == ["2026-09-08", "2026-09-09", "2026-09-10"]
    assert len(briefing.history("daily", root=tmp_path)) == 3


def test_daily_and_weekly_are_kept_apart(tmp_path):
    briefing.save(payload("2026-09-10"), kind="daily", root=tmp_path)
    briefing.save(payload("2026-09-10"), kind="weekly", root=tmp_path)
    assert briefing.read("daily", "2026-09-10", root=tmp_path)
    assert briefing.read("weekly", "2026-09-10", root=tmp_path)
    assert len(briefing.history("daily", root=tmp_path)) == 1
    assert len(briefing.history("weekly", root=tmp_path)) == 2 - 1


def test_history_is_newest_first(tmp_path):
    for day in ("2026-09-08", "2026-09-10", "2026-09-09"):
        briefing.save(payload(day), kind="daily", root=tmp_path)
    dates = [h["generated"] for h in briefing.history("daily", root=tmp_path)]
    assert dates == ["2026-09-10", "2026-09-09", "2026-09-08"]


def test_rewriting_the_same_day_does_not_duplicate_history(tmp_path):
    briefing.save(payload("2026-09-10", events=10), kind="daily", root=tmp_path)
    briefing.save(payload("2026-09-10", events=20), kind="daily", root=tmp_path)
    rows = briefing.history("daily", root=tmp_path)
    assert len(rows) == 1 and rows[0]["events_total"] == 20


def test_a_brief_is_due_when_none_exists(tmp_path):
    assert briefing.due("daily", root=tmp_path)
    assert briefing.due("weekly", root=tmp_path)


def test_todays_daily_brief_is_not_due_again(tmp_path):
    briefing.save(payload(date.today().isoformat()), kind="daily", root=tmp_path)
    assert not briefing.due("daily", root=tmp_path)


def test_a_weekly_brief_stays_current_for_a_week(tmp_path):
    three_days_ago = (date.today() - timedelta(days=3)).isoformat()
    briefing.save(payload(three_days_ago), kind="weekly", root=tmp_path)
    assert not briefing.due("weekly", root=tmp_path)
    eight_days_ago = (date.today() - timedelta(days=8)).isoformat()
    store.write_json(
        tmp_path / "briefings" / "weekly" / f"{eight_days_ago}.json",
        payload(eight_days_ago),
    )
    (tmp_path / "briefings" / "weekly" / f"{three_days_ago}.json").unlink()
    assert briefing.due("weekly", root=tmp_path)


def test_the_archived_copy_is_trimmed_but_still_readable(tmp_path):
    briefing.save(payload("2026-09-10"), kind="daily", root=tmp_path)
    stored = briefing.read("daily", "2026-09-10", root=tmp_path)
    assert stored["summary"] and stored["events_total"] == 10
    assert stored["countries"][0]["country"] == "Germany"
    assert "sample" not in stored["countries"][0], "bulk should not be archived"
    assert stored["highlights"][0]["title"] == "A thing"


def test_latest_is_the_most_recent_brief_written(tmp_path):
    briefing.save(
        payload("2026-09-09", summary="older [E0]."), kind="daily", root=tmp_path
    )
    briefing.save(
        payload("2026-09-10", summary="newer [E0]."), kind="weekly", root=tmp_path
    )
    assert briefing.latest(root=tmp_path)["summary"] == "newer [E0]."


def test_foreground_llm_work_takes_priority_over_background():
    """Bulk research starved the brief's summary call until it timed out after
    300 seconds. Background work must yield to anything the user is waiting on."""
    import threading
    import time

    import llm

    order = []

    def background():
        with llm._slot("low"):
            order.append("background")
            time.sleep(0.25)

    def foreground():
        with llm._slot("high"):
            order.append("foreground")

    # Fill every slot with background work, then queue more of both.
    holders = [threading.Thread(target=background) for _ in range(llm.LLM_CONCURRENCY)]
    for t in holders:
        t.start()
    time.sleep(0.05)

    fg = threading.Thread(target=foreground)
    later_bg = threading.Thread(target=background)
    fg.start()
    time.sleep(0.02)
    later_bg.start()

    for t in holders + [fg, later_bg]:
        t.join(timeout=5)

    assert "foreground" in order
    assert order.index("foreground") < len(order) - 1, "foreground ran last"
