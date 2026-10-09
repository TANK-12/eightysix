"""Projects, tasks, notes and workflows for the Enjoy layout (A15).

WHAT A PROJECT IS
    A conversation folder. The classic layout files conversations into
    folders; the Enjoy layout calls each folder a project and each
    conversation filed in it a task. The project's extras (a stable id, its
    working folder and its saved workflows) live on the same row of
    folders.json, so renaming the folder in either layout keeps them. Notes
    and documents are markdown files under <data>/projects/<id>/notes, so the
    id, not the name, is what they hang on.

WHAT NEEDS YOU
    Each finished turn is recorded on the conversation (meta.last_turn, see
    runner.Conversation.note_turn) and opening a task in the Enjoy layout
    marks it seen. A task needs you when its last turn failed, had tool calls
    refused, or finished since you last looked.
"""

from __future__ import annotations

import os
import re
import secrets
import time
from pathlib import Path

import runner

STATES = ("running", "needs you")
MAX_STEPS = 20
MAX_STEP = 2000


def state(meta: dict) -> str:
    """running | needs you | quiet | new, for one conversation's meta."""
    if meta.get("busy"):
        return "running"
    turn = meta.get("last_turn")
    if not isinstance(turn, dict):
        return "new"
    if not turn.get("ok") or turn.get("denied"):
        return "needs you"
    if float(turn.get("at") or 0) > float(meta.get("seen") or 0):
        return "needs you"
    return "quiet"


def _rows(reg: runner.Registry) -> list[dict]:
    """Every folder, each given a stable id the first time it is seen."""
    rows = reg.folders()
    if any(not row.get("id") for row in rows):
        for row in rows:
            row.setdefault("id", secrets.token_hex(6))
        reg.set_folders(rows)
    return rows


def _public(row: dict, tasks: list[dict] | None = None) -> dict:
    out = {
        "id": row["id"],
        "name": row["name"],
        "cwd": row.get("cwd") or "",
        "workflows": row.get("workflows") or [],
    }
    if tasks is not None:
        out["tasks"] = tasks
        out["counts"] = {s: sum(t["state"] == s for t in tasks) for s in STATES}
    return out


def listing(reg: runner.Registry) -> dict:
    """Projects with their tasks, and the tasks that sit in no project."""
    rows = _rows(reg)
    names = {row["name"] for row in rows}
    tasks: dict[str, list[dict]] = {name: [] for name in names}
    loose = []
    for meta in reg.list():
        if meta.get("archived"):
            continue  # quiet loose tasks sit in the Chat layout's Archived list
        meta["state"] = state(meta)
        folder = meta.get("folder") or ""
        (tasks[folder] if folder in names else loose).append(meta)
    return {
        "projects": [_public(row, tasks[row["name"]]) for row in rows],
        "loose": loose,
    }


def _row(reg: runner.Registry, pid: str) -> tuple[list[dict], dict]:
    rows = _rows(reg)
    row = next((r for r in rows if r.get("id") == pid), None)
    if row is None:
        raise KeyError("No such project")
    return rows, row


def get(reg: runner.Registry, pid: str) -> dict:
    return _public(_row(reg, pid)[1])


def _cwd(cwd: str) -> str:
    path = os.path.expanduser(str(cwd or "").strip() or "~")
    if not os.path.isdir(path):
        raise ValueError("That working folder does not exist")
    return path


def create(reg: runner.Registry, name: str, cwd: str = "") -> dict:
    folder = _cwd(cwd)
    reg.add_folder(name)
    rows = _rows(reg)
    row = next(r for r in rows if r["name"] == runner.Registry.folder_name(name))
    row["cwd"] = folder
    reg.set_folders(rows)
    return _public(row)


def _workflows(flows) -> list[dict]:
    if not isinstance(flows, list):
        raise ValueError("Workflows are a list")
    clean = []
    for flow in flows:
        name = " ".join(str((flow or {}).get("name") or "").split())[:60]
        steps = [
            str(s).strip()[:MAX_STEP]
            for s in (flow or {}).get("steps") or []
            if str(s).strip()
        ]
        if not name:
            raise ValueError("A workflow needs a name")
        if not 1 <= len(steps) <= MAX_STEPS:
            raise ValueError(f"A workflow has 1 to {MAX_STEPS} steps")
        clean.append({"name": name, "steps": steps})
    return clean


def update(
    reg: runner.Registry, pid: str, *, cwd=None, workflows=None, name=None
) -> dict:
    rows, row = _row(reg, pid)
    if cwd is not None:
        row["cwd"] = _cwd(cwd)
    if workflows is not None:
        row["workflows"] = _workflows(workflows)
    reg.set_folders(rows)
    if name is not None and name != row["name"]:
        reg.update_folder(row["name"], new_name=name)
    return get(reg, pid)


def workflow_prompt(flow: dict) -> str:
    """A saved workflow as the first message of a new task."""
    steps = "\n".join(f"{i}. {step}" for i, step in enumerate(flow["steps"], 1))
    return (
        f"Workflow: {flow['name']}\n\nWork through these steps in order, "
        f"and tell me when each one is done:\n\n{steps}"
    )


# --- notes and documents ----------------------------------------------------------


def _notes_dir(reg: runner.Registry, pid: str) -> Path:
    _row(reg, pid)  # the project must exist
    if not re.fullmatch(r"[0-9a-f]{12}", pid):
        raise KeyError("No such project")
    return reg.data_dir / "projects" / pid / "notes"


def _note_path(reg: runner.Registry, pid: str, name: str) -> Path:
    stem = runner.safe_name(name)
    if stem.lower().endswith(".md"):
        stem = stem[:-3]
    return _notes_dir(reg, pid) / f"{stem or 'note'}.md"


def notes(reg: runner.Registry, pid: str) -> list[dict]:
    folder = _notes_dir(reg, pid)
    files = sorted(
        folder.glob("*.md") if folder.is_dir() else [],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return [
        {"name": p.stem, "updated": p.stat().st_mtime, "bytes": p.stat().st_size}
        for p in files
    ]


def read_note(reg: runner.Registry, pid: str, name: str) -> str:
    path = _note_path(reg, pid, name)
    if not path.is_file():
        raise KeyError("No such note")
    return path.read_text(encoding="utf-8")


def save_note(reg: runner.Registry, pid: str, name: str, text: str) -> dict:
    path = _note_path(reg, pid, name)
    if len(text) > 1_000_000:
        raise ValueError("A note is at most 1 MB")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
    return {"name": path.stem, "updated": time.time(), "bytes": len(text)}


def delete_note(reg: runner.Registry, pid: str, name: str) -> None:
    path = _note_path(reg, pid, name)
    if path.is_file():
        path.unlink()
