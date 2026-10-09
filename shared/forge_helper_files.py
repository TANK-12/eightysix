"""Where Claude Code keeps a session's helpers (subagents), for every Forge
page that shows them (Board, Crew Room, Mission Control, the Claude app).

A helper's transcript is <project>/<session id>/subagents/agent-<id>.jsonl,
with agent-<id>.meta.json beside it. Ultracode's workflow helpers sit one
level deeper, in subagents/workflows/wf_<id>/. A new place is one more
entry in PLACES."""

from __future__ import annotations

import glob
import os

PLACES = ("", os.path.join("workflows", "*"))


def transcripts(subagents: str) -> list[str]:
    """Every helper transcript (agent-*.jsonl) under one session's subagents folder."""
    return _find(subagents, "agent-*.jsonl")


def metas(subagents: str) -> list[str]:
    """Every helper meta file (agent-*.meta.json) under one subagents folder."""
    return _find(subagents, "agent-*.meta.json")


def transcript(subagents: str, agent_id: str) -> str | None:
    """One helper's transcript by its id (without the "agent-" prefix)."""
    found = _find(subagents, glob.escape(f"agent-{agent_id}.jsonl"))
    return found[0] if found else None


def _find(subagents: str, name: str) -> list[str]:
    base = glob.escape(subagents)
    return [
        path
        for place in PLACES
        for path in sorted(glob.glob(os.path.join(base, place, name)))
    ]
