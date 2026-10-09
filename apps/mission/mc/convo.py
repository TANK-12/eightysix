"""A session's transcript as the Claude app's conversation events.

Mission Control draws chats with the Claude app's own renderer
(shared/forge_convo.js), which takes Claude Code's stream-json events plus the
Claude app's forge_* events. A transcript (~/.claude/projects/<dir>/<id>.jsonl)
holds nearly the same lines, so each one is turned into those events here:

- a prompt -> forge_user (text, time; a message typed mid-turn says so);
  a helper's task notification (handed over as if typed) -> one forge_sys
  line, its summary;
- an assistant line -> assistant, its blocks trimmed (long tool inputs cut,
  thinking text kept, signatures dropped);
- tool results -> user with tool_result blocks (text cut to RESULT_CHARS,
  images kept only when small);
- a compacted conversation -> the compact divider;
- a board note from Emerson handed over by the notes hook -> forge_user with
  `via: "board note #N"`, so a "Message" shows where it landed.

Pages: the newest TAIL_BYTES on first open, older pages with `before` (the
crew room's backwards reader), and the live tail with `after`, a byte offset
the page keeps. Only whole lines are ever read; a last line still being
written waits for the next poll.
"""

from __future__ import annotations

import json
import os
import re

from mc import borrow

TAIL_BYTES = 384 * 1024
AFTER_MAX_BYTES = 2 * 1024 * 1024
MAX_LINE_BYTES = 8 * 1024 * 1024
TEXT_CHARS = 20000
INPUT_CHARS = 3000
RESULT_CHARS = 4000
IMAGE_B64_MAX = 600 * 1024

NOTE_LINE = re.compile(
    r"^#(\d+) Emerson(?: \([^)]*\))? -> ([^:]+): (.*?)(?: \(\d+[smhd] ago\))?$",
    re.M,
)
COMMAND = re.compile(r"<command-name>([^<]*)</command-name>")
COMMAND_ARGS = re.compile(r"<command-args>([^<]*)</command-args>", re.S)
STDOUT = re.compile(r"<local-command-stdout>(.*?)</local-command-stdout>", re.S)
REMINDER = re.compile(r"<system-reminder>.*?</system-reminder>", re.S)
# a background helper or command that finished, handed over as if typed
NOTIFY = re.compile(r"<task-notification>(.*?)(?:</task-notification>|$)", re.S)
NOTIFY_PART = re.compile(r"<(summary|status)>(.*?)</\1>", re.S)
INTERRUPTED = "[Request interrupted by user"


def _cut(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + "\n…"


def _trim_input(value: object, depth: int = 0) -> object:
    """A tool call's input with long strings cut (a Write's whole file)."""
    if isinstance(value, str):
        return _cut(value, INPUT_CHARS)
    if isinstance(value, dict) and depth < 4:
        return {k: _trim_input(v, depth + 1) for k, v in value.items()}
    if isinstance(value, list) and depth < 4:
        return [_trim_input(v, depth + 1) for v in value[:50]]
    return value


def _image_part(part: dict) -> dict:
    data = (part.get("source") or {}).get("data") or ""
    if len(data) <= IMAGE_B64_MAX:
        return part
    return {"type": "text", "text": f"[a {len(data) * 3 // 4 // 1024} KB image]"}


def _result_block(block: dict) -> dict:
    content = block.get("content")
    if isinstance(content, str):
        content = _cut(content, RESULT_CHARS)
    elif isinstance(content, list):
        parts = []
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "image":
                parts.append(_image_part(part))
            else:
                parts.append(
                    {
                        "type": "text",
                        "text": _cut(str(part.get("text") or ""), RESULT_CHARS),
                    }
                )
        content = parts
    else:
        content = ""
    return {
        "type": "tool_result",
        "tool_use_id": block.get("tool_use_id"),
        "content": content,
        "is_error": bool(block.get("is_error")),
    }


def prompt_text(text: str) -> tuple[str, str]:
    """What a typed message shows: ("user", words), ("sys", a line) or ("", "")
    for wrapper-only text (a system reminder, a hook's echo)."""
    command = COMMAND.search(text)
    if command:
        args = COMMAND_ARGS.search(text)
        extra = (" " + args.group(1).strip()) if args and args.group(1).strip() else ""
        return "user", command.group(1).strip() + extra
    note = NOTIFY.search(text)
    if note:
        parts = dict(NOTIFY_PART.findall(note.group(1)))
        line = " ".join((parts.get("summary") or "").split()) or "A helper finished"
        status = (parts.get("status") or "").strip()
        if status and status != "completed":
            line += f" ({status})"
        return "sys", _cut(line, 300)
    stdout = STDOUT.search(text)
    if stdout:
        out = stdout.group(1).strip()
        return ("sys", _cut(out, 600)) if out else ("", "")
    text = REMINDER.sub("", text).strip()
    if not text:
        return "", ""
    if text.startswith(INTERRUPTED):
        return "sys", "Interrupted."
    return "user", _cut(text, TEXT_CHARS)


def _user_events(entry: dict, at: object) -> list[dict]:
    if entry.get("isCompactSummary") or entry.get("isVisibleInTranscriptOnly"):
        return []  # the summary a compaction writes; the divider marks it
    content = (entry.get("message") or {}).get("content")
    meta = bool(entry.get("isMeta"))
    if isinstance(content, str):
        content = [{"type": "text", "text": content}]
    texts: list[str] = []
    results: list[dict] = []
    images = 0
    for block in content or []:
        if not isinstance(block, dict):
            continue
        kind = block.get("type")
        if kind == "tool_result":
            results.append(_result_block(block))
        elif kind == "text" and not meta:
            texts.append(str(block.get("text") or ""))
        elif kind == "image" and not meta:
            images += 1
    events: list[dict] = []
    if results:
        events.append({"type": "user", "message": {"content": results}, "at": at})
    words = "\n".join(t for t in texts if t.strip())
    shown, line = prompt_text(words) if words else ("", "")
    if images:
        pics = f"[{images} image{'s' if images > 1 else ''}]"
        shown, line = "user", (line + "\n" + pics).strip() if shown == "user" else pics
    if shown == "user":
        events.append({"type": "forge_user", "text": line, "at": at})
    elif shown == "sys":
        events.append({"type": "forge_sys", "text": line, "at": at})
    return events


def _assistant_event(entry: dict, at: object) -> list[dict]:
    message = entry.get("message") or {}
    if entry.get("isApiErrorMessage"):
        text = " ".join(
            str(b.get("text") or "")
            for b in message.get("content") or []
            if isinstance(b, dict)
        )
        return [{"type": "forge_sys", "tone": "bad", "text": _cut(text, 600), "at": at}]
    blocks = []
    for block in message.get("content") or []:
        if not isinstance(block, dict):
            continue
        kind = block.get("type")
        if kind == "text" and str(block.get("text") or "").strip():
            blocks.append({"type": "text", "text": _cut(block["text"], TEXT_CHARS)})
        elif kind == "thinking":
            # Claude Code often keeps only the signature; an empty card
            # per step would be noise, so only kept reasoning is shown.
            text = str(block.get("thinking") or "")
            if text.strip():
                blocks.append({"type": "thinking", "thinking": _cut(text, TEXT_CHARS)})
        elif kind == "tool_use":
            blocks.append(
                {
                    "type": "tool_use",
                    "id": block.get("id"),
                    "name": str(block.get("name") or ""),
                    "input": _trim_input(block.get("input") or {}),
                }
            )
    if not blocks:
        return []
    return [
        {
            "type": "assistant",
            "message": {"id": message.get("id"), "content": blocks},
            "model": message.get("model"),
            "at": at,
        }
    ]


def _attachment_events(entry: dict, at: object) -> list[dict]:
    att = entry.get("attachment") or {}
    kind = att.get("type")
    if kind == "hook_additional_context":
        content = att.get("content")
        text = "\n".join(content) if isinstance(content, list) else str(content or "")
        return [
            {
                "type": "forge_user",
                "text": m.group(3).strip(),
                "via": f"board note #{m.group(1)} from Emerson",
                "note": int(m.group(1)),
                "at": at,
            }
            for m in NOTE_LINE.finditer(text)
        ]
    if kind == "queued_command":
        prompt = att.get("prompt")
        if isinstance(prompt, list):
            prompt = "\n".join(
                str(p.get("text") or "") for p in prompt if isinstance(p, dict)
            )
        shown, line = prompt_text(str(prompt or ""))
        if shown == "user":
            return [{"type": "forge_user", "text": line, "during_turn": True, "at": at}]
        if shown == "sys":
            return [{"type": "forge_sys", "text": line, "at": at}]
    return []


def events(entry: dict) -> list[dict]:
    """The Claude app events one transcript line becomes (often none)."""
    kind = entry.get("type")
    if kind == "_big":
        size = int(entry.get("bytes") or 0) // 1024
        return [{"type": "forge_sys", "text": f"a {size} KB entry is not shown"}]
    if entry.get("isSidechain"):
        return []
    at = entry.get("timestamp")
    if kind == "user":
        return _user_events(entry, at)
    if kind == "assistant":
        return _assistant_event(entry, at)
    if kind == "attachment":
        return _attachment_events(entry, at)
    if kind == "system" and entry.get("subtype") == "compact_boundary":
        return [
            {
                "type": "system",
                "subtype": "compact_boundary",
                "compact_metadata": entry.get("compactMetadata") or {},
                "at": at,
            }
        ]
    return []


def _line_end(fh, pos: int, size: int) -> int | None:
    """Just past the next newline at or after pos, or None when the line is
    still being written."""
    fh.seek(pos)
    while pos < size:
        block = fh.read(min(1024 * 1024, size - pos))
        hit = block.find(b"\n")
        if hit >= 0:
            return pos + hit + 1
        pos += len(block)
    return None


def _whole_end(fh, size: int) -> int:
    """Where the last whole line ends (just after its newline)."""
    borrow.setup()
    import conversation  # pyright: ignore[reportMissingImports]

    return conversation._last_newline(fh, size) + 1


def _parse(lines: list[bytes]) -> list[dict]:
    out: list[dict] = []
    for line in lines:
        if len(line) > MAX_LINE_BYTES:
            out.extend(events({"type": "_big", "bytes": len(line)}))
            continue
        try:
            entry = json.loads(line) if line.strip() else None
        except ValueError:
            continue
        if isinstance(entry, dict):
            out.extend(events(entry))
    return out


def page(
    path: str,
    before: int | None = None,
    after: int | None = None,
    chunk: int = TAIL_BYTES,
) -> dict:
    """Events from a transcript.

    after=N: everything written since byte N (the live tail), up to
    AFTER_MAX_BYTES at a time; `after` in the answer is where to ask next,
    and `reset` says the file got shorter (start again from the tail).
    Otherwise the page ending at `before` (the newest when None), with
    `before` for the next older page and `after` for the live tail.
    """
    with open(path, "rb") as fh:
        size = fh.seek(0, os.SEEK_END)
        if after is not None:
            if after > size:
                return {"events": [], "after": 0, "size": size, "reset": True}
            fh.seek(after)
            data = fh.read(min(size - after, AFTER_MAX_BYTES))
            cut = data.rfind(b"\n")
            if cut < 0 and len(data) == AFTER_MAX_BYTES:
                # one line longer than the window: step over it, say so
                end = _line_end(fh, after + len(data), size)
                if end is None:
                    return {"events": [], "after": after, "size": size, "reset": False}
                return {
                    "events": events({"type": "_big", "bytes": end - after}),
                    "after": end,
                    "size": size,
                    "reset": False,
                    "more": end < _whole_end(fh, size),
                }
            if cut < 0:
                return {"events": [], "after": after, "size": size, "reset": False}
            data = data[: cut + 1]
            return {
                "events": _parse(data.split(b"\n")),
                "after": after + len(data),
                "size": size,
                "reset": False,
                "more": after + len(data) < _whole_end(fh, size),
            }
        end = _whole_end(fh, size)
    borrow.setup()
    import conversation  # pyright: ignore[reportMissingImports]

    raw = conversation.read_page(path, end if before is None else before, chunk)
    shown: list[dict] = []
    for entry in raw["entries"]:
        shown.extend(events(entry))
    return {
        "events": shown,
        "before": raw["before"],
        "more": raw["more"],
        "after": end,
        "size": size,
    }


def handed_notes(
    path: str, start: int = 0, end: int | None = None, carry: list | None = None
) -> list[dict]:
    """Board notes from Emerson handed to this transcript between bytes
    `start` and `end`, each with the first reply written after it:
    [{note, at, reply, reply_at}]. `carry` are notes handed over in an
    earlier read that still wait for a reply; they come back first."""
    found: list[dict] = [] if carry is None else [dict(n) for n in carry]
    open_notes: list[dict] = list(found)
    with open(path, "rb") as fh:
        fh.seek(start)
        data = fh.read((end if end is not None else os.path.getsize(path)) - start)
    for line in data.split(b"\n"):
        if b"Emerson" not in line and b'"assistant"' not in line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if not isinstance(entry, dict) or entry.get("isSidechain"):
            continue
        for ev in events(entry):
            if ev["type"] == "forge_user" and ev.get("note"):
                note = {"note": ev["note"], "at": ev.get("at"), "reply": None}
                found.append(note)
                open_notes.append(note)
            elif (
                ev["type"] == "assistant"
                and open_notes
                and (entry.get("message") or {}).get("stop_reason") == "end_turn"
            ):
                # the text that ends the turn, not narration between tools
                text = "\n".join(
                    b["text"] for b in ev["message"]["content"] if b["type"] == "text"
                ).strip()
                if text:
                    for note in open_notes:
                        note["reply"] = _cut(text, 2000)
                        note["reply_at"] = ev.get("at")
                    open_notes = []
    return found
