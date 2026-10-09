"""The "Get all new info" button: five years for what is held, nothing lost.

No network and no model.
"""

import time
from datetime import date

from fastapi.testclient import TestClient

import dossier_link
import store
import sweep
import web_app
from signals import registry as sources
from signals.registry import Reading, SignalSpec


def _fake_source(seen):
    def fetch(name, ctx):
        seen.append(ctx.days)
        return [Reading(date=date.today().isoformat(), value=2.0)]

    return SignalSpec(
        name="fake", label="Fake", kind="attention", unit="u", fetch=fetch
    )


def test_a_history_refresh_rereads_five_years_and_keeps_old_readings(
    tmp_path, monkeypatch
):
    seen = []
    monkeypatch.setattr(sources, "enabled_sources", lambda: [_fake_source(seen)])
    old = {"date": "2019-01-01", "value": 1.0, "detail": "", "url": "", "sample": 0}
    store.write_json(store.series_path("x", "fake", tmp_path), [old])

    sweep.sweep_subject("x", "X", sweep.Context(fetcher=None, days=60), root=tmp_path)
    assert seen == [60], "an ordinary sweep of a held source reads the short window"

    sweep.sweep_subject(
        "x", "X", sweep.Context(fetcher=None, days=60), root=tmp_path, history=True
    )
    assert seen[-1] == sweep.HISTORY_DAYS
    dates = [p["date"] for p in store.read_series("x", "fake", tmp_path)]
    assert dates == ["2019-01-01", date.today().isoformat()]


def test_held_subjects_are_the_ones_with_signals(tmp_path, monkeypatch):
    store.write_json(store.series_path("x", "fake", tmp_path), [])
    monkeypatch.setattr(
        dossier_link,
        "library",
        lambda: [{"slug": "x", "name": "X", "entity_type": "country"}],
    )
    assert sweep.held_subjects(tmp_path) == [
        {"slug": "x", "name": "X", "entity_type": "country"}
    ]


def _idle() -> dict:
    """A fresh sweep state. The route marks the sweep running before its thread
    starts, and the stand-in runner below never clears it, so a shared state
    would leave the next test answering "already running"."""
    return {"running": False, "done": 0, "total": 0, "log": [], "last": ""}


def test_the_button_sweeps_every_held_subject_with_history(monkeypatch):
    runs = []
    held = [{"slug": "x", "name": "X", "entity_type": ""}]
    monkeypatch.setattr(sweep, "held_subjects", lambda root=None: held)
    monkeypatch.setattr(sweep, "watchlist", lambda limit=40: [{"slug": "other"}])
    monkeypatch.setattr(web_app, "_sweep_state", _idle())
    monkeypatch.setattr(web_app, "_run_sweep", lambda *args: runs.append(args))
    response = TestClient(web_app.app).post("/api/sweep", json={"history": True})
    assert response.status_code == 200 and response.json()["subjects"] == 1
    # The sweep runs on its own thread; give it a moment to be called.
    for _ in range(50):
        if runs:
            break
        time.sleep(0.02)
    subjects, _days, _only, history = runs[0]
    assert subjects == held and history is True


def test_with_nothing_swept_yet_the_button_falls_back_to_the_watchlist(monkeypatch):
    runs = []
    monkeypatch.setattr(sweep, "held_subjects", lambda root=None: [])
    monkeypatch.setattr(
        sweep, "watchlist", lambda limit=40: [{"slug": "w", "name": "W"}]
    )
    monkeypatch.setattr(web_app, "_sweep_state", _idle())
    monkeypatch.setattr(web_app, "_run_sweep", lambda *args: runs.append(args))
    response = TestClient(web_app.app).post("/api/sweep", json={"history": True})
    assert response.json()["subjects"] == 1
