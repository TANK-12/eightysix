"""The human name of a Claude Code session, the same everywhere in Forge.

Claude Code calls sessions ejb-a9 or relay-59-work. People see them as
Hotaru or Mika: the Claude app's tab name for a session it runs, else the
name the crew board gave it (~/.claude/crew/<crew>/board.json, member
"persona"). The crew skill's touch() already copies the tab name onto the
board, so the two agree; the tab name still wins here, because the board only
learns it when the session next runs a crew command (Emerson, 2026-10-07:
Crew Room showed ejb-a9 while the Board and the tab said Hotaru).
"""

from __future__ import annotations

import glob
import json
import os
import re
import time
import urllib.request

CACHE_SECONDS = 10
_app_cache: dict[str, tuple[float, dict[str, str]]] = {}


def claude_app_names(apps_dir: str, timeout: float = 1.5) -> dict[str, str]:
    """Session id -> tab name from the running Claude app (the app whose
    forge_app.json has role "claude"). Empty while it is closed. Asked at
    most every CACHE_SECONDS per apps folder."""
    if not apps_dir:
        return {}
    cached = _app_cache.get(apps_dir)
    if cached and time.time() - cached[0] < CACHE_SECONDS:
        return cached[1]
    names: dict[str, str] = {}
    for path in sorted(glob.glob(os.path.join(apps_dir, "*", "forge_app.json"))):
        try:
            with open(path, encoding="utf-8") as fh:
                manifest = json.load(fh)
        except (OSError, ValueError):
            continue
        if manifest.get("role") != "claude" or not manifest.get("port"):
            continue
        req = urllib.request.Request(
            f"http://127.0.0.1:{manifest['port']}/api/sessions",
            headers={"X-Forge": "1"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as reply:
                sessions = json.load(reply).get("sessions") or {}
        except (OSError, ValueError, AttributeError):
            sessions = {}
        names = {
            str(sid): str(conv.get("name") or "")
            for sid, conv in sessions.items()
            if isinstance(conv, dict) and conv.get("name")
        }
        break
    _app_cache[apps_dir] = (time.time(), names)
    return names


def board_names(crew_home: str) -> dict[str, str]:
    """Session id -> the name a crew board gave it, across every board. When
    two boards name one session, the one that saw it last wins."""
    found: dict[str, tuple[float, str]] = {}
    for path in glob.glob(os.path.join(crew_home, "*", "board.json")):
        try:
            with open(path, encoding="utf-8") as fh:
                members = json.load(fh).get("members") or {}
        except (OSError, ValueError, AttributeError):
            continue
        if not isinstance(members, dict):
            continue
        # a hand-edited or half-written board must not take the pages down
        for member in members.values():
            if not isinstance(member, dict):
                continue
            sid, persona = member.get("session"), member.get("persona")
            if not isinstance(sid, str) or not sid or not persona:
                continue
            try:
                seen = float(member.get("last_seen") or 0)
            except (TypeError, ValueError):
                seen = 0.0
            if sid not in found or seen > found[sid][0]:
                found[sid] = (seen, str(persona))
    return {sid: persona for sid, (_, persona) in found.items()}


def labels(
    crew_home: str, apps_dir: str = "", app_names: dict[str, str] | None = None
) -> dict[str, str]:
    """Session id -> human name: the Claude app's tab name, else the board's.
    A caller that already asked the Claude app (the Board, for tab titles)
    passes its answer as app_names instead of asking again."""
    if app_names is None:
        app_names = claude_app_names(apps_dir)
    return {**board_names(crew_home), **{k: v for k, v in app_names.items() if v}}


RELAY_TASKS = os.path.expanduser("~/.local/share/forge/relay/tasks")
_RELAY_NAME = re.compile(r"^relay-(\d+)-")


def relay_task(session_name: str, tasks_dir: str = "") -> dict | None:
    """{"task": "109", "title": "..."} for a Relay session called relay-109-work,
    else None. The title is the task file's own (tasks/<goal>/0109-*.md)."""
    found = _RELAY_NAME.match(session_name or "")
    if not found:
        return None
    number = found.group(1)
    title = ""
    for path in glob.glob(
        os.path.join(tasks_dir or RELAY_TASKS, "*", f"{int(number):04d}-*.md")
    ):
        try:
            with open(path, encoding="utf-8") as fh:
                head = fh.read(1500)
        except OSError:
            continue
        match = re.search(r"^title:[ \t]*(.+)$", head, re.M)
        if match:
            title = match.group(1).strip()
            break
    return {"task": number, "title": title}
