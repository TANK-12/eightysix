"""Crew boards (~/.claude/crew/<crew>/board.json, written by the crew skill):
the Crew Room's reader for tasks, claims and log, plus the notes and
personas from crew.peek(), which reads the file without taking the lock."""

from __future__ import annotations

import time

ACTIVE_DAYS = 2
# A note to Emerson older than this stays on its crew's list but leaves
# "Needs you": replies like "on it" are rarely acked and would pile up.
NEEDS_YOU_HOURS = 24
NOTES_SHOWN = 40
QUIET_NOTES_SHOWN = 10
MEMBER_RECENT_HOURS = 6
EMERSON = "Emerson"


def last_activity(board: dict) -> float:
    times = [m.get("last_seen") or 0 for m in (board.get("members") or {}).values()]
    times += [x.get("t") or 0 for x in board.get("log") or []]
    times += [n.get("t") or 0 for n in board.get("notes") or []]
    return max(times, default=0)


def shape(
    summary: dict,
    board: dict,
    crew_mod,
    now: float | None = None,
    live: set[str] | frozenset[str] = frozenset(),
) -> dict:
    """One crew for the page. summary is the Crew Room's entry, board the raw
    file (for notes and personas), live the names and session ids running now.
    A shared board (forge) remembers every session that ever joined, so only
    members seen lately, running now, holding a task or leading are sent."""
    now = time.time() if now is None else now
    members = board.get("members") or {}
    notes = []
    for n in (board.get("notes") or [])[-NOTES_SHOWN:]:
        to = n.get("to")
        sender = n.get("from", "")
        notes.append(
            {
                "id": n.get("id"),
                "t": n.get("t") or 0,
                "from": sender,
                "from_persona": (members.get(sender) or {}).get("persona", ""),
                "to": to,
                "text": n.get("text", ""),
                "re": n.get("re"),
                "fyi": bool(n.get("fyi")),
                "for_emerson": to == EMERSON
                and bool(crew_mod.open_for(board, n, EMERSON)),
                "acked": bool(n.get("ack")),
            }
        )
    last = last_activity(board)
    owners = {t.get("owner") for t in summary.get("tasks") or []}

    def current(m: dict) -> bool:
        raw = members.get(m["name"]) or {}
        return (
            now - (m.get("last_seen") or 0) < MEMBER_RECENT_HOURS * 3600
            or m["name"] in owners
            or m["name"] == summary.get("commander")
            or m["name"] in live
            or (raw.get("session") or "") in live
        )

    shown = [m for m in summary.get("members") or [] if current(m)]
    active = now - last < ACTIVE_DAYS * 86400
    if not active:
        notes = notes[-QUIET_NOTES_SHOWN:]
    return {
        "name": summary.get("name") or board.get("crew") or "",
        "commander": summary.get("commander"),
        "goal": summary.get("goal", ""),
        "members": [
            {
                **m,
                "persona": (members.get(m["name"]) or {}).get("persona", ""),
                "session": (members.get(m["name"]) or {}).get("session", ""),
                "slot": (members.get(m["name"]) or {}).get("slot"),
            }
            for m in shown
        ],
        "members_hidden": len(summary.get("members") or []) - len(shown),
        "tasks": summary.get("tasks") or [],
        "claims": summary.get("claims") or [],
        "log": summary.get("log") or [],
        "notes": notes[::-1],
        "last": last,
        "active": active,
    }


def collect(
    room_crews: list[dict],
    crew_mod,
    now: float | None = None,
    live: set[str] | frozenset[str] = frozenset(),
):
    """(crews for the page, raw boards for sessions.build), newest first."""
    out, raws = [], []
    for summary in room_crews:
        board = crew_mod.peek(summary["name"])
        board.setdefault("crew", summary["name"])
        raws.append(board)
        out.append(shape(summary, board, crew_mod, now, live))
    out.sort(key=lambda c: -c["last"])
    return out, raws


def notes_for_emerson(crews: list[dict], now: float | None = None) -> list[dict]:
    now = time.time() if now is None else now
    return [
        {**n, "crew": c["name"]}
        for c in crews
        for n in c["notes"]
        if n["for_emerson"] and now - n["t"] < NEEDS_YOU_HOURS * 3600
    ]
