import json

import pytest
from fastapi.testclient import TestClient

import launch
import web_app
from conftest import write_jsonl, write_proc


class FakeStdin:
    def __init__(self):
        self.data = b""
        self.closed = False

    def write(self, data):
        self.data += data

    def close(self):
        self.closed = True


class FakeProc:
    def __init__(self, args, **kw):
        self.args = args
        self.kw = kw
        self.pid = 4242
        self.stdin = FakeStdin() if kw.get("stdin") == launch.subprocess.PIPE else None

    def wait(self):
        return 0


@pytest.fixture
def spawned(tmp_path, monkeypatch):
    """Nothing is ever started: Popen records its calls, every program exists."""
    calls = []

    def popen(args, **kw):
        calls.append(FakeProc(args, **kw))
        return calls[-1]

    monkeypatch.setattr(launch.subprocess, "Popen", popen)
    monkeypatch.setattr(launch.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.delenv("CREWROOM_CLAUDE_BIN", raising=False)
    monkeypatch.setenv("CREWROOM_DATA_DIR", str(tmp_path / "data"))
    return calls


def test_terminal_opens_claude_in_the_folder(spawned, tmp_path):
    result = launch.open_terminal(str(tmp_path))
    assert spawned[0].args == [
        "gnome-terminal",
        f"--working-directory={tmp_path}",
        "--",
        "/usr/bin/claude",
    ]
    assert spawned[0].kw["start_new_session"] is True
    assert result["terminal"] == "gnome-terminal"


def test_terminal_refuses_a_missing_folder_or_terminal(spawned, tmp_path, monkeypatch):
    with pytest.raises(launch.LaunchError, match="does not exist"):
        launch.open_terminal(str(tmp_path / "nope"))
    monkeypatch.setattr(launch.shutil, "which", lambda _name: None)
    with pytest.raises(launch.LaunchError, match="terminal"):
        launch.open_terminal(str(tmp_path))
    assert spawned == []


def test_background_task_runs_headless_in_auto_mode(spawned, tmp_path):
    record = launch.start_task("say ok", str(tmp_path), "haiku", background=False)
    proc = spawned[0]
    args = proc.args
    assert args[:2] == ["/usr/bin/claude", "-p"]
    assert args[args.index("--permission-mode") + 1] == "auto"
    assert args[args.index("--model") + 1] == "haiku"
    assert args[args.index("--session-id") + 1] == record["id"]
    assert args[args.index("--output-format") + 1] == "stream-json"
    assert "say ok" not in args, "the prompt goes in on stdin"
    assert proc.stdin.data == b"say ok" and proc.stdin.closed
    assert proc.kw["cwd"] == str(tmp_path)
    home = tmp_path / "data" / "tasks" / record["id"]
    assert proc.kw["stdout"].name == str(home / "output.jsonl")
    assert (home / "pid").read_text().strip() == "4242"
    assert json.loads((home / "task.json").read_text())["returncode"] == 0


def test_default_model_adds_no_flag_and_bad_input_is_refused(spawned, tmp_path):
    launch.start_task("go", str(tmp_path), "", background=False)
    assert "--model" not in spawned[0].args
    with pytest.raises(launch.LaunchError):
        launch.start_task("   ", str(tmp_path))
    with pytest.raises(launch.LaunchError):
        launch.start_task("go", str(tmp_path), "gpt")
    assert len(spawned) == 1


def test_task_list_reads_status_and_result(spawned, tmp_path):
    done = launch.start_task("say ok", str(tmp_path), background=False)
    home = tmp_path / "data" / "tasks" / done["id"]
    write_jsonl(
        home / "output.jsonl",
        [{"type": "result", "is_error": False, "result": "ok", "total_cost_usd": 0.01}],
    )
    running = launch.start_task("keep going", str(tmp_path), background=False)
    path = tmp_path / "data" / "tasks" / running["id"] / "task.json"
    record = json.loads(path.read_text())
    record.pop("returncode", None)
    record.update(started_at=done["started_at"] + 10, proc_start="77")
    path.write_text(json.dumps(record))
    write_proc(tmp_path / "proc", 4242, "claude", ["claude"], start=77)

    tasks = launch.list_tasks(proc_dir=str(tmp_path / "proc"))
    assert [t["status"] for t in tasks] == ["running", "done"]
    assert tasks[1]["result"] == "ok" and tasks[1]["cost_usd"] == 0.01
    found = launch.find_task(done["id"])
    assert found is not None and found["prompt"] == "say ok"
    assert launch.find_task("../etc") is None


def test_launch_endpoints_refuse_other_sites(spawned, tree, tmp_path, monkeypatch):
    monkeypatch.setenv("CREWROOM_CLAUDE_DIR", str(tree["claude"]))
    monkeypatch.setenv("CREWROOM_PROC_DIR", str(tree["proc"]))
    client = TestClient(web_app.app)  # no lifespan: art seeding is not needed
    body = {"prompt": "say ok", "folder": str(tmp_path), "model": "haiku"}
    evil = client.post(
        "/api/launch/task", json=body, headers={"Origin": "http://evil.example"}
    )
    assert evil.status_code == 403
    plain = client.post(
        "/api/launch/task",
        content=json.dumps(body),
        headers={"Content-Type": "text/plain"},
    )
    assert plain.status_code >= 400
    assert spawned == []
    ok = client.post(
        "/api/launch/task", json=body, headers={"Origin": "http://testserver"}
    )
    assert ok.status_code == 200 and len(spawned) == 1
    bad = client.post("/api/launch/terminal", json={"folder": str(tmp_path / "nope")})
    assert bad.status_code == 400 and "does not exist" in bad.json()["detail"]
    opts = client.get("/api/launch/options").json()
    assert opts["mode"] == "auto" and opts["terminal"] == "gnome-terminal"
    assert "/home/ejb/Forge" in opts["recent"]
    assert any(a["label"] == "Crew Room" for a in opts["apps"])
    assert client.get("/api/tasks").json()["tasks"][0]["prompt"] == "say ok"


def test_a_task_names_its_attached_files(spawned, tree, tmp_path, monkeypatch):
    import base64

    monkeypatch.setenv("CREWROOM_CLAUDE_DIR", str(tree["claude"]))
    monkeypatch.setenv("CREWROOM_PROC_DIR", str(tree["proc"]))
    client = TestClient(web_app.app)
    data = base64.b64encode(b"PNG").decode()
    got = client.post("/api/attach", json={"name": "shot.png", "data": data}).json()
    assert got["path"].startswith(str(tmp_path / "data" / "attachments") + "/")
    evil = client.post(
        "/api/attach",
        json={"name": "x.png", "data": data},
        headers={"Origin": "http://evil.example"},
    )
    assert evil.status_code == 403
    body = {"prompt": "fix this", "folder": str(tmp_path), "files": [got["path"]]}
    assert client.post("/api/launch/task", json=body).status_code == 200
    sent = spawned[-1].stdin.data.decode()
    assert sent == f"fix this\n\nAttached files:\n- {got['path']}"
    body["files"] = ["/etc/passwd"]
    assert client.post("/api/launch/task", json=body).status_code == 400
