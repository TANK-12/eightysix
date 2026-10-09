"""Every Claude session on the laptop as one list: live ones from the Crew
Room's readers, ended ones from the Claude app's everyone.py, each with its
helpers, crews, Relay task and Claude-app tab.

Groups, in the order the page shows them:
  needs_you  the session waits on Emerson (its file says status "waiting")
  working    busy and wrote something in the last 5 minutes
  idle       alive, not working
  ended      its process is gone (kept for everyone.COLD_DAYS)
"""

from __future__ import annotations

import os
import re

GROUPS = ("needs_you", "working", "idle", "ended")
WINDOW = 200_000
BIG_WINDOW = 1_000_000
ENDED_SHOWN = 30
FEED_SHOWN = 6
HELPERS_SHOWN = 12
_CODE = re.compile(r"^[a-z]{1,3}\d{1,3}$")


def context_window(model: str | None, used: int = 0) -> int:
    """Tokens the model can hold: 1M for a [1m] model id, else 200k. A
    session already holding more than 200k is on the 1M window (Opus 5.5
    runs with 1M under a plain model id, ultracode sessions among them)."""
    if (model and "[1m]" in model.lower()) or used > WINDOW:
        return BIG_WINDOW
    return WINDOW


def group_of(status: str, busy: bool, alive: bool) -> str:
    if not alive:
        return "ended"
    if status == "waiting":
        return "needs_you"
    return "working" if busy else "idle"


def _mtime(path: str | None) -> float:
    try:
        return os.path.getmtime(path) if path else 0.0
    except OSError:
        return 0.0


def _same_task(description: str, title: str) -> bool:
    """A helper's Agent description against a crew task title: equal, or the
    same short code in front ("H1 Mission Control" and "H1 Mission Control app")."""
    a, b = description.strip().lower(), title.strip().lower()
    if not a or not b:
        return False
    if a == b or a.startswith(b) or b.startswith(a):
        return True
    ha, hb = a.split()[0], b.split()[0]
    return ha == hb and bool(_CODE.match(ha))


def membership(boards: list[dict]) -> dict[str, list[dict]]:
    """Session id or board name -> the crews it is in. Board members carry
    their session id when they joined from a live session."""
    found: dict[str, list[dict]] = {}
    for board in boards:
        for name, member in (board.get("members") or {}).items():
            entry = {
                "crew": board.get("crew") or "",
                "member": name,
                "role": (member or {}).get("role", ""),
                "persona": (member or {}).get("persona", ""),
                "commander": board.get("commander") == name,
            }
            for key in {name, (member or {}).get("session") or ""} - {""}:
                found.setdefault(key, []).append(entry)
    return {key: one_per_crew(entries) for key, entries in found.items()}


def one_per_crew(entries: list[dict]) -> list[dict]:
    """One session can join a board under several names: one entry per
    crew, the commander's if any of them leads it."""
    by_crew: dict[str, dict] = {}
    for entry in entries:
        kept = by_crew.get(entry["crew"])
        if kept is None or (entry["commander"] and not kept["commander"]):
            by_crew[entry["crew"]] = entry
    return list(by_crew.values())


def _crew_helpers(boards: list[dict], commander_keys: set[str]) -> list[tuple]:
    """(crew, member, persona, task) for every task a commander's crew owns."""
    out = []
    for board in boards:
        if board.get("commander") not in commander_keys:
            continue
        members = board.get("members") or {}
        for task in board.get("tasks") or []:
            owner = task.get("owner")
            if owner and owner != board.get("commander"):
                persona = (members.get(owner) or {}).get("persona", "")
                out.append((board.get("crew"), owner, persona, task))
    return out


def _helper_rows(live: list[dict], basic: list[dict], window_of) -> list[dict]:
    """Crew Room's detailed helpers first, then everyone.py's plain list for
    the older ones it no longer keeps."""
    rows = []
    seen = set()
    for h in live:
        seen.add(h["id"])
        tokens = h.get("tokens") or {}
        rows.append(
            {
                "id": h["id"],
                "type": h.get("type", ""),
                "task": h.get("task", ""),
                "state": h.get("state", "done"),
                "model": h.get("model"),
                "family": h.get("family"),
                "effort": h.get("effort"),
                "action": h.get("action", ""),
                "feed": (h.get("actions") or [])[-FEED_SHOWN:],
                "context": tokens.get("last_context", 0),
                "window": window_of(h.get("model"), tokens.get("last_context", 0)),
                "idle_seconds": h.get("idle_seconds"),
            }
        )
    for h in basic:
        # everyone.py ids keep the file's "agent-" prefix; the Crew Room's do not
        agent_id = h["id"].removeprefix("agent-")
        if agent_id in seen or len(rows) >= HELPERS_SHOWN:
            continue
        rows.append(
            {
                "id": agent_id,
                "type": h.get("type", ""),
                "task": h.get("description", ""),
                "state": "done",
                "model": h.get("model") or None,
                "family": None,
                "effort": None,
                "action": "finished",
                "feed": [],
                "context": 0,
                "window": WINDOW,
                "updated": h.get("updated"),
            }
        )
    return rows[:HELPERS_SHOWN]


def build(
    room: dict,
    everyone_rows: list[dict],
    boards: list[dict],
    conversations: dict,
    relay_runs: dict,
    summarize_ended=None,
) -> list[dict]:
    """One row per session, needs-you first, then working, idle, ended.

    room: Crew Room sources.collect_all() (sessions, helpers).
    everyone_rows: Claude app everyone.sessions() (live and cold).
    boards: crew boards as on disk (crew.peek).
    conversations: Claude app session id -> {id, name, title}.
    relay_runs: session id -> {task, kind, account}.
    summarize_ended: transcript path -> {model, effort, actions, tokens} for
    ended sessions (cached by the caller), or None to skip.
    """
    crews_of = membership(boards)
    helpers_by_parent: dict[str, list[dict]] = {}
    for h in room.get("helpers") or []:
        helpers_by_parent.setdefault(h.get("parent", ""), []).append(h)
    basic_by_id = {r["session_id"]: r for r in everyone_rows}
    rows = []
    live_ids = set()
    for s in room.get("sessions") or []:
        sid = s["id"]
        live_ids.add(sid)
        conv = conversations.get(sid) or {}
        tokens = s.get("tokens") or {}
        crews = one_per_crew(
            crews_of.get(sid, []) + crews_of.get(s.get("name", ""), [])
        )
        last = max(
            s.get("updated_at") or 0,
            s.get("started_at") or 0,
            _mtime(s.get("transcript")),
        )
        rows.append(
            {
                "id": sid,
                "name": s.get("name", ""),
                "label": conv.get("name") or s.get("label") or _persona(crews),
                "title": conv.get("title", ""),
                "group": group_of(s.get("status", ""), bool(s.get("busy")), True),
                "status": s.get("status", ""),
                "pid": s.get("pid"),
                "kind": s.get("kind", ""),
                "background": bool(s.get("background")),
                "cwd": s.get("cwd", ""),
                "place": s.get("place", ""),
                "model": s.get("model"),
                "family": s.get("family"),
                "effort": s.get("effort"),
                "action": s.get("action", ""),
                "feed": (s.get("actions") or [])[-FEED_SHOWN:],
                "context": tokens.get("last_context", 0),
                "window": context_window(s.get("model"), tokens.get("last_context", 0)),
                "turns": tokens.get("turns", 0),
                "started": s.get("started_at") or 0,
                "last_active": last,
                "helpers": _helper_rows(
                    helpers_by_parent.get(sid, []),
                    (basic_by_id.get(sid) or {}).get("helpers") or [],
                    context_window,
                ),
                "crews": crews,
                "relay": relay_runs.get(sid),
                "claude_tab": conv.get("id"),
            }
        )
    ended = [
        r
        for r in everyone_rows
        if r.get("state") == "cold" and r["session_id"] not in live_ids
    ]
    ended.sort(key=lambda r: -(r.get("updated") or 0))
    for r in ended[:ENDED_SHOWN]:
        sid = r["session_id"]
        conv = conversations.get(sid) or {}
        crews = crews_of.get(sid, [])
        summary = summarize_ended(sid) if summarize_ended else None
        summary = summary or {}
        tokens = summary.get("tokens") or {}
        cwd = r.get("cwd", "")
        rows.append(
            {
                "id": sid,
                "name": r.get("name", ""),
                "label": conv.get("name") or _persona(crews),
                "title": conv.get("title", ""),
                "group": "ended",
                "status": "ended",
                "pid": r.get("pid"),
                "kind": "",
                "background": r.get("entrypoint") == "sdk-cli",
                "cwd": cwd,
                "place": (
                    "~"
                    if cwd == os.path.expanduser("~")
                    else os.path.basename(cwd) or cwd
                ),
                "model": summary.get("model"),
                "family": _family(summary.get("model")),
                "effort": summary.get("effort"),
                "action": "ended",
                "feed": (summary.get("actions") or [])[-FEED_SHOWN:],
                "context": tokens.get("last_context", 0),
                "window": context_window(
                    summary.get("model"), tokens.get("last_context", 0)
                ),
                "turns": tokens.get("turns", 0),
                "started": r.get("started") or 0,
                "last_active": r.get("updated") or 0,
                "helpers": _helper_rows([], r.get("helpers") or [], context_window),
                "crews": crews,
                "relay": relay_runs.get(sid),
                "claude_tab": conv.get("id"),
            }
        )
    _match_crew_helpers(rows, boards)
    order = {g: i for i, g in enumerate(GROUPS)}
    rows.sort(key=lambda r: (order[r["group"]], -r["last_active"]))
    return rows


def _persona(crews: list[dict]) -> str:
    return next((c["persona"] for c in crews if c.get("persona")), "")


def _family(model: str | None) -> str | None:
    if not model:
        return None
    lowered = model.lower()
    return next((f for f in ("opus", "sonnet", "haiku", "fable") if f in lowered), None)


def _match_crew_helpers(rows: list[dict], boards: list[dict]) -> None:
    """Tag a commander's helper agents with the crew member and task they
    took, matched on the task title (the board does not record agent ids)."""
    for row in rows:
        keys = {row["id"], row["name"]}
        for crew, member, persona, task in _crew_helpers(boards, keys):
            for h in row["helpers"]:
                if not h.get("crew_member") and _same_task(
                    h.get("task", ""), task.get("title", "")
                ):
                    h.update(
                        crew=crew,
                        crew_member=member,
                        persona=persona,
                        crew_task=task.get("id"),
                        crew_status=task.get("status", ""),
                    )
                    break


def counts(rows: list[dict]) -> dict[str, int]:
    out = {g: 0 for g in GROUPS}
    for r in rows:
        out[r["group"]] += 1
    out["helpers_working"] = sum(
        1 for r in rows for h in r["helpers"] if h.get("state") == "working"
    )
    return out
