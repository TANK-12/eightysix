"""Relay page backend: shows the queue, goals, sessions and meters, and writes
the same task, goal and settings files the boss reads. It never starts a
session itself; it pokes the boss, which launches on its next tick.
"""

from __future__ import annotations

import os
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(ROOT, "static")
SHARED_DIR = os.environ.get("FORGE_SHARED_DIR") or os.path.join(
    ROOT, "..", "..", "shared"
)
for extra in (ROOT, SHARED_DIR):
    if extra not in sys.path:
        sys.path.insert(0, extra)

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel  # noqa: E402

import actions  # noqa: E402
import channels  # noqa: E402
import forge_attach  # noqa: E402
import forge_attach_api  # noqa: E402
import forge_session_names  # noqa: E402
import items  # noqa: E402
import picker  # noqa: E402
import runs  # noqa: E402
import store  # noqa: E402
from commands import Command  # noqa: E402

app = FastAPI(title="Relay")
HIDDEN_SETTINGS = ("paused",)


_run_names: dict[str, tuple[str, str]] = {}


def _session_of(run: dict) -> tuple[str, str]:
    """A run's Claude session id (a resumed chat keeps its old one) and the
    name it was started under (relay-59-work)."""
    command = run.get("command") or []
    name = ""
    if "--name" in command[:-1]:
        name = str(command[command.index("--name") + 1])
    return str(run.get("session") or run.get("id") or ""), name


def _run_session(run_id: str) -> tuple[str, str]:
    """_session_of for a run by id; a run's record never changes its session,
    so each is read once."""
    if run_id not in _run_names:
        run = store.read_json(runs.run_dir(run_id) / "run.json")
        if not isinstance(run, dict):
            return run_id, ""
        _run_names[run_id] = _session_of(run)
    return _run_names[run_id]


def session_labels() -> dict[str, str]:
    """Session id -> the name Emerson sees for it in the Claude app, Crew Room
    and the Board (relay-59-work = Mika), from shared/forge_session_names.py."""
    return forge_session_names.labels(
        os.environ.get("CREW_HOME") or os.path.expanduser("~/.claude/crew"),
        os.environ.get("FORGE_APPS_DIR") or os.path.dirname(ROOT),
    )


def _task_view(task: dict, labels: dict[str, str] | None = None) -> dict:
    view = {k: v for k, v in task.items() if k != "body"}
    view["state"] = task.get("body", "").partition("## State")[2].strip()[-1500:]
    session, name = _run_session(task["last_run"]) if task.get("last_run") else ("", "")
    view["session_name"] = name
    view["session_label"] = (labels or {}).get(session, "")
    return view


@app.get("/api/state")
def state():
    store.ensure()
    st = store.state()
    now = time.time()
    labels = session_labels()
    active = []
    for run in runs.active():
        info = runs.summary(run)
        info.pop("result", None)
        session, name = _session_of(run)
        active.append(
            {
                **run,
                **info,
                "alive": runs.alive(run),
                "age": now - run["started"],
                "session_name": name,
                "session_label": labels.get(session, ""),
            }
        )
    settings = store.settings()
    return {
        "now": now,
        "boss_age": now - st["heartbeat"] if st.get("heartbeat") else None,
        "wait_reason": st.get("wait_reason", ""),
        "paused": settings["paused"],
        "meters": st.get("meters") or {},
        "room": picker.has_room(st.get("meters") or {}, settings),
        "running": active,
        "tasks": [_task_view(t, labels) for t in items.all_tasks()],
        "goals": [{k: v for k, v in g.items()} for g in items.all_goals()],
        "events": store.events(80)[::-1],
        "settings": settings,
        "mail_password_set": bool(store.secret("mail_password")),
        "mail_ready": bool(channels.ready(settings)),
    }


@app.get("/api/runs/{run_id}/tail")
def tail(run_id: str):
    run = store.read_json(runs.run_dir(os.path.basename(run_id)) / "run.json")
    if not isinstance(run, dict):
        raise HTTPException(404, "No such session")
    return {"lines": runs.tail_lines(run, 60)}


class TaskIn(BaseModel):
    title: str = ""
    text: str
    goal: str = ""
    priority: str = "normal"
    folder: str = ""
    effort: str = ""
    account: str = ""
    done_when: str = ""
    files: list[str] = []


@app.post("/api/tasks")
def add_task(body: TaskIn):
    if not body.text.strip() and not body.files:
        raise HTTPException(400, "Write what the task should do")
    body.text = forge_attach.with_note(body.text, ATTACH.paths(body.files))
    if body.goal and not items.find_goal(body.goal):
        raise HTTPException(400, f"No goal called {body.goal}")
    options = {
        k: v
        for k, v in {
            "priority": body.priority,
            "folder": body.folder,
            "effort": body.effort,
            "account": body.account,
            "done_when": body.done_when,
        }.items()
        if v
    }
    title = body.title.strip() or body.text.strip().splitlines()[0][:80]
    cmd = Command("task", title=title, text=body.text, goal=body.goal, options=options)
    return {"task": _task_view(actions.add_task(cmd, "the Relay page"))}


# ---- files attached to a new request (Relay task 118) -------------------------
# Saved in Relay's attachments folder (WhatsApp files land there too) and
# named in the request as "Attached files:" lines (shared/forge_attach.py).

ATTACH = forge_attach_api.Attachments(lambda: store.path("attachments"), what="request")
app.include_router(ATTACH.router())


class GoalIn(BaseModel):
    title: str
    text: str = ""
    priority: str = "normal"
    folder: str = ""
    check: str = ""


@app.post("/api/goals")
def add_goal(body: GoalIn):
    if not body.title.strip():
        raise HTTPException(400, "Give the goal a title")
    options = {
        k: v
        for k, v in {
            "priority": body.priority,
            "folder": body.folder,
            "check": body.check,
        }.items()
        if v
    }
    cmd = Command("goal", title=body.title, text=body.text, options=options)
    return {"goal": actions.add_goal(cmd, "the Relay page")}


@app.post("/api/goals/{slug}/{action}")
def goal_action(slug: str, action: str):
    goal = items.find_goal(slug)
    if not goal:
        raise HTTPException(404, "No such goal")
    status = {"pause": "paused", "resume": "active", "done": "done"}.get(action)
    if not status:
        raise HTTPException(400, "Unknown action")
    goal["status"] = status
    if status == "active":
        goal["empty_plans"] = 0
    items.save(goal)
    store.event("goal", f"goal {slug} set to {status}")
    store.poke()
    return {"ok": True}


@app.post("/api/tasks/{number}/{action}")
def task_action(number: int, action: str):
    if action == "stop":
        return {"message": actions.stop_task(number)}
    if action == "retry":
        return {"message": actions.retry_task(number)}
    raise HTTPException(400, "Unknown action")


@app.post("/api/pause")
def pause():
    return {"message": actions.set_paused(True)}


@app.post("/api/resume")
def resume():
    return {"message": actions.set_paused(False)}


class SettingsIn(BaseModel):
    changes: dict


@app.post("/api/settings")
def save_settings(body: SettingsIn):
    changes = {k: v for k, v in body.changes.items() if k not in HIDDEN_SETTINGS}
    try:
        saved = store.save_settings(changes)
    except (ValueError, TypeError) as e:
        raise HTTPException(400, str(e))
    store.poke()
    return {"settings": saved}


class PasswordIn(BaseModel):
    password: str


@app.post("/api/mail/password")
def mail_password(body: PasswordIn):
    value = "".join(body.password.split())  # Google shows it in groups of four
    if len(value) < 8:
        raise HTTPException(400, "That does not look like an app password")
    store.save_secret("mail_password", value)
    store.event("mail", "mail app password saved")
    return {"ok": True}


@app.post("/api/mail/test")
def mail_test():
    settings = {**store.settings(), "mail_enabled": True}
    ready = channels.ready(settings)
    if not ready:
        raise HTTPException(
            400, "Fill in the mailbox address, your address and the app password first"
        )
    try:
        messages = [m.test(settings) for m in ready.values()]
    except Exception as e:
        raise HTTPException(502, f"Mail test failed: {e}")
    store.event("mail", "test mail sent")
    return {"message": " ".join(messages)}


app.mount("/shared", StaticFiles(directory=SHARED_DIR), name="shared")
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
