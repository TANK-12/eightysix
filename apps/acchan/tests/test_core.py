"""Deterministic tests: registry, router, agent loop (with a scripted model),
conversation trimming, documents, keys, calculator, MCP, web endpoints.
No Jan and no desktop needed."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("ACCHAN_DATA", str(tmp_path / "data"))
    monkeypatch.setenv("FORGE_JAN_SETTINGS_DIR", str(tmp_path / "jan"))
    monkeypatch.setenv("JAN_MODELS_DIR", str(tmp_path / "jan-models"))
    import acchan.conversation as conversation

    monkeypatch.setattr(conversation, "DATA", tmp_path / "data")
    import acchan.memory as memory_mod

    monkeypatch.setattr(memory_mod, "DATA", tmp_path / "data")
    yield


from acchan import agent as agent_mod  # noqa: E402
from acchan import desktop, llm, prompts, registry, router  # noqa: E402
from acchan.conversation import Conversation  # noqa: E402
from acchan.tools import docs, system  # noqa: E402

registry.load_all()


# ------------------------------------------------------------------ registry
def test_every_tool_has_a_description_and_valid_schema():
    assert len(registry.TOOLS) >= 55
    for tool in registry.TOOLS.values():
        assert tool.description and not tool.description.startswith(tool.name)
        schema = tool.schema()["function"]["parameters"]
        assert set(schema["required"]) <= set(schema["properties"])
        for prop in schema["properties"].values():
            assert prop["type"] in ("string", "integer", "number", "boolean", "array")


def test_every_toolset_declares_keywords_and_examples_that_exist():
    for name in registry.TOOLSETS:
        assert registry.KEYWORDS[name], name
        for _said, tool_name, args in registry.EXAMPLES[name]:
            assert tool_name in registry.TOOLS, tool_name
            assert set(args) <= set(registry.TOOLS[tool_name].properties), tool_name
        for companion in registry.COMPANIONS.get(name, ()):
            assert companion in registry.TOOLS


def test_call_coerces_and_repairs_arguments():
    assert registry.call("calculate", '{"expression": 17}') == "17 = 17"
    # a lone wrong key is mapped onto the lone missing required one
    assert registry.call("calculate", {"expr": "2*3"}) == "2*3 = 6"
    # trailing garbage after the JSON object
    assert registry.call("calculate", '{"expression": "1+1"} extra') == "1+1 = 2"
    # tool names are fuzzy-matched
    assert registry.resolve_name("functions.calculate") == "calculate"
    assert registry.resolve_name("calculat") == "calculate"


def test_call_errors_say_how_to_fix():
    with pytest.raises(registry.ToolError, match="no tool called"):
        registry.call("teleport_the_cat", {})
    with pytest.raises(registry.ToolError, match="needs"):
        registry.call("move_path", {"source": "a"})


def test_read_and_edit_file(tmp_path):
    target = tmp_path / "app.py"
    target.write_text("def add(a, b):\n    return a - b\n")
    out = registry.call("read_file", {"path": str(target)})
    assert "    2      return a - b" in out
    # indentation dropped by the model is tolerated
    registry.call(
        "edit_file", {"path": str(target), "old": "return a - b", "new": "return a + b"}
    )
    assert "return a + b" in target.read_text()
    registry.call(
        "edit_file",
        {
            "path": str(target),
            "old": "def add(a, b):\nreturn a + b",
            "new": "def add(a, b):\nreturn b + a",
        },
    )
    assert target.read_text() == "def add(a, b):\n    return b + a\n"
    with pytest.raises(registry.ToolError, match="not found"):
        registry.call(
            "edit_file", {"path": str(target), "old": "nothing like this", "new": "x"}
        )


def test_calculator():
    assert system.calculate("348 * 29") == "348 * 29 = 10092"
    assert system.calculate("15% of 80") == "15% of 80 = 12"
    assert system.calculate("2^10") == "2^10 = 1024"
    assert system.calculate("sqrt(16)") == "sqrt(16) = 4"
    with pytest.raises(registry.ToolError):
        system.calculate("__import__('os')")


# -------------------------------------------------------------------- router
@pytest.mark.parametrize(
    "text,tool,args",
    [
        ("pause", "media_control", {"action": "pause", "player": ""}),
        (
            "skip this song on qobuz",
            "media_control",
            {"action": "next", "player": "qobuz"},
        ),
        ("volume 40", "set_volume", {"percent": 40}),
        ("close this window", "close_window", {"window": "this"}),
        ("please switch to firefox", "focus_window", {"window": "firefox"}),
        ("go to reddit.com", "open_web", {"address": "reddit.com"}),
        ("open youtube", "open_web", {"address": "youtube.com"}),
        ("open ~/Documents", "open_item", {"target": "~/Documents"}),
        ("open a new terminal tab", "terminal_new_tab", {}),
        (
            "run npm run dev in the background",
            "shell_run",
            {"command": "npm run dev", "shell": "bg-npm", "timeout": 5},
        ),
        (
            "please run `make && make test` in the background",
            "shell_run",
            {"command": "make && make test", "shell": "bg-make", "timeout": 5},
        ),
        (
            "run pytest and black headless",
            "shell_run",
            {"command": "pytest and black", "shell": "bg-pytest", "timeout": 5},
        ),
        ("show me the terminal", "shell_show", {}),
        ("show the background shell", "shell_show", {}),
        ("close all the background shells", "shell_close", {"shell": "all"}),
        ("close the headless browser", "close_headless_browser", {}),
        (
            "remind me in 20 minutes to check the oven",
            "remind_me",
            {"minutes": 20, "message": "check the oven"},
        ),
        (
            "remember that my calculus exam is on the 3rd of November",
            "remember",
            {"fact": "my calculus exam is on the 3rd of November"},
        ),
    ],
)
def test_fast_path(text, tool, args):
    calls = router.fast_path(text)
    assert calls and calls[0].tool == tool and calls[0].args == args


def test_fast_path_leaves_real_questions_to_a_model():
    for text in (
        "what is in my downloads folder",
        "open my resume",
        "why is the sky blue?",
        "summarise lecture 5",
    ):
        assert router.fast_path(text) is None, text


def test_fast_path_splits_compound_commands():
    calls = router.fast_path("open youtube and pause the music")
    assert calls is not None
    assert [c.tool for c in calls] == ["open_web", "media_control"]


def test_plan_picks_tier_and_toolsets():
    assert router.plan("hi acchan").tier == "tiny"
    assert router.plan("fix the bug in app.py").tier == "medium"
    p = router.plan("find my lecture notes")
    assert p.tier == "small" and "docs" in p.toolsets
    assert "system" in router.plan("what is 348 * 29").toolsets
    # a follow-up keeps the tools already in use
    assert "media" in router.plan("and the next one", used=["media"]).toolsets


def test_companion_tools_travel_with_their_toolset():
    names = [t["function"]["name"] for t in prompts.tool_schemas(["docs"])]
    assert "find_files" in names and "ask_document" in names


def test_system_prompt_is_stable_and_names_the_rules():
    a = prompts.system_prompt("small", ["files"])
    b = prompts.system_prompt("small", ["files"])
    assert a == b
    assert "Never say you cannot" in a and "Examples:" in a
    # the 0.8B now acts too: short rules of its own, and chat without tools
    assert "Never say you can't" in prompts.system_prompt("tiny", ["apps"])
    assert "fresh one" in prompts.system_prompt("tiny", [])


# ------------------------------------------------------- agent (scripted llm)
class Script:
    """Stands in for llm.stream, replaying prepared replies."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def __call__(self, tier, messages, tools=None, **kw):
        self.calls.append(
            {
                "tier": tier,
                "tools": [t["function"]["name"] for t in tools or []],
                "messages": messages,
            }
        )
        return self.replies.pop(0)


def reply(content="", calls=None):
    return llm.Reply(content=content, tool_calls=calls or [], model="fake")


def call(name, **args):
    return {"id": "c1", "name": name, "arguments": json.dumps(args)}


def run(monkeypatch, script, text, tier=None):
    monkeypatch.setattr(llm, "stream", script)
    conv = Conversation(source="test")
    events = list(agent_mod.Agent(conv, forced_tier=tier).run(text))
    return conv, events


def test_agent_runs_a_tool_then_answers(monkeypatch):
    script = Script(
        [reply(calls=[call("calculate", expression="6*7")]), reply("It's 42.")]
    )
    conv, events = run(monkeypatch, script, "what is 6 times 7 with the calculator")
    kinds = [e["type"] for e in events]
    assert kinds.count("tool") == 1 and events[-1]["type"] == "done"
    result = next(e for e in events if e["type"] == "result")
    assert result["ok"] and "= 42" in result["result"]
    assert events[-1]["text"] == "It's 42."
    assert [m["role"] for m in conv.messages] == [
        "user",
        "assistant",
        "tool",
        "assistant",
    ]


def test_agent_reads_tool_calls_written_as_text(monkeypatch):
    text_call = '<tool_call>{"name": "calculate", "arguments": {"expression": "2+2"}}</tool_call>'
    script = Script([reply(text_call), reply("4")])
    _conv, events = run(monkeypatch, script, "calculate 2+2")
    assert any(e["type"] == "result" and "= 4" in e["result"] for e in events)


def test_agent_nudges_a_refusal(monkeypatch):
    script = Script(
        [
            reply("I'm sorry, I can't do calculations."),
            reply(calls=[call("calculate", expression="9*9")]),
            reply("81"),
        ]
    )
    conv, events = run(monkeypatch, script, "work out 9 * 9 for my homework")
    assert any("You do have tools" in m.get("content", "") for m in conv.messages)
    assert events[-1]["text"] == "81"


def test_agent_stops_repeated_calls_and_escalates(monkeypatch):
    same = call("calculate", expression="1+1")
    script = Script(
        [
            reply(calls=[same]),
            reply(calls=[same]),
            reply(calls=[call("nonsense_tool")]),
            reply("done"),
        ]
    )
    _conv, events = run(
        monkeypatch, script, "calculate 1+1 for my homework", tier="small"
    )
    results = [e for e in events if e["type"] == "result"]
    assert "already made this exact call" in results[1]["result"]
    assert any(e["type"] == "escalate" and e["to"] == "medium" for e in events)
    assert script.calls[-1]["tier"] == "medium"


def test_agent_fast_path_needs_no_model(monkeypatch):
    monkeypatch.setattr(
        registry.TOOLS["set_volume"],
        "func",
        lambda percent, player="": f"vol {percent}",
    )
    script = Script([])
    _conv, events = run(monkeypatch, script, "volume 30")
    assert events[0] == {"type": "route", "tier": "none", "toolsets": [], "fast": True}
    assert events[-1]["text"] == "Volume set to 30%."
    assert script.calls == []


def test_agent_falls_back_to_a_model_when_the_fast_path_fails(monkeypatch):
    def broken(window):
        raise registry.ToolError("No window matches")

    monkeypatch.setattr(registry.TOOLS["focus_window"], "func", broken)
    script = Script([reply("There's no such window open.")])
    conv, events = run(monkeypatch, script, "switch to blender")
    assert events[-1]["text"] == "There's no such window open."
    assert any("attempt failed" in m.get("content", "") for m in conv.messages)


def test_agent_wraps_up_when_steps_run_out(monkeypatch):
    monkeypatch.setitem(agent_mod.MAX_STEPS, "small", 2)
    script = Script(
        [
            reply(calls=[call("calculate", expression="1")]),
            reply(calls=[call("calculate", expression="2")]),
            reply("Summary."),
        ]
    )
    _conv, events = run(monkeypatch, script, "calculate things", tier="small")
    assert script.calls[-1]["tools"] == [] and events[-1]["text"] == "Summary."


# -------------------------------------------------------------- conversation
def test_trim_keeps_recent_and_never_starts_on_a_tool_result():
    conv = Conversation()
    for i in range(30):
        conv.add({"role": "user", "content": f"question {i} " + "x" * 200})
        conv.add(
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": str(i),
                        "type": "function",
                        "function": {"name": "t", "arguments": "{}"},
                    }
                ],
            }
        )
        conv.add({"role": "tool", "tool_call_id": str(i), "content": "r" * 2000})
        conv.add({"role": "assistant", "content": f"answer {i}"})
    view = conv.trimmed(6000)
    assert view[0]["role"] == "user"
    assert view[-1]["content"] == "answer 29"
    assert sum(len(m.get("content") or "") for m in view) < 9000


def test_conversation_round_trip():
    conv = Conversation(source="test")
    conv.add({"role": "user", "content": "hello there"})
    conv.save()
    again = Conversation.load(conv.id)
    assert again.messages == conv.messages and again.title == "hello there"
    assert Conversation.list_all()[0]["id"] == conv.id


# ------------------------------------------------------------------ documents
def test_best_passages_finds_the_right_page():
    pages = [
        f"[page {n}]\n" + ("filler words about nothing in particular. " * 40)
        for n in range(1, 30)
    ]
    pages[16] = (
        "[page 17]\nThe derivative of ln x is 1/x, valid for x greater than zero."
    )
    hits = docs.best_passages("\n\n".join(pages), "what is the derivative of ln x", k=2)
    assert any("[page 17]" in h and "1/x" in h for h in hits)


def test_read_document_markdown(tmp_path, monkeypatch):
    monkeypatch.setattr(docs, "CACHE", tmp_path / "cache")
    note = tmp_path / "notes.md"
    note.write_text("# Week 3\nIntegration by parts: u dv = uv - v du.\n")
    assert "Integration by parts" in registry.call(
        "read_document", {"source": str(note)}
    )
    out = registry.call(
        "ask_document", {"source": str(note), "question": "integration by parts"}
    )
    assert "uv - v du" in out


# ----------------------------------------------------------------------- keys
def test_key_combos():
    assert desktop.split_combo("ctrl+shift+t") == (["ctrl", "shift"], "t")
    assert desktop.split_combo("<Super><Shift>Page_Down") == (
        ["super", "shift"],
        "Page_Down",
    )
    g = desktop.Gnome()
    assert g._code("Page_Down") == 109 and g._code("a") == 30 and g._code("F11") == 87


# ------------------------------------------------------------------------ MCP
def test_mcp_lists_and_calls_tools():
    sys.path.insert(0, str(ROOT))
    import mcp_server

    listed = mcp_server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert listed is not None
    assert len(listed["result"]["tools"]) == len(registry.TOOLS)
    done = mcp_server.handle(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "calculate", "arguments": {"expression": "3*3"}},
        }
    )
    assert done is not None
    assert (
        done["result"]["content"][0]["text"] == "3*3 = 9"
        and not done["result"]["isError"]
    )
    assert (
        mcp_server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
        is None
    )


# ----------------------------------------------------------------- web / API
@pytest.fixture
def client(monkeypatch):
    from fastapi.testclient import TestClient

    import web_app

    script = Script([reply("Hello from the fake model.")] * 10)
    monkeypatch.setattr(llm, "stream", script)
    return TestClient(web_app.app)


def test_openai_endpoint_non_streaming(client):
    res = client.post(
        "/v1/chat/completions",
        json={
            "model": "acchan",
            "messages": [
                {"role": "system", "content": "ignored"},
                {"role": "user", "content": "hi there friend"},
            ],
        },
    )
    body = res.json()
    assert res.status_code == 200
    assert body["choices"][0]["message"]["content"] == "Hello from the fake model."


def test_openai_endpoint_streaming(client):
    with client.stream(
        "POST",
        "/v1/chat/completions",
        json={
            "model": "acchan",
            "stream": True,
            "messages": [{"role": "user", "content": "hi there friend"}],
        },
    ) as res:
        lines = [l for l in res.iter_lines() if l.startswith("data:")]
    assert lines[-1] == "data: [DONE]"
    text = "".join(
        json.loads(l[5:])["choices"][0]["delta"].get("content", "") for l in lines[:-1]
    )
    assert text == "Hello from the fake model."


def test_chat_stream_and_conversation_listing(client):
    with client.stream("POST", "/api/chat", json={"text": "hello there acchan"}) as res:
        events = [json.loads(l[5:]) for l in res.iter_lines() if l.startswith("data:")]
    assert events[0]["type"] == "start" and events[-1]["type"] == "done"
    cid = events[0]["conversation"]
    assert any(
        c["id"] == cid for c in client.get("/api/conversations").json()["conversations"]
    )
    assert (
        client.get(f"/api/conversations/{cid}").json()["messages"][0]["content"]
        == "hello there acchan"
    )


def test_tabs_come_from_the_manifest(client):
    tabs = client.get("/api/tabs").json()["tabs"]
    assert [t["name"] for t in tabs] == ["claude", "study-companion"]
    assert all(t["port"] for t in tabs)


def test_working_folder_rides_in_the_first_message_not_the_system_prompt(
    monkeypatch,
):
    script = Script([reply("hi"), reply("again")])
    monkeypatch.setattr(llm, "stream", script)
    conv = Conversation(source="test")
    list(agent_mod.Agent(conv, cwd="/tmp/proj").run("hello there acchan"))
    list(agent_mod.Agent(conv, cwd="/tmp/proj").run("and again"))
    assert (
        conv.messages[0]["content"] == "(Working folder: /tmp/proj)\nhello there acchan"
    )
    assert conv.messages[2]["content"] == "and again"
    assert "/tmp/proj" not in script.calls[0]["messages"][0]["content"]
    conv.save()
    assert conv.title == "hello there acchan"


# ------------------------------------- 2026-09-23: one model, tiny with tools
from acchan import memory, spelling  # noqa: E402


@pytest.mark.parametrize(
    "said,fixed",
    [
        ("open a new firfox window", "open a new firefox window"),
        ("open a firefox indow and tb", "open a firefox window and tab"),
        ("wriet a story", "write a story"),
        ("what is 6 times 7", "what is 6 times 7"),  # nothing to fix
        ("open ~/Documents/notes.md", "open ~/Documents/notes.md"),  # paths kept
    ],
)
def test_spelling_fixes_typos_from_emersons_log(said, fixed):
    assert spelling.correct(said) == fixed


def test_emersons_log_new_firefox_window_is_instant():
    calls = router.fast_path(spelling.correct("open a new firfox window"))
    assert calls and calls[0].tool == "open_web"
    assert calls[0].args.get("new_window") is True


def test_emersons_log_window_and_tab():
    calls = router.fast_path(spelling.correct("open a firefox indow and tb"))
    assert calls is not None
    assert [c.tool for c in calls] == ["open_web", "open_web"]
    assert calls[0].args.get("new_window") is True


def test_new_tab_is_a_tab_not_a_search():
    from acchan.tools import browser

    assert browser._as_url("about:newtab") == "about:newtab"


def test_model_questions_are_answered_not_guessed():
    for text in ("what model is this?", "which model are you", "what llm are you on"):
        assert router.asks_model(text), text
    assert not router.asks_model("open the model folder")
    # and "this" alone is no longer a screen request
    assert "screen" not in router.plan("what model is this?").toolsets


def test_stories_are_chat_without_tools():
    for text in ("write a story", "tell me a joke about cats", "write a poem"):
        assert router.plan(text).toolsets == [], text


def test_tiny_gets_tools_now():
    p = router.plan("open a terminal and run git status", forced_tier="tiny")
    assert p.tier == "tiny" and "shell" in p.toolsets or "terminal" in p.toolsets


def test_agent_parses_qwen_xml_tool_calls():
    text = (
        "<tool_call>\n<function=calculate>\n<parameter=expression>\n2+3\n"
        "</parameter>\n</function>\n</tool_call>"
    )
    found = agent_mod.calls_in_text(text)
    assert found and found[0]["name"] == "calculate"
    assert json.loads(found[0]["arguments"]) == {"expression": "2+3"}
    assert agent_mod.strip_calls(text) == ""
    bare = "<tool_call>\n<function=whats_on_screen>\n</function>\n</tool_call>"
    assert agent_mod.calls_in_text(bare)[0]["name"] == "whats_on_screen"


def test_sticky_mode_starts_tiny_and_keeps_one_model(monkeypatch):
    script = Script(
        [
            reply(calls=[call("calculate", expression="6*7")]),
            reply("42."),
            reply("Hello again!"),
        ]
    )
    monkeypatch.setattr(llm, "stream", script)
    conv = Conversation(source="test")
    list(agent_mod.Agent(conv).run("what is 6 times 7 for my homework"))
    list(agent_mod.Agent(conv).run("thanks, what else can you do"))
    assert {c["tier"] for c in script.calls} == {"tiny"}
    assert "calculate" in script.calls[0]["tools"]


def test_sticky_mode_keeps_the_bigger_model_after_stepping_up(monkeypatch):
    script = Script(
        [
            reply(calls=[call("nonexistent_tool_xyz")]),
            reply(calls=[call("calculate", expression="__import__('os')")]),
            reply("done"),  # now on small
            reply("still here"),  # next message stays on small
        ]
    )
    monkeypatch.setattr(llm, "stream", script)
    conv = Conversation(source="test")
    events = list(agent_mod.Agent(conv).run("calculate something weird"))
    assert any(e["type"] == "escalate" for e in events)
    list(agent_mod.Agent(conv).run("ok thanks"))
    assert script.calls[-1]["tier"] == "small"
    again = Conversation.load(conv.id)
    assert again.tier == "small"


def test_switch_mode_still_picks_per_message(monkeypatch):
    script = Script([reply("hi!")])
    _conv, events = run(monkeypatch, script, "hi acchan", tier="switch")
    route = next(e for e in events if e["type"] == "route")
    assert route["tier"] == "tiny"


def test_repeated_reply_is_asked_again(monkeypatch):
    story = "Once upon a time a cat napped in the sun all day long and was happy."
    script = Script([reply(story), reply(story), reply("A brand new tale.")])
    monkeypatch.setattr(llm, "stream", script)
    conv = Conversation(source="test")
    list(agent_mod.Agent(conv).run("write a story"))
    events = list(agent_mod.Agent(conv).run("write another story"))
    assert events[-1]["text"] == "A brand new tale."


def test_long_chat_is_summarised_not_forgotten(monkeypatch):
    conv = Conversation(source="test")
    for i in range(40):
        conv.add({"role": "user", "content": f"message {i} " + "x" * 400})
        conv.add({"role": "assistant", "content": f"answer {i} " + "y" * 400})
    seen = {}

    def fake_complete(tier, system, user, **kw):
        seen["user"] = user
        return "Emerson's favourite colour is teal."

    monkeypatch.setattr(llm, "complete", fake_complete)
    monkeypatch.setattr(llm, "stream", Script([reply("teal!")]))
    events = list(agent_mod.Agent(conv).run("what's my favourite colour?"))
    assert conv.summary == "Emerson's favourite colour is teal."
    assert "message 0 " in seen["user"]
    assert conv.summary_upto > 0
    sent = llm.stream.calls[0]["messages"]  # type: ignore[attr-defined]
    assert "teal" in sent[0]["content"]  # the summary rides in the system prompt
    assert events[-1]["text"] == "teal!"


def test_long_term_memory_tools_and_prompt():
    registry.call("remember", {"fact": "Emerson studies MATH1014 at Curtin"})
    assert "MATH1014" in registry.call("recall", {"query": "math"})
    assert "MATH1014" in prompts.system_prompt("tiny", ["apps"])
    registry.call("forget", {"fact": "MATH1014"})
    assert "MATH1014" not in prompts.system_prompt("tiny", ["apps"])
    assert memory.facts() == []


def test_new_system_tools_exist():
    for name in ("what_time", "set_brightness", "lock_screen", "wifi", "bluetooth"):
        assert name in registry.TOOLS, name
    assert "20" in registry.call("what_time", {})  # the year
    assert registry.TOOLS["weather"].toolset == "system"


# ------------------------------------------ session 3: tabs, persona, the 0.8B
NEW_TAB = {"address": "about:newtab"}
NEW_WINDOW = {"address": "about:newtab", "new_window": True}


@pytest.mark.parametrize(
    "said, tool, args",
    [
        ("new tab", "open_web", NEW_TAB),
        ("open a new firefox tab", "open_web", NEW_TAB),
        ("open a new tab in firefox", "open_web", NEW_TAB),
        ("open firefox tab", "open_web", NEW_TAB),
        ("open a tab in firefox", "open_web", NEW_TAB),
        ("firefox new tab", "open_web", NEW_TAB),
        ("make a new tab", "open_web", NEW_TAB),
        ("open another tab", "open_web", NEW_TAB),
        ("new firefox window", "open_web", NEW_WINDOW),
        ("new window", "open_web", NEW_WINDOW),
        ("open another firefox window", "open_web", NEW_WINDOW),
        ("can you open a new window in firefox", "open_web", NEW_WINDOW),
        ("open a new browser window", "open_web", NEW_WINDOW),
        ("open youtube in a new tab", "open_web", {"address": "youtube.com"}),
        (
            "open github in a new window",
            "open_web",
            {"address": "github.com", "new_window": True},
        ),
        ("open a firefox tab with github", "open_web", {"address": "github.com"}),
        ("open wikipedia tab", "open_web", {"address": "wikipedia.org"}),
        ("open wikipeida tab", "open_web", {"address": "wikipedia.org"}),
        ("new youtube tab", "open_web", {"address": "youtube.com"}),
        ("open a private window", "open_web", {"address": "", "private": True}),
        ("open a new incognito window", "open_web", {"address": "", "private": True}),
        ("what tabs do I have open?", "browser_tabs", {}),
        ("list my tabs", "browser_tabs", {}),
        ("list th etabs i have open", "browser_tabs", {}),
        ("show me all my tabs", "browser_tabs", {}),
        ("how many tabs are open?", "browser_tabs", {}),
        ("switch to the youtube tab", "switch_tab", {"tab": "youtube"}),
        ("go to my claude tab", "switch_tab", {"tab": "claude"}),
        ("switch to tab 3", "switch_tab", {"tab": "3"}),
        ("close the youtube tab", "close_tab", {"tab": "youtube"}),
        ("what is 1234 * 5678", "calculate", {"expression": "1234 * 5678"}),
        ("what it 2+2", "calculate", {"expression": "2+2"}),
        ("what is 348 times 29?", "calculate", {"expression": "348 * 29"}),
        ("15% of 80", "calculate", {"expression": "15% of 80"}),
        ("opena new text doc", "launch_app", {"name": "text editor"}),
    ],
)
def test_tabs_windows_and_sums_need_no_model(said, tool, args):
    calls = router.fast_path(spelling.correct(said))
    assert calls, said
    assert (calls[0].tool, calls[0].args) == (tool, args), said


def test_several_new_tabs_and_window_plus_tab():
    calls = router.fast_path("open 3 new tabs")
    assert calls and [c.args for c in calls] == [NEW_TAB] * 3
    calls = router.fast_path(spelling.correct("opena new firfox window and tab"))
    assert calls and [c.args for c in calls] == [NEW_WINDOW, NEW_TAB]


def test_questions_that_are_not_commands_still_go_to_a_model():
    for text in (
        "should I close this window?",
        "why do I have so many tabs?",
        "what is a tab?",
        "open the tab with my lecture notes and summarise it",
    ):
        calls = router.fast_path(text)
        assert not calls or calls[0].tool not in ("close_window",), text
    assert router.fast_path("why do I have so many tabs?") is None


def test_private_window_opens_firefox_private(monkeypatch):
    from acchan.tools import browser

    ran = []
    monkeypatch.setattr(browser, "spawn", lambda cmd: ran.append(cmd))
    browser.open_web("", private=True)
    browser.open_web("about:newtab", new_window=True)
    assert ran == [
        ["firefox", "--private-window"],
        ["firefox", "--new-window", "about:newtab"],
    ]


def many_tabs(n=31):
    return [
        {
            "window": 1,
            "index": i,
            "title": f"Page number {i} with a fairly long descriptive title here",
            "url": f"https://www.example{i}.com/some/long/path?x={i}",
            "active": i == 5,
        }
        for i in range(1, n + 1)
    ]


def test_tab_list_is_compact_and_complete(monkeypatch):
    from acchan.tools import browser

    monkeypatch.setattr(browser, "firefox_tabs", lambda: many_tabs())
    text = browser.browser_tabs()
    assert text.splitlines()[0].startswith("31 tabs open")
    for i in range(1, 32):
        assert f"#{i} " in text
    assert f"example31.com" in text
    # small enough that even the 0.8B's result limit keeps every tab
    assert len(text) < agent_mod.RESULT_LIMIT["tiny"]


def test_every_tab_reaches_the_user_even_through_a_model(monkeypatch):
    from acchan.tools import browser

    monkeypatch.setattr(browser, "firefox_tabs", lambda: many_tabs())
    # The model calls the tool, then would summarise 8 tabs; the real list wins.
    script = Script(
        [reply(calls=[call("browser_tabs")]), reply("You have tabs 1 to 8 open.")]
    )
    _conv, events = run(
        monkeypatch, script, "anything interesting in the tabs I've got", "tiny"
    )
    final = events[-1]["text"]
    for i in range(1, 32):
        assert f"#{i} " in final
    assert len(script.calls) == 1


def test_list_tools_are_marked_to_show_their_result():
    for name in ("browser_tabs", "list_windows", "list_dir", "list_apps", "recall"):
        assert registry.TOOLS[name].show, name
    assert not registry.TOOLS["open_web"].show


def test_plain_persona_by_default_and_cat_on_request(monkeypatch):
    from acchan import settings

    text = prompts.system_prompt("tiny", ["apps"])
    assert "nya" not in text.lower() and "catgirl" not in text.lower()
    assert "emoji" in text.lower()
    for fast in router.fast_path("pause the music") or []:
        assert "nya" not in fast.reply.lower()
    settings.save({"persona": "cat"})
    assert "catgirl" in prompts.system_prompt("tiny", ["apps"])
    settings.save({"persona": "plain"})
    assert "catgirl" not in prompts.system_prompt("tiny", ["apps"])


def test_tiny_is_offered_a_handful_of_tools_that_fit():
    cases = {
        "open a new firefox window and put wikipedia in it": "open_web",
        "which windows are open right now": "list_windows",
        "move the file ~/a.txt into ~/Documents": "move_path",
        "what's in my downloads folder": "list_dir",
        "turn the brightness down to 30": "set_brightness",
    }
    for text, wanted in cases.items():
        p = router.plan(text, forced_tier="tiny")
        offered = router.rank_tools(text, p.toolsets, router.TINY_TOOLS)
        assert wanted in offered, (text, offered)
        assert len(offered) <= router.TINY_TOOLS


def test_tiny_model_sees_only_the_ranked_tools(monkeypatch):
    script = Script([reply(calls=[call("list_windows")]), reply("done")])
    run(monkeypatch, script, "which windows are open right now please", "tiny")
    offered = script.calls[0]["tools"]
    assert "list_windows" in offered and len(offered) <= router.TINY_TOOLS


def test_claiming_without_calling_gets_a_nudge(monkeypatch):
    monkeypatch.setattr(
        registry.TOOLS["list_windows"], "func", lambda: "firefox: Wikipedia"
    )
    script = Script(
        [
            reply("Let me check your windows for you."),
            reply(calls=[call("list_windows")]),
        ]
    )
    conv, events = run(monkeypatch, script, "check which windows I have open", "tiny")
    nudges = [
        m for m in conv.messages if "Nothing happened" in (m.get("content") or "")
    ]
    assert nudges and "list_windows" in nudges[0]["content"]
    assert "firefox: Wikipedia" in events[-1]["text"]


def test_same_tool_three_times_is_stopped(monkeypatch):
    monkeypatch.setattr(
        registry.TOOLS["ask_document"], "func", lambda source, question: "passage"
    )
    script = Script(
        [
            reply(calls=[call("ask_document", source="~/a.pdf", question="x")]),
            reply(calls=[call("ask_document", source="~/a.pdf", question="y")]),
            reply(calls=[call("ask_document", source="~/a.pdf", question="z")]),
            reply("Here is what I found."),
        ]
    )
    _conv, events = run(monkeypatch, script, "find my notes about x", "small")
    results = [e["result"] for e in events if e["type"] == "result"]
    assert "three times" in results[2]


def test_thinking_toggle_reaches_jan_and_is_shown(monkeypatch):
    from acchan import settings

    seen = {}

    def fake(tier, messages, tools=None, thinking=False, max_tokens=0, **kw):
        seen["thinking"], seen["max"] = thinking, max_tokens
        return llm.Reply(
            content="Because of Rayleigh scattering.", reasoning="Light..."
        )

    monkeypatch.setattr(llm, "stream", fake)
    conv = Conversation(source="test")
    list(agent_mod.Agent(conv).run("why is the sky blue"))
    assert seen["thinking"] is False
    settings.save({"thinking": True})
    events = list(agent_mod.Agent(conv).run("why is the sea blue"))
    assert seen["thinking"] is True
    # no cap by default; with one, thinking gets more room
    assert seen["max"] is None or seen["max"] > agent_mod.REPLY_TOKENS["tiny"]
    assert {"type": "thinking", "text": "Light..."} in events
    one_off = agent_mod.Agent(conv)
    one_off.thinking = False  # a request can override the setting
    list(one_off.run("why is grass green"))
    assert seen["thinking"] is False


def test_replies_are_not_forced_to_be_tiny():
    for tier, sets in (("tiny", []), ("small", []), ("tiny", ["apps"])):
        text = prompts.system_prompt(tier, sets)
        assert "one short sentence" not in text and "one to three short" not in text
    assert "short paragraph" in prompts.system_prompt("tiny", [])


def test_settings_endpoint_round_trip(client):
    assert client.get("/api/settings").json() == {
        "persona": "plain",
        "thinking": False,
        "speak": False,
        "voice": "am_michael",
        "terminal_view": "headless",
        "browser_view": "headless",
        "reply_limit": 0,
    }
    client.post("/api/settings", json={"thinking": True, "junk": 1})
    assert client.get("/api/settings").json()["thinking"] is True


def test_navigate_tools_press_the_right_keys(monkeypatch):
    from acchan.tools import windows

    pressed, typed = [], []
    monkeypatch.setattr(windows, "send_keys", lambda combos: pressed.append(combos))
    monkeypatch.setattr(windows, "type_into", lambda text: typed.append(text))
    registry.call("navigate", {"action": "Go back"})
    registry.call("navigate", {"action": "refresh"})
    registry.call("scroll", {"direction": "down", "times": "2"})
    registry.call("find_on_page", {"text": "exam"})
    assert pressed == [
        ["alt+left"],
        ["f5"],
        ["pagedown", "pagedown"],
        ["ctrl+f"],
        ["enter"],
    ]
    assert typed == ["exam"]
    with pytest.raises(registry.ToolError):
        registry.call("navigate", {"action": "fly"})


def test_no_matching_tool_falls_back_to_working_the_app():
    p = router.plan("do the thing in the settings of qbz for me", forced_tier="small")
    assert "ui" in p.toolsets
    assert "app_controls" in prompts.system_prompt("small", p.toolsets)
    assert "navigate" in router.plan("scroll down a bit in firefox").toolsets


@pytest.mark.parametrize(
    "text",
    [
        "Open file:///tmp/x.html with page_open, then read it with page_read",
        "read https://example.com and tell me what it says",
        "summarise the website www.example.org",
        "take a screenshot of the web page",
    ],
)
def test_reading_web_pages_offers_the_page_tools(text):
    assert "pages" in router.plan(text).toolsets


def test_history_follows_the_model_window_except_tiny(monkeypatch):
    windows = {"big": 131072, "old": 20000}
    monkeypatch.setattr(llm.forge_jan, "context_size", lambda m: windows.get(m))
    big = agent_mod.history_limit("medium", "big")
    assert big == int((131072 - agent_mod.CONTEXT_RESERVE) * agent_mod.CHARS_PER_TOKEN)
    assert big > 300_000
    assert agent_mod.history_limit("tiny", "big") == agent_mod.HISTORY_LIMIT["tiny"]
    assert agent_mod.history_limit("large", "old") == agent_mod.HISTORY_LIMIT["large"]
    assert (
        agent_mod.history_limit("small", "unknown") == agent_mod.HISTORY_LIMIT["small"]
    )


def test_context_size_reads_the_router_preset(tmp_path):
    import forge_jan

    preset = tmp_path / "router.preset.ini"
    preset.write_text(
        "[*]\nctx-size = 8192\n\n[m-big]\nctx-size = 131072\n[m-none]\nmodel = x\n"
    )
    proc = tmp_path / "proc" / "42"
    proc.mkdir(parents=True)
    argv = ["/x/llama-server", "--models-preset", str(preset), "--port", "1"]
    (proc / "cmdline").write_bytes(b"\0".join(a.encode() for a in argv))
    root = str(tmp_path / "proc")
    assert forge_jan.context_size("m-big", root) == 131072
    assert forge_jan.context_size("m-none", root) == 8192
    assert forge_jan.context_size("m-big", str(tmp_path / "empty")) is None


def test_long_entries_copy_the_base_with_a_big_window(tmp_path):
    import forge_jan

    base = tmp_path / "m4b"
    base.mkdir()
    (base / "model.yml").write_text(
        "ctx_size: 20000\nmodel_path: llamacpp/models/m4b/model.gguf\n"
        "n_gpu_layers: 32\nname: Qwen 4B\nsize_bytes: 5\n"
    )
    assert forge_jan.long_entries(["m4b", "missing"], tmp_path) == ["m4b-long"]
    long = (tmp_path / "m4b-long" / "model.yml").read_text()
    assert "ctx_size: 131072" in long and "n_gpu_layers: 32" in long
    assert "model_path: llamacpp/models/m4b/model.gguf" in long
    assert "name: Qwen 4B (long context, Forge apps)" in long
    assert "size_bytes" not in long and "20000" not in long
    (base / "model.yml").write_text(
        (base / "model.yml").read_text().replace("32", "24")
    )
    forge_jan.long_entries(["m4b"], tmp_path)  # tuning on the base carries over
    assert "n_gpu_layers: 24" in (tmp_path / "m4b-long" / "model.yml").read_text()
    assert (base / "model.yml").read_text().startswith("ctx_size: 20000")


def test_bigger_tiers_prefer_long_copies_but_fall_back(monkeypatch):
    monkeypatch.setattr(llm.JAN, "settings", lambda: {"models": {}})
    monkeypatch.setattr(
        llm.forge_jan,
        "models",
        lambda refresh=False: list(llm.BASE_MODELS.values())
        + ["qwen35-0_8b-spectralquant-calib360-q4_k_m"],
    )
    assert llm.model_for("medium") == "Qwen3_5-4B-IQ4_XS"
    monkeypatch.setattr(
        llm.forge_jan,
        "models",
        lambda refresh=False: ["Qwen3_5-4B-IQ4_XS-long", "Qwen3_5-4B-IQ4_XS"],
    )
    assert llm.model_for("medium") == "Qwen3_5-4B-IQ4_XS-long"
    assert llm.DEFAULT_MODELS["tiny"] == ["qwen35-0_8b-spectralquant-calib360-q4_k_m"]


# ------------------------------------------- long files (Emerson's platformer)
class RoomyScript(Script):
    def __call__(self, tier, messages, tools=None, **kw):
        self.budgets = getattr(self, "budgets", []) + [kw.get("max_tokens")]
        return super().__call__(tier, messages, tools, **kw)


def cut_write():
    # a reply that ran out of room inside the call: the arguments come back empty
    r = reply(calls=[{"id": "c9", "name": "write_file", "arguments": "{}"}])
    r.finish = "length"
    return r


def test_a_cut_off_write_is_asked_again_with_room_for_a_whole_file(
    monkeypatch, tmp_path
):
    limit_replies(monkeypatch, 900)
    page = tmp_path / "game" / "index.html"
    script = RoomyScript(
        [
            cut_write(),
            reply(calls=[call("write_file", path=str(page), content="<html>\n")]),
            reply("Saved it."),
        ]
    )
    conv, events = run(monkeypatch, script, "write my platformer to a file")
    assert script.budgets[1] >= script.budgets[0] + 5000
    assert page.read_text() == "<html>\n"
    assert not any("needs path" in str(e.get("result", "")) for e in events)


def test_a_file_too_long_even_then_is_written_in_parts(monkeypatch):
    script = RoomyScript(
        [cut_write(), cut_write(), reply("I'll write it in parts.")] + [reply("ok")] * 3
    )
    conv, events = run(monkeypatch, script, "write my platformer to a file")
    result = next(e for e in events if e["type"] == "result")
    assert not result["ok"] and "append_file" in result["result"]


def test_append_file_adds_to_the_end(tmp_path):
    from acchan.tools import files

    page = tmp_path / "a.html"
    files.write_file(str(page), "one\n")
    assert "2 lines" in files.append_file(str(page), "two\n")
    assert page.read_text() == "one\ntwo\n"


def test_claiming_a_file_after_every_write_failed_gets_a_plain_note(monkeypatch):
    script = Script(
        [reply(calls=[call("write_file")])] + [reply("I created the game!")] * 4
    )
    conv, events = run(monkeypatch, script, "make me a game file")
    assert "No file was saved" in events[-1]["text"]


# ------------------------------------------ reply length and the Jan prompt
def limit_replies(monkeypatch, n):
    from acchan import settings as settings_mod

    real = settings_mod.load
    monkeypatch.setattr(settings_mod, "load", lambda: {**real(), "reply_limit": n})


def test_replies_have_no_cap_by_default(monkeypatch):
    # Emerson, 2026-09-27: "reply cap limitless"; the model's window is the limit
    script = RoomyScript([reply("Hi there, all done.")] * 2)
    run(monkeypatch, script, "write a long story about a dragon to me")
    assert script.budgets[0] is None


def test_a_reply_limit_setting_caps_replies(monkeypatch):
    limit_replies(monkeypatch, 3000)
    script = RoomyScript([reply("Hi there, all done.")] * 2)
    run(monkeypatch, script, "write a long story about a dragon to me")
    assert 3000 <= script.budgets[0] < 6000


def test_the_prompt_teaches_long_files_and_shell_syntax():
    from acchan import prompts

    big = prompts.system_prompt("large", ["files", "shell"])
    tiny = prompts.system_prompt("tiny", ["files", "shell"])
    assert "append_file" in big and "append_file" in tiny
    assert "&&" in big and "index.html" in big
    assert len(tiny) < len(big)
