"""What Emerson typed to Claude Code, and when each session started, read
from Claude Code's own transcripts. History is backfilled on the first read,
since every line carries its own time."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

NAME = "claude"
LABEL = "Claude Code"
DESCRIPTION = "Your messages to Claude Code and when sessions start (titles only)."
DEFAULT_ON = True
INTERVAL = 60

ROOT = Path(
    os.environ.get("CALENDAR_CLAUDE_PROJECTS") or Path.home() / ".claude/projects"
)
SKIP = ("<", "Caveat", "This session is being continued", "[Request interrupted")


def when(stamp: str) -> float | None:
    try:
        return datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()
    except (ValueError, AttributeError):
        return None


def said(line: dict) -> str:
    """The text Emerson typed, or "" for tool results, meta and system lines."""
    if line.get("type") != "user" or line.get("isMeta") or line.get("isSidechain"):
        return ""
    content = (line.get("message") or {}).get("content")
    if isinstance(content, list):
        blocks = [b for b in content if isinstance(b, dict)]
        if any(b.get("type") == "tool_result" for b in blocks):
            return ""
        content = " ".join(b.get("text", "") for b in blocks if b.get("type") == "text")
    if not isinstance(content, str):
        return ""
    text = content.strip()
    return "" if not text or text.startswith(SKIP) else text


def project_name(folder: str) -> str:
    return folder.replace("-home-ejb", "~").replace("-", "/") or "~"


def collect(state: dict, root: Path = ROOT) -> list[dict]:
    offsets = state.setdefault("offsets", {})
    events: list[dict] = []
    if not root.is_dir():
        return events
    for path in root.glob("*/*.jsonl"):
        key = str(path)
        start = offsets.get(key, 0)
        if path.stat().st_size <= start:
            continue
        with path.open("rb") as f:
            f.seek(start)
            chunk = f.read()
        end = chunk.rfind(b"\n") + 1  # a half-written last line waits for next time
        project = project_name(path.parent.name)
        new_file = start == 0
        for raw in chunk[:end].splitlines():
            try:
                line = json.loads(raw)
            except ValueError:
                continue
            ts = when(line.get("timestamp", ""))
            if ts is None:
                continue
            if new_file:
                events.append(
                    {
                        "ts": ts,
                        "source": NAME,
                        "kind": "session",
                        "title": f"Claude Code session in {project}",
                        "key": f"claude:session:{path.stem}",
                    }
                )
                new_file = False
            text = said(line)
            if text:
                events.append(
                    {
                        "ts": ts,
                        "source": NAME,
                        "kind": "said",
                        "title": text[:200],
                        "tags": [project.strip("/")[:30] or "home"],
                        "key": f"claude:{line.get('uuid') or ts}",
                    }
                )
        offsets[key] = start + end
    return events
