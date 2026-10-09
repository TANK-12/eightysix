"""Claude conversations survive a Forge restart or a reboot (Emerson,
2026-09-27: "make it so that claude sessions survive even when i restart my
laptop").

A turn in progress is marked on disk ("working") when a message is sent and
cleared when the turn ends or the user presses Stop. Forge quitting or the
laptop going down leaves the mark, and the next time the Claude app starts it
resumes each marked conversation with --resume and a short "carry on" message.
Claude Code is tests/fake_claude.py, so nothing is spent."""

import json
import sys
import time
from pathlib import Path

import pytest

import runner

FAKE = Path(__file__).with_name("fake_claude.py")


@pytest.fixture
def data(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_CLAUDE_BIN", f"{sys.executable} {FAKE}")
    monkeypatch.setenv("FAKE_CLAUDE_ARGS", str(tmp_path / "args.jsonl"))
    return tmp_path


def until(check, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if check():
            return True
        time.sleep(0.05)
    return False


def stored(registry, conv_id) -> dict:
    path = registry.data_dir / "conversations" / f"{conv_id}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def started_turn(registry, text="slow"):
    conv = registry.create(cwd=str(registry.data_dir))
    conv.send(text, [])
    assert until(lambda: bool(conv.meta.get("session_id")))
    return conv


def test_a_finished_turn_leaves_no_mark(data):
    reg = runner.Registry(data / "d")
    conv = started_turn(reg, "hello")
    assert until(lambda: not conv.busy)
    assert "working" not in stored(reg, conv.meta["id"])


def test_forge_quitting_mid_turn_leaves_the_mark(data):
    reg = runner.Registry(data / "d")
    conv = started_turn(reg)
    assert stored(reg, conv.meta["id"]).get("working")
    reg.stop_all()  # what the backend does when Forge quits
    assert stored(reg, conv.meta["id"]).get("working")


def test_the_users_stop_clears_the_mark(data):
    reg = runner.Registry(data / "d")
    conv = started_turn(reg)
    conv.stop()
    assert "working" not in stored(reg, conv.meta["id"])


def test_the_next_start_resumes_marked_conversations(data):
    reg = runner.Registry(data / "d")
    conv = started_turn(reg)
    session = conv.meta["session_id"]
    reg.stop_all()

    fresh = runner.Registry(data / "d")  # the Claude app starting again
    resumed = fresh.resume_interrupted(gap=0, wait=True)
    assert resumed == [conv.meta["id"]]
    again = fresh.get(conv.meta["id"])
    assert again is not None
    assert until(lambda: any(e.get("type") == "forge_resumed" for e in again.events))
    log = data / "args.jsonl"
    assert until(
        lambda: len(log.read_text().splitlines()) >= 2
    ), "the CLI started again"
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert "--resume" in calls[-1] and session in calls[-1]
    said = [e for e in again.events if e.get("type") == "forge_user"][-1]["text"]
    assert "carry on" in said.lower()
    # the resumed turn ends like any other and takes the mark with it
    assert until(lambda: not again.busy)
    assert "working" not in stored(fresh, conv.meta["id"])
    fresh.stop_all()


def test_nothing_is_resumed_when_the_setting_is_off(data):
    reg = runner.Registry(data / "d")
    conv = started_turn(reg)
    reg.stop_all()
    fresh = runner.Registry(data / "d")
    fresh.resume_after_restart = lambda: False
    assert fresh.resume_interrupted(gap=0, wait=True) == []
    assert stored(fresh, conv.meta["id"]).get("working"), "still marked for the page"


def test_a_conversation_never_started_is_not_resumed(data):
    reg = runner.Registry(data / "d")
    conv = reg.create(cwd=str(reg.data_dir))
    conv.meta["working"] = time.time()  # marked, but Claude never gave an id
    conv.save_meta()
    assert runner.Registry(data / "d").resume_interrupted(gap=0, wait=True) == []
