"""The terminal app, driven headless through Textual's test harness with a
scripted client (no backend, no Jan)."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from acchan import client, tui  # noqa: E402


def test_tui_sends_and_shows_tool_cards_and_reply(monkeypatch, tmp_path):
    import acchan.conversation as conversation

    monkeypatch.setattr(conversation, "DATA", tmp_path)
    monkeypatch.setattr(client, "backend_up", lambda: False)
    sent = []

    def fake_send(text, conv, tier, cwd, source="tui"):
        sent.append((text, tier, source))
        yield {"type": "start", "conversation": "c-1"}
        yield {"type": "tool", "id": "t1", "name": "list_dir", "args": {"path": "~"}}
        yield {
            "type": "result",
            "id": "t1",
            "name": "list_dir",
            "ok": True,
            "result": "Documents/\nMusic/",
        }
        yield {"type": "text", "delta": "You have Documents and Music."}
        yield {
            "type": "done",
            "text": "You have Documents and Music.",
            "stats": {"seconds": 1.2, "tier": "small"},
        }

    monkeypatch.setattr(client, "send", fake_send)

    async def scenario():
        app = tui.build_app(None, None)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.press("ctrl+t")  # auto -> switch per message
            await pilot.press("ctrl+t")  # -> 0.8B
            await pilot.press("ctrl+t")  # -> 2B
            box = app.query_one("#input")
            box.value = "what's in my home folder"  # type: ignore[attr-defined]
            await pilot.press("enter")
            for _ in range(50):
                await pilot.pause(0.05)
                if not app.busy:  # type: ignore[attr-defined]
                    break
            await pilot.pause(0.1)
            text = " ".join(str(w.render()) for w in app.query("Static"))
            titles = [c.title for c in app.query("Collapsible")]  # type: ignore[attr-defined]
            return app.conversation, text, titles  # type: ignore[attr-defined]

    conv, text, titles = asyncio.run(scenario())
    assert sent == [("what's in my home folder", "small", "tui")]
    assert conv == "c-1"
    assert any(t.startswith("✓") and "list_dir" in t for t in titles)
    assert "small · 1.2s" in text
