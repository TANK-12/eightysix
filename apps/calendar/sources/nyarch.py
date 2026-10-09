"""What Emerson says to Nyarch Assistant. Its history (a pickle) has no times,
so the first read only takes note of what is there; later messages are
logged at the time they are noticed. The pickle is read with a locked-down
unpickler that refuses anything but plain data, so a file cannot run code."""

from __future__ import annotations

import os
import pickle
import time
from pathlib import Path

NAME = "nyarch"
LABEL = "Nyarch Assistant"
DESCRIPTION = "New messages to Nyarch, logged when noticed (its history has no times)."
DEFAULT_ON = True
INTERVAL = 60

PATH = Path(
    os.environ.get("CALENDAR_NYARCH_CHATS")
    or Path.home() / ".var/app/moe.nyarchlinux.assistant/datachats.pkl"
)


class PlainData(pickle.Unpickler):
    def find_class(self, module, name):
        raise pickle.UnpicklingError(f"not plain data: {module}.{name}")


def read_chats(path: Path) -> dict:
    with path.open("rb") as f:
        data = PlainData(f).load()
    chats = data.get("chats") if isinstance(data, dict) else None
    return chats if isinstance(chats, dict) else {}


def collect(state: dict, path: Path = PATH, now: float | None = None) -> list[dict]:
    if not path.is_file():
        return []
    mtime = path.stat().st_mtime
    if state.get("mtime") == mtime:
        return []
    try:
        chats = read_chats(path)
    except (pickle.UnpicklingError, EOFError, OSError, ValueError, AttributeError):
        return []
    counts = state.setdefault("counts", {})
    first = not state.get("mtime")
    state["mtime"] = mtime
    events = []
    ts = now or time.time()
    for chat in chats.values():
        if not isinstance(chat, dict):
            continue
        cid = str(chat.get("id") or chat.get("name"))
        messages = chat.get("chat") or []
        before = counts.get(cid, 0)
        counts[cid] = len(messages)
        if first:
            continue
        for i, m in enumerate(messages[before:], start=before):
            if isinstance(m, dict) and m.get("User") == "User" and m.get("Message"):
                events.append(
                    {
                        "ts": ts,
                        "source": NAME,
                        "kind": "said",
                        "title": str(m["Message"])[:200],
                        "tags": [str(chat.get("name") or "")[:30]],
                        "key": f"nyarch:{cid}:{i}",
                    }
                )
    return events
