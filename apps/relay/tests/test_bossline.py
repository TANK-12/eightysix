import json
import subprocess
import time

import actions
import bossline
import chat
import items
import localchat
import meters
import oneshot
import picker
import pytest
import runs
import store
from commands import parse

ROOM = {"default": {"five": 30, "week": 10}, "hey": {"five": 100, "week": 40}}


def wa(text):
    return actions.apply(parse("", text, source="whatsapp"), "whatsapp")


def status(number) -> str:
    return (items.find_task(number) or {}).get("status", "")


def sent() -> list[str]:
    """Texts waiting in the WhatsApp outbox."""
    folder = chat.outbox_dir()
    if not folder.is_dir():
        return []
    return [
        json.loads(f.read_text()).get("text", "")
        for f in sorted(folder.glob("*-text.json"))
    ]


def run_line(answer_text="", error=None, readings=None):
    """One boss-line round with a fake model: ask, then deliver."""
    asked = []

    def asker(questions, settings, got):
        asked.append((questions, got))
        if error:
            raise error
        return answer_text

    line = bossline.Line(asker=asker)
    settings = store.settings()
    line.step(settings, lambda: readings or ROOM)
    end = time.time() + 5
    while line.busy() and time.time() < end:
        time.sleep(0.01)
    line.step(settings, lambda: readings or ROOM)
    return asked


@pytest.fixture(autouse=True)
def whatsapp_on():
    store.save_settings({"whatsapp_enabled": True})


# ---- which messages go to the boss --------------------------------------------------


def test_boss_prefix_goes_to_the_boss_line_only_on_whatsapp():
    assert parse("", "boss how long for 63?", source="whatsapp").kind == "boss"
    cmd = parse("", "Boss: stop the cosmos job", source="whatsapp")
    assert (cmd.kind, cmd.text) == ("boss", "stop the cosmos job")
    assert parse("", "@boss, whats running", source="whatsapp").kind == "boss"
    # not the prefix: a file name, a plain chat, mail
    assert parse("", "boss.py is broken", source="whatsapp").kind == "chat"
    assert parse("", "the boss is slow", source="whatsapp").kind == "chat"
    assert parse("", "boss what runs", source="mail").kind == "task"
    # the word on its own is the mode switch
    assert parse("", "boss", source="whatsapp").kind == "quick"


def test_boss_question_is_queued_without_an_instant_reply():
    reply, made = wa("boss what is running?")
    assert reply == "" and made is None
    assert bossline.take() == ["what is running?"]
    assert bossline.take() == []


def test_boss_mode_sends_every_plain_message_there():
    said = wa("boss")[0]
    assert "Boss line on" in said and localchat.mode() == "boss"
    wa("hows the cosmos job")
    assert bossline.take() == ["hows the cosmos job"]
    wa("status")  # commands still answer at once
    assert bossline.take() == []
    assert "Back to the Claude chat" in wa("claude")[0]
    wa("hello")
    assert bossline.take() == []


# ---- answering ---------------------------------------------------------------------


def test_answer_comes_back_labelled_and_is_remembered():
    wa("boss what's running")
    asked = run_line("Nothing runs right now. 2 queued.")
    assert asked and asked[0][0] == ["what's running"]
    assert sent() == ["Boss: Nothing runs right now. 2 queued."]
    history = (store.read_json(store.path("bossline.json")) or {})["history"]
    assert history[-1]["q"] == "what's running"


def test_stop_runs_when_asked_by_name():
    task = items.new_task("Cosmos zoom", "fix the zoom")
    wa("boss stop the cosmos job please")
    run_line(f"Stopping {task['id']}.\nACTION stop {task['id']}")
    assert status(task["id"]) == "stopped"
    assert sent()[0].startswith(f"Boss: Stopping {task['id']}.")


def test_action_he_did_not_ask_for_is_refused():
    task = items.new_task("Cosmos zoom", "fix the zoom")
    wa(f"boss how is {task['id']} doing")
    run_line(f"Fine.\nACTION stop {task['id']}")
    assert status(task["id"]) == "queued"
    assert "you did not ask for that" in sent()[0]


def test_stop_of_an_unknown_number_is_refused():
    wa("boss stop it")
    run_line("Stopping.\nACTION stop 999")
    assert "Not done" in sent()[0]


def test_tell_passes_a_note_to_a_running_task(monkeypatch):
    task = items.new_task("Cosmos zoom", "fix the zoom")
    task["status"] = "running"
    items.save(task)
    told = []
    monkeypatch.setattr(
        actions, "tell_task", lambda n, text: told.append((n, text)) or "Told."
    )
    wa("boss tell the cosmos one to use 60fps")
    run_line(f"Passing it on.\nACTION tell {task['id']} use 60fps for the test")
    assert told == [(task["id"], "use 60fps for the test")]


def test_task_action_queues_a_real_task():
    wa("boss queue a task to fix the cosmos zoom")
    run_line("Queuing it.\nACTION task: Cosmos: fix the zoom jump on scroll")
    made = [t for t in items.all_tasks() if "zoom jump" in t.get("title", "")]
    assert made and made[0]["status"] == "queued"
    assert f"Queued task {made[0]['id']}" in sent()[0]


def test_bare_command_lines_are_never_sent_or_run():
    task = items.new_task("x", "y")
    wa("boss stop x")
    run_line(f"Ok.\nstop {task['id']}")
    assert status(task["id"]) == "queued"
    assert sent() == ["Boss: Ok."]


def test_no_account_with_room_answers_with_plain_state():
    wa("boss whats up")
    asked = run_line(error=bossline.NoRoom("no account has room (x)"))
    assert asked  # the asker raised; nothing else was called
    text = sent()[0]
    assert text.startswith("Boss: No Claude account can take a question")
    assert "Running (0):" in text


def test_answer_without_room_never_calls_claude(monkeypatch):
    full = {"default": {"five": 100, "week": 1}, "hey": {"five": 100, "week": 1}}
    monkeypatch.setattr(oneshot, "ask", lambda *a, **k: pytest.fail("called"))
    with pytest.raises(bossline.NoRoom):
        bossline.answer(["hi"], store.settings(), full)


# ---- what the boss reads and how it asks --------------------------------------------


def test_summary_is_compact_and_calm():
    store.save_state({"meters": ROOM, "wait_reason": "spacing launches (x)"})
    items.new_task("Queued thing", "do it")
    text = bossline.summary()
    assert "Running (0):" in text and "Queued (1):" in text
    assert "Room to launch on default." in text
    assert "No account" not in text
    assert len(text) <= bossline.SUMMARY_CHARS


def test_oneshot_is_lean(monkeypatch):
    seen = {}

    def fake_run(argv, **kw):
        seen["argv"], seen["env"] = argv, kw["env"]
        return subprocess.CompletedProcess(argv, 0, stdout="hi\n", stderr="")

    monkeypatch.setattr(oneshot.subprocess, "run", fake_run)
    monkeypatch.setenv("RELAY_CLAUDE_BIN", "/bin/true")
    assert oneshot.ask("q", "sys", "default", "opus", "low") == "hi\n"
    argv = seen["argv"]
    for flag in ("--system-prompt", "--setting-sources", "--strict-mcp-config"):
        assert flag in argv
    assert argv[argv.index("--tools") + 1] == ""
    assert argv[argv.index("--model") + 1] == "opus"


def test_prompt_file_is_read_and_turn_uses_settings(monkeypatch):
    got = {}
    monkeypatch.setattr(
        oneshot, "ask", lambda prompt, system, account, **k: got.update(k, a=account)
    )
    bossline.answer(["hi"], store.settings(), ROOM)
    assert got["a"] == "default"  # hey is full; default has room
    assert (got["model"], got["effort"]) == ("opus", "low")
    assert "ACTION stop 12" in bossline.PROMPT.read_text()


# ---- calm about one full account (two subscriptions) --------------------------------


def test_one_full_account_is_not_a_warning():
    lines = meters.describe(ROOM, store.DEFAULTS)
    assert lines[0] == "default: 5-hour 30%, week 10%"
    assert lines[1].startswith("hey: 5-hour 100%, week 40%, resting")
    assert lines[-1] == "Room to launch on default."


def test_warning_only_when_no_account_can_launch():
    full = {"default": {"five": 99, "week": 1}, "hey": {"five": 100, "week": 1}}
    assert meters.describe(full, store.DEFAULTS)[-1].startswith(
        "No account can launch now"
    )


def test_spacing_with_one_full_account_is_calm():
    now = 1_000_000.0
    settings = {**store.DEFAULTS, "launch_gap_minutes": 3}
    account, why = picker.pick_account(ROOM, {"default": now - 30}, now, settings)
    assert account is None
    assert why.startswith("spacing launches (default:") and "hey" not in why
    full = {"default": {"five": 99, "week": 1}, "hey": {"five": 100, "week": 1}}
    assert picker.pick_account(full, {}, now, settings)[1].startswith(
        "no account has room"
    )


def test_status_shows_both_meters_calmly():
    store.save_state({"meters": ROOM})
    text = actions.status_text()
    assert "\nRunning (0):" in text and "\nQueued (0):" in text  # shutdown watcher
    assert "Room to launch on default." in text and "No account" not in text


# Critic findings (task 72), kept as tests.


@pytest.mark.parametrize(
    "act,question",
    [
        ("stop 1", "when will 1 end?"),
        ("retry 1", "what's running again?"),
        ("task: build a thing", "how many tasks are queued?"),
        ("stop 1", "don't stop anything"),
        ("tell 1 hurry up", "let me know when it's done"),
        ("resume", "will the queue continue tonight?"),
    ],
)
def test_questions_alone_never_run_actions(act, question):
    items.new_task("Cosmos zoom", "fix the zoom")
    assert not bossline.allowed(act, [question])


def test_marked_number_must_match_and_units_are_not_numbers():
    task = items.new_task("Cosmos zoom", "fix the zoom")
    assert not bossline.allowed(f"stop {task['id']}", ["stop task 7"])
    assert bossline.allowed(f"stop {task['id']}", [f"stop #{task['id']} now"])
    assert bossline.allowed(f"tell {task['id']} x", ["tell cosmos to use 60fps"])


def test_boss_words_inside_a_sentence_stay_a_task_or_chat():
    for text in ["Boss fight in emberfield is too hard, fix it", "boss level 3"]:
        assert parse("", text, source="whatsapp").kind != "boss"
    assert parse("", "boss: stop 12", source="whatsapp").kind == "boss"


def test_failed_readings_keep_the_question_waiting():
    bossline.ask_later("what runs")
    line = bossline.Line(asker=lambda q, s, r: "x")

    def broken():
        raise RuntimeError("meter")

    with pytest.raises(RuntimeError):
        line.step(store.settings(), broken)
    assert [w["q"] for w in bossline._load()["waiting"]] == ["what runs"]


def test_one_failing_action_does_not_lose_the_rest(monkeypatch):
    task = items.new_task("Cosmos zoom", "fix the zoom")
    task["status"] = "running"
    items.save(task)
    wa(f"boss stop {task['id']} and queue a task to build x")
    monkeypatch.setattr(
        actions, "add_task", lambda *a, **kw: (_ for _ in ()).throw(ValueError("x"))
    )
    run_line(f"Ok.\nACTION stop {task['id']}\nACTION task: build x")
    assert "Failed" in sent()[-1]
    assert status(task["id"]) != "running"


def test_failed_reply_is_logged_not_raised(monkeypatch):
    wa("boss what runs")
    line = bossline.Line(asker=lambda q, s, r: "All quiet.")
    line.step(store.settings(), lambda: ROOM)
    end = time.time() + 5
    while line.busy() and time.time() < end:
        time.sleep(0.01)
    monkeypatch.setattr(
        chat, "reply", lambda *a, **kw: (_ for _ in ()).throw(OSError("disk"))
    )
    assert "failed" in line.step(store.settings(), lambda: ROOM)


def test_task_action_without_a_colon_keeps_its_words():
    said = bossline.act(
        "task build the cosmos page by 12:30",
        ["queue a task to build the cosmos page by 12:30"],
    )
    assert said.startswith("Queued task")
    assert [t["title"] for t in items.all_tasks()] == ["build the cosmos page by 12:30"]


# Task 105: what the boss line refused on 2026-10-08 that he really asked for.


def running_work(monkeypatch, *numbers):
    monkeypatch.setattr(
        runs,
        "active",
        lambda: [{"task": str(n), "kind": "work"} for n in numbers]
        + [{"task": "47", "kind": "chat"}],
    )


@pytest.mark.parametrize(
    "question",
    [
        "Please email a task that will read the chat and find the bug and fix it",
        "Are you Claude can you read the chat and make taks to fix this issue",
        "message the one working session to start a new session to fix it",
        "spawn a helper to fix the WhatsApp chat",
    ],
)
def test_task_requests_in_his_words_are_allowed(question):
    assert bossline.allowed("task: fix the chat", [question], earlier=[])


def test_tell_it_goes_to_the_only_running_work_task(monkeypatch):
    task = items.new_task("Mech and exoskeleton tester", "x")
    ask = "What is running on hey and tell it to hand off to default at 80 percent"
    running_work(monkeypatch, task["id"])
    assert bossline.allowed(f"tell {task['id']} hand off at 80", [ask], earlier=[])
    running_work(monkeypatch, task["id"], 999)  # two running: he must say which
    assert not bossline.allowed(f"tell {task['id']} hand off", [ask], earlier=[])


def test_let_me_know_is_not_a_tell(monkeypatch):
    task = items.new_task("Mech tester", "x")
    running_work(monkeypatch, task["id"])
    ask = ["let me know when it's done"]
    assert not bossline.allowed(f"tell {task['id']} hurry", ask, earlier=[])


def test_do_it_yourself_leans_on_his_last_questions(monkeypatch):
    task = items.new_task("Mech tester", "x")
    running_work(monkeypatch, task["id"])
    earlier = ["Can you message the one working session to start a fix session"]
    act = f"tell {task['id']} please spawn a helper"
    assert bossline.allowed(act, ["Do it yourself"], earlier=earlier)
    assert not bossline.allowed(act, ["Do it yourself"], earlier=[])
    # stop and pause need his words now, never an earlier question
    assert not bossline.allowed(
        f"stop {task['id']}", ["ok"], earlier=[f"stop {task['id']}"]
    )
    assert not bossline.allowed("pause", ["ok"], earlier=["pause everything"])


def test_recent_reads_only_the_last_fifteen_minutes():
    bossline.remember(["tell 12 to hurry"], "Told.")
    data = bossline._load()
    data["history"].insert(0, {"at": time.time() - 3600, "q": "old one", "a": "x"})
    store.write_json(store.path("bossline.json"), data)
    assert bossline.recent() == ["tell 12 to hurry"]


def test_long_answers_are_remembered_whole():
    bossline.remember(["q"], "a" * 1500)
    assert len(bossline._load()["history"][-1]["a"]) == 1500


def test_summary_names_the_chat_run(monkeypatch):
    task = items.new_task("WhatsApp chat", "x")
    monkeypatch.setattr(
        runs,
        "active",
        lambda: [
            {
                "task": task["id"],
                "kind": "chat",
                "account": "default",
                "effort": "low",
                "started": time.time() - 60,
            }
        ],
    )
    monkeypatch.setattr(
        runs, "summary", lambda run: {"context_tokens": 1000, "last_action": ""}
    )
    assert "the WhatsApp chat itself (not a work task)" in bossline.summary()


def test_units_and_times_are_not_task_numbers():
    found = bossline.BARE_NUMBER.findall
    assert found("hand off at 80 percent, 60fps, 80%, at 13:00, 2.5x") == []
    assert found("stop 12 and 7") == ["12", "7"]


# The task-105 critic's cases.


def test_stop_never_falls_back_to_the_only_running_task(monkeypatch):
    task = items.new_task("Mech tester", "x")
    running_work(monkeypatch, task["id"])
    for ask in ["stop sending me so many messages", "can you stop splitting replies"]:
        assert not bossline.allowed(f"stop {task['id']}", [ask], earlier=[])
    for ask in ["tell me what is running", "did you get my message?"]:
        assert not bossline.allowed(f"tell {task['id']} x", [ask], earlier=[])


@pytest.mark.parametrize(
    "act,now,earlier",
    [
        ("tell {n} x", "don't tell {n} anything yet", "tell {n} to hurry"),
        ("resume", "don't resume yet", "resume launching"),
        ("resume", "how is it going?", "resume"),
        ("retry {n}", "ok thanks", "retry {n}"),
        ("task: do it", "how many open tasks are there?", "how is it going"),
    ],
)
def test_earlier_asks_never_beat_what_he_says_now(act, now, earlier):
    n = items.new_task("Mech tester", "x")["id"]
    fill = lambda t: t.format(n=n)  # noqa: E731
    assert not bossline.allowed(fill(act), [fill(now)], earlier=[fill(earlier)])


def test_this_messages_number_wins_over_an_earlier_one():
    items.new_task("one", "x")
    two = items.new_task("two", "x")["id"]
    ask = [f"tell {two} to wait for me"]
    assert bossline.allowed(f"tell {two} wait", ask, earlier=["how is task 1 doing"])


def test_plain_questions_queue_no_task():
    for ask in [
        "is the new session done?",
        "how many open tasks are there?",
        "did you send the job to mika?",
    ]:
        assert not bossline.allowed("task: x", [ask], earlier=[])
