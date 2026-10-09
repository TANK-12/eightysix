"""A greeting gets one light model call, and a dropped client stops its run.

WHY THIS EXISTS
    "any model, and 4b with think, takes an ungodly time to respond to hey"
    (Emerson, 2026-09-25). A plain "hey" went through the full tool loop: the
    Think setting applied to it (up to 2000 extra tokens), the whole chat
    history went along, a history summary could run first, an empty or failed
    reply stepped up to a bigger model (another model load), and a reply the
    client had stopped reading kept Jan busy for the next message.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from acchan import agent as agent_mod  # noqa: E402
from acchan import llm, router  # noqa: E402
from acchan.conversation import Conversation  # noqa: E402


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("ACCHAN_DATA", str(tmp_path / "data"))
    import acchan.conversation as conversation
    import acchan.memory as memory_mod

    monkeypatch.setattr(conversation, "DATA", tmp_path / "data")
    monkeypatch.setattr(memory_mod, "DATA", tmp_path / "data")


class Recorder:
    """Stands in for llm.stream and llm.complete, keeping every argument."""

    def __init__(self, content="Hey! What are we doing today?", error=None):
        self.content, self.error = content, error
        self.calls: list[dict] = []
        self.summaries = 0

    def stream(self, tier, messages, tools=None, **kw):
        self.calls.append({"tier": tier, "messages": messages, "tools": tools, **kw})
        if self.error:
            raise llm.LLMError(self.error)
        return llm.Reply(content=self.content, model="fake")

    def complete(self, *a, **kw):
        self.summaries += 1
        return "summary"


def long_chat() -> Conversation:
    conv = Conversation(source="test")
    conv.summary = "They talked about tabs."
    for i in range(40):
        conv.add({"role": "user", "content": f"open thing {i} " + "x" * 300})
        conv.add(
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": f"c{i}",
                        "type": "function",
                        "function": {"name": "launch_app", "arguments": "{}"},
                    }
                ],
            }
        )
        conv.add({"role": "tool", "tool_call_id": f"c{i}", "content": "y" * 500})
        conv.add({"role": "assistant", "content": f"Opened thing {i}."})
    conv.toolsets = ["apps", "ui"]
    conv.tier = "medium"
    return conv


def run(monkeypatch, fake, text, conv=None, thinking=True):
    monkeypatch.setattr(llm, "stream", fake.stream)
    monkeypatch.setattr(llm, "complete", fake.complete)
    a = agent_mod.Agent(conv or long_chat())
    a.thinking = thinking
    return a, list(a.run(text))


@pytest.mark.parametrize(
    "text", ["hey", "hi!", "Hello", "thanks", "thank you so much", "good morning"]
)
def test_greetings_are_small_talk(text):
    assert router.is_small_talk(text)


@pytest.mark.parametrize(
    "text",
    [
        "hey open firefox",
        "hey can you find my lecture notes",
        "hello, list my tabs",
        "write me a story about a dragon",
        "what is on my screen",
    ],
)
def test_requests_are_not_small_talk(text):
    assert not router.is_small_talk(text)


def test_hey_is_one_light_call(monkeypatch):
    fake = Recorder()
    a, events = run(monkeypatch, fake, "hey")
    assert len(fake.calls) == 1
    sent = fake.calls[0]
    assert sent["tools"] is None
    assert sent["thinking"] is False
    assert sent["max_tokens"] <= 200
    assert sent["tier"] == "medium"  # the chat's model: no switch, no reload
    roles = [m["role"] for m in sent["messages"]]
    assert "tool" not in roles and roles[0] == "system"
    assert len(sent["messages"]) <= 1 + agent_mod.SMALL_TALK_TURNS
    assert sent["messages"][-1]["content"].endswith("hey")
    assert sum(len(m["content"]) for m in sent["messages"]) < 5000
    assert fake.summaries == 0  # no history summary before a greeting
    done = events[-1]
    assert done["type"] == "done" and done["text"] == fake.content
    assert done["stats"]["small_talk"] is True
    assert a.conv.messages[-1] == {"role": "assistant", "content": fake.content}


def test_a_failed_greeting_does_not_load_a_bigger_model(monkeypatch):
    fake = Recorder(error="timed out")
    _, events = run(monkeypatch, fake, "hey")
    assert len(fake.calls) == 1
    assert not any(e["type"] == "escalate" for e in events)
    assert events[-1]["type"] == "error"


def test_an_empty_greeting_reply_is_not_retried_on_a_bigger_model(monkeypatch):
    fake = Recorder(content="")
    _, events = run(monkeypatch, fake, "hey")
    assert len(fake.calls) == 1
    assert events[-1]["type"] == "done" and events[-1]["text"]


def test_a_real_request_still_gets_tools(monkeypatch):
    fake = Recorder(content="Done.")
    run(monkeypatch, fake, "hey can you find my lecture notes", thinking=False)
    assert fake.calls and fake.calls[0]["tools"]


# ------------------------------------------------------------ dropped clients
class FakeAgent:
    def __init__(self):
        self.stopped = False
        self.conv = Conversation(source="test")

    def stop(self):
        self.stopped = True


def test_a_dropped_client_stops_the_run():
    import queue

    import web_app

    agent, events = FakeAgent(), queue.Queue()
    events.put({"type": "route"})
    stream = web_app._sse(agent, events)  # type: ignore[arg-type]
    first = next(stream)
    assert json.loads(first.removeprefix("data: "))["type"] == "start"
    next(stream)
    stream.close()  # the page or terminal went away mid-reply
    assert agent.stopped


def test_a_finished_run_is_not_stopped():
    import queue

    import web_app

    agent, events = FakeAgent(), queue.Queue()
    events.put({"type": "done"})
    events.put(None)
    assert len(list(web_app._sse(agent, events))) == 2  # type: ignore[arg-type]
    assert not agent.stopped


def test_a_run_whose_client_left_while_queued_never_starts():
    import web_app

    class Queued(FakeAgent):
        def __init__(self):
            super().__init__()
            import threading

            self.stop_event = threading.Event()
            self.stop_event.set()
            self.ran = False

        def run(self, text):
            self.ran = True
            yield {"type": "done"}

    agent = Queued()
    events = web_app._events(agent, "hey")  # type: ignore[arg-type]
    assert events.get(timeout=5) is None
    assert not agent.ran


def test_small_talk_can_be_switched_off_for_timing(monkeypatch):
    fake = Recorder()
    monkeypatch.setattr(llm, "stream", fake.stream)
    a = agent_mod.Agent(Conversation(source="test"))
    a.thinking, a.small_talk = True, False
    list(a.run("hey"))
    assert fake.calls[0]["thinking"] is True  # the old, full path
