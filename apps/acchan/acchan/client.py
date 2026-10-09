"""Running a message from a client (the terminal app, one-shot CLI).

Prefers the backend at 127.0.0.1:8451, so every client shares one Jan lane
and one conversation store; falls back to running the agent in this process
when the backend is not up.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Iterator

BACKEND = os.environ.get("ACCHAN_URL", "http://127.0.0.1:8451")


def backend_up() -> bool:
    try:
        with urllib.request.urlopen(BACKEND + "/api/status", timeout=2) as response:
            return response.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


def send(
    text: str,
    conversation: str | None,
    tier: str | None,
    cwd: str | None,
    source: str = "tui",
) -> Iterator[dict]:
    """Events for one message. The first event is {"type": "start", "conversation": id}."""
    if backend_up():
        body = json.dumps(
            {
                "text": text,
                "conversation": conversation,
                "tier": tier,
                "cwd": cwd,
                "source": source,
            }
        ).encode()
        request = urllib.request.Request(
            BACKEND + "/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=3600) as response:
            for raw in response:
                line = raw.decode("utf-8", "replace").strip()
                if line.startswith("data:"):
                    yield json.loads(line[5:])
        return
    from .agent import Agent
    from .conversation import Conversation

    conv = (
        Conversation.load(conversation) if conversation else Conversation(source=source)
    )
    yield {"type": "start", "conversation": conv.id, "local": True}
    yield from Agent(conv, cwd=cwd, forced_tier=tier).run(text)


def stop(conversation: str | None) -> None:
    try:
        body = json.dumps({"conversation": conversation}).encode()
        request = urllib.request.Request(
            BACKEND + "/api/stop",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(request, timeout=3).close()
    except (urllib.error.URLError, OSError):
        pass
