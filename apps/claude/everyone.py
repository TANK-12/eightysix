"""Every Claude Code session on this laptop, for the Claude app's "everyone" view.

Each running session writes ~/.claude/sessions/<pid>.json (shared by every
account); a file whose pid is gone is a session that ended ("cold"). Helper
agents (subagents) live beside their parent's transcript in
projects/<dir>/<session id>/subagents/agent-*.jsonl with a .meta.json
(ultracode's one level deeper; shared/forge_helper_files.py knows where).
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

COLD_DAYS = 3
HELPER_LIVE_SECONDS = 120
CREW = "forge"
CREW_SKILL = Path.home() / ".claude/skills/crew"


def alive(pid) -> bool:
    try:
        os.kill(int(pid), 0)
    except (OSError, TypeError, ValueError):
        return False
    return True


def _helpers(projects: Path, session_id: str, parent_live: bool, now: float):
    shared = str(Path(__file__).resolve().parents[2] / "shared")
    if shared not in sys.path:
        sys.path.insert(0, shared)
    import forge_helper_files  # pyright: ignore[reportMissingImports]

    found = []
    metas = [
        Path(m)
        for folder in projects.glob(f"*/{session_id}/subagents")
        for m in forge_helper_files.metas(str(folder))
    ]
    for meta_path in metas:
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        log = meta_path.with_name(meta_path.name.replace(".meta.json", ".jsonl"))
        updated = log.stat().st_mtime if log.exists() else meta_path.stat().st_mtime
        working = parent_live and now - updated < HELPER_LIVE_SECONDS
        found.append(
            {
                "id": meta_path.name.split(".")[0],
                "description": meta.get("description") or meta.get("agentType", ""),
                "type": meta.get("agentType", ""),
                "model": meta.get("model", ""),
                "state": "working" if working else "done",
                "updated": updated,
            }
        )
    return sorted(found, key=lambda h: h["updated"], reverse=True)


def sessions(sessions_dir: Path, projects: Path, now: float | None = None) -> list:
    """Working first, then idle, then cold (ended in the last COLD_DAYS)."""
    now = time.time() if now is None else now
    rows = []
    for path in sessions_dir.glob("*.json") if sessions_dir.is_dir() else []:
        try:
            info = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        sid = info.get("sessionId")
        if not sid:
            continue
        live = alive(info.get("pid"))
        updated = (info.get("updatedAt") or info.get("startedAt") or 0) / 1000
        if not live and now - max(updated, path.stat().st_mtime) > COLD_DAYS * 86400:
            continue
        if not live:
            state = "cold"
        elif info.get("status") == "busy":
            state = "working"
        else:
            state = "idle"
        rows.append(
            {
                "session_id": sid,
                "name": info.get("name", ""),
                "pid": info.get("pid"),
                "cwd": info.get("cwd", ""),
                "entrypoint": info.get("entrypoint", ""),
                "version": info.get("version", ""),
                "state": state,
                "started": (info.get("startedAt") or 0) / 1000,
                "updated": updated,
                "helpers": _helpers(projects, sid, live, now),
            }
        )
    order = {"working": 0, "idle": 1, "cold": 2}
    return sorted(rows, key=lambda r: (order[r["state"]], -r["updated"]))


def _crew():
    if str(CREW_SKILL) not in sys.path:
        sys.path.insert(0, str(CREW_SKILL))
    import crew  # pyright: ignore[reportMissingImports]

    return crew


def message(session_id: str, text: str, crew_name: str = CREW) -> dict:
    """A note from Emerson on the crew board, addressed to that session's board
    name; the notes hook hands it over at the session's next step, even mid-job."""
    crew = _crew()
    name = crew.session_names().get(session_id)
    if not name:
        raise LookupError("That session has no board name")
    body = f"Emerson asks (answer him in your next reply, then carry on): {text}"
    with crew.open_board(crew_name) as board:
        note = crew.add_note(board, "Emerson", body, to=name)
    return {"id": note["id"], "to": name}
