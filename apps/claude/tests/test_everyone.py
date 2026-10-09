import json
import os
import time

import everyone
from test_claude_panel import client, home  # noqa: F401  # pyright: ignore

H = {"X-Forge": "1"}


def write_session(folder, pid, sid, status="busy", name="ejb-zz"):
    folder.mkdir(parents=True, exist_ok=True)
    now = time.time() * 1000
    (folder / f"{pid}.json").write_text(
        json.dumps(
            {
                "pid": pid,
                "sessionId": sid,
                "cwd": "/home/x",
                "name": name,
                "status": status,
                "startedAt": now,
                "updatedAt": now,
            }
        )
    )


def test_states_and_helpers(tmp_path):
    sessions, projects = tmp_path / "sessions", tmp_path / "projects"
    write_session(sessions, os.getpid(), "live-1", "busy", "ejb-aa")
    write_session(sessions, 999999999, "dead-1", "busy", "ejb-bb")
    helpers = projects / "-home-x" / "live-1" / "subagents"
    helpers.mkdir(parents=True)
    (helpers / "agent-a1.meta.json").write_text(
        json.dumps({"agentType": "Explore", "description": "find things"})
    )
    (helpers / "agent-a1.jsonl").write_text("{}\n")
    rows = everyone.sessions(sessions, projects)
    assert [(r["session_id"], r["state"]) for r in rows] == [
        ("live-1", "working"),
        ("dead-1", "cold"),
    ]
    assert rows[0]["helpers"][0]["description"] == "find things"
    assert rows[0]["helpers"][0]["state"] == "working"
    assert rows[1]["helpers"] == []
    # ultracode's workflow helpers sit one folder deeper
    flow = helpers / "workflows" / "wf_1"
    flow.mkdir(parents=True)
    (flow / "agent-b2.meta.json").write_text(
        json.dumps({"description": "legs:landing"})
    )
    (flow / "agent-b2.jsonl").write_text("{}\n")
    rows = everyone.sessions(sessions, projects)
    assert {h["description"] for h in rows[0]["helpers"]} == {
        "find things",
        "legs:landing",
    }


def test_idle_and_old_cold_sessions(tmp_path):
    sessions = tmp_path / "sessions"
    write_session(sessions, os.getpid(), "live-2", "idle")
    write_session(sessions, 999999998, "old", "idle")
    later = time.time() + 5 * 86400
    rows = everyone.sessions(sessions, tmp_path / "p", now=later)
    assert [(r["session_id"], r["state"]) for r in rows] == [("live-2", "idle")]


def test_open_resumes_only_cold_sessions(client):
    got = client.post(
        "/api/everyone/sess-cold/open",
        json={"state": "cold", "cwd": "/tmp", "name": "ejb-cc"},
        headers=H,
    )
    assert got.status_code == 200
    meta = client.get("/api/conversations", headers=H).json()["conversations"]
    resumed = next(m for m in meta if m["id"] == got.json()["id"])
    assert resumed["session_id"] == "sess-cold"
    assert resumed["title"] == "Resumed ejb-cc"
    again = client.post(
        "/api/everyone/sess-cold/open", json={"state": "cold"}, headers=H
    )
    assert again.json()["id"] == got.json()["id"]
    busy = client.post(
        "/api/everyone/sess-live/open", json={"state": "working"}, headers=H
    )
    assert busy.status_code == 409


def test_relay_session_carries_its_task_title(client, tmp_path, monkeypatch):
    import forge_session_names

    tasks = tmp_path / "tasks" / "inbox"
    tasks.mkdir(parents=True)
    (tasks / "0109-mission.md").write_text(
        "---\nid: 109\ntitle: Mission Control conversation view\n---\n# x\n"
    )
    monkeypatch.setattr(forge_session_names, "RELAY_TASKS", str(tmp_path / "tasks"))
    assert forge_session_names.relay_task("relay-109-work") == {
        "task": "109",
        "title": "Mission Control conversation view",
    }
    assert forge_session_names.relay_task("relay-7-work") == {"task": "7", "title": ""}
    assert forge_session_names.relay_task("ejb-a9") is None

    sessions = tmp_path / "sessions"
    write_session(sessions, 1, "sid-r", name="relay-109-work")
    real = everyone.sessions
    monkeypatch.setattr(
        everyone, "sessions", lambda *_: real(sessions, tmp_path / "projects")
    )
    rows = client.get("/api/everyone", headers=H).json()["sessions"]
    assert rows[0]["relay"] == {
        "task": "109",
        "title": "Mission Control conversation view",
    }
