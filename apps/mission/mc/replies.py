"""Messages Emerson sends from Mission Control, and the answers that come back.

A "Note to everyone" or a "Message" to one session is a note on a crew board
(the notes hook hands it over at each session's next step). Each one sent
from here is written down in MESSAGES_FILE, so its answers can be gathered
under it, one line per session:

- a board reply: `crew ack <board> <me> <id> --note "..."` posts the answer
  back to Emerson as a note with re=<id> (a plain "ok" ack only marks it seen);
- an answer in chat: the session's transcript shows the note being handed
  over (convo.handed_notes), and the first reply it wrote after that.

Answers are copied into the file as they are found, so they outlive the board
(it keeps only its last 200 notes) and the transcript tail.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from datetime import datetime
from typing import Callable, Iterable

from mc import borrow, convo

EMERSON = "Emerson"
KEEP = 60
SCAN_START_BYTES = 4 * 1024 * 1024
ASK_ALL = (
    "Emerson asks everyone (answer with crew ack --note so your reply reaches"
    " his Mission Control, then carry on): "
)

_lock = threading.Lock()
_scans: dict[str, dict] = {}


def _when(at: object) -> float:
    """Seconds since the epoch from a board time (number) or a transcript
    time (ISO text); 0 when unknown."""
    if isinstance(at, (int, float)):
        return float(at)
    if isinstance(at, str) and at:
        try:
            return datetime.fromisoformat(at.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return 0.0
    return 0.0


def data_dir() -> str:
    return os.environ.get("MISSION_DATA_DIR") or os.path.expanduser(
        "~/.local/share/forge/mission"
    )


def store_path() -> str:
    return os.path.join(data_dir(), "messages.json")


def load() -> dict:
    try:
        with open(store_path(), encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {"messages": []}
    if not isinstance(data, dict) or not isinstance(data.get("messages"), list):
        return {"messages": []}
    return data


def save(data: dict) -> None:
    os.makedirs(data_dir(), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=data_dir(), prefix=".messages-")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1)
    os.replace(tmp, store_path())


def record(
    crew: str,
    note_id: int,
    text: str,
    kind: str = "all",
    to: str | None = None,
    session: str | None = None,
) -> dict:
    """Write down a message just posted, newest first, keeping the last KEEP."""
    msg = {
        "id": int(note_id),
        "crew": crew,
        "kind": kind,
        "to": to,
        "session": session,
        "text": text,
        "at": time.time(),
        "replies": {},
    }
    with _lock:
        data = load()
        data["messages"] = [msg] + [
            m
            for m in data["messages"]
            if not (m.get("id") == msg["id"] and m.get("crew") == crew)
        ]
        del data["messages"][KEEP:]
        save(data)
    return msg


def broadcast(text: str, crew: str = "forge") -> dict:
    """A note to everyone on a board that asks for answers by board reply."""
    crew_mod = borrow.crew()
    with crew_mod.open_board(crew) as board:
        note = crew_mod.add_note(board, EMERSON, ASK_ALL + text)
    return record(crew, note["id"], text, "all")


def scan_transcript(path: str) -> list[dict]:
    """The board notes handed to one transcript and the replies after them,
    read on from where the last call stopped."""
    try:
        size = os.path.getsize(path)
    except OSError:
        return []
    state = _scans.get(path)
    if state is None or size < state["offset"]:
        start = max(0, size - SCAN_START_BYTES)
        state = {"offset": start, "aligned": start == 0, "found": {}}
        _scans[path] = state
    if size > state["offset"]:
        start = state["offset"]
        with open(path, "rb") as fh:
            if not state["aligned"]:  # a first read from mid-file: skip the cut line
                fh.seek(start)
                fh.readline()
                start = fh.tell()
            end = convo._whole_end(fh, size)
        if end > start:
            pending = [n for n in state["found"].values() if not n.get("reply")]
            for item in convo.handed_notes(path, start, end, carry=pending):
                state["found"][item["note"]] = item
            state["offset"], state["aligned"] = end, True
    return list(state["found"].values())


def _peek(crew: str, cache: dict) -> dict:
    if crew not in cache:
        try:
            cache[crew] = borrow.crew().peek(crew)
        except Exception:
            cache[crew] = {}
    return cache[crew]


def threads(
    sessions: Iterable[dict],
    transcript: Callable[[str], str | None],
) -> list[dict]:
    """Every recorded message with its answers, newest first.

    `sessions` are Mission Control's session rows (id, name, group,
    last_active); `transcript` finds a session's transcript path."""
    rows = list(sessions)
    by_name = {s.get("name"): s for s in rows if s.get("name")}
    boards: dict[str, dict] = {}
    with _lock:
        data = load()
        changed = False
        out = []
        for msg in data["messages"]:
            replies = msg.setdefault("replies", {})
            board = _peek(msg["crew"], boards)
            notes = board.get("notes") or []
            note = next((n for n in notes if n.get("id") == msg["id"]), None)
            seen = set((note or {}).get("done_by") or [])
            if note and note.get("ack"):
                seen.add(note["ack"].get("by"))
            for n in notes:
                who = n.get("from")
                if n.get("re") == msg["id"] and who and who != EMERSON:
                    got = replies.get(who)
                    if (
                        not got
                        or got.get("via") != "board"
                        or got.get("note") != n["id"]
                    ):
                        replies[who] = {
                            "text": n.get("text", ""),
                            "at": n.get("t"),
                            "via": "board",
                            "note": n["id"],
                        }
                        changed = True
            for s in rows:
                name = s.get("name")
                if not name or name in replies:
                    continue
                if msg["kind"] == "one" and name != msg.get("to"):
                    continue
                if (s.get("last_active") or 0) < msg["at"] - 60:
                    continue
                path = transcript(s["id"])
                if not path:
                    continue
                for item in scan_transcript(path):
                    if item["note"] == msg["id"]:
                        seen.add(name)
                        if item.get("reply"):
                            replies[name] = {
                                "text": item["reply"],
                                "at": item.get("reply_at"),
                                "via": "chat",
                            }
                            changed = True
            if msg["kind"] == "one":
                expected = [msg["to"]] if msg.get("to") else []
            else:
                expected = [
                    s["name"]
                    for s in rows
                    if s.get("name") and s.get("group") not in ("ended",)
                ]
            answered = set(replies)
            out.append(
                {
                    **{
                        k: msg.get(k)
                        for k in ("id", "crew", "kind", "to", "text", "at")
                    },
                    "replies": [
                        {
                            "from": who,
                            "session": (by_name.get(who) or {}).get("id"),
                            **r,
                        }
                        for who, r in sorted(
                            replies.items(), key=lambda kv: _when(kv[1].get("at"))
                        )
                    ],
                    "seen": sorted(n for n in seen - answered if n),
                    "waiting": sorted(
                        n for n in expected if n not in answered and n not in seen
                    ),
                }
            )
        if changed:
            save(data)
    return out
