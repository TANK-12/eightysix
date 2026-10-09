"""Crew teamwork boards written by the crew skill: ~/.claude/crew/*/board.json."""

from __future__ import annotations

import glob
import json
import os

from context import Context

NAME = "crews"
ORDER = 30
LOG_LINES = 8


def collect(ctx: Context) -> list[dict]:
    crews = []
    for path in sorted(
        glob.glob(os.path.join(ctx.claude_dir, "crew", "*", "board.json"))
    ):
        try:
            with open(path, encoding="utf-8") as fh:
                board = json.load(fh)
        except (OSError, ValueError):
            continue
        if not isinstance(board, dict):
            continue
        members = board.get("members") or {}
        crews.append(
            {
                "name": board.get("crew") or os.path.basename(os.path.dirname(path)),
                "commander": board.get("commander"),
                "goal": board.get("goal") or "",
                "members": [
                    {
                        "name": name,
                        "role": (m or {}).get("role", ""),
                        "last_seen": (m or {}).get("last_seen"),
                    }
                    for name, m in members.items()
                ],
                "tasks": [
                    {
                        "id": t.get("id"),
                        "title": t.get("title", ""),
                        "owner": t.get("owner"),
                        "status": t.get("status", "open"),
                        "files": t.get("files") or [],
                        "note": t.get("note", ""),
                    }
                    for t in board.get("tasks") or []
                    if isinstance(t, dict)
                ],
                "claims": [
                    {"path": c.get("path"), "owner": c.get("owner")}
                    for c in board.get("claims") or []
                    if isinstance(c, dict)
                ],
                "log": (board.get("log") or [])[-LOG_LINES:],
            }
        )
    return crews
