"""The WhatsApp channel's pure parts, chat mode and the outbox. The live page
is checked by hand (WIP.md); these never open Whatsie."""

import time
from contextlib import contextmanager

import actions
import chat
import cli
import items
import prompts
import quick
import pytest
import runs
import store
from channels import whatsapp
from commands import parse
from test_boss import settle, task_, world  # noqa: F401  (world is a fixture)

ME = "🔨"


def msg(i, text, me=True):
    return {"id": f"ID{i}", "text": text, "me": me}


def wa(text, thread_task=""):
    return actions.apply(
        parse("", text, source="whatsapp"), "whatsapp", thread_task=thread_task
    )


@pytest.fixture
def notes(monkeypatch):
    """Crew board notes the code would post, instead of posting them."""
    sent: list = []
    monkeypatch.setattr(
        actions, "crew_note", lambda to, text: sent.append((to, text)) or True
    )
    return sent


# ---- reading the page ------------------------------------------------------------


def test_first_look_only_remembers():
    state: dict = {}
    assert whatsapp.pick_new([msg(1, "old request")], state) == []
    assert state["wa_seen"] == ["ID1"]


def test_only_emersons_new_messages_and_never_relays_own():
    state = {"wa_seen": ["ID1"]}
    found = [
        msg(1, "old"),
        msg(2, "fix the cosmos orbit bug"),
        msg(3, "hello from the business", me=False),
        msg(4, f"{ME} #5 Done: something"),
        msg(5, ""),
    ]
    new = whatsapp.pick_new(found, state)
    assert [m.text for m in new] == ["fix the cosmos orbit bug"]
    assert new[0].trusted and new[0].channel == "whatsapp"
    assert whatsapp.pick_new(found, state) == []


def test_hash_number_points_at_a_task():
    incoming = whatsapp.to_incoming(msg(9, "#12 also do the tests"))
    assert incoming.in_reply_to == "#12" and incoming.text == "also do the tests"


# ---- phone-friendly text -----------------------------------------------------------


def test_compose_marks_tags_and_splits_without_cutting():
    assert whatsapp.compose("Done: x", "body", "#4") == [f"{ME} #4 *Done: x*\nbody"]
    assert whatsapp.compose("Re: x", "short", "")[0].startswith(f"{ME} short")
    words = " ".join(f"word{i}" for i in range(400))  # about 3000 characters
    parts = whatsapp.compose("", words, settings={"whatsapp_part_chars": 900})
    assert len(parts) == 4 and all(len(p) <= 903 for p in parts)
    assert all(p.startswith(ME) for p in parts)
    assert "…" not in "".join(parts)
    rejoined = " ".join(p.removeprefix(ME).strip() for p in parts)
    assert rejoined == words  # split at spaces, nothing lost
    many = whatsapp.compose("", words * 3, settings={"whatsapp_max_parts": 2})
    assert len(many) == 2 and many[-1].endswith("ask me for the rest.)")


def test_phone_drops_code_and_shell_commands():
    text = (
        "Fixed it.\n```\npython3 -m pytest -q\n```\n$ systemctl --user restart x\n"
        "Ran `pytest` and `cd ~/Forge/apps/relay && .venv/bin/python -m pytest -q`."
    )
    out = chat.phone(text)
    assert "systemctl" not in out and "```" not in out and "-q" not in out
    assert "Fixed it." in out and "(code left out)" in out and "Ran pytest and" in out
    assert "systemctl" not in actions.status_text()


def test_long_titles_are_cut_at_a_word_without_dots():
    line = "make the WhatsApp agent a bit dumber or auto compact after a bit so that it can spawn"
    title = parse("", line, source="cli").title
    assert "…" not in title and len(title) <= 80 and line.startswith(title)
    assert title.endswith("so that it can")


def test_whatsapp_help_is_short():
    reply, _ = wa("help")
    assert reply == quick.command_list() and len(reply) < 1500


def test_notify_levels():
    mine = {"source": "whatsapp"}
    other = {"source": "mail"}
    s = {"whatsapp_notify": "mine"}
    assert whatsapp.wants(s, "Done: a", mine)
    assert not whatsapp.wants(s, "Done: a", other)
    assert not whatsapp.wants(s, "Started: a", mine)
    assert not whatsapp.wants(s, "Relay digest 2026-10-06", None)
    assert whatsapp.wants(s, "Task 3 needs you: a", other)
    assert whatsapp.wants(s, "Parked: a", other)
    assert not whatsapp.wants({"whatsapp_notify": "quiet"}, "Done: a", mine)
    assert whatsapp.wants({"whatsapp_notify": "all"}, "Relay digest", None)


# ---- commands -------------------------------------------------------------------


def test_commands_parse():
    assert parse("", "progress", source="whatsapp").kind == "progress"
    cmd = parse("", "progress 12", source="whatsapp")
    assert (cmd.kind, cmd.number) == ("progress", 12)
    assert parse("", "usage", source="whatsapp").kind == "usage"
    cmd = parse("", "notify quiet", source="whatsapp")
    assert (cmd.kind, cmd.text) == ("notify", "quiet")
    cmd = parse("", "say @Kaito hold the GPU", source="whatsapp")
    assert (cmd.kind, cmd.title, cmd.text) == ("say", "Kaito", "hold the GPU")
    assert (
        parse("", "I'm trying to chat with you say hi", source="whatsapp").kind
        == "chat"
    )
    assert parse("", "fix the bug", source="cli").kind == "task"  # unchanged elsewhere
    cmd = parse("", "new: fix the orbit bug\neffort: xhigh", source="cli")
    assert (cmd.kind, cmd.text, cmd.options["effort"]) == (
        "work",
        "fix the orbit bug",
        "xhigh",
    )


def test_whatsapp_may_not_set_a_shell_check():
    cmd = parse("", "goal: x\ncheck: rm -rf ~\nbody", source="whatsapp")
    assert "check" not in cmd.options


def test_notify_from_whatsapp():
    wa("notify all")
    assert store.settings()["whatsapp_notify"] == "all"


# ---- the chat ---------------------------------------------------------------------


def test_plain_messages_go_to_one_chat_task(notes):
    reply, made = wa("Give me a paragraph or something")
    assert reply == "" and made is None  # the chat answers, not the boss
    chat_id = store.settings()["whatsapp_chat_task"]
    task = task_(chat_id)
    assert chat.is_chat(task) and task["status"] == "queued"
    wa("I'm trying to chat with you say hi")
    assert [str(t["id"]) for t in items.all_tasks()] == [str(chat_id)]  # still one task
    assert [m.split(" Emerson: ")[1] for m in chat.new_messages(task_(chat_id))] == [
        "Give me a paragraph or something",
        "I'm trying to chat with you say hi",
    ]
    assert notes == []
    task = task_(chat_id)
    task["status"] = "running"
    items.save(task)
    wa("are you there")
    assert notes and notes[0][0] == f"relay-{chat_id}-chat"
    assert "relay inbox" in notes[0][1]
    assert task_(chat_id)["status"] == "running"


def test_inbox_takes_new_messages_once():
    chat.route("one")
    chat.route("two\nsecond line")
    out = chat.inbox()
    assert "Emerson: one" in out and "second line" in out
    assert chat.inbox() == "No new messages."
    body = task_(store.settings()["whatsapp_chat_task"])["body"]
    assert "[new]" not in body and "Emerson: one" in body  # kept as history


def test_messages_section_keeps_the_last_forty():
    for i in range(50):
        chat.route(f"m{i}")
    task = task_(store.settings()["whatsapp_chat_task"])
    messages = chat.new_messages(task)
    assert len(messages) == chat.KEEP_MESSAGES and messages[-1].endswith("m49")
    assert task["body"].rstrip().endswith("- status: not started")


def test_chat_model_switch_clears_resume():
    task = chat.chat_task()
    assert task is not None
    task["resume_ok"] = "yes"
    items.save(task)
    assert "now runs on opus at high" in chat.set_model("opus", "high")
    s = store.settings()
    assert (s["whatsapp_chat_model"], s["whatsapp_chat_effort"]) == ("opus", "high")
    assert task_(task["id"])["resume_ok"] == ""
    assert "must be" in chat.set_model("gpt")


def test_the_light_chat_is_haiku_5_5_never_4_5():
    # the default, a step down by name, and a setting saved as haiku
    assert chat.chat_model(store.settings()) == ("haiku", "low")
    for down, effort in (("haiku", ""), ("Haiku", ""), ("light", "max")) + (
        ("down", "high"),
        ("default", ""),
    ):
        assert "now runs on haiku at low" in chat.set_model(down, effort)
        s = store.settings()
        assert (s["whatsapp_chat_model"], s["whatsapp_chat_effort"]) == (
            "haiku",
            "low",
        )
    store.save_settings(
        {"whatsapp_chat_model": "haiku", "whatsapp_chat_effort": "high"}
    )
    assert chat.chat_model(store.settings()) == ("haiku", "high")
    # haiku at a chosen effort keeps it (critic, task 99)
    chat.set_model("haiku", "medium")
    assert chat.chat_model(store.settings()) == ("haiku", "medium")
    # "haiku" always launches as the 5.5 id (Claude Code's alias is 4.5)
    assert store.model_id("haiku") == "claude-haiku-5-5"
    assert store.model_id("Haiku") == "claude-haiku-5-5"
    assert store.model_id("opus") == "opus" and store.model_id("") == ""
    # sonnet low is still there by name
    chat.set_model("sonnet", "low")
    assert chat.chat_model(store.settings()) == ("sonnet", "low")
    # the step-ups still work
    chat.set_model("sonnet", "medium")
    assert chat.chat_model(store.settings()) == ("sonnet", "medium")
    chat.set_model("opus", "high")
    assert chat.chat_model(store.settings()) == ("opus", "high")
    # the chat prompt steps down to the light chat
    assert "relay chat-model haiku" in prompts.CHAT_RULES


# ---- the work task ------------------------------------------------------------------


def test_work_task_is_one_at_a_time(notes):
    reply, task = wa("new: fix the orbit bug")
    assert task is not None and task["source"] == "whatsapp"
    assert (task["model"], task["effort"]) == ("opus", "high")
    assert store.settings()["whatsapp_work_task"] == task["id"]
    assert f"Work task {task['id']}" in reply and "…" not in reply
    reply, made = wa("new: and the tests")
    assert made is None and "Added to work task" in reply
    assert "Added later by Emerson" in task_(task["id"])["body"]
    assert "and the tests" in task_(task["id"])["body"]
    running = task_(task["id"])
    running["status"] = "running"
    items.save(running)
    reply, made = wa("task: also the docs")  # task: from WhatsApp is work too
    assert made is None and notes[-1][0] == f"relay-{task['id']}-work"
    running["status"] = "done"
    items.save(running)
    _, second = wa("new: next job\neffort: medium")
    assert second and second["id"] != task["id"] and second["effort"] == "medium"
    assert len([t for t in items.all_tasks() if not chat.is_chat(t)]) == 2


def test_chat_session_starts_work_from_the_terminal(capsys):
    cli.main(["new: rewrite the README\neffort: xhigh"])
    task = items.find_task(store.settings()["whatsapp_work_task"])
    assert task and task["source"] == "whatsapp" and task["effort"] == "xhigh"
    assert "Work task" in capsys.readouterr().out


def test_hash_reply_to_a_running_task_is_told(monkeypatch):
    _, task = wa("new: long job")
    assert task is not None
    task["status"] = "running"
    items.save(task)
    told = []
    monkeypatch.setattr(actions, "tell_task", lambda n, t: told.append((n, t)) or "ok")
    reply, made = wa("also this", thread_task=str(task["id"]))
    assert made is None and told == [(str(task["id"]), "also this")]


def test_hash_reply_to_a_finished_task_becomes_work():
    old = items.new_task("old job", "x", status="done")
    old["status"] = "done"
    items.save(old)
    _, task = wa("redo the last bit", thread_task=str(old["id"]))
    assert task and task["follow_of"] == str(old["id"])
    assert store.settings()["whatsapp_work_task"] == task["id"]


def test_read_more_is_clicked_before_messages_are_read(monkeypatch):
    monkeypatch.setattr(whatsapp.time, "sleep", lambda s: None)
    order, left = [], [2, 1, 0]

    class Page:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def js(self, script):
            if script == whatsapp.READ_MORE:
                order.append("more")
                return left.pop(0)
            order.append("read")
            return [{"id": "a", "me": True, "text": "the full text"}]

    monkeypatch.setattr(whatsapp, "page", lambda settings: Page())
    monkeypatch.setattr(whatsapp, "open_chat", lambda p, name: None)
    assert whatsapp.messages({"whatsapp_chat": "me"})[0]["text"] == "the full text"
    assert order == ["more", "more", "more", "read"]


# ---- the outbox ---------------------------------------------------------------------


def test_reply_and_files_go_through_the_outbox(tmp_path, capsys):
    store.save_settings(
        {"whatsapp_enabled": True, "whatsapp_files_dir": str(tmp_path / "out")}
    )
    chat.chat_task()
    cli.main(["reply", "hi", "there"])
    assert "Queued" in capsys.readouterr().out
    picture = tmp_path / "shot.png"
    picture.write_bytes(b"png")
    assert "Queued shot.png" in chat.send_file(str(picture), "the shot")
    assert chat.send_file(str(tmp_path / "nope.png")).startswith("No file")
    cli.main(["unsend", "2"])
    sent = []
    assert chat.flush(sent.append) == 3
    assert [e["kind"] for e in sent] == ["text", "file", "delete"]
    assert sent[0]["text"] == "hi there" and sent[2]["count"] == 2
    assert sent[1]["path"].startswith(str(tmp_path / "out"))
    assert chat.pending() == []
    assert "Relay: hi there" in task_(store.settings()["whatsapp_chat_task"])["body"]


def test_outbox_keeps_order_retries_then_gives_up():
    store.save_settings({"whatsapp_enabled": True})
    chat.reply("first")
    chat.reply("second")

    def broken(entry):
        raise ConnectionError("Whatsie is not up")

    def later():  # as if the retry wait has passed
        for file in chat.pending():
            entry = store.read_json(file) or {}
            entry.pop("next_at", None)
            store.write_json(file, entry)

    assert chat.flush(broken) == 0
    assert chat.flush(broken) == 0 and chat.pending()  # too soon: not tried
    assert (store.read_json(chat.pending()[0]) or {})["tries"] == 1
    for _ in range(3):
        later()
        assert chat.flush(broken) == 0
    assert len(chat.pending()) == 2  # nothing skipped ahead of "first"
    later()
    chat.flush(broken)
    assert len(chat.pending()) == 1
    assert len(list((chat.outbox_dir() / "failed").glob("*.json"))) == 1
    sent = []
    chat.flush(sent.append)
    assert [e["text"] for e in sent] == ["second"]


def test_pictures_go_as_media_and_the_rest_as_documents():
    assert whatsapp.attach_kind("/x/shot.PNG") == "Photos & videos"
    assert whatsapp.attach_kind("/x/clip.mp4") == "Photos & videos"
    assert whatsapp.attach_kind("/x/notes.txt") == "Document"
    assert whatsapp.attach_kind("/x/README") == "Document"


def test_sent_files_are_remembered_outside_the_outbox():
    for i in range(205):
        chat.remember_sent(f"id{i}")
    chat.remember_sent("id3")  # already gone from the last 200: added again
    chat.remember_sent("")
    ids = chat.sent_files()
    assert len(ids) == 200 and ids[-1] == "id3" and ids.count("id3") == 1
    # The boss sends every .json in the outbox: the list must not be one.
    assert chat.pending() == []
    assert '["id' in whatsapp.own_last(2) and "slice(-2)" in whatsapp.own_last(2)


def test_unsend_stops_at_a_failure_without_deleting_more(monkeypatch):
    class Page:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def js(self, script):
            return ["a", "b", "c"]

    done = []

    def delete_one(p, mid):
        if mid == "b":
            raise LookupError("no delete dialog")
        done.append(mid)
        return 1

    monkeypatch.setattr(whatsapp, "page", lambda s: Page())
    monkeypatch.setattr(whatsapp, "open_chat", lambda p, c: None)
    monkeypatch.setattr(whatsapp, "delete_one", delete_one)
    settings = {"whatsapp_chat": "Indeed"}
    # Newest first; "b" fails after "c" went: done, so a retry deletes nothing older.
    assert whatsapp.delete_last(settings, 3) == 1 and done == ["c"]
    with pytest.raises(LookupError):
        whatsapp.delete_last(settings, ids=["b"])


def test_reply_needs_whatsapp_on():
    assert "off" in chat.reply("hi")
    assert chat.pending() == []


# ---- the boss and the chat session -----------------------------------------------------


def argv_value(call, flag):
    argv = call["argv"]
    return argv[argv.index(flag) + 1] if flag in argv else None


def test_chat_session_runs_idles_resumes_and_steps_up(world):
    store.save_settings({"whatsapp_enabled": True, "paused": True})
    chat.route("does the boss use usage?")
    settle(world)
    chat_id = store.settings()["whatsapp_chat_task"]
    task = task_(chat_id)
    assert task["status"] == chat.IDLE  # not done, not parked
    first = world.calls()[0]
    assert argv_value(first, "--model") == "claude-haiku-5-5"  # never the alias
    assert argv_value(first, "--effort") == "low"
    assert "--resume" not in first["argv"]
    assert "does the boss use usage?" in first["prompt"]
    assert "relay reply" in first["prompt"]
    assert chat.new_messages(task) == []  # handed to the session
    # it never ran relay reply, so its last words go out instead
    assert [(store.read_json(f) or {})["text"] for f in chat.pending()] == [
        "Report: done"
    ]
    assert not world.mail.sent  # nothing by mail for the chat

    chat.route("and what about haiku")
    settle(world)
    second = world.calls(2)[1]
    assert "--resume" in second["argv"] and "and what about haiku" in second["prompt"]

    chat.set_model("opus", "high")
    chat.route("think harder about it")
    settle(world)
    third = world.calls(3)[2]
    assert argv_value(third, "--model") == "opus" and "--resume" not in third["argv"]
    assert "think harder about it" in third["prompt"]
    assert task_(chat_id)["status"] == chat.IDLE


def test_a_big_chat_starts_fresh(world, monkeypatch):
    store.save_settings({"whatsapp_enabled": True, "whatsapp_chat_context_k": 10})
    chat.route("hello")
    settle(world)
    assert task_(store.settings()["whatsapp_chat_task"])["resume_ok"] == ""
    chat.route("again")
    settle(world)
    assert "--resume" not in world.calls(2)[1]["argv"]


def test_chat_does_not_take_a_work_slot(world):
    store.save_settings({"whatsapp_enabled": True, "max_sessions": 1})
    items.new_task("Work", "FAKE:sleep")
    world.boss.tick()
    chat.route("hi while you work")
    world.boss.tick()
    kinds = sorted(r["kind"] for r in runs.active())
    assert kinds == ["chat", "work"]
    for run in runs.active():
        runs.stop(run)


def test_boss_sends_no_ack_for_chat(world, monkeypatch):
    from channels import Incoming

    sent = []

    class Channel:
        def send(self, *a, **k):
            sent.append(a)
            return ""

    store.save_settings({"whatsapp_enabled": True})
    world.boss.handle(
        Incoming("whatsapp", "me", "", "just saying hi", "wa:1", trusted=True),
        Channel(),
    )
    assert sent == [] and chat.new_messages(chat.chat_task() or {})


def test_hung_whatsie_is_stopped_after_a_while(monkeypatch):
    calls = []
    clock = [1000.0]

    def refuse(port, url):
        raise TimeoutError("timed out")

    monkeypatch.setattr(whatsapp.cdp, "open_page", refuse)
    monkeypatch.setattr(whatsapp.time, "time", lambda: clock[0])
    monkeypatch.setattr(whatsapp, "start_whatsie", lambda s: calls.append("start"))
    monkeypatch.setattr(whatsapp, "stop_whatsie", lambda s: calls.append("stop"))
    monkeypatch.setitem(whatsapp._down, "since", 0.0)
    for step in (0, 100, 200):
        clock[0] = 1000.0 + step
        with pytest.raises(ConnectionError):
            whatsapp.page({})
    assert "stop" not in calls
    clock[0] = 1000.0 + whatsapp.HUNG_AFTER + 1
    with pytest.raises(ConnectionError):
        whatsapp.page({})
    assert calls.count("stop") == 1


def test_numbered_counts_up_with_a_day_sign_and_survives_restart():
    wed = time.mktime((2026, 10, 7, 9, 0, 0, 0, 0, -1))  # a Wednesday
    assert whatsapp.numbered(f"{ME} hello", wed) == "1 ◆ hello"
    assert whatsapp.numbered("no mark", wed + 86400) == "2 ■ no mark"
    # the count is on disk, so a fresh process carries on from it
    assert store.read_json(store.path("whatsapp_count.json")) == {"next": 3}
    signs = {whatsapp.numbered("x", wed + d * 86400).split()[1] for d in range(7)}
    assert signs == set(whatsapp.DAY_SIGNS)


def test_send_numbers_every_part(monkeypatch):
    typed = []
    seen = iter([[], [{"id": "a"}]])

    class FakePage:
        def js(self, expr):
            return next(seen)

    @contextmanager
    def fake_page(settings):
        yield FakePage()

    monkeypatch.setattr(whatsapp, "page", fake_page)
    monkeypatch.setattr(whatsapp, "open_chat", lambda p, chat: None)
    monkeypatch.setattr(whatsapp, "type_message", lambda p, text: typed.append(text))
    assert whatsapp.send({"whatsapp_chat": "me"}, "", "first") == "wa:a"
    assert typed[0].split()[0] == "1" and ME not in typed[0]
    assert typed[0].endswith("first")


def test_several_files_queue_as_one_lot(tmp_path, capsys):
    store.save_settings(
        {"whatsapp_enabled": True, "whatsapp_files_dir": str(tmp_path / "out")}
    )
    files = []
    for name in ("a.png", "b.mp4", "c.pdf"):
        f = tmp_path / name
        f.write_bytes(b"x")
        files.append(str(f))
    cli.main(["send-file", *files, "three", "things"])
    assert "Queued a.png, b.mp4, c.pdf" in capsys.readouterr().out
    sent = []
    assert chat.flush(sent.append) == 1
    assert sent[0]["names"] == ["a.png", "b.mp4", "c.pdf"]
    assert len(set(sent[0]["paths"])) == 3 and sent[0]["caption"] == "three things"
    assert chat.send_files([files[0], str(tmp_path / "nope")]).startswith("No file")
    assert chat.pending() == []


def test_send_files_uses_one_tray_per_kind_and_one_caption(monkeypatch):
    trays, typed = [], []

    @contextmanager
    def fake_page(settings):
        yield object()

    monkeypatch.setattr(whatsapp, "page", fake_page)
    monkeypatch.setattr(whatsapp, "open_chat", lambda p, c: None)
    monkeypatch.setattr(whatsapp, "send_tray", lambda p, paths: trays.append(paths))
    monkeypatch.setattr(whatsapp, "type_message", lambda p, text: typed.append(text))
    whatsapp.send_files(
        {"whatsapp_chat": "me"},
        ["/x/1.png", "/x/2.jpg", "/x/3.pdf"],
        "look",
        ["one.png", "two.jpg", "three.pdf"],
    )
    assert trays == [["/x/1.png", "/x/2.jpg"], ["/x/3.pdf"]]
    assert len(typed) == 1 and typed[0].endswith(
        "look\n1. one.png\n2. two.jpg\n3. three.pdf"
    )
    # The single-file form with no caption types nothing; an old entry has "path" only.
    trays.clear(), typed.clear()
    monkeypatch.setattr(whatsapp, "send_tray", lambda p, paths: trays.append(paths))
    whatsapp.deliver({"whatsapp_chat": "me"}, {"kind": "file", "path": "/x/1.png"})
    assert trays == [["/x/1.png"]] and typed == []


def test_send_tray_sets_every_file_in_one_call(monkeypatch):
    calls = []

    class P:
        def js(self, script):
            return []

        def call(self, method, **kw):
            calls.append((method, kw))
            return {"result": {"objectId": "n1"}}

    monkeypatch.setattr(whatsapp, "js_click", lambda p, s: True)
    monkeypatch.setattr(whatsapp, "click", lambda p, s: True)
    monkeypatch.setattr(whatsapp, "wait_for", lambda p, e, t=0: True)
    whatsapp.send_tray(P(), ["/x/1.png", "/x/2.png"])
    sets = [kw for m, kw in calls if m == "DOM.setFileInputFiles"]
    assert sets == [{"files": ["/x/1.png", "/x/2.png"], "objectId": "n1"}]


def test_own_messages_are_told_by_number_and_day_sign():
    assert whatsapp.is_own("12 ◆ hello") and whatsapp.is_own(f"{ME} old style")
    assert not whatsapp.is_own("12 hello") and not whatsapp.is_own("fix it")
    assert '"^\\\\d+' in whatsapp.own_last(1) or "RegExp" in whatsapp.own_last(1)


def test_an_empty_read_marks_nothing_seen():
    state: dict = {}
    assert whatsapp.pick_new([], state) == [] and "wa_seen" not in state
    whatsapp.pick_new([{"id": "a", "me": True, "text": "old"}], state)
    assert whatsapp.pick_new([], state) == [] and state["wa_seen"] == ["a"]


def test_messages_waits_for_rows_to_show(monkeypatch):
    reads = [
        [{"id": "a", "text": "", "shown": False}],
        [{"id": "a", "text": "hi", "shown": True}],
    ]

    class Page:
        def js(self, _):
            return reads.pop(0) if len(reads) > 1 else reads[0]

    @contextmanager
    def fake_page(_):
        yield Page()

    monkeypatch.setattr(whatsapp, "page", fake_page)
    monkeypatch.setattr(whatsapp, "open_chat", lambda p, c: None)
    monkeypatch.setattr(whatsapp, "expand", lambda p: 0)
    monkeypatch.setattr(whatsapp.time, "sleep", lambda s: None)
    assert whatsapp.messages({"whatsapp_chat": "Indeed"})[0]["text"] == "hi"


def test_a_message_written_offline_still_counts():
    state: dict = {}
    seen = [
        {"id": "a", "me": True, "text": "old", "pre": "[7:20 pm, 07/10/2026] E: "},
        {
            "id": "b",
            "me": True,
            "text": "84 ◆ relay",
            "pre": "[7:30 pm, 07/10/2026] E: ",
        },
    ]
    whatsapp.pick_new(seen, state)
    late = {
        "id": "c",
        "me": True,
        "text": "do the thing",
        "pre": "[7:25 pm, 07/10/2026] E: ",
    }
    got = whatsapp.pick_new(seen + [late], state)
    assert [m.text for m in got] == ["do the thing"]
