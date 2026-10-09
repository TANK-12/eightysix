"""Relay's queue, running sessions, pause state and account meters, read
from its data folder with Relay's own store/items/runs modules. Read-only:
pause and resume go through the Relay page's HTTP API (actions.py)."""

from __future__ import annotations

import time

TASKS_SHOWN = 40
OPEN_STATES = ("queued", "running", "handing_over", "reviewing", "blocked", "idle")
NEEDS_YOU = ("blocked",)
TASK_KEYS = (
    "id",
    "title",
    "status",
    "priority",
    "goal",
    "source",
    "role",
    "attempts",
    "created",
    "started",
    "last_ended",
    "effort",
    "note",
)


def _num(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def snapshot(store, items, runs, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    if not store.data_dir().is_dir():
        return {"present": False}
    st = store.state()
    settings = store.settings()
    running = []
    for run in runs.active():
        info = runs.summary(run)
        info.pop("result", None)
        running.append(
            {
                "id": run.get("id"),
                "session": run.get("session"),
                "task": str(run.get("task") or ""),
                "kind": run.get("kind", ""),
                "account": run.get("account", ""),
                "effort": run.get("effort", ""),
                "folder": run.get("folder", ""),
                "alive": bool(runs.alive(run)),
                "started": run.get("started") or 0,
                "last_action": info.get("last_action", ""),
                "last_text": (info.get("last_text") or "")[-240:],
                "context": info.get("context_tokens", 0),
                "last_at": info.get("last_at", 0),
            }
        )
    tasks = []
    counts: dict[str, int] = {}
    for t in items.all_tasks():
        status = str(t.get("status") or "queued")
        counts[status] = counts.get(status, 0) + 1
        row = {k: t.get(k, "") for k in TASK_KEYS}
        row["account"] = t.get("last_account") or t.get("ran_on") or ""
        row["id"] = int(_num(t.get("id")))
        tasks.append(row)
    titles = {str(t["id"]): t.get("title", "") for t in tasks}
    for r in running:
        r["title"] = titles.get(r["task"], "")
    open_first = sorted(
        tasks,
        key=lambda t: (
            t["status"] not in OPEN_STATES,
            -max(_num(t["last_ended"]), _num(t["started"]), _num(t["created"])),
        ),
    )
    meters = {}
    for account, m in (st.get("meters") or {}).items():
        m = m or {}
        meters[account] = {
            "five": m.get("five"),
            "week": m.get("week"),
            "resets": m.get("resets"),
            "week_resets": m.get("week_resets"),
            "error": m.get("error", ""),
        }
    heartbeat = st.get("heartbeat")
    return {
        "present": True,
        "paused": bool(settings.get("paused")),
        "max_sessions": settings.get("max_sessions"),
        "wait_reason": st.get("wait_reason", ""),
        "boss_seen": heartbeat or 0,
        "boss_up": bool(heartbeat) and now - float(heartbeat) < 180,
        "meters": meters,
        "running": running,
        "counts": counts,
        "tasks": open_first[:TASKS_SHOWN],
        "goals": [
            {
                "slug": g.get("slug", ""),
                "title": g.get("title", ""),
                "status": g.get("status", ""),
            }
            for g in items.all_goals()
        ],
        "events": [
            {"at": e.get("at"), "kind": e.get("kind", ""), "text": e.get("text", "")}
            for e in store.events(15)[::-1]
        ],
    }


def runs_by_session(relay: dict) -> dict[str, dict]:
    return {
        r["session"]: {
            "task": r["task"],
            "title": r.get("title", ""),
            "kind": r["kind"],
            "account": r["account"],
        }
        for r in relay.get("running") or []
        if r.get("session")
    }


def needs_you(relay: dict) -> list[dict]:
    return [
        {"task": t["id"], "title": t["title"], "note": t.get("note", "")}
        for t in relay.get("tasks") or []
        if t["status"] in NEEDS_YOU
    ]
