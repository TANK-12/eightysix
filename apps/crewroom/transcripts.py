"""Read the end of a Claude Code transcript and say what it is doing.

Transcripts grow to many megabytes, so only the last TAIL_BYTES are ever read.
Bubbles show tool names and file names in plain words, never message bodies.
"""

from __future__ import annotations

import json
import os

TAIL_BYTES = 64 * 1024
HEAD_BYTES = 16 * 1024
# One big tool result (a screenshot, a long file) can fill the whole normal
# tail; this wider read is tried once when the normal tail holds no model.
WIDE_TAIL_BYTES = 1024 * 1024
RECENT_ACTIONS = 6

# Tool name -> how to say it. "{file}" is the base name of the tool's file
# argument; a tool not listed here reads as "using <Tool>".
VERBS = {
    "Read": "reading {file}",
    "Edit": "editing {file}",
    "MultiEdit": "editing {file}",
    "Write": "writing {file}",
    "NotebookEdit": "editing {file}",
    "Grep": "searching the code",
    "Glob": "looking for files",
    "WebFetch": "reading a web page",
    "WebSearch": "searching the web",
    "TodoWrite": "updating the to-do list",
    "Agent": "sending out a helper",
    "Task": "sending out a helper",
    "Skill": "following the {skill} skill",
    "AskUserQuestion": "asking Emerson a question",
    "ExitPlanMode": "presenting a plan",
    "EnterPlanMode": "planning",
    "ListAgents": "checking who else is working",
    "SendMessage": "messaging another session",
    "Artifact": "publishing a page",
    "ScheduleWakeup": "scheduling a check-in",
    "ToolSearch": "loading a tool",
}


def read_tail(path: str, limit: int = TAIL_BYTES) -> list[dict]:
    """Parsed JSON lines from the last `limit` bytes. The first line is
    usually cut in half by the seek and is dropped."""
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            start = max(0, size - limit)
            fh.seek(start)
            data = fh.read()
    except OSError:
        return []
    lines = data.split(b"\n")
    if start > 0:
        lines = lines[1:]
    return _parse(lines)


def read_head(path: str, limit: int = HEAD_BYTES) -> list[dict]:
    """Parsed JSON lines from the first `limit` bytes, for where a session
    started. A last line cut by the limit simply fails to parse."""
    try:
        with open(path, "rb") as fh:
            data = fh.read(limit)
    except OSError:
        return []
    return _parse(data.split(b"\n"))


def _parse(lines: list[bytes]) -> list[dict]:
    entries = []
    for line in lines:
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, dict):
            entries.append(entry)
    return entries


def describe_tool(name: str, tool_input: dict) -> str:
    """One short plain-words phrase for a tool call."""
    tool_input = tool_input if isinstance(tool_input, dict) else {}
    if name == "Bash":
        desc = str(tool_input.get("description") or "").strip()
        if desc:
            return _shorten(desc[0].lower() + desc[1:])
        return "running a command"
    template = VERBS.get(name)
    if template is None:
        if name.startswith("mcp__"):
            return "using " + name.split("__")[-1].replace("_", " ")
        return f"using {name}"
    path = (
        tool_input.get("file_path")
        or tool_input.get("notebook_path")
        or tool_input.get("path")
        or ""
    )
    skill = str(tool_input.get("skill") or "a")
    return _shorten(
        template.format(file=os.path.basename(str(path)) or "a file", skill=skill)
    )


def _shorten(text: str, limit: int = 60) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def summarize(entries: list[dict]) -> dict:
    """Model, effort, recent actions and token averages from transcript
    entries, oldest first."""
    model = None
    effort = None
    actions: list[dict] = []
    seen_usage: set[str] = set()
    contexts: list[int] = []
    outputs: list[int] = []
    last_kind = None
    last_time = None
    for entry in entries:
        kind = entry.get("type")
        if kind not in ("assistant", "user"):
            continue
        last_time = entry.get("timestamp") or last_time
        message = entry.get("message") or {}
        if kind == "user":
            content = message.get("content")
            if isinstance(content, str) or (
                isinstance(content, list)
                and any(c.get("type") == "text" for c in content if isinstance(c, dict))
            ):
                last_kind = "prompt"
            continue
        msg_model = message.get("model")
        if msg_model and not str(msg_model).startswith("<"):
            model = msg_model
            if entry.get("effort"):
                effort = entry.get("effort")
            usage = message.get("usage") or {}
            key = str(message.get("id") or entry.get("requestId") or entry.get("uuid"))
            if usage and key not in seen_usage:
                seen_usage.add(key)
                contexts.append(
                    int(usage.get("input_tokens") or 0)
                    + int(usage.get("cache_read_input_tokens") or 0)
                    + int(usage.get("cache_creation_input_tokens") or 0)
                )
                outputs.append(int(usage.get("output_tokens") or 0))
        for block in message.get("content") or []:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "tool_use":
                actions.append(
                    {
                        "tool": block.get("name") or "",
                        "text": describe_tool(
                            str(block.get("name") or ""), block.get("input") or {}
                        ),
                        "at": entry.get("timestamp"),
                    }
                )
                last_kind = "tool"
            elif btype == "text":
                last_kind = "reply"
            elif btype == "thinking":
                last_kind = "thinking"
    return {
        "model": model,
        "effort": effort,
        "actions": actions[-RECENT_ACTIONS:],
        "last_kind": last_kind,
        "last_time": last_time,
        "tokens": {
            "turns": len(contexts),
            "avg_context": round(sum(contexts) / len(contexts)) if contexts else 0,
            "last_context": contexts[-1] if contexts else 0,
            "avg_output": round(sum(outputs) / len(outputs)) if outputs else 0,
        },
    }


def current_action(summary: dict, busy: bool) -> str:
    """The speech bubble."""
    if not busy:
        return "taking a break"
    kind = summary.get("last_kind")
    if kind == "thinking":
        return "thinking"
    if kind == "reply":
        return "writing a reply"
    if kind == "prompt":
        return "reading the request"
    actions = summary.get("actions") or []
    if actions:
        return actions[-1]["text"]
    return "working"


def model_family(model: str | None) -> str | None:
    """opus, sonnet, haiku or fable from a model id, for colour coding."""
    if not model:
        return None
    lowered = model.lower()
    for family in ("opus", "sonnet", "haiku", "fable"):
        if family in lowered:
            return family
    return None
