"""The Jan front desk (frontdesk.py) with a fake Jan: answers, hand-offs,
failure fallback, and the waiting-for-usage line. Live Jan is checked with
`frontdesk.py --samples` (WIP.md)."""

import json
import time
from pathlib import Path

import boss as boss_mod
import chat
import frontdesk
import items
import store
from test_boss import task_, world  # noqa: F401  (world is a fixture)


def desk_on():
    store.save_settings({"whatsapp_enabled": True, "whatsapp_frontdesk": "jan"})


def run(desk):
    """Step until the desk is idle and its last answer applied."""
    out = []
    for _ in range(20):
        out.append(desk.step(store.settings()))
        if desk.thread:
            desk.thread.join(5)
        if not desk.busy() and desk.result is None:
            task = chat.chat_task(create=False) or {}
            if task.get("status") != frontdesk.DESK:
                return out
    return out


def outbox():
    return [str((store.read_json(f) or {}).get("text") or "") for f in chat.pending()]


def test_parse_answer_and_handoffs():
    assert frontdesk.parse("Hey mate!") == ("Hey mate!", "", "")
    assert frontdesk.parse("Passing this on.\nHANDOFF chat: he wants Claude") == (
        "Passing this on.",
        "chat",
        "he wants Claude",
    )
    reply, kind, note = frontdesk.parse(
        "On it.\n**HANDOFF work:** fix the orbit flicker in Cosmos\nDone when it is smooth"
    )
    assert (reply, kind) == ("On it.", "work")
    assert note == "fix the orbit flicker in Cosmos Done when it is smooth"


def test_route_goes_to_the_desk_only_when_on():
    store.save_settings({"whatsapp_enabled": True})
    task, running = chat.route("hi")
    assert task_(task["id"])["status"] == "queued" and not running
    desk_on()
    task_file = task_(task["id"])
    task_file["status"] = chat.IDLE
    items.save(task_file)
    chat.route("hi again")
    assert task_(task["id"])["status"] == frontdesk.DESK


def test_jan_answers_itself():
    desk_on()
    seen = []
    desk = frontdesk.Desk(lambda task, msgs: seen.append(msgs) or "All quiet, mate.")
    task, _ = chat.route("whats running")
    run(desk)
    task = task_(task["id"])
    assert seen == [[seen[0][0]]] and "whats running" in seen[0][0]
    assert task["status"] == chat.IDLE
    assert chat.new_messages(task) == []
    assert outbox() == ["All quiet, mate."]
    assert "Jan: All quiet, mate." in task["body"]


def test_jan_hands_over_to_the_claude_chat():
    desk_on()
    desk = frontdesk.Desk(
        lambda t, m: "Passing this to Claude.\nHANDOFF chat: needs files"
    )
    task, _ = chat.route("look at my calc worksheet")
    run(desk)
    task = task_(task["id"])
    assert task["status"] == "queued"
    new = chat.new_messages(task)
    assert any("look at my calc worksheet" in m for m in new)
    assert any("Jan handed over: needs files" in m for m in new)
    assert outbox() == ["Passing this to Claude."]


def test_jan_starts_work():
    desk_on()
    desk = frontdesk.Desk(
        lambda t, m: "On it.\nHANDOFF work: add dark mode to NovelForge"
    )
    task, _ = chat.route("add a dark mode to novelforge")
    run(desk)
    work = task_(store.settings()["whatsapp_work_task"])
    assert "add dark mode to NovelForge" in work["body"]
    assert work["status"] == "queued" and work.get("model") == "opus"
    sent = outbox()
    assert sent[0] == "On it." and sent[1].startswith(f"Work task {work['id']} queued")
    assert task_(task["id"])["status"] == chat.IDLE


def test_jan_failure_falls_back_to_claude_and_is_skipped_a_while():
    desk_on()
    calls = []

    def broken(t, m):
        calls.append(m)
        raise frontdesk.forge_jan.JanError("Jan is not answering")

    desk = frontdesk.Desk(broken)
    task, _ = chat.route("hello?")
    run(desk)
    assert task_(task["id"])["status"] == "queued" and len(calls) == 1
    t = task_(task["id"])
    t["status"] = chat.IDLE
    items.save(t)
    chat.route("still there?")
    run(desk)
    assert len(calls) == 1  # skipped: straight to Claude
    assert task_(task["id"])["status"] == "queued"


def test_messages_during_a_claude_wait_go_back_to_jan():
    desk_on()
    task, _ = chat.route("first")
    t = task_(task["id"])
    t["status"] = "queued"
    items.save(t)
    chat.route("second, while queued")
    assert task_(task["id"])["status"] == "queued"  # Claude is about to start
    store.save_state({**store.state(), "chat_wait": "no account has room"})
    chat.route("third, Claude is out of usage")
    assert task_(task["id"])["status"] == frontdesk.DESK


def test_jan_gets_facts_and_the_talk_so_far():
    desk_on()
    task, _ = chat.route("one")
    chat.mark_read(task, chat.new_messages(task_(task["id"])))
    chat.log_reply("hi there", who="Jan")
    chat.route("two")
    task = task_(task["id"])
    prompt = frontdesk.user_prompt(task, chat.new_messages(task))
    assert "Facts:" in prompt and "Usage:" in prompt
    assert "Jan: hi there" in prompt.split("New from Emerson")[0]
    assert "two" in prompt.split("New from Emerson")[1]
    assert "HANDOFF work" in frontdesk.system_prompt()


def test_waiting_text_says_when_usage_returns():
    soon = time.time() + 3600
    iso = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(soon))
    text = boss_mod.waiting_text(
        {"a": {"five": 99, "week": 10, "resets": iso}, "b": {"five": 1, "week": 99}}
    )
    assert time.strftime("%H:%M", time.localtime(soon)) in text
    assert "out of usage" in text
    assert "about" not in boss_mod.waiting_text({"a": {"five": 99, "resets": None}})


def test_a_claude_handoff_without_usage_says_so_once(world):
    store.save_settings({"whatsapp_enabled": True})
    world.readings["a"]["five"] = 99
    world.readings["b"]["five"] = 99
    chat.route("needs claude")
    world.boss.tick()
    world.boss.tick()
    texts = outbox()
    assert len(texts) == 1 and "out of usage" in texts[0]


def test_sample_set_is_well_formed():
    data = json.loads(
        (Path(__file__).parent / "frontdesk_samples.json").read_text(encoding="utf-8")
    )
    wants = {s["want"] for s in data["samples"]}
    assert wants == {"answer", "chat", "work"} and len(data["samples"]) >= 12
