"""The conversation view's backend: transcript lines as the Claude app's
events (mc/convo.py), the reply box (actions.say), Ask Jan, and messages with
the answers that come back (mc/replies.py)."""

from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient

from conftest import SIDS, write_jsonl

H = {"X-Mission": "1"}


@pytest.fixture
def client(laptop, monkeypatch):
    import web_app
    from mc import actions

    monkeypatch.setattr(web_app, "_sources", lambda: laptop["src"])
    monkeypatch.setattr(actions, "claude_names", lambda: {})
    return TestClient(web_app.app)


# --- transcript lines -> events ---------------------------------------------


def ev(entry):
    from mc import convo

    return convo.events(entry)


def test_prompts_commands_reminders_and_interrupts():
    assert ev({"type": "user", "timestamp": "T", "message": {"content": "hi"}}) == [
        {"type": "forge_user", "text": "hi", "at": "T"}
    ]
    cmd = "<command-name>/model</command-name><command-args>opus</command-args>"
    assert ev({"type": "user", "message": {"content": cmd}})[0]["text"] == "/model opus"
    only_reminder = "<system-reminder>secret</system-reminder>"
    assert ev({"type": "user", "message": {"content": only_reminder}}) == []
    assert ev({"type": "user", "isMeta": True, "message": {"content": "meta"}}) == []
    got = ev({"type": "user", "message": {"content": "[Request interrupted by user]"}})
    assert got[0]["type"] == "forge_sys"
    assert ev({"type": "user", "isSidechain": True, "message": {"content": "x"}}) == []
    pic = {"type": "image", "source": {"data": "AAAA"}}
    got = ev(
        {
            "type": "user",
            "message": {"content": [{"type": "text", "text": "look"}, pic]},
        }
    )
    assert got[0]["text"] == "look\n[1 image]"


def test_assistant_blocks_are_trimmed_and_thinking_kept():
    from mc import convo

    long_input = {"file_path": "/a", "content": "x" * (convo.INPUT_CHARS + 500)}
    got = ev(
        {
            "type": "assistant",
            "timestamp": "T",
            "message": {
                "id": "m1",
                "model": "claude-opus-5-5",
                "content": [
                    {"type": "thinking", "thinking": "hmm", "signature": "s" * 900},
                    {"type": "text", "text": "Done."},
                    {
                        "type": "tool_use",
                        "id": "t1",
                        "name": "Write",
                        "input": long_input,
                    },
                ],
            },
        }
    )
    assert len(got) == 1 and got[0]["type"] == "assistant"
    blocks = got[0]["message"]["content"]
    assert blocks[0] == {"type": "thinking", "thinking": "hmm"}  # no signature
    assert blocks[1]["text"] == "Done."
    assert len(blocks[2]["input"]["content"]) < convo.INPUT_CHARS + 10
    err = ev(
        {
            "type": "assistant",
            "isApiErrorMessage": True,
            "message": {"content": [{"type": "text", "text": "API Error: 529"}]},
        }
    )
    assert err[0]["type"] == "forge_sys" and err[0]["tone"] == "bad"


def test_signature_only_thinking_is_dropped():
    from mc import convo

    got = ev(
        {
            "type": "assistant",
            "message": {
                "id": "m2",
                "content": [
                    {"type": "thinking", "thinking": "", "signature": "s" * 50},
                    {"type": "tool_use", "id": "t9", "name": "Bash", "input": {}},
                ],
            },
        }
    )
    assert [b["type"] for b in got[0]["message"]["content"]] == ["tool_use"]


def test_tool_results_cut_text_and_drop_big_images():
    from mc import convo

    big = {"type": "image", "source": {"data": "A" * (convo.IMAGE_B64_MAX + 4)}}
    small = {"type": "image", "source": {"type": "base64", "data": "AAAA"}}
    got = ev(
        {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "t1",
                        "content": [{"type": "text", "text": "y" * 9000}, big, small],
                    },
                    {
                        "type": "tool_result",
                        "tool_use_id": "t2",
                        "content": "ok",
                        "is_error": True,
                    },
                ]
            },
        }
    )
    results = got[0]["message"]["content"]
    first = results[0]["content"]
    assert len(first[0]["text"]) < 4100
    assert first[1]["type"] == "text" and "KB image" in first[1]["text"]
    assert first[2] == small
    assert results[1]["is_error"] is True and results[1]["content"] == "ok"


def test_board_notes_from_emerson_become_messages():
    hook = (
        "Crew board 'forge':\n#12 Kaito (ejb-ab) -> everyone: not Emerson\n"
        "#13 Emerson -> ejb-busy: Emerson asks (answer him): which colour? (2m ago)\n"
    )
    got = ev(
        {
            "type": "attachment",
            "timestamp": "T",
            "attachment": {"type": "hook_additional_context", "content": [hook]},
        }
    )
    assert got == [
        {
            "type": "forge_user",
            "text": "Emerson asks (answer him): which colour?",
            "via": "board note #13 from Emerson",
            "note": 13,
            "at": "T",
        }
    ]
    queued = {
        "type": "attachment",
        "attachment": {
            "type": "queued_command",
            "prompt": [{"type": "text", "text": "also this"}],
        },
    }
    assert ev(queued)[0]["during_turn"] is True
    compact = {
        "type": "system",
        "subtype": "compact_boundary",
        "compactMetadata": {"pre_tokens": 9},
    }
    assert ev(compact)[0]["compact_metadata"] == {"pre_tokens": 9}


NOTIFY = (
    "<task-notification>\n<task-id>a1</task-id>\n<status>completed</status>\n"
    '<summary>Agent "Critic 5" finished</summary>\n<result>a long report</result>\n'
    "</task-notification>"
)


def test_a_helpers_report_is_a_grey_line_not_emersons_words():
    # Claude Code hands a finished helper's report over as if typed: it is
    # not Emerson talking, so no pink bubble full of tags (Relay task 109)
    want = [{"type": "forge_sys", "text": 'Agent "Critic 5" finished', "at": "T"}]
    typed = {"type": "user", "timestamp": "T", "message": {"content": NOTIFY}}
    assert ev(typed) == want
    queued = {
        "type": "attachment",
        "timestamp": "T",
        "attachment": {"type": "queued_command", "prompt": NOTIFY},
    }
    assert ev(queued) == want
    failed = NOTIFY.replace("completed", "failed").replace("finished", "stopped")
    typed["message"]["content"] = failed
    assert ev(typed)[0]["text"] == 'Agent "Critic 5" stopped (failed)'
    typed["message"]["content"] = "<task-notification><status>completed</status>"
    assert ev(typed)[0]["text"] == "A helper finished"


# --- pages and the live tail ------------------------------------------------


def line(text):
    return json.dumps({"type": "user", "message": {"content": text}}) + "\n"


def test_tail_then_after_reads_only_whole_new_lines(tmp_path):
    from mc import convo

    path = tmp_path / "t.jsonl"
    path.write_text(line("one") + line("two"))
    first = convo.page(str(path))
    assert [e["text"] for e in first["events"]] == ["one", "two"]
    assert first["after"] == path.stat().st_size and first["more"] is False
    with open(path, "a") as fh:
        fh.write(line("three") + line("four")[:-9])  # the last one half written
    nxt = convo.page(str(path), after=first["after"])
    assert [e["text"] for e in nxt["events"]] == ["three"]
    with open(path, "a") as fh:
        fh.write(line("four")[-9:])
    last = convo.page(str(path), after=nxt["after"])
    assert [e["text"] for e in last["events"]] == ["four"]
    assert convo.page(str(path), after=last["after"])["events"] == []
    assert convo.page(str(path), after=10**9)["reset"] is True


def test_older_pages_join_up(tmp_path):
    from mc import convo

    path = tmp_path / "t.jsonl"
    path.write_text("".join(line(f"m{i}") for i in range(40)))
    seen = []
    got = convo.page(str(path), chunk=300)
    seen = [e["text"] for e in got["events"]]
    while got["more"]:
        got = convo.page(str(path), before=got["before"], chunk=300)
        seen = [e["text"] for e in got["events"]] + seen
    assert seen == [f"m{i}" for i in range(40)]


def test_events_endpoint(client, laptop):
    sid = SIDS["busy"]
    r = client.get(f"/api/sessions/{sid}/events")
    assert r.status_code == 200
    body = r.json()
    assert [e["type"] for e in body["events"]] == [
        "forge_user",
        "assistant",
        "assistant",
    ]
    again = client.get(f"/api/sessions/{sid}/events", params={"after": body["after"]})
    assert again.json()["events"] == []
    helper = client.get(f"/api/sessions/{sid}/events", params={"agent": "abc123"})
    assert helper.status_code == 200
    assert (
        client.get(f"/api/sessions/{sid}/events", params={"after": -1}).status_code
        == 400
    )
    assert (
        client.get(f"/api/sessions/{sid}/events", params={"agent": "../x"}).status_code
        == 400
    )
    assert client.get("/api/sessions/nope!/events").status_code == 400


# --- the reply box ----------------------------------------------------------


@pytest.fixture
def fake_claude(monkeypatch):
    from mc import actions

    calls = []

    def http_json(port, path, payload=None, method="POST"):
        calls.append((path, payload))
        if path.endswith("/open"):
            return {"id": "conv-new"}
        return {"ok": True}

    monkeypatch.setattr(actions, "http_json", http_json)
    monkeypatch.setattr(actions, "manifest_port", lambda **_: 8445)
    return calls


def test_say_to_a_claude_tab_sets_model_then_sends(client, monkeypatch, fake_claude):
    from mc import actions

    monkeypatch.setattr(
        actions, "claude_names", lambda: {SIDS["idle"]: {"id": "conv-9"}}
    )
    r = client.post(
        f"/api/sessions/{SIDS['idle']}/say",
        json={"text": "carry on", "model": "opus", "effort": "max", "ultrathink": True},
        headers=H,
    )
    assert r.status_code == 200 and r.json()["via"] == "claude"
    assert fake_claude == [
        ("/api/conversations/conv-9/settings", {"model": "opus", "effort": "max"}),
        ("/api/conversations/conv-9/send", {"text": "ultrathink. carry on"}),
    ]


def test_say_to_an_ended_session_resumes_it(client, fake_claude):
    r = client.post(
        f"/api/sessions/{SIDS['ended']}/say",
        json={"text": "what happened?", "state": "ended", "cwd": "/home/x/old"},
        headers=H,
    )
    assert r.json() == {"ok": True, "via": "resumed", "conversation": "conv-new"}
    assert [c[0] for c in fake_claude] == [
        f"/api/everyone/{SIDS['ended']}/open",
        "/api/conversations/conv-new/send",
    ]


def test_say_to_a_terminal_session_is_a_board_note(client, laptop, monkeypatch):
    from mc import borrow

    monkeypatch.setattr(
        borrow.everyone(), "message", lambda sid, text: {"id": 41, "to": "ejb-busy"}
    )
    r = client.post(f"/api/sessions/{SIDS['busy']}/say", json={"text": "hi"}, headers=H)
    assert r.json()["via"] == "board"
    stored = json.loads(
        (laptop["claude"].parent / "mission" / "messages.json").read_text()
    )
    assert stored["messages"][0]["id"] == 41 and stored["messages"][0]["kind"] == "one"


def test_say_refuses_bad_input(client):
    sid = SIDS["busy"]
    assert (
        client.post(f"/api/sessions/{sid}/say", json={"text": "x"}).status_code == 403
    )
    assert (
        client.post(
            f"/api/sessions/{sid}/say", json={"text": " "}, headers=H
        ).status_code
        == 400
    )
    bad = client.post(
        f"/api/sessions/{sid}/say", json={"text": "x", "model": "a b"}, headers=H
    )
    assert bad.status_code == 400


def test_options_fall_back_when_claude_app_is_closed(client, monkeypatch):
    from mc import actions

    monkeypatch.setattr(actions, "manifest_port", lambda **_: None)
    got = client.get("/api/options").json()
    assert got["claude_app"] is False and "max" in got["efforts"]


# --- Ask Jan ----------------------------------------------------------------


def test_ask_jan_needs_jan_running(client, monkeypatch):
    import forge_jan

    monkeypatch.setattr(forge_jan, "router_url", lambda *a: None)
    r = client.post(
        f"/api/sessions/{SIDS['busy']}/ask-jan", json={"text": "status?"}, headers=H
    )
    assert r.status_code == 503 and "never starts" in r.json()["detail"]


def test_ask_jan_answers_from_the_conversation(client, monkeypatch):
    import forge_jan
    import web_app

    asked = {}

    def chat_messages(model, messages, **kw):
        asked["model"], asked["text"] = model, messages[1]["content"]
        return "It is editing app.py."

    monkeypatch.setattr(forge_jan, "router_url", lambda *a: "http://x")
    monkeypatch.setattr(forge_jan, "chat_messages", chat_messages)
    monkeypatch.setattr(
        web_app.jan, "model_for", lambda role, fallback="": "qwen-small"
    )
    r = client.post(
        f"/api/sessions/{SIDS['busy']}/ask-jan", json={"text": "status?"}, headers=H
    )
    assert r.json() == {"answer": "It is editing app.py.", "model": "qwen-small"}
    assert (
        "Emerson: do the thing" in asked["text"]
        and "(ran Edit: app.py)" in asked["text"]
    )


# --- messages and the answers that come back --------------------------------


def board_of(laptop, crew="forge"):
    return laptop["crew_home"] / crew / "board.json"


def test_broadcast_collects_board_and_chat_replies(client, laptop):
    r = client.post("/api/broadcast", json={"text": "what are you on?"}, headers=H)
    assert r.status_code == 200
    note_id = r.json()["id"]
    board = json.loads(board_of(laptop).read_text())
    asked = next(n for n in board["notes"] if n["id"] == note_id)
    assert asked["from"] == "Emerson" and asked["to"] is None
    assert (
        asked["text"].endswith("what are you on?")
        and "crew ack --note" in asked["text"]
    )

    # ejb-idle answers on the board (what crew ack --note writes) ...
    board["notes"].append(
        {
            "id": note_id + 1,
            "t": time.time(),
            "from": "ejb-idle",
            "to": "Emerson",
            "text": "tidying docs",
            "re": note_id,
        }
    )
    # ... ejb-wait marks it seen with a plain ok ...
    asked["done_by"] = ["ejb-wait"]
    board_of(laptop).write_text(json.dumps(board))
    # ... and ejb-busy answers in its own chat after the hook handed it over
    path = laptop["project"] / f"{SIDS['busy']}.jsonl"
    hook = f"#{note_id} Emerson -> everyone: {asked['text']} (0m ago)"
    with open(path, "a") as fh:
        fh.write(
            json.dumps(
                {
                    "type": "attachment",
                    "timestamp": "2026-10-07T10:01:00Z",
                    "attachment": {
                        "type": "hook_additional_context",
                        "content": [hook],
                    },
                }
            )
            + "\n"
        )
        fh.write(
            json.dumps(
                {
                    "type": "assistant",
                    "timestamp": "2026-10-07T10:01:05Z",
                    "message": {
                        "id": "r1",
                        "stop_reason": "end_turn",
                        "content": [{"type": "text", "text": "Building the map."}],
                    },
                }
            )
            + "\n"
        )

    thread = client.get("/api/messages").json()["messages"][0]
    assert thread["id"] == note_id and thread["text"] == "what are you on?"
    got = {r["from"]: (r["via"], r["text"]) for r in thread["replies"]}
    assert got == {
        "ejb-idle": ("board", "tidying docs"),
        "ejb-busy": ("chat", "Building the map."),
    }
    assert thread["seen"] == ["ejb-wait"]
    assert "ejb-busy" not in thread["waiting"] and "ejb-stale" in thread["waiting"]
    assert (
        next(r for r in thread["replies"] if r["from"] == "ejb-busy")["session"]
        == SIDS["busy"]
    )

    # answers outlive the board pruning the reply note
    board["notes"] = [n for n in board["notes"] if n["id"] != note_id + 1]
    board_of(laptop).write_text(json.dumps(board))
    again = client.get("/api/messages").json()["messages"][0]
    assert {r["from"] for r in again["replies"]} == {"ejb-idle", "ejb-busy"}


def test_chat_reply_found_when_it_comes_in_a_later_read(laptop, tmp_path):
    from mc import replies

    path = tmp_path / "s.jsonl"
    hook = "#7 Emerson -> ejb-x: Emerson asks (answer him in your next reply): ready? (0m ago)"
    write_jsonl(
        path,
        [
            {
                "type": "attachment",
                "attachment": {"type": "hook_additional_context", "content": hook},
            }
        ],
    )
    first = replies.scan_transcript(str(path))
    assert first == [{"note": 7, "at": None, "reply": None}]
    with open(path, "a") as fh:
        fh.write(
            json.dumps(
                {
                    "type": "assistant",
                    "message": {
                        "stop_reason": "end_turn",
                        "content": [{"type": "text", "text": "Yes."}],
                    },
                }
            )
            + "\n"
        )
    again = replies.scan_transcript(str(path))
    assert again[0]["reply"] == "Yes."


def test_message_to_one_session_is_recorded_and_waits(client, laptop, monkeypatch):
    from mc import borrow

    monkeypatch.setattr(
        borrow.everyone(), "message", lambda sid, text: {"id": 99, "to": "ejb-wait"}
    )
    assert (
        client.post(
            f"/api/sessions/{SIDS['wait']}/message", json={"text": "ping"}, headers=H
        ).status_code
        == 200
    )
    thread = client.get("/api/messages").json()["messages"][0]
    assert (
        thread["kind"] == "one"
        and thread["waiting"] == ["ejb-wait"]
        and thread["replies"] == []
    )


def test_broadcast_to_a_missing_board_is_refused(client):
    r = client.post("/api/broadcast", json={"text": "x", "crew": "nope"}, headers=H)
    assert r.status_code == 404


# --- critic fixes (2026-10-07) ----------------------------------------------


def test_narration_between_tools_is_not_the_answer(tmp_path):
    from mc import replies

    path = tmp_path / "s.jsonl"
    hook = "#8 Emerson -> everyone: Emerson asks (answer him in your next reply): status? (0m ago)"
    say = lambda text, stop: {  # noqa: E731
        "type": "assistant",
        "message": {"stop_reason": stop, "content": [{"type": "text", "text": text}]},
    }
    write_jsonl(
        path,
        [
            {
                "type": "attachment",
                "attachment": {"type": "hook_additional_context", "content": hook},
            },
            say("Now let me run the tests.", "tool_use"),
        ],
    )
    assert replies.scan_transcript(str(path))[0]["reply"] is None
    with open(path, "a") as fh:
        fh.write(json.dumps(say("All green, map done.", "end_turn")) + "\n")
    assert replies.scan_transcript(str(path))[0]["reply"] == "All green, map done."


def test_compact_summary_is_not_a_message_from_emerson():
    summary = {
        "type": "user",
        "isCompactSummary": True,
        "isVisibleInTranscriptOnly": True,
        "message": {"content": "This session is being continued from " + "x" * 20000},
    }
    assert ev(summary) == []


def test_live_tail_steps_over_a_line_longer_than_its_window(tmp_path, monkeypatch):
    from mc import convo

    monkeypatch.setattr(convo, "AFTER_MAX_BYTES", 1000)
    path = tmp_path / "t.jsonl"
    path.write_text(line("one"))
    start = convo.page(str(path))["after"]
    with open(path, "a") as fh:
        fh.write(line("y" * 5000) + line("two"))
    got = convo.page(str(path), after=start)
    assert got["after"] > start + 5000 and got["more"] is True
    assert "not shown" in got["events"][0]["text"]
    nxt = convo.page(str(path), after=got["after"])
    assert [e["text"] for e in nxt["events"]] == ["two"]
    with open(path, "a") as fh:  # a long line still being written: wait
        fh.write('{"type": "user", "message": {"content": "' + "z" * 3000)
    assert convo.page(str(path), after=nxt["after"])["after"] == nxt["after"]


def test_ask_jan_reads_the_helpers_own_chat(client, monkeypatch):
    import web_app

    asked = []
    monkeypatch.setattr(
        web_app, "_transcript", lambda sid, agent=None: asked.append(agent) or "/x"
    )
    monkeypatch.setattr(web_app.convo, "page", lambda path: {"events": []})
    monkeypatch.setattr(web_app.jan_ask, "ask", lambda *a: {"answer": "ok"})
    sid = SIDS["busy"]
    url = f"/api/sessions/{sid}/ask-jan"
    assert (
        client.post(url, json={"text": "hi", "agent": "abc123"}, headers=H).status_code
        == 200
    )
    assert asked == ["abc123"]
    bad = client.post(url, json={"text": "hi", "agent": "../x"}, headers=H)
    assert bad.status_code == 400


def test_overview_survives_nonsense_map_sizes(client):
    for q in (
        "mapw=nan&maph=inf&zoom=nan",
        "mapw=-5&maph=-1&zoom=99",
        "mapw=320&zoom=3",
    ):
        r = client.get("/api/overview?" + q)
        assert r.status_code == 200, q
        assert "lanes" in r.json()["graph"]  # sizes are the page's business now


def test_replies_sort_board_and_chat_times_together():
    from mc import replies

    assert replies._when(100.0) == 100.0
    assert replies._when("1970-01-01T00:02:00Z") == 120.0
    assert replies._when("garbage") == 0.0 and replies._when(None) == 0.0
