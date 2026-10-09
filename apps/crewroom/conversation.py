"""A session's whole conversation, paged backwards through its transcript.

Transcripts reach tens of megabytes, so a page is about CHUNK_BYTES read from
a byte offset towards the start of the file, and the whole file is never
loaded. Pages always hold whole lines: the next page ends exactly where this
one began. The newest page drops a last line that is still being written.

Entries become plain items for the details panel: prompts, replies, tool calls
in plain words, and tool results as a size (with their text only when small).
Images and very large lines are only ever a size.
"""

from __future__ import annotations

import json
import os

import transcripts

CHUNK_BYTES = 256 * 1024
# One line longer than this (a screenshot result) is reported as a size only.
MAX_LINE_BYTES = 8 * 1024 * 1024
TEXT_CHARS = 20000
RESULT_TEXT_BYTES = 16 * 1024
DETAIL_CHARS = 300
SCAN_BYTES = 64 * 1024

# The first of these a tool call has becomes the small print under it.
DETAIL_KEYS = (
    "command",
    "file_path",
    "notebook_path",
    "path",
    "pattern",
    "url",
    "query",
    "description",
    "skill",
)


def _last_newline(fh, pos: int) -> int:
    """Offset of the last newline before `pos`, or -1. Scans backwards in
    blocks without keeping them."""
    while pos > 0:
        low = max(0, pos - SCAN_BYTES)
        fh.seek(low)
        index = fh.read(pos - low).rfind(b"\n")
        if index >= 0:
            return low + index
        pos = low
    return -1


def read_page(path: str, before: int | None = None, chunk: int = CHUNK_BYTES) -> dict:
    """Whole JSON lines ending at byte `before` (the end of the file when None),
    reaching back about `chunk` bytes. `before` in the result is where the
    next, older page ends; `more` is False once the start is reached."""
    with open(path, "rb") as fh:
        size = fh.seek(0, os.SEEK_END)
        end = size if before is None else max(0, min(int(before), size))
        if end == size:
            end = _last_newline(fh, end) + 1
        start = 0
        if end - chunk > 0:
            low = end - chunk
            # Read one byte early: a newline there means the line starting
            # exactly at `low` is whole and belongs to this page.
            fh.seek(low - 1)
            index = fh.read(end - low + 1).find(b"\n")
            start = low + index if index >= 0 else end
            if start >= end:  # a single line longer than the chunk
                start = _last_newline(fh, end - 1) + 1
        entries: list[dict] = []
        if end - start > MAX_LINE_BYTES:
            entries.append({"type": "_big", "bytes": end - start})
        elif end > start:
            fh.seek(start)
            for line in fh.read(end - start).split(b"\n"):
                if len(line) > MAX_LINE_BYTES:
                    entries.append({"type": "_big", "bytes": len(line)})
                    continue
                try:
                    entry = json.loads(line) if line.strip() else None
                except ValueError:
                    continue
                if isinstance(entry, dict):
                    entries.append(entry)
    return {"entries": entries, "before": start, "more": start > 0, "size": size}


def _cap(text: str, limit: int) -> tuple[str, bool]:
    return (text, False) if len(text) <= limit else (text[:limit], True)


def tool_detail(tool_input: object) -> str | None:
    if not isinstance(tool_input, dict):
        return None
    for key in DETAIL_KEYS:
        value = tool_input.get(key)
        if isinstance(value, str) and value.strip():
            return _cap(" ".join(value.split()), DETAIL_CHARS)[0]
    return None


def _image_bytes(block: dict) -> int:
    data = (block.get("source") or {}).get("data") or ""
    return len(data) * 3 // 4


def _result(block: dict, at: object) -> dict:
    content = block.get("content")
    parts = [content] if isinstance(content, str) else content or []
    texts: list[str] = []
    images = 0
    size = 0
    for part in parts:
        if isinstance(part, str):
            texts.append(part)
        elif isinstance(part, dict) and part.get("type") == "image":
            images += 1
            size += _image_bytes(part)
        elif isinstance(part, dict):
            texts.append(str(part.get("text") or ""))
    text = "\n".join(texts)
    text_bytes = len(text.encode("utf-8"))
    size += text_bytes
    return {
        "kind": "result",
        "tool_use_id": block.get("tool_use_id"),
        "bytes": size,
        "error": bool(block.get("is_error")),
        "text": text if text_bytes <= RESULT_TEXT_BYTES else None,
        "images": images,
        "at": at,
    }


def _text_item(kind: str, text: str, at: object) -> dict:
    text, cut = _cap(text, TEXT_CHARS)
    return {"kind": kind, "text": text, "truncated": cut, "at": at}


def items(entry: dict) -> list[dict]:
    """What one transcript entry shows in the conversation view."""
    kind = entry.get("type")
    if kind == "_big":
        return [{"kind": "big", "bytes": entry.get("bytes", 0)}]
    if kind not in ("user", "assistant") or entry.get("isSidechain"):
        return []
    at = entry.get("timestamp")
    meta = bool(entry.get("isMeta"))
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, str):
        if kind == "user" and not meta and content.strip():
            return [_text_item("prompt", content, at)]
        return [_text_item("reply", content, at)] if kind == "assistant" else []
    out: list[dict] = []
    for block in content or []:
        if not isinstance(block, dict):
            continue
        btype = block.get("type")
        if btype == "text" and str(block.get("text") or "").strip():
            if kind == "assistant":
                out.append(_text_item("reply", block["text"], at))
            elif not meta:
                out.append(_text_item("prompt", block["text"], at))
        elif btype == "image":
            out.append({"kind": "image", "bytes": _image_bytes(block), "at": at})
        elif btype == "tool_result":
            out.append(_result(block, at))
        elif btype == "tool_use":
            name = str(block.get("name") or "")
            out.append(
                {
                    "kind": "tool",
                    "id": block.get("id"),
                    "name": name,
                    "text": transcripts.describe_tool(name, block.get("input") or {}),
                    "detail": tool_detail(block.get("input")),
                    "at": at,
                }
            )
    return out


def page(path: str, before: int | None = None, chunk: int = CHUNK_BYTES) -> dict:
    raw = read_page(path, before, chunk)
    shown: list[dict] = []
    for entry in raw["entries"]:
        shown.extend(items(entry))
    return {
        "items": shown,
        "before": raw["before"],
        "more": raw["more"],
        "size": raw["size"],
    }
