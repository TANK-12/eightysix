"""`relay as-whatsapp`: a line Emerson types in Mission Control's WhatsApp
mirror is handled as if he had sent it on WhatsApp (Relay task 109)."""

import io
import sys

import bossline
import chat
import cli
import items
import store


def run(capsys, monkeypatch, *argv, stdin=""):
    monkeypatch.setattr(sys, "stdin", io.StringIO(stdin))
    cli.main(["as-whatsapp", *argv])
    return capsys.readouterr().out.strip()


def entries() -> list[str]:
    task = chat.chat_task(create=False)
    assert task is not None
    return chat._split(task["body"])[1]


def who(entry: str) -> str:
    return entry.removeprefix(chat.NEW).split(" ", 2)[2].split(":", 1)[0]


def flat(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def outbox() -> list:
    return [store.read_json(f) for f in chat.pending()]


def test_a_plain_line_goes_to_the_chat_once(capsys, monkeypatch):
    store.save_settings({"whatsapp_enabled": True})
    out = run(capsys, monkeypatch, "hi", "there")
    assert out.startswith("Sent")
    said = entries()
    assert len(said) == 1 and said[0].startswith(chat.NEW)
    assert said[0].endswith("Emerson: hi there")  # unread: the chat answers it
    task = chat.chat_task(create=False)
    assert task is not None and task["status"] == "queued"
    assert [e["text"] for e in outbox()] == ["From Mission Control: hi there"]


def test_a_command_is_answered_in_both_places(capsys, monkeypatch):
    store.save_settings({"whatsapp_enabled": True})
    out = run(capsys, monkeypatch, "status")
    said = entries()
    assert [who(e) for e in said] == ["Emerson", "Relay"]
    assert not said[0].startswith(chat.NEW)  # read: nobody answers it twice
    assert said[0].endswith("Emerson: status")
    assert flat(chat.message_text(said[1])) == flat(out)
    sent = [e["text"] for e in outbox()]
    assert sent == ["From Mission Control: status", out]  # in that order


def test_a_boss_line_goes_to_the_boss(capsys, monkeypatch):
    store.save_settings({"whatsapp_enabled": True})
    out = run(capsys, monkeypatch, stdin="boss: what is running?\n")
    assert out.startswith("Sent")
    assert bossline.take() == ["what is running?"]
    said = entries()
    assert len(said) == 1 and said[0].endswith("Emerson: boss: what is running?")
    assert not said[0].startswith(chat.NEW)


def test_whatsapp_off_logs_but_sends_nothing(capsys, monkeypatch):
    out = run(capsys, monkeypatch, "status")
    assert outbox() == []
    said = entries()
    assert [who(e) for e in said] == ["Emerson", "Relay"]
    assert flat(chat.message_text(said[1])) == flat(out)


def test_nothing_to_send(capsys, monkeypatch):
    assert run(capsys, monkeypatch, stdin="  \n") == "Nothing to send."
    assert chat.chat_task(create=False) is None


def test_a_line_like_the_dropped_oldest_one_shows_once(capsys, monkeypatch):
    # the log keeps its last KEEP_MESSAGES lines: when the line that drops
    # out says the same words, the new one is still logged once (critic C11)
    store.save_settings({"whatsapp_enabled": True})
    task = chat.chat_task()
    assert task is not None
    head, _, tail = chat._split(task.get("body", ""))
    old = ["Mon 10:00 Emerson: hi"] + [
        f"Mon 10:{n:02d} Relay: line {n}" for n in range(1, chat.KEEP_MESSAGES)
    ]
    task["body"] = chat._join(head, old, tail)
    items.save(task)
    run(capsys, monkeypatch, "hi")
    said = entries()
    assert len(said) == chat.KEEP_MESSAGES
    his = [e for e in said if e.removeprefix(chat.NEW).endswith("Emerson: hi")]
    assert his == [said[-1]]


def test_an_answer_with_whatsapp_off_still_reaches_the_chat_log():
    # Mission Control's mirror reads the log, so with WhatsApp off an answer
    # lands there all the same, and nothing is queued (critic C13)
    assert chat.chat_task() is not None
    out = chat.reply("all done")
    assert "off" in out
    assert outbox() == []
    assert entries()[-1].endswith("Relay: all done")
