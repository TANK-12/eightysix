"""Everything the page shows, gathered in one call, plus a signature so the
page can ask "anything new?" and get a two-field answer when nothing is."""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from typing import Callable

from mc import borrow, crews as crews_view, graph, relay_view, sessions as sessions_view

# Keys that tick on every read without anything having happened.
VOLATILE = {"now", "idle_seconds", "boss_seen"}
_ended_cache: dict[tuple, dict] = {}


@dataclass
class Sources:
    """Where to read. Tests point every field at a fixture tree."""

    claude_dir: str = field(default_factory=lambda: os.path.expanduser("~/.claude"))
    proc_dir: str = "/proc"
    forge_apps_dir: str = field(default_factory=lambda: borrow.APPS)
    # -> {session id: {id, name, title}} from the Claude app
    conversations: Callable[[], dict] | None = None

    def context(self, now: float):
        borrow.setup()
        from context import Context  # pyright: ignore[reportMissingImports]

        return Context(
            claude_dir=self.claude_dir,
            proc_dir=self.proc_dir,
            now=now,
            clock_ticks=os.sysconf("SC_CLK_TCK"),
            cpu_count=os.cpu_count() or 1,
            forge_apps_dir=self.forge_apps_dir,
        )


def signature(data) -> str:
    def strip(x):
        if isinstance(x, dict):
            return {k: strip(v) for k, v in x.items() if k not in VOLATILE}
        if isinstance(x, list):
            return [strip(v) for v in x]
        return x

    raw = json.dumps(strip(data), sort_keys=True, default=str)
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def _ended_summary(claude_dir: str):
    borrow.setup()
    import transcripts  # pyright: ignore[reportMissingImports]
    from sources import sessions as live  # pyright: ignore[reportMissingImports]

    from context import Context  # pyright: ignore[reportMissingImports]

    ctx = Context(claude_dir=claude_dir)

    def summarize(session_id: str) -> dict | None:
        path = live.find_transcript(ctx, session_id)
        if not path:
            return None
        try:
            st = os.stat(path)
        except OSError:
            return None
        key = (path, st.st_mtime, st.st_size)
        if key not in _ended_cache:
            if len(_ended_cache) > 400:
                _ended_cache.clear()
            _ended_cache[key] = transcripts.summarize(transcripts.read_tail(path))
        return _ended_cache[key]

    return summarize


def collect(
    src: Sources | None = None,
    now: float | None = None,
) -> dict:
    """Everything the page shows."""
    src = src or Sources()
    now = time.time() if now is None else now
    borrow.setup()
    import sources as room_sources  # pyright: ignore[reportMissingImports]
    import items  # pyright: ignore[reportMissingImports]
    import runs  # pyright: ignore[reportMissingImports]
    import store  # pyright: ignore[reportMissingImports]

    errors: dict[str, str] = {}
    room = room_sources.collect_all(src.context(now))
    errors.update(room.get("errors") or {})

    try:
        relay = relay_view.snapshot(store, items, runs, now)
    except Exception as exc:  # Relay's files are someone else's; never blank the page
        relay = {"present": False}
        errors["relay"] = f"{type(exc).__name__}: {exc}"

    crew_mod = borrow.crew()
    live = {s.get("name", "") for s in room.get("sessions") or []} | {
        s.get("id", "") for s in room.get("sessions") or []
    }
    crew_list, boards = crews_view.collect(
        room.get("crews") or [], crew_mod, now, live - {""}
    )

    try:
        everyone_rows = borrow.everyone().sessions(
            __import__("pathlib").Path(src.claude_dir, "sessions"),
            __import__("pathlib").Path(src.claude_dir, "projects"),
            now,
        )
    except Exception as exc:
        everyone_rows = []
        errors["ended"] = f"{type(exc).__name__}: {exc}"

    conversations: dict = {}
    if src.conversations is not None:
        try:
            conversations = src.conversations() or {}
        except Exception as exc:
            errors["claude_app"] = f"{type(exc).__name__}: {exc}"

    rows = sessions_view.build(
        room,
        everyone_rows,
        boards,
        conversations,
        relay_view.runs_by_session(relay),
        _ended_summary(src.claude_dir),
    )
    needs = [
        {
            "kind": "session",
            "session": r["id"],
            "label": r["label"] or r["name"],
            "text": r["action"],
        }
        for r in rows
        if r["group"] == "needs_you"
    ]
    needs += [
        {
            "kind": "note",
            "crew": n["crew"],
            "note": n["id"],
            "label": n["from_persona"] or n["from"],
            "text": n["text"],
        }
        for n in crews_view.notes_for_emerson(crew_list, now)
    ]
    needs += [
        {
            "kind": "relay",
            "task": t["task"],
            "label": f"Relay task {t['task']}",
            "text": t["title"],
        }
        for t in relay_view.needs_you(relay)
    ]
    jan = room.get("jan") if isinstance(room.get("jan"), dict) else {}
    data = {
        "sessions": rows,
        "counts": sessions_view.counts(rows),
        "needs_you": needs,
        "crews": crew_list,
        "relay": relay,
        "jan": jan,
        "graph": graph.build(rows, crew_list, relay, jan),
        "errors": errors,
    }
    data["sig"] = signature(data)
    data["now"] = now
    return data
