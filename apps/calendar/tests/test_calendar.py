"""The Calendar: the event store, every feeder on fixture data, the collector
(state kept, nothing logged twice, reminders fired), and the HTTP API."""

import json
import os
import pickle
import time

import pytest

import collector as collector_mod
import store as store_mod
from sources import apps, claude, forge, hyprland, jan, nyarch


@pytest.fixture
def db(tmp_path):
    s = store_mod.Store(tmp_path / "e.db")
    yield s
    s.close()


# --- store ----------------------------------------------------------------------


def test_add_query_update_delete_and_keys_dedupe(db):
    e = db.add(
        {
            "title": "  Maths   test ",
            "kind": "milestone",
            "ts": 100,
            "tags": "uni, maths",
        }
    )
    assert (
        e["title"] == "Maths test"
        and e["tags"] == ["uni", "maths"]
        and e["source"] == "emerson"
    )
    assert db.add({"title": "x", "key": "k1", "ts": 200, "source": "script:backup"})
    assert db.add({"title": "x again", "key": "k1", "ts": 201}) is None
    assert [x["title"] for x in db.query(0, 1000)] == ["Maths test", "x"]
    assert [x["title"] for x in db.query(0, 1000, sources=["script"])] == ["x"]
    assert [x["title"] for x in db.query(text="math")] == ["Maths test"]
    assert db.update(e["id"], {"title": "Maths test 2"})["title"] == "Maths test 2"
    assert db.delete(e["id"]) and not db.delete(e["id"])


@pytest.mark.parametrize(
    "said,stored",
    [
        ("sudo is 9214 now doo all the task", "sudo is •••• now doo all the task"),
        (
            "9214 is my sudo i dont get what the issue is",
            "•••• is my sudo i dont get what the issue is",
        ),
        ("9214 sudo", "•••• sudo"),
        ("my password: 55123", "my password: ••••"),
        ("add 15 more features", "add 15 more features"),
        ("port 8453 is the calendar", "port 8453 is the calendar"),
    ],
)
def test_passwords_typed_in_chat_are_masked(db, said, stored):
    assert db.add({"title": said, "body": said})["title"] == stored


def test_bad_events_are_refused(db):
    for bad in [
        {"title": ""},
        {"title": "a", "kind": "party"},
        {"title": "a", "ts": "soon"},
        {"title": "a", "source": "bad source!"},
    ]:
        with pytest.raises(store_mod.EventError):
            db.add(bad)


def test_odd_times_and_tags_are_refused_not_crashed(db):
    for bad in [
        {"title": "a", "ts": "nan"},
        {"title": "a", "ts": "inf"},
        {"title": "a", "ts": 1e300},
        {"title": "a", "end_ts": "-inf"},
        {"title": "a", "tags": 5},
        {"title": "a", "tags": True},
    ]:
        with pytest.raises(store_mod.EventError):
            db.add(bad)
    e = db.add({"title": "ok", "ts": 100})
    for bad in [{"ts": "nan"}, {"end_ts": float("inf")}, {"tags": 5}]:
        with pytest.raises(store_mod.EventError):
            db.update(e["id"], bad)


def test_a_bad_time_already_stored_does_not_break_reading(db):
    # one script once logged ts=inf: every search that met it answered 500
    db.add({"title": "fine", "ts": 100})
    with db._lock:
        db.db.execute(
            "INSERT INTO events (ts, end_ts, source, kind, title, created) "
            "VALUES (?, NULL, 'script:x', 'note', 'broken', 0)",
            (float("inf"),),
        )
        db.db.execute(
            "INSERT INTO events (ts, end_ts, source, kind, title, created) "
            "VALUES (200, ?, 'script:x', 'note', 'open end', 0)",
            (float("inf"),),
        )
        db.db.commit()
    found = db.query()
    json.dumps(found, allow_nan=False)
    assert [(e["title"], e["end_ts"]) for e in found] == [
        ("fine", None),
        ("open end", None),
    ]
    assert None not in db.day_counts(-1e12, 1e13, 0)


def test_day_counts_and_pruning_spare_emersons_own(db):
    day = 86400 * 10
    db.add({"title": "a", "source": "claude", "ts": day + 10})
    db.add({"title": "b", "source": "script:x", "ts": day + 20})
    db.add({"title": "mine", "source": "emerson", "ts": day + 30})
    assert db.day_counts(day, day + 86400, 0) == {
        "1970-01-11": {"claude": 1, "script": 1, "emerson": 1}
    }
    assert db.prune(1, now=day + 5 * 86400) == 2
    assert [e["title"] for e in db.query()] == ["mine"]


# --- feeders ----------------------------------------------------------------------


def test_claude_feeder_reads_only_typed_messages_and_resumes(tmp_path):
    proj = tmp_path / "-home-ejb-Forge"
    proj.mkdir()
    lines = [
        {
            "type": "user",
            "timestamp": "2026-09-24T10:00:00Z",
            "uuid": "u1",
            "message": {"content": "make more and more"},
        },
        {
            "type": "user",
            "timestamp": "2026-09-24T10:00:05Z",
            "uuid": "u2",
            "message": {"content": [{"type": "tool_result", "content": "x"}]},
        },
        {
            "type": "user",
            "timestamp": "2026-09-24T10:00:06Z",
            "uuid": "u3",
            "isMeta": True,
            "message": {"content": "meta"},
        },
        {
            "type": "assistant",
            "timestamp": "2026-09-24T10:00:07Z",
            "message": {"content": "hi"},
        },
    ]
    f = proj / "s1.jsonl"
    f.write_text("\n".join(json.dumps(x) for x in lines) + "\n")
    state = {}
    events = claude.collect(state, tmp_path)
    assert [e["kind"] for e in events] == ["session", "said"]
    assert (
        events[1]["title"] == "make more and more" and events[1]["key"] == "claude:u1"
    )
    assert claude.collect(state, tmp_path) == []  # nothing new
    with f.open("a") as out:
        out.write(
            json.dumps(
                {
                    "type": "user",
                    "timestamp": "2026-09-24T11:00:00Z",
                    "uuid": "u4",
                    "message": {"content": "so tldr"},
                }
            )
            + "\n"
        )
        out.write('{"type": "user", "half written')
    assert [e["title"] for e in claude.collect(state, tmp_path)] == ["so tldr"]


def test_jan_feeder_logs_threads_and_user_messages(tmp_path):
    t = tmp_path / "t1"
    t.mkdir()
    (t / "thread.json").write_text(json.dumps({"title": "Poems"}))
    msgs = [
        {
            "id": "a",
            "role": "user",
            "created_at": 1789000000000,
            "content": [{"type": "text", "text": {"value": "write 5 paragraphs"}}],
        },
        {
            "id": "b",
            "role": "assistant",
            "created_at": 1789000001000,
            "content": [{"type": "text", "text": {"value": "ok"}}],
        },
    ]
    (t / "messages.jsonl").write_text("\n".join(json.dumps(m) for m in msgs))
    events = jan.collect({}, tmp_path)
    assert [(e["kind"], e["title"]) for e in events] == [
        ("session", "Jan: Poems"),
        ("said", "write 5 paragraphs"),
    ]


def test_nyarch_feeder_notes_history_first_then_logs_new_and_refuses_code(tmp_path):
    path = tmp_path / "chats.pkl"
    chats = {
        "chats": {
            0: {
                "id": "c1",
                "name": "Hi",
                "chat": [{"User": "User", "Message": "hello"}],
            }
        }
    }
    path.write_bytes(pickle.dumps(chats))
    state = {}
    assert nyarch.collect(state, path) == []  # history has no times: only noted
    chats["chats"][0]["chat"] += [
        {"User": "Assistant", "Message": "hey"},
        {"User": "User", "Message": "open firefox"},
    ]
    path.write_bytes(pickle.dumps(chats))
    os.utime(path, (time.time() + 5, time.time() + 5))
    events = nyarch.collect(state, path, now=123)
    assert [(e["title"], e["ts"]) for e in events] == [("open firefox", 123)]

    class Evil:
        def __reduce__(self):
            return (os.system, ("echo pwned",))

    path.write_bytes(pickle.dumps({"chats": {0: Evil()}}))
    os.utime(path, (time.time() + 9, time.time() + 9))
    assert nyarch.collect(state, path) == []  # refused, not run


def test_apps_feeder_logs_opens_and_closes_after_the_first_look():
    state = {}
    assert apps.collect(state, now=0, programs={"Firefox"}, flatpaks=set()) == []
    opened = apps.collect(state, now=60, programs={"Firefox"}, flatpaks={"Jan"})
    assert [e["title"] for e in opened] == ["Opened Jan"]
    closed = apps.collect(
        state, now=60 + 3 * 3600 + 120, programs=set(), flatpaks={"Jan"}
    )
    assert [e["title"] for e in closed] == ["Closed Firefox (open 3 h 3 min)"]


def test_desktop_files_are_parsed_and_hidden_ones_skipped(tmp_path):
    (tmp_path / "ff.desktop").write_text(
        "[Desktop Entry]\nName=Firefox\nExec=/usr/lib/firefox/firefox %u\nType=Application\n"
    )
    (tmp_path / "hid.desktop").write_text(
        "[Desktop Entry]\nName=Helper\nExec=helper\nNoDisplay=true\n"
    )
    (tmp_path / "act.desktop").write_text(
        "[Desktop Entry]\nName=Kitty\nExec=kitty\n[Desktop Action new]\nName=New window\nExec=kitty --new\n"
    )
    programs, _ = apps.launchers([tmp_path])
    assert programs == {"firefox": "Firefox", "kitty": "Kitty"}


def test_forge_feeder_uses_ports(tmp_path):
    (tmp_path / "cal").mkdir()
    (tmp_path / "cal" / "forge_app.json").write_text(
        json.dumps({"port": 8453, "label": "Calendar"})
    )
    ports = forge.forge_ports(tmp_path)
    state = {}
    assert forge.collect(state, now=1, ports=ports, open_ports=set()) == []
    assert [
        e["title"] for e in forge.collect(state, now=2, ports=ports, open_ports={8453})
    ] == ["Forge: opened Calendar"]
    assert [
        e["title"] for e in forge.collect(state, now=3, ports=ports, open_ports=set())
    ] == ["Forge: closed Calendar"]


def test_hyprland_feeder_logs_new_window_titles_only():
    state = {}
    assert (
        hyprland.collect(
            state, now=1, windows=[{"address": "0x1", "class": "kitty", "title": "~"}]
        )
        == []
    )
    ev = hyprland.collect(
        state,
        now=2,
        windows=[
            {"address": "0x1", "class": "kitty"},
            {"address": "0x2", "class": "firefox", "title": "YouTube"},
        ],
    )
    assert [e["title"] for e in ev] == ["firefox: YouTube"]


# --- collector ----------------------------------------------------------------------


class FakeFeeder:
    NAME = "fake"
    LABEL = "Fake"
    INTERVAL = 10
    DEFAULT_ON = True

    def __init__(self):
        self.calls = 0

    def collect(self, state):
        self.calls += 1
        state["n"] = state.get("n", 0) + 1
        return [
            {
                "title": f"tick {state['n']}",
                "source": "fake",
                "key": f"fake:{state['n'] // 2}",
            }
        ]


class BrokenFeeder(FakeFeeder):
    NAME = "broken"

    def collect(self, state):
        raise RuntimeError("boom")


def test_collector_runs_on_interval_keeps_state_and_survives_a_broken_feeder(
    tmp_path, db, monkeypatch
):
    fake = FakeFeeder()
    c = collector_mod.Collector(db, tmp_path, {"fake": fake, "broken": BrokenFeeder()})
    c.tick(now=100)
    c.tick(now=105)  # too soon
    c.tick(now=111)
    assert fake.calls == 2
    assert len(db.query()) == 2  # keys 0 and 1
    assert c.last["broken"]["error"] == "RuntimeError: boom"
    again = collector_mod.Collector(db, tmp_path, {"fake": fake})
    assert again.states["fake"]["n"] == 2  # state survived a restart
    c.save_settings({"paused": True})
    c.tick(now=500)
    assert fake.calls == 2


def test_due_reminders_pop_up_once(tmp_path, db, monkeypatch):
    shown = []
    monkeypatch.setattr(collector_mod, "notify", lambda t, b: shown.append(t))
    db.add({"title": "Maths test opens", "kind": "reminder", "ts": 50})
    db.add({"title": "Later", "kind": "reminder", "ts": 5000})
    c = collector_mod.Collector(db, tmp_path, {})
    c.tick(now=100)
    c.tick(now=200)
    assert shown == ["Maths test opens"]


# --- HTTP ----------------------------------------------------------------------------


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_CALENDAR_DATA", str(tmp_path / "data"))
    monkeypatch.setenv("FORGE_CALENDAR_NO_COLLECT", "1")
    import importlib

    import web_app

    importlib.reload(web_app)
    from fastapi.testclient import TestClient

    with TestClient(web_app.app) as c:
        yield c


def test_api_needs_the_forge_header_and_round_trips(client):
    assert client.get("/api/events").status_code == 403
    h = {"X-Forge": "1"}
    r = client.post(
        "/api/events",
        headers=h,
        json={"title": "Backup done", "source": "script:backup", "key": "b1"},
    )
    assert r.status_code == 200 and r.json()["event"]["source"] == "script:backup"
    assert client.post(
        "/api/events", headers=h, json={"title": "Backup done", "key": "b1"}
    ).json()["duplicate"]
    assert client.post("/api/events", headers=h, json={"title": ""}).status_code == 400
    eid = r.json()["event"]["id"]
    assert (
        client.patch(
            f"/api/events/{eid}", headers=h, json={"title": "Backup finished"}
        ).json()["event"]["title"]
        == "Backup finished"
    )
    assert [
        e["title"]
        for e in client.get("/api/events?q=backup", headers=h).json()["events"]
    ] == ["Backup finished"]
    feeders = client.get("/api/feeders", headers=h).json()
    assert {f["name"] for f in feeders["feeders"]} == {
        "apps",
        "claude",
        "forge",
        "hyprland",
        "jan",
        "nyarch",
    }
    s = client.post(
        "/api/feeders/settings",
        headers=h,
        json={"enabled": {"apps": False}, "keep_days": 30},
    ).json()["settings"]
    assert s["enabled"]["apps"] is False and s["keep_days"] == 30
    assert client.delete(f"/api/events/{eid}", headers=h).json()["ok"]


def test_api_answers_400_not_500_to_wrong_types(client):
    h = {"X-Forge": "1", "Content-Type": "application/json"}
    for body in (
        '{"title": "a", "tags": 5}',
        '{"title": "a", "ts": "inf"}',
        '{"title": "a", "ts": NaN}',
    ):
        assert client.post("/api/events", headers=h, content=body).status_code == 400
    eid = client.post("/api/events", headers=h, json={"title": "ok"}).json()["event"][
        "id"
    ]
    r = client.patch(f"/api/events/{eid}", headers=h, content='{"ts": "nan"}')
    assert r.status_code == 400
    for body in (
        '{"enabled": [1]}',
        '{"enabled": "apps"}',
        '{"keep_days": 1e400}',
        '{"keep_days": "12x"}',
    ):
        r = client.post("/api/feeders/settings", headers=h, content=body)
        assert r.status_code == 400, body
    assert "keep_days" in r.json()["detail"]
    assert client.get("/api/events?limit=10000", headers=h).status_code == 200


def test_negative_keep_days_long_searches_and_odd_times_are_refused(client):
    h = {"X-Forge": "1", "Content-Type": "application/json"}
    r = client.post("/api/feeders/settings", headers=h, json={"keep_days": -5})
    assert r.status_code == 400 and "forever" in r.json()["detail"]
    assert client.get("/api/feeders", headers=h).json()["settings"]["keep_days"] != 0
    r = client.get("/api/events", headers=h, params={"q": "a" * 60000})
    assert r.status_code == 200
    for body in (
        {"title": "t", "ts": True},
        {"title": "t", "ts": 2e9, "end_ts": 1e9},
    ):
        assert client.post("/api/events", headers=h, json=body).status_code == 400
    e = client.post("/api/events", headers=h, json={"title": "t", "ts": 1000}).json()
    eid = e["event"]["id"]
    assert (
        client.patch(f"/api/events/{eid}", headers=h, json={"ts": None}).status_code
        == 400
    )
    r = client.patch(f"/api/events/{eid}", headers=h, json={"end_ts": 500})
    assert r.status_code == 400
    r = client.patch(f"/api/events/{eid}", headers=h, json={"end_ts": 1500})
    assert r.status_code == 200 and r.json()["event"]["ts"] == 1000
