"""Live Claude Code sessions: ~/.claude/sessions/<pid>.json plus the tail of
each one's transcript."""

from __future__ import annotations

import glob
import json
import os

import forge_session_names
import transcripts
from context import Context, proc_start_ticks

NAME = "sessions"
ORDER = 10

# sessionId -> (model, effort) last seen, so a transcript tail that is all
# tool output does not blank the name tag between polls.
_known: dict[str, tuple[str | None, str | None]] = {}


def read_summary(transcript: str | None, session_id: str) -> dict:
    summary = transcripts.summarize(
        transcripts.read_tail(transcript) if transcript else []
    )
    if summary["model"]:
        _known[session_id] = (summary["model"], summary["effort"])
        return summary
    if session_id in _known:
        summary["model"], summary["effort"] = _known[session_id]
        return summary
    if transcript:
        wide = transcripts.summarize(
            transcripts.read_tail(transcript, transcripts.WIDE_TAIL_BYTES)
        )
        if wide["model"]:
            _known[session_id] = (wide["model"], wide["effort"])
            summary["model"], summary["effort"] = wide["model"], wide["effort"]
            if not summary["actions"]:
                summary["actions"] = wide["actions"]
                summary["tokens"] = wide["tokens"]
    return summary


def is_alive(ctx: Context, pid: int, proc_start: str | None) -> bool:
    """The pid exists and, when the session file recorded its start time, it
    is the same process rather than a later one that reused the number."""
    started = proc_start_ticks(ctx.proc_dir, pid)
    if started is None:
        return False
    return proc_start is None or str(proc_start) == started


def find_transcript(ctx: Context, session_id: str) -> str | None:
    matches = glob.glob(
        os.path.join(
            ctx.claude_dir, "projects", "*", f"{glob.escape(session_id)}.jsonl"
        )
    )
    if not matches:
        return None
    return max(matches, key=lambda p: os.path.getmtime(p))


ACTIVE_SECONDS = 300


def collect(ctx: Context) -> list[dict]:
    sessions = []
    # Hotaru rather than ejb-a9, as the Claude app's tabs and the Board say
    labels = forge_session_names.labels(
        os.path.join(ctx.claude_dir, "crew"), ctx.forge_apps_dir
    )
    for path in sorted(glob.glob(os.path.join(ctx.claude_dir, "sessions", "*.json"))):
        try:
            with open(path, encoding="utf-8") as fh:
                info = json.load(fh)
            pid = int(info.get("pid") or os.path.basename(path).split(".")[0])
        except (OSError, ValueError, TypeError):
            continue
        if not is_alive(ctx, pid, info.get("procStart")):
            continue
        session_id = str(info.get("sessionId") or "")
        transcript = find_transcript(ctx, session_id) if session_id else None
        summary = read_summary(transcript, session_id)
        # A headless `claude -p` (Crew Room background tasks, the Claude
        # panel) writes entrypoint "sdk-cli" and, on 2.1.273, no status while
        # it runs; it is working for as long as it is alive.
        background = info.get("entrypoint") == "sdk-cli"
        busy = info.get("status") == "busy" or (background and not info.get("status"))
        # Nothing written for 5 minutes means not active, whatever the file
        # says (Emerson, 2026-09-30); the Board uses the same rule.
        last = max(
            (info.get("startedAt") or 0) / 1000,
            (info.get("updatedAt") or 0) / 1000,
            os.path.getmtime(transcript) if transcript else 0,
        )
        if busy and ctx.now - last > ACTIVE_SECONDS:
            busy = False
        cwd = str(info.get("cwd") or "")
        home = os.path.expanduser("~")
        sessions.append(
            {
                "id": session_id,
                "pid": pid,
                "name": info.get("name") or f"session {pid}",
                "label": labels.get(session_id, ""),
                "status": info.get("status") or "idle",
                "busy": busy,
                "kind": info.get("kind") or "",
                "background": background,
                "cwd": cwd,
                "place": "~" if cwd == home else os.path.basename(cwd) or cwd,
                "started_at": (info.get("startedAt") or 0) / 1000,
                "updated_at": (info.get("updatedAt") or 0) / 1000,
                "model": summary["model"],
                "family": transcripts.model_family(summary["model"]),
                "effort": summary["effort"],
                "action": transcripts.current_action(summary, busy),
                "actions": summary["actions"],
                "tokens": summary["tokens"],
                "transcript": transcript,
            }
        )
    sessions.sort(key=lambda s: s["started_at"])
    return sessions
