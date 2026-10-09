"""Slash commands typed in a tab, and commands Claude queues for itself
through the panel_command tool (panel_commands.py, browser_mcp.py), with the
fake Claude Code (tests/fake_claude.py)."""

import json
import sys
import time
from pathlib import Path

import pytest

import browser_mcp
import panel_commands
import runner

FAKE = Path(__file__).with_name("fake_claude.py")


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_CLAUDE_BIN", f"{sys.executable} {FAKE}")
    monkeypatch.setenv("FAKE_CLAUDE_ARGS", str(tmp_path / "args.jsonl"))
    return tmp_path


def wait_for(conv, kind, n=1, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if sum(e.get("type") == kind for e in conv.events) >= n:
            return True
        time.sleep(0.03)
    return False


def inputs(home):
    return [json.loads(x) for x in (home / "inputs.jsonl").read_text().splitlines()]


def test_a_slash_command_goes_untagged_and_a_message_keeps_its_tag(home):
    conv = runner.Registry(home / "data").create()
    conv.send("hello", [])
    assert wait_for(conv, "result")
    conv.send("  /compact keep the test list", [])
    assert wait_for(conv, "result", 2)
    sent = inputs(home)
    assert sent[0].startswith("[persona:") and sent[0].endswith("hello")
    assert sent[1] == "/compact keep the test list"
    personas = [e for e in conv.events if e["type"] == "forge_persona"]
    assert len(personas) == 1  # none for the command
    assert any(e.get("subtype") == "compact_boundary" for e in conv.events)
    conv.stop(quiet=True)


def test_command_lines_follow_the_registry():
    assert panel_commands.command_line("compact") == "/compact"
    assert (
        panel_commands.command_line("/compact", "  keep   tests ")
        == "/compact keep tests"
    )
    assert panel_commands.command_line("rename", "new name") == "/rename new name"
    for name, args in [
        ("rm", ""),
        ("", ""),
        ("context", "x"),
        ("rename", ""),
        ("compact; ls", ""),
        (["compact"], ""),
        ("compact", 5),
    ]:
        with pytest.raises(ValueError):
            panel_commands.command_line(name, args)  # type: ignore[arg-type]
    # every registry entry is complete
    for name, spec in panel_commands.COMMANDS.items():
        assert spec["args"] in ("none", "optional", "required") and spec["help"]


def test_the_tool_is_offered_only_with_a_queue_and_queues(tmp_path, monkeypatch):
    monkeypatch.setattr(browser_mcp, "QUEUE", "")
    names = [t["name"] for t in browser_mcp.tool_list()]
    assert "panel_command" not in names
    queue = tmp_path / "q.jsonl"
    monkeypatch.setattr(browser_mcp, "QUEUE", str(queue))
    assert "panel_command" in [t["name"] for t in browser_mcp.tool_list()]
    call = lambda args: browser_mcp.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "panel_command", "arguments": args},
        }
    )
    ok = call({"command": "compact", "args": "keep the plan"})
    assert ok and not ok["result"]["isError"]
    bad = call({"command": "shell", "args": "rm -rf"})
    assert bad and bad["result"]["isError"]
    assert panel_commands.take_next(queue) == "/compact keep the plan"
    assert panel_commands.take_next(queue) is None


def test_each_conversation_gets_its_own_queue_in_its_mcp_config(tmp_path):
    path = runner.mcp_config(tmp_path, tmp_path / "none.json", conv_id="abc")
    env = json.loads(path.read_text())["mcpServers"]["forge-browser"]["env"]
    assert env["FORGE_PANEL_QUEUE"] == str(runner.command_queue(tmp_path, "abc"))
    shared = runner.mcp_config(tmp_path, tmp_path / "none.json")
    assert (
        "FORGE_PANEL_QUEUE"
        not in json.loads(shared.read_text())["mcpServers"]["forge-browser"]["env"]
    )


def test_a_queued_command_runs_as_the_next_message_after_the_turn(home):
    conv = runner.Registry(home / "data").create()
    queue = runner.command_queue(conv.data_dir, conv.meta["id"])
    conv.send("wait for it", [])
    assert wait_for(conv, "system")
    # Claude calls the tool mid-turn: queued, not sent yet
    panel_commands.queue(queue, "compact")
    panel_commands.queue(queue, "context")
    assert wait_for(conv, "result", 3, timeout=15)
    kinds = [
        (e["type"], e.get("command") or e.get("text"))
        for e in conv.events
        if e["type"] in ("forge_asked", "forge_user")
    ]
    assert kinds == [
        ("forge_user", "wait for it"),
        ("forge_asked", "/compact"),
        ("forge_user", "/compact"),
        ("forge_asked", "/context"),
        ("forge_user", "/context"),
    ]
    sent = inputs(home)
    assert sent[1:] == ["/compact", "/context"]
    assert not queue.exists()
    deadline = time.time() + 3
    while conv.busy and time.time() < deadline:
        time.sleep(0.05)
    assert not conv.busy
    conv.stop(quiet=True)


def test_the_queue_survives_appends_and_takers_at_once(tmp_path):
    import threading

    queue = tmp_path / "q.jsonl"
    taken: list[str] = []
    done = threading.Event()

    def writer():
        for i in range(300):
            panel_commands.queue(queue, "rename", f"n{i}")
        done.set()

    def taker():
        while not done.is_set() or queue.exists():
            line = panel_commands.take_next(queue)
            if line:
                taken.append(line)

    threads = [threading.Thread(target=writer)] + [
        threading.Thread(target=taker) for _ in range(2)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert sorted(taken) == sorted(f"/rename n{i}" for i in range(300))


def test_a_poisoned_line_never_jams_the_queue(tmp_path):
    queue = tmp_path / "q.jsonl"
    queue.write_text(
        "[" * 200000 + "\n" + "not json\n" + json.dumps({"command": 5}) + "\n"
    )
    panel_commands.queue(queue, "context")
    assert panel_commands.take_next(queue) == "/context"
    assert panel_commands.take_next(queue) is None
