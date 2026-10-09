import json
from datetime import datetime

from fastapi.testclient import TestClient

import web_app
import where
from conftest import write_jsonl, write_proc
from sources import sessions


def test_live_terminal_session(tree, tmp_path, monkeypatch):
    monkeypatch.setenv("CREWROOM_DATA_DIR", str(tmp_path / "data"))
    proc = tree["proc"]
    write_proc(proc, 111, "claude", ["claude"], start=5000, ppid=110, fd0="/dev/pts/7")
    write_proc(proc, 110, "bash", ["bash"], ppid=100)
    write_proc(
        proc, 100, "gnome-terminal-", ["/usr/lib/gnome-terminal-server"], ppid=50
    )
    write_proc(proc, 50, "systemd", ["/usr/lib/systemd/systemd", "--user"], ppid=1)
    info = where.describe(tree["ctx"], "sess-a")
    assert info is not None and info["alive"] is True
    assert info["tty"] == "/dev/pts/7"
    assert info["terminal"] == "GNOME Terminal"
    assert info["name"] == "forge-builder" and info["folder"] == "/home/ejb/Forge"
    assert info["started_at"] == 1.0
    assert info["resume"] is None and info["background"] is False


def test_program_chain_of_only_shells_under_systemd_is_unknown(tree):
    proc = tree["proc"]
    write_proc(proc, 600, "claude", ["claude"], ppid=601)
    write_proc(proc, 601, "bash", ["-bash"], ppid=602)
    write_proc(proc, 602, "systemd", ["/usr/lib/systemd/systemd"], ppid=1)
    assert where.terminal_program(str(proc), 600) is None
    assert where.terminal_device(str(proc), 600) is None


def test_ended_session_gets_a_resume_command(tree, tmp_path, monkeypatch):
    monkeypatch.setenv("CREWROOM_DATA_DIR", str(tmp_path / "data"))
    project = tree["claude"] / "projects" / "-home-ejb"
    write_jsonl(
        project / "sess-b.jsonl",
        [
            {"type": "permission-mode"},
            {
                "type": "user",
                "cwd": "/home/ejb/My Folder",
                "timestamp": "2026-09-16T01:00:00Z",
                "message": {"content": "hi"},
            },
            {"type": "ai-title", "aiTitle": "Say hi"},
        ],
    )
    info = where.describe(tree["ctx"], "sess-b")  # its pid was reused
    assert info is not None and info["alive"] is False and info["name"] == "Say hi"
    assert info["resume"] == "cd '/home/ejb/My Folder' && claude --resume sess-b"
    assert (
        info["started_at"]
        == datetime.fromisoformat("2026-09-16T01:00:00+00:00").timestamp()
    )
    assert where.describe(tree["ctx"], "nobody") is None


def test_background_task_is_marked_and_busy(tree, tmp_path, monkeypatch):
    monkeypatch.setenv("CREWROOM_DATA_DIR", str(tmp_path / "data"))
    home = tmp_path / "data" / "tasks" / "sess-x"
    home.mkdir(parents=True)
    (home / "task.json").write_text(
        json.dumps({"id": "sess-x", "pid": 500, "prompt": "say ok", "model": "haiku"})
    )
    write_proc(tree["proc"], 500, "claude", ["claude", "-p"], start=700, ppid=1)
    # A headless run's session file has no status (seen on Claude Code 2.1.273).
    (tree["claude"] / "sessions" / "500.json").write_text(
        json.dumps(
            {
                "pid": 500,
                "sessionId": "sess-x",
                "cwd": "/tmp",
                "procStart": "700",
                "kind": "interactive",
                "entrypoint": "sdk-cli",
                "name": "tmp-1",
                "startedAt": tree["ctx"].now * 1000,
            }
        )
    )
    info = where.describe(tree["ctx"], "sess-x")
    assert info is not None
    assert info["terminal"] == "Crew Room background task" and info["tty"] is None
    assert info["background"] is True and info["task"]["prompt"] == "say ok"
    live = {s["id"]: s for s in sessions.collect(tree["ctx"])}["sess-x"]
    assert live["background"] is True and live["busy"] is True
    assert {s["id"]: s for s in sessions.collect(tree["ctx"])}["sess-a"][
        "background"
    ] is False


def test_conversation_and_where_endpoints(tree, tmp_path, monkeypatch):
    monkeypatch.setenv("CREWROOM_CLAUDE_DIR", str(tree["claude"]))
    monkeypatch.setenv("CREWROOM_PROC_DIR", str(tree["proc"]))
    monkeypatch.setenv("CREWROOM_DATA_DIR", str(tmp_path / "data"))
    client = TestClient(web_app.app)
    page = client.get("/api/sessions/sess-a/conversation").json()
    assert [i["kind"] for i in page["items"]] == ["prompt", "tool", "tool", "result"]
    assert page["more"] is False
    older = client.get("/api/sessions/sess-a/conversation", params={"before": 0}).json()
    assert older["items"] == []
    assert client.get("/api/sessions/nobody/conversation").status_code == 404
    assert client.get("/api/sessions/sess*/conversation").status_code == 400
    assert client.get("/api/sessions/sess-a/where").json()["name"] == "forge-builder"
    assert client.get("/api/sessions/nobody/where").status_code == 404
