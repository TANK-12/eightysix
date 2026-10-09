import json
import os
import sys
import time

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CREW_HOME", str(tmp_path / "crews"))
    import web_app

    # no real sessions, no real Claude app: tests that want them set their own
    (tmp_path / "no-sessions").mkdir()
    monkeypatch.setattr(web_app, "SESSIONS_DIR", str(tmp_path / "no-sessions"))
    monkeypatch.setattr(web_app, "_claude_call", lambda path, method="GET": None)
    monkeypatch.setattr(web_app, "_names_cache", (0.0, {}))
    return TestClient(web_app.app), web_app


def test_jan_board_exists_before_anyone_posts(client):
    c, _ = client
    assert c.get("/api/boards").json()["boards"] == ["jan"]
    r = c.get("/api/board/jan").json()
    assert r["board"]["notes"] == []


def test_emerson_posts_and_a_session_sees_it(client):
    c, web_app = client
    assert (
        c.post(
            "/api/board/jan/post", json={"text": "reload Jan", "to": "ejb-9d"}
        ).status_code
        == 200
    )
    note = c.get("/api/board/jan").json()["board"]["notes"][0]
    assert (note["from"], note["to"], note["text"]) == (
        "Emerson",
        "ejb-9d",
        "reload Jan",
    )
    out = web_app.crew.cmd_notes(
        web_app._run("jan", "dump"),
        web_app.crew.parser().parse_args(["notes", "jan", "--for", "ejb-9d"]),
    )
    assert "Emerson -> ejb-9d" in out


def test_answering_a_note_closes_it(client):
    c, _ = client
    c.post("/api/board/jan/post", json={"text": "hi"})
    assert c.post("/api/board/jan/ack/1", json={"note": "seen"}).status_code == 200
    ack = c.get("/api/board/jan").json()["board"]["notes"][0]["ack"]
    assert (ack["by"], ack["note"]) == ("Emerson", "seen")
    assert c.post("/api/board/jan/ack/7", json={}).status_code == 400


def test_unknown_board_and_empty_note_are_refused(client):
    c, _ = client
    assert c.get("/api/board/nope").status_code == 404
    assert c.post("/api/board/jan/post", json={"text": "  "}).status_code == 400


def _fake_proc(root, pid, alias, utime):
    d = root / str(pid)
    d.mkdir(parents=True, exist_ok=True)
    argv = ["llama-server", "--port", "1", "--alias", alias]
    (d / "cmdline").write_bytes(b"\0".join(a.encode() for a in argv) + b"\0")
    (d / "comm").write_text("llama-server\n")
    fields = ["S"] + ["0"] * 10 + [str(utime), "0"] + ["0"] * 30
    (d / "stat").write_text(f"{pid} (llama-server) " + " ".join(fields))


def test_jan_status_reports_busy_only_after_a_second_look(client, tmp_path):
    _, web_app = client
    proc = tmp_path / "proc"
    _fake_proc(proc, 101, "Qwen3_5-4B-IQ4_XS", 50)
    web_app._last_ticks.clear()
    assert web_app.jan_status(str(proc)) == [
        {"model": "Qwen3_5-4B-IQ4_XS", "busy": None}
    ]
    assert web_app.jan_status(str(proc))[0]["busy"] is False
    _fake_proc(proc, 101, "Qwen3_5-4B-IQ4_XS", 90)
    assert web_app.jan_status(str(proc))[0]["busy"] is True


def test_forge_is_the_page_default_once_it_exists(client):
    c, web_app = client
    web_app._run("forge", "join", "ejb-f7", "--role", "solo", "--slot", "S2")
    r = c.get("/api/boards").json()
    assert r["default"] == "forge" and "jan" in r["boards"]


def test_emerson_answers_a_session_without_closing_it_for_others(client):
    c, web_app = client
    web_app._run("forge", "post", "ejb-74", "S5 started")
    web_app._run("forge", "join", "ejb-f7", "--role", "solo")
    assert (
        c.post(
            "/api/board/forge/post", json={"text": "nice", "to": "ejb-74", "re": 1}
        ).status_code
        == 200
    )
    assert c.post("/api/board/forge/ack/1", json={}).status_code == 200
    notes = c.get("/api/board/forge").json()["board"]["notes"]
    assert notes[0].get("ack") is None and notes[0]["done_by"] == ["Emerson"]
    assert (notes[1]["to"], notes[1]["re"]) == ("ejb-74", 1)
    assert c.post("/api/board/forge/ack/1", json={"close": True}).status_code == 200
    assert (
        c.get("/api/board/forge").json()["board"]["notes"][0]["ack"]["by"] == "Emerson"
    )


def test_sessions_lists_live_ones_with_slot_and_brief_state(
    client, tmp_path, monkeypatch
):
    c, web_app = client
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    (sessions / "1.json").write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "name": "ejb-f7",
                "status": "busy",
                "startedAt": 1000,
                "updatedAt": time.time() * 1000,
            }
        )
    )
    (sessions / "2.json").write_text(json.dumps({"pid": 999999999, "name": "gone"}))
    briefs = tmp_path / "briefs"
    briefs.mkdir()
    (briefs / "2026-09-25-S2-hub-shell.md").write_text(
        "# S2: the Forge hub shell\n\n## Owns\n- hub\n\n## State\n- A15 done, checked\n- A16 not done\n"
    )
    monkeypatch.setattr(web_app, "SESSIONS_DIR", str(sessions))
    monkeypatch.setattr(web_app, "BRIEFS_DIR", str(briefs))
    web_app._run("forge", "join", "ejb-f7", "--role", "solo", "--slot", "S2")
    got = c.get("/api/board/forge").json()["sessions"]
    assert [s["name"] for s in got] == ["ejb-f7"]
    assert got[0]["slot"] == "S2" and got[0]["status"] == "busy"
    assert got[0]["brief"]["title"] == "S2: the Forge hub shell"
    assert got[0]["brief"]["state"] == ["- A15 done, checked", "- A16 not done"]


def test_quiet_sessions_are_not_active_and_agents_and_tab_names_show(
    client, tmp_path, monkeypatch
):
    c, web_app = client
    root = tmp_path / "claude"
    sessions, project = root / "sessions", root / "projects" / "-home-ejb"
    sessions.mkdir(parents=True)
    agents = project / "sid-q" / "subagents"
    agents.mkdir(parents=True)
    old = time.time() - 600
    for sid, name in (("sid-q", "ejb-q"), ("sid-w", "ejb-w")):
        (sessions / f"{name}.json").write_text(
            json.dumps(
                {"pid": os.getpid(), "sessionId": sid, "name": name, "status": "busy"}
            )
        )
        (project / f"{sid}.jsonl").write_text("{}\n")
    os.utime(project / "sid-q.jsonl", (old, old))
    (agents / "agent-1.meta.json").write_text(
        json.dumps({"agentType": "Explore", "description": "Find the hooks"})
    )
    (agents / "agent-1.jsonl").write_text("{}\n")
    (agents / "agent-2.meta.json").write_text(json.dumps({"description": "Old one"}))
    for f in ("agent-2.meta.json",):
        os.utime(agents / f, (old, old))
    monkeypatch.setattr(web_app, "SESSIONS_DIR", str(sessions))
    monkeypatch.setattr(web_app, "claude_names", lambda: {"sid-w": {"name": "Nagi"}})
    web_app._run("forge", "join", "ejb-w")
    web_app._run("forge", "post", "ejb-w", "hello")
    got = c.get("/api/board/forge").json()
    by = {s["name"]: s for s in got["sessions"]}
    # ejb-q's own transcript is 10 minutes old, but its agent is writing
    assert by["ejb-q"]["active"] and by["ejb-q"]["status"] == "busy"
    assert [(a["description"], a["running"]) for a in by["ejb-q"]["agents"]] == [
        ("Find the hooks", True),
        ("Old one", False),
    ]
    assert by["ejb-w"]["active"] and by["ejb-w"]["label"] == "Nagi"
    assert got["board"]["members"]["ejb-w"]["persona"] == "Nagi"
    os.utime(agents / "agent-1.jsonl", (old, old))
    os.utime(agents / "agent-1.meta.json", (old, old))
    quiet = {s["name"]: s for s in c.get("/api/board/forge").json()["sessions"]}
    assert not quiet["ejb-q"]["active"] and quiet["ejb-q"]["status"] == "idle"
    assert not any(a["running"] for a in quiet["ejb-q"]["agents"])


def _fake_stat(root, pid, ppid, comm):
    d = root / str(pid)
    d.mkdir(parents=True)
    (d / "stat").write_text(f"{pid} ({comm}) S {ppid} 1 1 0\n")


def test_a_session_maps_to_its_terminal_tab(client, tmp_path):
    _, web_app = client
    proc = tmp_path / "proc"
    _fake_stat(proc, 400, 1, "gnome-terminal-")
    _fake_stat(proc, 410, 400, "bash")
    _fake_stat(proc, 420, 400, "bash")
    _fake_stat(proc, 421, 420, "claude")
    _fake_stat(proc, 430, 400, "bash")
    assert web_app.terminal_of(421, str(proc)) == {
        "server": 400,
        "tab": 1,
        "kind": "gnome-terminal-",
    }
    _fake_stat(proc, 500, 1, "Xwayland")
    _fake_stat(proc, 501, 500, "claude")
    assert web_app.terminal_of(501, str(proc)) is None


def test_go_to_a_session_switches_the_tab(client, tmp_path, monkeypatch):
    client, web_app = client
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    (sessions / "77.json").write_text(json.dumps({"pid": 77, "name": "ejb-77"}))
    monkeypatch.setattr(web_app, "SESSIONS_DIR", str(sessions))
    monkeypatch.setattr(
        web_app, "terminal_of", lambda pid, proc="/proc": {"server": 1, "tab": 2}
    )
    calls = []
    monkeypatch.setattr(web_app, "_gdbus", lambda *a: calls.append(a) or True)
    r = client.post("/api/session/ejb-77/go")
    assert r.status_code == 200 and r.json()["tab"] == 2
    assert any("active-tab" in " ".join(c) and "<2>" in " ".join(c) for c in calls)
    assert client.post("/api/session/nobody/go").status_code == 404


def test_emerson_can_post_an_fyi_note(client):
    c, _ = client
    assert c.post(
        "/api/board/jan/post", json={"text": "heads up", "fyi": True}
    ).json() == {"ok": True}
    c.post("/api/board/jan/post", json={"text": "question"})
    notes = c.get("/api/board/jan").json()["board"]["notes"]
    assert notes[0].get("fyi") is True and not notes[1].get("fyi")


def test_notify_sends_a_desktop_notification(client, monkeypatch):
    c, web_app = client
    calls = []
    monkeypatch.setattr(
        web_app.subprocess, "Popen", lambda argv, **kw: calls.append(argv)
    )
    r = c.post("/api/notify", json={"title": "ejb-55", "body": "done with B27"})
    assert r.json() == {"ok": True}
    assert calls[0][0] == "notify-send" and calls[0][-2:] == ["ejb-55", "done with B27"]
    assert c.post("/api/notify", json={"title": " ", "body": ""}).status_code == 400


def test_go_opens_a_claude_app_session_when_it_has_no_terminal(
    client, tmp_path, monkeypatch
):
    client, web_app = client
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    (sessions / "88.json").write_text(
        json.dumps({"pid": 88, "name": "ejb-88", "sessionId": "s-88"})
    )
    monkeypatch.setattr(web_app, "SESSIONS_DIR", str(sessions))
    monkeypatch.setattr(web_app, "terminal_of", lambda pid, proc="/proc": None)
    asked, shown = [], []
    monkeypatch.setattr(
        web_app,
        "_claude_call",
        lambda path, method="GET": asked.append((method, path)) or {"name": "Umi"},
    )
    monkeypatch.setattr(web_app, "_forge_show", lambda name: shown.append(name) or True)
    got = client.post("/api/session/ejb-88/go").json()
    assert got == {"ok": True, "app": "claude", "conversation": "Umi", "reason": ""}
    assert asked == [("POST", "/api/sessions/s-88/focus?pid=88")]
    assert shown == ["claude"]
    monkeypatch.setattr(web_app, "_claude_call", lambda path, method="GET": None)
    got = client.post("/api/session/ejb-88/go").json()
    assert got["ok"] is False and got["nowhere"] is True


def test_the_claude_app_is_found_by_its_manifest_role():
    import web_app

    found = web_app._claude_app()
    assert found is not None and found["name"] == "claude" and found["port"]


def test_sessions_carry_their_claude_app_name(client, tmp_path, monkeypatch):
    client, web_app = client
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    import os

    me = os.getpid()
    (sessions / "1.json").write_text(
        json.dumps({"pid": me, "name": "ejb-me", "sessionId": "s-me"})
    )
    monkeypatch.setattr(web_app, "SESSIONS_DIR", str(sessions))
    monkeypatch.setattr(
        web_app,
        "_claude_call",
        lambda path, method="GET": {
            "sessions": {"s-me": {"name": "Yui", "title": "tabs"}}
        },
    )
    monkeypatch.setattr(web_app, "_names_cache", (0.0, {}))
    live = web_app.live_sessions({})
    assert [(s["name"], s["label"], s["topic"]) for s in live] == [
        ("ejb-me", "Yui", "tabs")
    ]


def test_a_terminal_session_shows_its_crew_persona(client, tmp_path, monkeypatch):
    # B27: no Claude app tab, so the Board shows the name the crew board gave it
    client, web_app = client
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    import os

    (sessions / "1.json").write_text(
        json.dumps({"pid": os.getpid(), "name": "ejb-t", "sessionId": "s-t"})
    )
    monkeypatch.setattr(web_app, "SESSIONS_DIR", str(sessions))
    monkeypatch.setattr(web_app, "_claude_call", lambda path, method="GET": None)
    monkeypatch.setattr(web_app, "_names_cache", (0.0, {}))
    live = web_app.live_sessions({"members": {"ejb-t": {"persona": "Hina"}}})
    assert [(s["name"], s["label"]) for s in live] == [("ejb-t", "Hina")]


def test_a_session_named_on_another_board_shows_that_name(
    client, tmp_path, monkeypatch
):
    # one rule with Crew Room and Relay (shared/forge_session_names.py): a
    # Relay session named Mika on the forge board is Mika on every board
    client, web_app = client
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    (sessions / "1.json").write_text(
        json.dumps({"pid": os.getpid(), "name": "relay-59-work", "sessionId": "sid-59"})
    )
    board = tmp_path / "crews" / "forge"
    board.mkdir(parents=True)
    (board / "board.json").write_text(
        json.dumps(
            {"members": {"relay-59-work": {"session": "sid-59", "persona": "Mika"}}}
        )
    )
    monkeypatch.setattr(web_app, "SESSIONS_DIR", str(sessions))
    monkeypatch.setattr(web_app, "_claude_call", lambda path, method="GET": None)
    monkeypatch.setattr(web_app, "_names_cache", (0.0, {}))
    live = web_app.live_sessions({"members": {}})
    assert [(s["name"], s["label"]) for s in live] == [("relay-59-work", "Mika")]
    # a broken board elsewhere is skipped, not fatal
    for i, bad in enumerate(
        (
            {"members": ["x"]},
            {"members": {"a": {"session": "s", "persona": "P", "last_seen": "soon"}}},
            {"members": {"b": {"session": ["s"], "persona": "Q"}}},
        )
    ):
        (tmp_path / "crews" / f"bad{i}").mkdir()
        (tmp_path / "crews" / f"bad{i}" / "board.json").write_text(json.dumps(bad))
    live = web_app.live_sessions({"members": {}})
    assert [(s["name"], s["label"]) for s in live] == [("relay-59-work", "Mika")]


def test_notes_and_answers_starting_with_a_dash_are_kept_as_typed(client):
    # crew.py reads its arguments with argparse: a note "--help" or "-x" used
    # to be taken for an option and the Board answered 500
    c, _ = client
    for text in ("--help", "-x", "--fyi"):
        r = c.post("/api/board/jan/post", json={"text": text, "to": "--close"})
        assert r.status_code == 200
    notes = c.get("/api/board/jan").json()["board"]["notes"]
    assert [(n["text"], n["to"], bool(n.get("fyi"))) for n in notes] == [
        ("--help", "--close", False),
        ("-x", "--close", False),
        ("--fyi", "--close", False),
    ]
    assert c.post("/api/board/jan/ack/1", json={"note": "-h"}).status_code == 200
    ack = c.get("/api/board/jan").json()["board"]["notes"][0]["ack"]
    assert (ack["by"], ack["note"]) == ("Emerson", "-h")


def test_oversized_notes_names_and_answers_are_refused(client):
    c, _ = client
    assert (
        c.post("/api/board/jan/post", json={"text": "hi", "to": "y" * 100}).status_code
        == 422
    )
    assert c.post("/api/board/jan/post", json={"text": "x" * 20001}).status_code == 422
    assert c.post("/api/board/jan/post", json={"text": "x" * 20000}).status_code == 200
    assert c.post("/api/board/jan/ack/1", json={"note": "n" * 4001}).status_code == 422
