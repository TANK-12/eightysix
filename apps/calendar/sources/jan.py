"""Conversations in the Jan app: each thread, and what Emerson typed there."""

from __future__ import annotations

import json
import os
from pathlib import Path

NAME = "jan"
LABEL = "Jan"
DESCRIPTION = "Threads in the Jan app and your messages in them."
DEFAULT_ON = True
INTERVAL = 120

ROOT = Path(
    os.environ.get("CALENDAR_JAN_THREADS")
    or Path.home() / ".var/app/ai.jan.Jan/data/Jan/data/threads"
)


def text_of(message: dict) -> str:
    parts = []
    for block in message.get("content") or []:
        if isinstance(block, dict) and block.get("type") == "text":
            value = (block.get("text") or {}).get("value", "")
            parts.append(value)
    return " ".join(parts).strip()


def collect(state: dict, root: Path = ROOT) -> list[dict]:
    seen = state.setdefault("sizes", {})
    events: list[dict] = []
    if not root.is_dir():
        return events
    for folder in root.iterdir():
        messages = folder / "messages.jsonl"
        if not messages.is_file():
            continue
        size = messages.stat().st_size
        if seen.get(folder.name) == size:
            continue
        seen[folder.name] = size
        title = "Jan thread"
        try:
            title = (
                json.loads((folder / "thread.json").read_text()).get("title") or title
            )
        except (OSError, ValueError):
            pass
        first = True
        for raw in messages.read_text(errors="replace").splitlines():
            try:
                m = json.loads(raw)
            except ValueError:
                continue
            ts = (m.get("created_at") or 0) / 1000
            if not ts:
                continue
            if first:
                events.append(
                    {
                        "ts": ts,
                        "source": NAME,
                        "kind": "session",
                        "title": f"Jan: {title}"[:200],
                        "key": f"jan:thread:{folder.name}",
                    }
                )
                first = False
            if m.get("role") == "user":
                text = text_of(m)
                if text:
                    events.append(
                        {
                            "ts": ts,
                            "source": NAME,
                            "kind": "said",
                            "title": text[:200],
                            "tags": [str(title)[:30]],
                            "key": f"jan:{m.get('id') or ts}",
                        }
                    )
    return events
