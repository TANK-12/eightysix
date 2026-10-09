"""The wave as a map: lanes of cards.

A lane is a crew (its commander's card on top, helpers and members under
it), Relay with the sessions it runs, a shared board (forge) with whoever is
left on it, a session on its own with its working helpers, or Jan with its
loaded models. Every agent is in exactly one lane: a Relay run whose session
already leads or sits in a crew keeps its place there and gets a task badge.

The page lays the lanes out itself (HTML, so text wraps and nothing can
overlap); this module only decides who goes in which lane, in what order.
"""

from __future__ import annotations

import re
from pathlib import Path

# "Bash: wait for ..." -> "wait for ..."; only tool names, so "Error: ..." stays
_TOOL = re.compile(
    r"^(?:Bash|Read|Edit|Write|MultiEdit|Grep|Glob|Agent|Task|TodoWrite|WebFetch"
    r"|WebSearch|NotebookEdit|Skill|ToolSearch|SendMessage|Monitor|mcp__[\w-]+): "
)
# "F=/x/y N='a b' cat ..." -> "cat ..."
_ENV = re.compile(r"""^(?:[A-Za-z_]\w*=(?:"[^"]*"|'[^']*'|\S*)(?:\s+|$))+""")
_HOME = str(Path.home())


def plain(action: str) -> str:
    """An action line without a leading tool name, shell variables or the
    home folder spelled out."""
    text = _TOOL.sub("", str(action or ""), count=1)
    # a line cut short inside its variables keeps them rather than go blank
    return (_ENV.sub("", text, count=1) or text).replace(_HOME, "~")


def _session_node(s: dict) -> dict:
    return {
        "id": "s:" + s["id"],
        "kind": "session",
        "ref": s["id"],
        "label": s.get("label") or s.get("name") or s["id"][:8],
        "sub": plain(s.get("action", "")),
        "state": s["group"],
        "family": s.get("family"),
        "helpers_busy": sum(
            1 for h in s.get("helpers") or [] if h.get("state") == "working"
        ),
    }


def _helper_node(h: dict, parent: str) -> dict:
    return {
        "id": "h:" + h["id"],
        "kind": "helper",
        "ref": parent,
        "helper": h["id"],
        "label": h.get("persona")
        or h.get("crew_member")
        or h.get("task", "")[:22]
        or "helper",
        "sub": plain(h.get("action", "")),
        "state": h.get("state", "done"),
        "family": h.get("family"),
        "type": h.get("type", ""),
    }


def build(sessions: list[dict], crews: list[dict], relay: dict, jan: dict | None):
    """Lanes in the order the page shows them: crews led by a live session,
    Relay, shared boards, sessions on their own, Jan."""
    live = [s for s in sessions if s["group"] != "ended"]
    by_id = {s["id"]: s for s in live}
    by_name = {s["name"]: s for s in live}
    placed: dict[str, dict] = {}  # session id -> its node
    lanes: list[dict] = []

    def commander_of(crew: dict) -> dict | None:
        cmd = by_name.get(crew.get("commander") or "")
        if cmd is None:
            member = next(
                (m for m in crew["members"] if m["name"] == crew.get("commander")), None
            )
            cmd = by_id.get((member or {}).get("session") or "")
        return cmd

    active = [c for c in crews if c.get("active")]
    # A session that leads a crew sits at the top of that crew, even when
    # another board (forge) also lists it as a member.
    leaders = {c["id"] for c in (commander_of(x) for x in active) if c}

    def members_of(crew: dict, taken: set) -> list[dict]:
        out = []
        for m in crew["members"]:
            if (
                m["name"] == crew.get("commander")
                or m["name"] in taken
                or m.get("persona") in taken
            ):
                continue
            s = by_name.get(m["name"]) or by_id.get(m.get("session") or "")
            if s and s["id"] not in placed and s["id"] not in leaders:
                node = _session_node(s)
                placed[s["id"]] = node
                out.append(node)
        return out

    shared = []
    for crew in active:
        cmd = commander_of(crew)
        if cmd is None or cmd["id"] in placed:
            shared.append(crew)  # no live lead (or it leads a lane drawn earlier)
            continue
        lead = _session_node(cmd)
        placed[cmd["id"]] = lead
        ring = [
            _helper_node(h, cmd["id"])
            for h in cmd["helpers"]
            if h.get("crew_member") or h["state"] == "working"
        ]
        taken = {n.get("label") for n in ring} | {
            h.get("crew_member") for h in cmd.get("helpers", [])
        }
        ring += members_of(crew, taken)
        lanes.append(
            {
                "id": "crew:" + crew["name"],
                "kind": "crew",
                "title": f"crew {crew['name']}",
                "subtitle": crew.get("goal", ""),
                "lead": lead,
                "ring": ring,
            }
        )

    runs = list(relay.get("running") or []) if relay.get("present") else []
    if runs:
        titles = {
            str(t.get("id")): t.get("title", "") for t in relay.get("tasks") or []
        }
        ring = []
        for r in runs:
            s = by_id.get(r.get("session") or "")
            if s and s["id"] in placed:
                placed[s["id"]]["relay_task"] = r.get("task")  # badge, not a twin
                continue
            if s:
                node = _session_node(s)
                placed[s["id"]] = node
            else:
                node = {
                    "id": "r:" + str(r["id"]),
                    "kind": "run",
                    "ref": r.get("session"),
                    "label": titles.get(str(r.get("task"))) or f"task {r['task']}",
                    "sub": plain(r.get("last_action", "")),
                    "state": "working" if r.get("alive") else "ended",
                    "family": None,
                }
            node["relay_task"] = r.get("task")
            ring.append(node)
        queued = (relay.get("counts") or {}).get("queued", 0)
        status = "paused" if relay.get("paused") else f"{len(runs)} running"
        if ring:  # every run shown elsewhere: its badge says it all
            lanes.append(
                {
                    "id": "relay",
                    "kind": "relay",
                    "title": "Relay",
                    "subtitle": f"{status} · {queued} queued",
                    "lead": None,
                    "ring": ring,
                }
            )

    for crew in shared:
        ring = members_of(crew, set())
        if not ring:
            continue
        lanes.append(
            {
                "id": "crew:" + crew["name"],
                "kind": "board",
                "title": f"crew {crew['name']}",
                "subtitle": (
                    "commander away" if crew.get("commander") else "shared board"
                ),
                "lead": None,
                "ring": ring,
            }
        )

    for s in live:
        if s["id"] in placed:
            continue
        lead = _session_node(s)
        placed[s["id"]] = lead
        lanes.append(
            {
                "id": "solo:" + s["id"],
                "kind": "solo",
                "title": s.get("place", ""),
                "subtitle": "",
                "lead": lead,
                "ring": [
                    _helper_node(h, s["id"])
                    for h in s["helpers"]
                    if h["state"] == "working" or h.get("crew_member")
                ],
            }
        )

    models = (jan or {}).get("models") or []
    if models:
        lanes.append(
            {
                "id": "jan",
                "kind": "jan",
                "title": "Jan",
                "subtitle": f"{len(models)} loaded",
                "lead": None,
                "ring": [
                    {
                        "id": "j:" + str(m.get("id") or m.get("name")),
                        "kind": "model",
                        "ref": None,
                        "label": str(m.get("short") or m.get("name") or "model"),
                        "sub": f"{round(m.get('cpu') or 0)}% cpu",
                        "state": "working" if (m.get("cpu") or 0) >= 25 else "idle",
                        "family": None,
                    }
                    for m in models
                ],
            }
        )

    nodes = []
    for lane in lanes:
        lead = lane.pop("lead")
        lane["lead"] = lead["id"] if lead else None
        nodes += ([lead] if lead else []) + lane["ring"]
        lane["ring"] = [n["id"] for n in lane["ring"]]
    return {"lanes": lanes, "nodes": nodes}
