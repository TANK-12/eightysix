"""The local chat (localchat.py) and the quick commands (quick.py), with a
fake Jan. Live Jan is scored with `localchat.py --bench` (WIP.md)."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import actions
import chat
import commands
import forge_jan
import forge_sysinfo
import frontdesk
import items
import localchat
import pytest
import quick
import store
from test_boss import task_, world  # noqa: F401  (world is a fixture)


def outbox():
    return [str((store.read_json(f) or {}).get("text") or "") for f in chat.pending()]


def wa(text):
    return actions.apply(commands.parse("", text, source="whatsapp"), "whatsapp")


def run(desk, state=None):
    for _ in range(20):
        desk.step(store.settings(), state)
        if desk.thread:
            desk.thread.join(5)
        if not desk.busy() and desk.result is None:
            if (chat.chat_task(create=False) or {}).get("status") != chat.DESK:
                return


# ---- quick commands ---------------------------------------------------------------


@pytest.mark.parametrize(
    "text,name,args",
    [
        ("command list", "commands", ()),
        ("Command list.", "commands", ()),
        ("cmds", "commands", ()),
        ("stats", "stats", ()),
        ("How hot", "stats", ()),
        ("top cpu", "top-cpu", ()),
        ("top", "top-cpu", ()),
        ("Top GPU", "top-gpu", ()),
        ("kill 3", "kill", ("3",)),
        ("kill 3, 5 and 7", "kill", ("3, 5 and 7",)),
        ("force kill 2", "force-kill", ("2",)),
        ("kill task 12", "kill-task", ("12",)),
        ("stop task 61 please", "kill-task", ("61",)),
        ("kill all", "kill-all", ()),
        ("please kill everything now", "kill-all", ()),
        ("local", "local", ()),
        ("Claude", "claude", ()),
        ("back to claude", "claude", ()),
        ("mode", "mode", ()),
        ("local model 2b", "local-model", ("2b",)),
        ("local model", "local-model", ("",)),
        ("jan start", "jan", (" start",)),
        ("find report", "find-files", ("report",)),
        ("find *.blend", "find-files", ("*.blend",)),
        ("search files eighty six notes", "find-files", ("eighty six notes",)),
        ("send 2", "send-found", ("2",)),
        ("send 1 and 3", "send-found", ("1 and 3",)),
        ("--command list", "commands", ()),
        ("/commands", "commands", ()),
        ("what can you do?", "commands", ()),
        ("think off", "think", ("off",)),
        ("Thinking auto", "think", ("auto",)),
        ("web search perth weather", "web", ("perth weather",)),
        ("google qwen 3.5 2b", "web", ("qwen 3.5 2b",)),
        ("Shut down the computer", "shutdown", ()),
        ("shutdown", "shutdown", ()),
        ("yes shut down", "shutdown-yes", ()),
        ("Yes, shutdown", "shutdown-yes", ()),
    ],
)
def test_quick_phrases(text, name, args):
    assert quick.match(text) == (name, args)


@pytest.mark.parametrize(
    "text",
    [
        "kill the lights in cosmos",
        "local news today?",
        "stop 12",
        "status",
        "hi",
        "find out why cosmos broke",
        "send it to me",
        "think about it",
        "shut down cosmos and restart it",
        "web app is broken",
    ],
)
def test_not_quick(text):
    assert quick.match(text) is None


def test_command_list_answers_on_whatsapp_and_keeps_old_commands():
    cmd = commands.parse("", "command list", source="whatsapp")
    assert cmd.kind == "quick"
    said, _ = actions.apply(cmd, "whatsapp")
    for word in ("top cpu", "kill all", "local", "stats", "status", "new:"):
        assert word in said
    assert wa("help")[0] == said
    assert "top cpu" in actions.apply(commands.parse("", "help"), "mail")[0]
    # a quick phrase inside a longer mail is not a command
    assert commands.parse("", "stats\nand some more lines").kind == "task"
    assert commands.parse("", "stop 12", source="whatsapp").kind == "stop"


def test_top_list_is_numbered_and_kill_ends_that_row(monkeypatch):
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        start = forge_sysinfo.start_time(child.pid)
        rows = [
            {
                "pid": child.pid,
                "comm": "python3",
                "start": start,
                "cpu": 90,
                "mem_mb": 10,
                "cmd": "python3",
            },
            {
                "pid": 1,
                "comm": "systemd",
                "start": forge_sysinfo.start_time(1),
                "cpu": 1,
                "mem_mb": 9,
                "cmd": "/sbin/init",
            },
        ]
        monkeypatch.setattr(forge_sysinfo, "top_cpu", lambda n, s: rows)
        text = quick.top_text("cpu")
        assert text.startswith("Top CPU") and "1. python3 90% CPU" in text
        assert "2. systemd" in text and "kill 3" in text
        out = quick.kill_rows([2, 1, 9])
        assert "2. systemd: left alone" in out
        assert "9: not on the list" in out
        assert "1. python3: ended." in out
        child.wait(5)
        assert quick.kill_rows([1]) == "1. python3: already gone."
    finally:
        child.kill()


def test_find_then_send_a_file(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / "docs").mkdir(parents=True)
    (home / ".ssh").mkdir()
    (home / "docs" / "Mech Report.pdf").write_bytes(b"pdf")
    (home / "docs" / "old report.txt").write_text("x")
    (home / "docs" / "report-token.txt").write_text("k")
    (home / ".ssh" / "report").write_text("k")
    os.utime(home / "docs" / "old report.txt", (1, 1))
    monkeypatch.setenv("HOME", str(home))
    store.save_settings(
        {"whatsapp_enabled": True, "whatsapp_files_dir": str(tmp_path / "out")}
    )
    chat.chat_task()
    listing = wa("find report")[0]
    rows = listing.splitlines()
    assert rows[1].startswith("1. Mech Report.pdf (~/docs, 3 B, ")
    assert rows[2].startswith("2. old report.txt (~/docs, 1 B, 1 Jan)")
    assert "token" not in listing and ".ssh" not in listing and len(rows) == 4
    assert wa("send 1")[0].startswith("Queued Mech Report.pdf")
    assert wa("send 9")[0] == "9: not on the list (1 to 2)."
    assert wa("find nothingcalledthis")[0].startswith("No files called")


def test_files_never_sent_from_relay_data_or_a_stale_list(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    secret = store.data_dir() / "settings.json"
    assert quick.unsendable(secret) == "never Relay's own data"
    assert quick.unsendable(Path("/etc/hostname")) == "only files in your home folder"
    store.write_json(quick._found_file(), {"at": 0, "paths": [str(secret)]})
    assert quick.send_found([1]).startswith("No fresh file list")


def test_kill_needs_a_fresh_list():
    assert "Write top cpu" in quick.kill_rows([1])
    store.write_json(quick._hogs_file(), {"at": time.time() - 3600, "rows": [{}]})
    assert "Write top cpu" in quick.kill_rows([1])


def test_relay_and_its_desktop_are_protected():
    import os

    assert quick.protected(os.getpid(), "python3")
    assert quick.protected(1234567, "gnome-shell")
    assert quick.protected(1234567, "whatsie")
    assert not quick.protected(1234567, "godot")


def test_kill_everything_pauses(world):
    said = quick.run("kill-all")
    assert said.startswith("Nothing was running") and "resume" in said
    assert store.settings()["paused"] is True


def test_a_quick_command_failure_is_a_reply(monkeypatch):
    def boom():
        raise OSError("no /proc")

    monkeypatch.setattr(quick, "stats_text", boom)
    assert quick.run("stats").startswith("That failed: OSError")


# ---- who answers --------------------------------------------------------------------


def test_modes_switch_and_describe(monkeypatch):
    monkeypatch.setattr(forge_jan, "ensure_router", lambda wait=0.0: True)
    assert localchat.mode() == "claude"
    assert "Local chat on" in wa("local")[0]
    assert store.settings()["whatsapp_frontdesk"] == "local"
    assert "local model" in localchat.describe() and "claude" in localchat.describe()
    assert wa("claude")[0] == "Back to the Claude chat."
    assert store.settings()["whatsapp_frontdesk"] == "off"
    assert "Front desk on" in wa("desk")[0]
    assert localchat.set_mode("sideways").startswith("Mode must")


def test_local_mode_routes_every_message_to_the_desk():
    store.save_settings({"whatsapp_enabled": True, "whatsapp_frontdesk": "local"})
    task, running = chat.route("hi")
    assert not running and task_(task["id"])["status"] == chat.DESK
    assert localchat.active(store.settings(), {})


def test_stand_in_only_while_claude_waits_and_fallback_is_auto():
    store.save_settings({"whatsapp_enabled": True})
    assert not localchat.active(store.settings(), {"chat_wait": "full"})
    store.save_settings({"whatsapp_fallback": "auto"})
    assert localchat.active(store.settings(), {"chat_wait": "full"})
    assert not localchat.active(store.settings(), {"chat_wait": ""})


def test_local_answer_goes_out_and_messages_are_read():
    store.save_settings({"whatsapp_enabled": True, "whatsapp_frontdesk": "local"})
    seen = []

    def fake(task, messages):
        seen.append(messages)
        return "All quiet, mate. Two tasks running."

    desk = frontdesk.Desk(asker=lambda t, m: "wrong asker", local_asker=fake)
    task, _ = chat.route("hows it going")
    run(desk)
    assert seen and "hows it going" in seen[0][0]
    assert outbox() == ["All quiet, mate. Two tasks running."]
    task = task_(task["id"])
    assert task["status"] == chat.IDLE and not chat.has_new(task)
    assert "Local: All quiet" in task["body"]


def test_local_failure_says_so_and_spends_no_usage():
    store.save_settings({"whatsapp_enabled": True, "whatsapp_frontdesk": "local"})

    def broken(task, messages):
        raise forge_jan.JanError("Jan is not answering")

    desk = frontdesk.Desk(local_asker=broken)
    task, _ = chat.route("hello?")
    run(desk)
    assert "not answering" in outbox()[0] and "command list" in outbox()[0]
    assert task_(task["id"])["status"] == chat.IDLE  # not queued for Claude


def test_actions_run_only_when_his_message_asked():
    store.save_settings({"whatsapp_enabled": True, "whatsapp_frontdesk": "local"})
    target = items.new_task("Cosmos fix", "do it", status="queued")
    n = str(target["id"])
    assert localchat.run_action(f"stop {n}", ["Emerson: hey whats up"]) == ""
    assert task_(n)["status"] == "queued"
    assert localchat.run_action("stop 999", [f"Emerson: stop {n} please"]) == ""
    assert localchat.run_action("pause", ["Emerson: pause everything"]).startswith(
        "Paused"
    )
    said = localchat.run_action(f"stop {n}", [f"Emerson: stop task {n} please"])
    assert said.startswith(f"Stopped task {n}")
    assert localchat.run_action("say @all hi", ["Emerson: say hi to all"]) == ""


def test_desk_runs_an_asked_action_from_the_answer():
    store.save_settings({"whatsapp_enabled": True, "whatsapp_frontdesk": "local"})
    desk = frontdesk.Desk(local_asker=lambda t, m: "Pausing now.\nACTION pause")
    chat.route("pause relay please")
    run(desk)
    assert outbox()[0] == "Pausing now."
    assert outbox()[1].startswith("Paused")


# ---- what it asks Jan ---------------------------------------------------------------


def test_conversation_is_real_turns_with_facts():
    task = {
        "body": "## Messages\n\n- 10:00 Emerson: hi\n- 10:00 Local: hey mate\n"
        "- 10:01 Emerson: and you?\n- 10:01 Local: grand\n"
    }
    turns = localchat.conversation(task, ["10:02 Emerson: whats up"], "CPU 41%")
    roles = [t["role"] for t in turns]
    assert roles == ["system", "user", "assistant", "user", "assistant", "user"]
    assert "CPU 41%" in turns[0]["content"] and "LOOKUP" in turns[0]["content"]
    assert turns[-1]["content"] == "whats up"


def test_chat_stamps_with_a_weekday_keep_who_said_what():
    task = {"body": "## Messages\n\n- Wed 15:47 Emerson: hi\n- Wed 15:48 Local: hey\n"}
    turns = localchat.conversation(task, ["Wed 15:49 Emerson: so?"], "f")
    assert [t["role"] for t in turns] == ["system", "user", "assistant", "user"]
    assert turns[1]["content"] == "hi" and turns[2]["content"] == "hey"
    # 15:48 was how "tell 15:48 I'm ready" got past the number check
    said = ["Wed 15:48 Emerson: I want you to make it a relay task"]
    assert localchat.run_action("tell 15 I'm ready", said) == ""


def test_lookups_from_words_and_from_the_model():
    assert localchat.auto_lookups(["whats using all the cpu"]) == ["cpu"]
    assert "progress" in localchat.auto_lookups(["how far is the eighty six job"])
    assert localchat.auto_lookups(["hello there"]) == []
    asked = []

    def asker(turns):
        asked.append(turns[0]["content"])
        if len(asked) == 1:
            return "LOOKUP disks"
        return "You have 140 GB free."

    looked = []

    def look(name, arg):
        looked.append(name)
        return f"{name} result"

    answer = localchat.ask({"body": ""}, ["hi there"], "facts", "m", asker, look)
    assert answer == "You have 140 GB free."
    assert looked == ["disks"] and "disks result" in asked[1]


def test_lookup_loop_stops_and_never_sends_a_bare_lookup():
    answer = localchat.ask(
        {"body": ""},
        ["hm"],
        "facts",
        "m",
        lambda turns: "LOOKUP board",
        lambda n, a: "x",
    )
    assert "could not find" in answer


def test_parse_splits_actions_and_drops_lookups():
    assert localchat.parse("Done.\nACTION stop 61\nLOOKUP cpu") == (
        "Done.",
        ["stop 61"],
    )


def test_shell_lookup_is_read_only():
    assert "Only these" in localchat._shell("rm -rf /tmp/x")
    assert "status" in localchat._shell("systemctl --user stop relay-boss")
    assert "git only" in localchat._shell("git push")
    assert localchat._shell("uname -s").strip() == "Linux"
    assert "never Relay's secrets" in localchat._file(str(store.data_dir() / "secrets"))
    assert "Only files" in localchat._file("/etc/passwd")


def test_usage_lines_are_plain(monkeypatch):
    soon = time.strftime(
        "%Y-%m-%dT%H:%M:%S%z", time.localtime(time.time() + 2 * 3600 + 120)
    )
    store.save_state({"meters": {"hey": {"five": 96, "week": 30, "resets": soon}}})
    line = localchat._usage_lines()
    assert line.startswith("hey: 5-hour 96%, week 30%, resting, back")
    assert "(in 2h0" in line and "No account can launch now" in line
    # two subscriptions: one full and one with room is calm, no warning
    store.save_state(
        {
            "meters": {
                "hey": {"five": 100, "week": 30, "resets": soon},
                "default": {"five": 40, "week": 9},
            }
        }
    )
    line = localchat._usage_lines()
    assert "Room to launch on default." in line
    assert "No account" not in line and "full" not in line


def test_pick_local_model(monkeypatch):
    monkeypatch.setattr(
        forge_jan, "models", lambda refresh=False: list(localchat.CANDIDATES.values())
    )
    assert "2b (now)" in wa("local model")[0]
    assert wa("local model 0.8b")[0] == "The local chat now runs on 0.8b."
    assert localchat.model() == localchat.CANDIDATES["0.8b"]
    assert wa("local model 70b")[0].startswith("No local model")


def test_bench_samples_are_well_formed():
    data = json.loads(Path(localchat.SAMPLES).read_text())
    assert data["facts"] and len(data["samples"]) >= 10
    for sample in data["samples"]:
        assert sample["text"]
        assert sample.get("lookup", "cpu") in localchat.LOOKUPS


# ---- the boss: Claude out of usage ---------------------------------------------------


def test_out_of_usage_the_local_model_stands_in_then_claude_returns(world):
    store.save_settings({"whatsapp_enabled": True, "whatsapp_fallback": "auto"})
    world.boss.desk = frontdesk.Desk(local_asker=lambda t, m: "Local here, all good.")
    world.readings["a"]["five"] = 99
    world.readings["b"]["five"] = 99
    task, _ = chat.route("hows it going")
    for _ in range(3):
        world.boss.tick()
        if world.boss.desk.thread:
            world.boss.desk.thread.join(5)
    texts = outbox()
    assert "out of usage" in texts[0] and "local model" in texts[0]
    assert "Local here, all good." in texts
    assert sum("out of usage" in t for t in texts) == 1
    assert task_(task["id"])["status"] == chat.IDLE
    # a second message while still out goes straight to the local model
    chat.route("and now?")
    assert task_(task["id"])["status"] == chat.DESK
    for _ in range(2):
        world.boss.tick()
        if world.boss.desk.thread:
            world.boss.desk.thread.join(5)
    # usage back: told once, and the next message is Claude's again
    world.readings["a"]["five"] = 10
    world.boss.tick()
    assert localchat.BACK_TEXT in outbox()
    assert not store.state().get("chat_wait")
    chat.route("claude again?")
    assert task_(task["id"])["status"] == "queued"


def test_ensure_router_never_starts_one_when_one_answers(monkeypatch, tmp_path):
    started = []
    monkeypatch.setattr(
        forge_jan.subprocess, "Popen", lambda *a, **k: started.append(a)
    )
    monkeypatch.setattr(forge_jan, "router_alive", lambda *a, **k: True)
    assert forge_jan.ensure_router(wait=0.1, data=tmp_path)
    monkeypatch.setattr(forge_jan, "router_alive", lambda *a, **k: False)
    assert not forge_jan.ensure_router(wait=0.1, data=tmp_path)  # nothing installed
    assert started == []


# ---- honest about deeds (Emerson's chat, 2026-10-07 15:20-15:53) -----------------


def _work_task():
    return task_(str(store.settings()["whatsapp_work_task"]))


def test_asking_for_a_task_queues_his_words_not_a_placeholder():
    store.save_settings({"whatsapp_enabled": True, "whatsapp_frontdesk": "local"})
    answer = "Got it, I'll queue it.\nACTION new: [full work request for Claude]"
    desk = frontdesk.Desk(local_asker=lambda t, m: answer)
    chat.route("make a relay task to fix the cosmos orbit flicker")
    run(desk)
    sent = outbox()
    assert sent[0] == "Got it, I'll queue it." and sent[1].startswith("Work task")
    body = _work_task()["body"]
    assert "fix the cosmos orbit flicker" in body and "[full work" not in body


def test_a_task_ask_queues_even_when_the_model_only_talks():
    store.save_settings({"whatsapp_enabled": True, "whatsapp_frontdesk": "local"})
    desk = frontdesk.Desk(local_asker=lambda t, m: "Sure, I can do that.")
    chat.route("the hub lags when an app covers it")
    run(desk)
    chat.route("Make a relay task for it")
    run(desk)
    assert outbox()[-1].startswith("Work task")
    body = _work_task()["body"]
    assert "hub lags when an app covers it" in body and "relay task for it" in body


def test_a_claimed_deed_with_nothing_done_is_corrected():
    store.save_settings({"whatsapp_enabled": True, "whatsapp_frontdesk": "local"})
    desk = frontdesk.Desk(local_asker=lambda t, m: "Got it, I'll shut it down now.")
    chat.route("Shut down the computer")
    run(desk)
    sent = outbox()
    assert len(sent) == 1 and "talk only" in sent[0]
    desk = frontdesk.Desk(local_asker=lambda t, m: "All quiet, two tasks running.")
    chat.route("hows it going")
    run(desk)
    assert "talk only" not in outbox()[-1]


def test_work_action_keeps_a_real_summary_and_his_words():
    task = {"body": "## Messages\n\n- Wed 15:43 Emerson: gpu lags under apps\n"}
    made = localchat.work_action(
        "new: Fix GPU lag when apps cover the hub", task, ["Wed 15:44 Emerson: do it"]
    )
    assert made.startswith("new: Fix GPU lag when apps cover the hub")
    assert "gpu lags under apps / do it" in made


def test_dash_help_is_the_command_list():
    said = wa("command list")[0]
    assert wa("--help")[0] == said and wa("--command list")[0] == said


# ---- thinking and the web ------------------------------------------------------------


def test_thinking_auto_on_off():
    assert not localchat.should_think("why is cosmos slow today")  # off by default
    quick.run("think", ("auto",))
    assert localchat.should_think("why is cosmos slow today")
    assert localchat.should_think("which is better, the 2b or the 4b?")
    assert not localchat.should_think("hey whats up")
    assert quick.run("think", ("off",)).startswith("The local model now answers")
    assert not localchat.should_think("why is cosmos slow today")
    quick.run("think", ("on",))
    assert localchat.should_think("hey")
    assert "Local thinking: on" in localchat.describe()
    assert "think on" in localchat.set_thinking("maybe")


def test_ask_passes_thinking_to_the_asker_choice():
    seen = []
    localchat.ask(
        {"body": ""}, ["why is it slow"], "f", "m", lambda t: "ok", think=True
    )
    answer = localchat.ask(
        {"body": ""}, ["hi"], "f", "m", lambda t: seen.append(t) or "hey"
    )
    assert answer == "hey" and seen


def test_web_lookup_from_words_but_not_for_files(monkeypatch):
    assert "web" in localchat.auto_lookups(["whats the weather in perth today"])
    assert "web" in localchat.auto_lookups(["google who won the f1 race"])
    assert "web" not in localchat.auto_lookups(["search for my report file"])
    asked = []
    monkeypatch.setattr(
        localchat.forge_websearch, "text", lambda q, n=6: asked.append(q) or "1. x"
    )
    assert (
        localchat.lookup("web", "can you search the web for perth weather?") == "1. x"
    )
    assert asked == ["perth weather"]


def test_shut_down_asks_first_and_yes_only_counts_soon(monkeypatch):
    calls = []
    monkeypatch.setattr(quick, "_power_off", lambda: calls.append(1))
    assert "No shut down was asked" in quick.run("shutdown-yes")
    assert "Reply yes shut down" in wa("shut down the laptop")[0]
    assert wa("yes shut down")[0].startswith("Shutting the laptop down")
    assert calls == [1]
    assert "No shut down was asked" in quick.run("shutdown-yes")  # once only
    store.write_json(quick._power_file(), {"asked": time.time() - 300})
    assert "No shut down was asked" in quick.run("shutdown-yes")
    assert calls == [1]


def test_it_knows_its_own_model_size_and_speed(monkeypatch):
    monkeypatch.setattr(forge_jan, "context_size", lambda name: 131072)
    assert localchat.size_of("Qwen3_5-2B-Uncensored-HauhauCS-Aggressive-Q4_K_M") == "2B"
    assert localchat.size_of("qwen35-0_8b-spectralquant-calib360-q4_k_m") == "0.8B"
    assert localchat.size_of("Qwen3_5-4B-IQ4_XS-long") == "4B"
    name = localchat.DEFAULT_MODEL
    localchat.record_speed(name, {"gen_tps": 11.6, "prompt_tps": 140.2})
    localchat.record_speed(name, {"gen_tps": None})  # a failed call keeps the last
    said = localchat.self_facts(name)
    assert "Qwen3.5 2B (2 billion parameters)" in said
    assert "131072 tokens" in said and "12 tokens/s writing" in said


def test_bare_command_lines_in_a_reply_are_dropped_not_run():
    reply, acts = localchat.parse(
        "It's warm, 71°C.\ntell 15:06 all good\n**ACTION**\nStop worrying, it is fine."
    )
    assert reply == "It's warm, 71°C.\nStop worrying, it is fine." and acts == []


def test_history_keeps_the_newest_within_its_budget():
    lines = "".join(
        f"- Wed 10:{i:02d} {'Emerson' if i % 2 == 0 else 'Local'}: m{i} "
        + "x" * 1400
        + "\n"
        for i in range(12)
    )
    turns = localchat.conversation({"body": "## Messages\n\n" + lines}, ["hi"], "f")
    history = "\n".join(t["content"] for t in turns[1:-1])
    assert len(history) <= localchat.HISTORY_CHARS + 20
    # 12 entries of ~1400 characters: the newest 8 fit in 12000
    assert "m11 " in history and "m4 " in history and "m3 " not in history
    assert [t["role"] for t in turns][-2:] == ["assistant", "user"]


@pytest.mark.parametrize(
    "text, name",
    [
        ("shut down", "shutdown"),
        ("shutdown the laptop", "shutdown"),
        ("turn off my pc", "shutdown"),
        ("yes shut down", "shutdown-yes"),
        ("power off cosmos", None),
        ("turn off the lights", None),
    ],
)
def test_shut_down_matches_only_the_whole_message(text, name):
    found = quick.match(text)
    assert (found[0] if found else None) == name
