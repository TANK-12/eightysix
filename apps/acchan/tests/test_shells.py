"""Headless shells and the background launcher: real bash on a real pty.

Checks the promises Emerson was given (2026-09-27): state carries over
between commands, exit codes come back, a long command can be interrupted,
and nothing Acchan started outlives it, not even after kill -9.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("ACCHAN_DATA", str(tmp_path / "data"))
    import acchan.conversation as conversation

    monkeypatch.setattr(conversation, "DATA", tmp_path / "data")
    yield
    from acchan import background, shells

    shells.close_all()
    background.close_all()


from acchan import background, registry, shells  # noqa: E402

registry.load_all()


def gone(pid: int, within: float = 5.0) -> bool:
    deadline = time.monotonic() + within
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        # A zombie still answers kill(0); it is dead for our purposes.
        try:
            if Path(f"/proc/{pid}/stat").read_text().split()[2] == "Z":
                return True
        except OSError:  # it vanished while being read
            return True
        time.sleep(0.05)
    return False


def test_state_carries_over_and_exit_codes_come_back(tmp_path):
    shell, new = shells.get("t", tmp_path)
    assert new
    assert shell.run("cd /tmp && export X=5").code == 0
    result = shell.run("pwd; echo $X; false")
    assert result.code == 1
    assert result.output.splitlines() == ["/tmp", "5"]
    again, new = shells.get("t")
    assert again is shell and not new


def test_timeout_then_ctrl_c_then_the_shell_still_works(tmp_path):
    shell, _ = shells.get("t", tmp_path)
    slow = shell.run("echo started; sleep 30", timeout=1)
    assert slow.code is None
    assert "started" in slow.output
    assert "still running" in str(slow)
    shell.send(shells.CONTROL["ctrl+c"], wait=0.3)
    after = shell.run("echo ok", timeout=5)
    assert (after.code, after.output) == (0, "ok")


def test_output_is_plain_text_and_the_transcript_has_it(tmp_path):
    shell, _ = shells.get("t", tmp_path)
    result = shell.run(r"printf '\033[31mred\033[0m\n'")
    assert result.output == "red"
    log = shell.log.read_text()
    assert "$ printf" in log and "red" in log and "\x1b" not in log
    assert "\x1f" not in log  # the exit-code marker never reaches the window


def test_read_returns_only_new_output(tmp_path):
    shell, _ = shells.get("t", tmp_path)
    shell.run("(sleep 0.3; echo later) &")
    time.sleep(0.8)
    assert "later" in shell.read()
    assert shell.read() == ""


def test_close_all_stops_the_shell_and_what_runs_in_it(tmp_path):
    shell, _ = shells.get("t", tmp_path)
    pid_file = tmp_path / "pid"
    shell.run(f"sleep 60 & echo $! > {pid_file}")
    grandchild = int(pid_file.read_text())
    bash = shell.proc.pid
    shells.close_all()
    assert gone(bash) and gone(grandchild)
    assert shells.SHELLS == {}


def test_background_close_all_counts_and_stops_children():
    procs = [background.start(["sleep", "60"]) for _ in range(2)]
    assert len(background.running()) == 2
    assert background.close_all() == 2
    assert all(gone(p.pid) for p in procs)
    assert background.running() == []


def test_children_die_when_acchan_is_killed_hard(tmp_path):
    # A stand-in Acchan starts a child from a short-lived worker thread (as
    # FastAPI does), then gets kill -9, so atexit never runs.
    script = (
        "import sys, threading, time\n"
        f"sys.path.insert(0, {str(ROOT)!r})\n"
        "from acchan import background\n"
        "box = []\n"
        "t = threading.Thread(target=lambda: box.append(background.start(['sleep', '60'])))\n"
        "t.start(); t.join()\n"
        "print(box[0].pid, flush=True)\n"
        "time.sleep(60)\n"
    )
    parent = subprocess.Popen(
        [sys.executable, "-c", script], stdout=subprocess.PIPE, text=True
    )
    assert parent.stdout is not None
    child = int(parent.stdout.readline())
    assert not gone(child, within=0.3)  # outlived the thread that asked for it
    parent.kill()
    parent.wait()
    assert gone(child)


def test_shell_tools_end_to_end(tmp_path):
    run = registry.TOOLS["shell_run"].func
    assert run(command="echo hi", shell="tool", folder=str(tmp_path)).startswith(
        "exit code 0\nhi"
    )
    assert "tool: running" in registry.TOOLS["shell_list"].func()
    assert "Closed" in registry.TOOLS["shell_close"].func(shell="all")
    with pytest.raises(registry.ToolError):
        registry.TOOLS["shell_read"].func(shell="nope")


def test_shell_jobs_die_when_acchan_is_killed_hard(tmp_path):
    pid_file = tmp_path / "pid"
    script = (
        "import sys, time\n"
        f"sys.path.insert(0, {str(ROOT)!r})\n"
        "from pathlib import Path\n"
        "from acchan import conversation, shells\n"
        f"conversation.DATA = Path({str(tmp_path)!r})\n"
        "shell, _ = shells.get('t', Path('/tmp'))\n"
        f"shell.run('sleep 60 & echo $! > {pid_file}')\n"
        "print(shell.proc.pid, flush=True)\n"
        "time.sleep(60)\n"
    )
    parent = subprocess.Popen(
        [sys.executable, "-c", script], stdout=subprocess.PIPE, text=True
    )
    assert parent.stdout is not None
    bash = int(parent.stdout.readline())
    job = int(pid_file.read_text())
    parent.kill()
    parent.wait()
    assert gone(bash) and gone(job)


def test_page_tools_pick_the_headless_browser_by_default(monkeypatch):
    from acchan import headless_browser, settings
    from acchan.tools import pages

    monkeypatch.setattr(headless_browser, "port", lambda wait=30.0: 4321)
    monkeypatch.setattr(pages.forge_accounts, "port_for", lambda name: 9222)
    assert pages._port("") == 4321
    assert pages._port("headless") == 4321
    assert pages._port("main") == 9222
    settings.save({"browser_view": "visible"})
    assert pages._port("") == 9222
    assert pages._port("acchan") == 4321


def test_headless_firefox_really_runs_reads_and_closes_with_acchan(tmp_path):
    from acchan import headless_browser
    from acchan.tools import pages

    page = tmp_path / "hello.html"
    page.write_text("<title>Hello Acchan</title><p>Only in the headless one</p>")
    assert "Opened" in registry.TOOLS["page_open"].func(url=f"file://{page}")
    assert "Hello Acchan" in registry.TOOLS["page_tabs"].func()
    assert "Only in the headless one" in registry.TOOLS["page_read"].func(tab="Hello")
    shot = registry.TOOLS["page_screenshot"].func(tab="Hello")
    png = Path(shot.rsplit(" to ", 1)[1])
    assert png.read_bytes()[:4] == b"\x89PNG"
    firefox = headless_browser._proc
    assert firefox is not None and pages.forge_bidi.port_open(headless_browser._port)
    background.close_all()  # what Acchan's exit runs
    assert gone(firefox.pid)
    assert background.session(firefox.pid) == []


def test_typing_in_the_shell_window_reaches_the_shell(tmp_path):
    from fastapi.testclient import TestClient

    import web_app

    shell, _ = shells.get("typed", tmp_path)
    client = TestClient(web_app.app)
    assert client.post(
        "/api/shells/typed/input", json={"text": "echo from-window"}
    ).json() == {"ok": True}
    deadline = time.monotonic() + 5
    while "from-window" not in shell.log.read_text() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert shell.log.read_text().count("from-window") >= 2  # typed line + output
    client.post("/api/shells/typed/input", json={"text": "\x03"})
    assert client.post("/api/shells/nope/input", json={"text": "x"}).status_code == 404


def test_shell_window_script_follows_and_exits_with_the_shell(tmp_path):
    shell, _ = shells.get("win", tmp_path)
    shell.run("echo shown-in-window")
    view = subprocess.Popen(
        [
            sys.executable,
            str(ROOT / "acchan/shell_window.py"),
            "win",
            str(shell.log),
            str(shell.proc.pid),
            "1",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    time.sleep(0.8)
    shells.close("win")
    view.wait(timeout=10)  # stdin stays open: only the shell ending closes it
    assert view.stdout is not None
    out = view.stdout.read()
    assert "shown-in-window" in out and "the shell has ended" in out


def test_bare_open_terminal_is_a_real_window_even_when_headless(monkeypatch):
    from acchan.tools import terminal

    spawned = []
    monkeypatch.setattr(terminal, "spawn", lambda cmd: spawned.append(cmd))
    registry.TOOLS["open_terminal"].func()
    assert spawned and ("gnome-terminal" in spawned[0][0] or "kitty" in spawned[0][0])
    out = registry.TOOLS["open_terminal"].func(command="echo hi", folder="/tmp")
    assert "exit code 0" in out and len(spawned) == 1
