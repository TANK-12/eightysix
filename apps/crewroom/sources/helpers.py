"""Background helpers (subagents) of the live sessions.

A helper's transcript is <project>/<sessionId>/subagents/agent-<id>.jsonl with
a .meta.json beside it naming its agent type. Its model and effort come from
~/.claude/agents/<type>.md frontmatter when that file exists, else from the
transcript itself.
"""

from __future__ import annotations

import glob
import json
import os

import forge_helper_files
import transcripts
from context import Context

NAME = "helpers"
ORDER = 20
WANTS_ROOM = True

ACTIVE_SECONDS = 90  # written to this recently: still working
RECENT_SECONDS = 600  # finished this recently: still in the room, reporting
PER_SESSION = 8


def agent_types(ctx: Context) -> dict[str, dict]:
    """name -> {model, effort, description} from agent definition frontmatter."""
    types: dict[str, dict] = {}
    for path in glob.glob(os.path.join(ctx.claude_dir, "agents", "*.md")):
        meta = read_frontmatter(path)
        name = meta.get("name") or os.path.splitext(os.path.basename(path))[0]
        types[name] = {
            "model": meta.get("model"),
            "effort": meta.get("effort"),
            "description": meta.get("description", ""),
        }
    return types


def read_frontmatter(path: str) -> dict[str, str]:
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read(8192)
    except OSError:
        return {}
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    meta = {}
    for line in text[3:end].splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip() and not line.startswith(" "):
            meta[key.strip()] = value.strip().strip("\"'")
    return meta


def collect(ctx: Context, room: dict) -> list[dict]:
    types = agent_types(ctx)
    helpers = []
    for session in room.get("sessions") or []:
        transcript = session.get("transcript")
        if not transcript:
            continue
        folder = os.path.join(os.path.dirname(transcript), session["id"], "subagents")
        found = []
        for path in forge_helper_files.transcripts(folder):
            try:
                age = ctx.now - os.path.getmtime(path)
            except OSError:
                continue
            if age > RECENT_SECONDS:
                continue
            found.append((age, path))
        found.sort()
        for age, path in found[:PER_SESSION]:
            helpers.append(describe(types, session, path, age))
    return helpers


def describe(types: dict[str, dict], session: dict, path: str, age: float) -> dict:
    agent_id = os.path.basename(path)[len("agent-") : -len(".jsonl")]
    meta = {}
    try:
        with open(path[: -len(".jsonl")] + ".meta.json", encoding="utf-8") as fh:
            meta = json.load(fh)
    except (OSError, ValueError):
        pass
    agent_type = str(meta.get("agentType") or "general-purpose")
    summary = transcripts.summarize(transcripts.read_tail(path))
    known = types.get(agent_type, {})
    working = age <= ACTIVE_SECONDS
    model = summary["model"] or known.get("model")
    return {
        "id": agent_id,
        "parent": session["id"],
        "parent_name": session["name"],
        "type": agent_type,
        "crew": agent_type.startswith("crew-"),
        "task": meta.get("description") or "",
        "state": "working" if working else "done",
        "model": model,
        "family": transcripts.model_family(model) or known.get("model"),
        "effort": known.get("effort") or summary["effort"],
        "action": (
            transcripts.current_action(summary, True) if working else "reporting back"
        ),
        "actions": summary["actions"],
        "tokens": summary["tokens"],
        "idle_seconds": round(age),
    }
