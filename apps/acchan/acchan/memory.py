"""Long-term memory: short facts Acchan keeps between chats.

Stored as one JSON list in ~/.local/share/forge/acchan/memory.json. The
newest facts go into every system prompt, for every model size, so even the
0.8B knows them without having to call a tool. They change only when a fact
is added or removed, so the prompt's cached start stays the same otherwise.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

DATA = Path(os.environ.get("ACCHAN_DATA", Path.home() / ".local/share/forge/acchan"))
IN_PROMPT = 15  # newest facts written into the system prompt
LIMIT = 300  # facts kept at most; the oldest go first


def _path() -> Path:
    return DATA / "memory.json"


def _load() -> list[dict]:
    try:
        return json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _save(rows: list[dict]) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(rows[-LIMIT:], ensure_ascii=False, indent=1), "utf-8")
    tmp.replace(path)


def facts() -> list[str]:
    return [row["fact"] for row in _load()]


def add(fact: str) -> bool:
    """Store a fact; False when it was already known."""
    fact = " ".join(fact.split())
    rows = _load()
    if any(row["fact"].lower() == fact.lower() for row in rows):
        return False
    rows.append({"fact": fact, "at": time.strftime("%Y-%m-%d")})
    _save(rows)
    return True


def search(query: str) -> list[str]:
    words = [w for w in query.lower().split() if len(w) > 2]
    rows = facts()
    if not words:
        return rows[-IN_PROMPT:]
    return [f for f in rows if any(w in f.lower() for w in words)]


def remove(text: str) -> list[str]:
    """Remove every fact containing `text`; returns what was removed."""
    rows = _load()
    gone = [r["fact"] for r in rows if text.lower() in r["fact"].lower()]
    if gone:
        _save([r for r in rows if r["fact"] not in gone])
    return gone


def for_prompt() -> str:
    recent = facts()[-IN_PROMPT:]
    if not recent:
        return ""
    return "What you remember about the user:\n" + "\n".join(f"- {f}" for f in recent)
