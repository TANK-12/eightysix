"""Relay task 105: the WhatsApp chat sat dead for 20 minutes because a
scratch test wrote its tmp folder into the real settings and the chat could
not launch there. These keep the data folder off limits to tests, fall back
to the home folder, and make a chat outage loud instead of silent."""

import os
import time
from pathlib import Path

import pytest

import boss as boss_mod
import bossline
import channels
import chat
import items
import picker
import prompts
import runs
import store
from test_boss import FakeChat, settle, task_, world  # noqa: F401  (a fixture)


def outbox() -> list[str]:
    return [(store.read_json(f) or {}).get("text", "") for f in chat.pending()]


def waiting() -> list[str]:
    return [w["q"] for w in bossline._load()["waiting"]]


# ---- the real data folder -----------------------------------------------------------


def test_tests_never_reach_the_real_data_folder(monkeypatch):
    monkeypatch.delenv("RELAY_DATA_DIR")
    with pytest.raises(RuntimeError, match="off limits"):
        store.data_dir()
    with pytest.raises(RuntimeError):
        store.save_settings({"default_folder": "/tmp/nowhere"})


def test_given_data_folder_is_used(tmp_path, monkeypatch):
    monkeypatch.setenv("RELAY_DATA_DIR", str(tmp_path / "x"))
    assert store.data_dir() == tmp_path / "x"


# ---- missing folders ----------------------------------------------------------------


def test_missing_default_folder_falls_back_to_home_and_logs_once(world, monkeypatch):
    logged = []
    monkeypatch.setattr(
        boss_mod.Boss, "log", lambda self, kind, text: logged.append((kind, text))
    )
    store.save_settings({"default_folder": "/tmp/relay-105-gone"})
    b = world.boss
    b.settings = store.settings()
    assert b.home_folder() == str(Path.home())
    assert b.home_folder() == str(Path.home())
    assert [k for k, t in logged if "relay-105-gone" in t] == ["error"]
    # back, then gone again: logged again
    store.save_settings({"default_folder": str(Path.home())})
    b.settings = store.settings()
    b.home_folder()
    store.save_settings({"default_folder": "/tmp/relay-105-gone"})
    b.settings = store.settings()
    b.home_folder()
    assert len([k for k, t in logged if "relay-105-gone" in t]) == 2


def test_task_folder_missing_launches_in_the_default_and_says_so(
    world, monkeypatch, tmp_path
):
    logged = []
    monkeypatch.setattr(
        boss_mod.Boss, "log", lambda self, kind, text: logged.append((kind, text))
    )
    task = items.new_task("x", "y", folder="/tmp/relay-105-gone-too")
    b = world.boss
    b.settings = store.settings()
    assert b.folder_for(task) == str(tmp_path)  # the fixture's default folder
    assert any("relay-105-gone-too is missing" in t for _, t in logged)


def test_runs_refuse_a_missing_folder_and_leave_nothing(world):
    task = items.new_task("x", "y")
    before = set(store.path("runs").glob("*")) if store.path("runs").exists() else set()
    with pytest.raises(RuntimeError, match="does not exist"):
        runs.start(task, "work", "a", "low", "hi", "/tmp/relay-105-gone")
    after = set(store.path("runs").glob("*")) if store.path("runs").exists() else set()
    assert after == before


def test_chat_launches_in_home_when_the_default_folder_is_gone(world):
    """The exact outage of 2026-10-08 11:34: now the chat just starts."""
    store.save_settings(
        {"whatsapp_enabled": True, "default_folder": "/tmp/relay-105-gone"}
    )
    chat.route("FAKE:sleep are you there")
    world.boss.tick()
    started = [r for r in runs.active() if r["kind"] == "chat"]
    assert started and started[0]["folder"] == str(Path.home())
    for run in runs.active():
        runs.stop(run)


# ---- a chat that cannot launch ------------------------------------------------------


def test_failed_chat_launch_tells_him_once_and_the_boss_line_answers(
    world, monkeypatch
):
    store.save_settings({"whatsapp_enabled": True})

    def broken(*a, **k):
        raise RuntimeError("no such folder")

    real_start = runs.start
    monkeypatch.setattr(runs, "start", broken)
    b = world.boss
    chat.route("hello?")
    b.settings, b.state = store.settings(), store.state()
    b.chat_now(1000.0)
    texts = outbox()
    assert len(texts) == 1 and "can't answer right now" in texts[0]
    assert "no such folder" in texts[0]
    assert waiting() == ["hello?"]
    task = chat.chat_task(create=False) or {}
    assert task["status"] == chat.IDLE and not chat.has_new(task)
    # a second message in the same outage: answered too, no second notice
    chat.route("still nothing?")
    b.chat_now(1010.0)
    assert len(outbox()) == 1 and waiting() == ["hello?", "still nothing?"]
    # it works again: once a chat session has answered, one "back" line
    monkeypatch.setattr(runs, "start", real_start)
    store.save_state(b.state)
    chat.route("back?")
    settle(world)
    assert outbox().count(boss_mod.BACK_TEXT) == 1
    assert len([t for t in outbox() if "can't answer" in t]) == 1
    state = store.state()
    assert "chat_fail" not in state and "chat_down_told" not in state


def test_a_failure_after_the_session_started_is_no_outage(world, monkeypatch):
    store.save_settings({"whatsapp_enabled": True})
    real_save = runs.save
    calls = []

    def save_once_broken(run):
        calls.append(run)
        if len(calls) == 1:
            raise OSError("disk hiccup")
        return real_save(run)

    monkeypatch.setattr(runs, "save", save_once_broken)
    b = world.boss
    chat.route("FAKE:sleep are you there")
    b.settings, b.state = store.settings(), store.state()
    b.chat_now(1000.0)
    assert [r["kind"] for r in runs.active()] == ["chat"]
    assert waiting() == [] and outbox() == []  # answered once, by the chat
    for run in runs.active():
        runs.stop(run)


def test_a_chat_stuck_in_the_queue_is_noticed_after_a_minute(world, monkeypatch):
    store.save_settings({"whatsapp_enabled": True})
    b = world.boss
    monkeypatch.setattr(boss_mod.Boss, "launch_chat", lambda self, now: None)
    chat.route("anyone?")
    b.settings, b.state = store.settings(), store.state()
    b.chat_now(2000.0)
    b.chat_now(2000.0 + boss_mod.CHAT_STUCK - 1)
    assert outbox() == [] and waiting() == []
    b.chat_now(2000.0 + boss_mod.CHAT_STUCK + 1)
    assert waiting() == ["anyone?"]
    assert "within a minute" in outbox()[0]


def test_a_known_usage_wait_is_not_called_stuck(world, monkeypatch):
    store.save_settings({"whatsapp_enabled": True})
    b = world.boss
    monkeypatch.setattr(boss_mod.Boss, "launch_chat", lambda self, now: None)
    chat.route("anyone?")
    b.settings, b.state = store.settings(), store.state()
    b.state["chat_wait"] = "both accounts are out"
    b.chat_now(3000.0)
    b.chat_now(3000.0 + 600)
    assert waiting() == [] and outbox() == []


def test_chat_failing_twice_goes_to_the_boss_line_and_rests(world, monkeypatch):
    monkeypatch.setattr(boss_mod.Boss, "boss_line", lambda self, now=0: None)
    store.save_settings({"whatsapp_enabled": True})
    chat.route("FAKE:error please")
    settle(world, ticks=4)
    task = task_(store.settings()["whatsapp_chat_task"])
    assert task["status"] == chat.IDLE and items.num(task, "fails") == 0
    assert any("failed twice" in t for t in outbox())
    assert not chat.has_new(task)
    assert any("FAKE:error please" in q for q in waiting())
    # the next message in the rest goes straight to the boss line: no two more
    # failed sessions, no false "back", no second notice (the critic's case)
    sessions = len(world.calls())
    chat.route("FAKE:error again")
    settle(world)
    assert len(world.calls()) == sessions
    assert any("FAKE:error again" in q for q in waiting())
    assert boss_mod.BACK_TEXT not in outbox()
    assert len([t for t in outbox() if "can't answer" in t]) == 1


# ---- faster pickup ------------------------------------------------------------------


def test_a_message_launches_the_chat_between_ticks(world, monkeypatch):
    fast = FakeChat()
    monkeypatch.setattr(channels, "ready", lambda settings: {"chat": fast})
    store.save_settings({"whatsapp_enabled": True})
    b = world.boss

    def handle(msg, channel):
        chat.route(msg["text"])

    monkeypatch.setattr(b, "handle", handle)
    fast.inbox = [{"text": "FAKE:sleep quick one"}]
    assert b.quick() is True
    assert [r["kind"] for r in runs.active()] == ["chat"]  # no tick needed
    for run in runs.active():
        runs.stop(run)


# ---- the board ----------------------------------------------------------------------


def test_board_hears_a_start_only_on_the_first_launch(world, monkeypatch):
    said = []
    monkeypatch.setattr(boss_mod.Boss, "board", lambda self, text: said.append(text))
    task = items.new_task("Twice", "FAKE:continue")
    settle(world, ticks=3)
    assert items.num(task_(task["id"]), "attempts") >= 2
    assert len([t for t in said if "started" in t]) == 1


# ---- hey hands over to default past 80 ----------------------------------------------


def test_work_moves_off_an_account_past_its_move_line(world):
    store.save_settings({"account_limits": {"a": {"move_at": 80}}})
    task = items.new_task("Long", "FAKE:sleep")
    world.boss.tick()
    run = runs.active()[0]
    assert run["account"] == "a"
    world.readings["a"]["five"] = 82
    world.boss.tick()
    assert task_(task["id"])["status"] == "handing_over"
    task_file = Path(task_(task["id"])["path"])
    task_file.write_text(task_file.read_text().replace("FAKE:sleep", "FAKE:done"))
    settle(world)
    assert task_(task["id"])["ran_on"] == "b"


@pytest.mark.parametrize("why", ["spacing", "limit", "paused"])
def test_no_move_when_the_other_account_cannot_take_it_now(world, why):
    """The critic's loop: hand over, relaunch on the same account, again."""
    store.save_settings(
        {"account_limits": {"a": {"move_at": 80, "slow_at": 101}}, "slow_at": 70}
    )
    task = items.new_task("Long", "FAKE:sleep")
    world.boss.tick()
    world.readings["a"]["five"] = 82
    if why == "paused":
        store.save_settings({"paused": True})
    elif why == "spacing":  # b is past its slow line and launched a moment ago
        world.readings["b"]["five"] = 75
        state = store.state()
        state.setdefault("last_launch", {})["b"] = time.time()
        store.save_state(state)
    else:  # b hit its usage limit a moment ago, though its meter lags
        state = store.state()
        state.setdefault("limited", {})["b"] = time.time()
        store.save_state(state)
    for _ in range(3):
        world.boss.tick()
    assert task_(task["id"])["status"] == "running"
    assert [r["kind"] for r in runs.active()] == ["work"]
    for run in runs.active():
        runs.stop(run)


def test_move_line_needs_somewhere_to_go():
    s, now = {**store.DEFAULTS}, 1_000_000.0
    both = {"hey": {"five": 85, "week": 10}, "default": {"five": 30, "week": 10}}
    assert picker.move_to(both, s, "hey", {}, now) == "default"
    assert picker.pick_account(both, {}, now, s)[0] == "default"
    forced = picker.pick_account(both, {}, now, s, forced="hey")
    assert forced[0] == "default" and "move line" in forced[1]
    full = {"hey": {"five": 85, "week": 10}, "default": {"five": 96, "week": 10}}
    assert picker.move_to(full, s, "hey", {}, now) == ""
    assert picker.pick_account(full, {}, now, s)[0] == "hey"  # carries on
    low = {"hey": {"five": 79, "week": 10}, "default": {"five": 30, "week": 10}}
    assert picker.move_to(low, s, "hey", {}, now) == ""
    # default launched a moment ago: wait for its gap rather than loop
    assert picker.move_to(both, s, "hey", {"default": now - 10}, now) == ""


# ---- what the chat is told ----------------------------------------------------------


def test_chat_rules_ask_for_one_message_per_answer():
    assert "One answer is one relay reply" in prompts.CHAT_RULES
    assert "Several short replies" not in prompts.CHAT_RULES
    assert "`task:` in place of `new:`" in prompts.CHAT_RULES


def test_one_answer_is_one_whatsapp_message():
    assert len(chat.chunks("word " * 500, store.DEFAULTS["whatsapp_part_chars"])) == 1


def test_message_text_drops_stamp_and_name():
    assert chat.message_text("Thu 11:34 Emerson: hi: there") == "hi: there"
    assert chat.message_text("no stamp here") == "no stamp here"


# ---- a side-by-side job from the chat -----------------------------------------------


def test_a_task_from_the_chat_session_is_its_own_and_reports_on_whatsapp(
    monkeypatch, capsys
):
    import cli
    from channels import whatsapp

    monkeypatch.setenv("RELAY_RUN_KIND", "chat")
    cli.main(["task: build the side job"])
    made = [t for t in items.all_tasks() if t["title"] == "build the side job"]
    assert made and made[0]["source"] == "whatsapp"
    assert store.settings().get("whatsapp_work_task") in (None, 0, "")
    s = store.settings()
    assert whatsapp.wants(s, "Done: build the side job", made[0])
    assert "beside the work task" in capsys.readouterr().out


def test_sessions_know_their_kind(world):
    task = items.new_task("x", "FAKE:sleep")
    run = runs.start(task, "chat", "a", "low", "hi", str(Path.home()))
    try:
        environ = Path(f"/proc/{run['pid']}/environ").read_bytes().split(b"\0")
        assert b"RELAY_RUN_KIND=chat" in environ
    finally:
        runs.stop(run)
