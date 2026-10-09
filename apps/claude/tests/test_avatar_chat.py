"""Chatting with the avatar through Jan: the reply-tag parser, history
trimming and the request that goes to Jan (PLAN-avatars-2.md, part 4)."""

import avatar_chat as ac


def test_tag_at_the_end_is_taken_off():
    assert ac.parse_reply("Hey you, back again? [wink]") == (
        "Hey you, back again?",
        "wink",
    )


def test_tag_variants_and_case():
    assert ac.parse_reply("Oh no. (SAD)")[1] == "sad"
    assert ac.parse_reply("Hmm, let me see *think*")[1] == "think"
    assert ac.parse_reply("Wow! [surprised].") == ("Wow!", "surprised")


def test_missing_or_unknown_tag_defaults_to_happy():
    assert ac.parse_reply("Just a line.") == ("Just a line.", "happy")
    assert ac.parse_reply("Line [angry]") == ("Line [angry]", "happy")


def test_think_blocks_and_stray_tags_are_dropped():
    text, tag = ac.parse_reply("<think>plan</think>So [shy] cute. [shy]")
    assert (text, tag) == ("So cute.", "shy")


def test_history_keeps_the_last_30_exchanges(tmp_path):
    h = ac.History(tmp_path)
    for i in range(35):
        h.add("yui", f"hi {i}", f"reply {i}", "happy")
    kept = h.load("yui")
    assert len(kept) == 60
    assert kept[0]["content"] == "hi 5"
    assert kept[-1] == {**kept[-1], "content": "reply 34", "tag": "happy"}
    h.clear("yui")
    assert h.load("yui") == []


def test_history_refuses_path_tricks(tmp_path):
    h = ac.History(tmp_path)
    try:
        h.load("../etc")
    except ValueError:
        pass
    else:
        raise AssertionError("a bad persona id was accepted")


def test_messages_carry_prompt_history_and_tags():
    persona = {"name": "Yui", "prompt": "Playful."}
    history = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello", "tag": "wink"},
    ]
    msgs = ac.messages(persona, history, "x" * 2000)
    assert msgs[0]["role"] == "system"
    assert "Yui" in msgs[0]["content"] and "[wink]" in msgs[0]["content"]
    assert msgs[2]["content"] == "hello [wink]"
    assert len(msgs[-1]["content"]) == ac.MAX_TEXT


def test_chat_endpoint_sends_history_to_jan_and_plays_the_tag(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    import web_app

    sent = []

    def fake_chat(model, system, user, **kw):
        sent.append((model, kw["extra"]["messages"]))
        return "Caught you staring, huh? [wink]"

    monkeypatch.setattr(web_app, "chats", ac.History(tmp_path))
    monkeypatch.setattr(
        web_app.jan, "model_for", lambda role, fallback="": f"fake-{role}"
    )
    monkeypatch.setattr(web_app.forge_jan, "loaded_models", lambda: [])
    monkeypatch.setattr(web_app.forge_jan, "chat", fake_chat)
    client = TestClient(web_app.app)
    forge = {"X-Forge": "1"}

    r = client.post("/api/avatars/chat/yui", json={"text": "hi"}, headers=forge)
    assert r.status_code == 200, r.text
    assert (r.json()["reply"], r.json()["tag"]) == ("Caught you staring, huh?", "wink")
    client.post("/api/avatars/chat/yui", json={"text": "again"}, headers=forge)
    model, msgs = sent[-1]
    assert model == "fake-chat"
    assert [m["role"] for m in msgs] == ["system", "user", "assistant", "user"]
    got = client.get("/api/avatars/chat/yui", headers=forge).json()["history"]
    assert len(got) == 4
    assert (
        client.post(
            "/api/avatars/chat/nobody", json={"text": "x"}, headers=forge
        ).status_code
        == 404
    )
    assert client.post("/api/avatars/chat/yui", json={"text": "x"}).status_code == 403
