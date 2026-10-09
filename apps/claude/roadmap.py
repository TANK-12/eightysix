"""The roadmap tab (A28): every session brief in ~/Forge/sessions and the
forge board's open notes, as data for the Enjoy layout's star map.

WHAT IS READ
    Briefs are the dated files, `<date>-<slot>-<topic>.md` (README, STATUS
    and QUICKSTART are not briefs). From each: the title line (slot, the
    session's name from `session "Hub"`, the topic), the `## Ledger` items
    (`- **A15** "Emerson's words" -> what it means [core]`, with or without
    the bold, an optional label before the quote, `A17-A19` ranges) and the
    `## State` lines. Headings count only at the start of a line: a ledger
    line may quote the words "## State".

HOW A STATE LINE IS MATCHED
    Only a State line's first physical line is read for its state, and only
    the ids before its first ": " or ". " are its subjects, so a chunk list
    indented under it or an id mentioned in passing changes nothing.
    `A21 done, checked; A18 done` gives each part its own state. Sub-items
    (A15a, A15b-d) roll up into their item: all the same state keeps it,
    a mix of done and not done is "in progress". An item handed to another
    session ("-> handed to S8", or "brief written as `<date>-S9-...md`")
    shows that session's state for the same id, or "moved" when that
    session has no such item.
    An item with no State line is "not done".

The notes are the unanswered ones on the forge board
(~/.claude/crew/forge/board.json, crew.py), newest first.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

SESSIONS = Path(
    os.environ.get(
        "FORGE_SESSIONS_DIR", Path(__file__).resolve().parents[2] / "sessions"
    )
)
BOARD = (
    Path(os.environ.get("CREW_HOME", Path.home() / ".claude/crew")) / "forge/board.json"
)

BRIEF = re.compile(r"^(\d{4}-\d{2}-\d{2})-(.+)\.md$")
ITEM = re.compile(r"^-\s*(?:\*\*)?A(\d+)(?:\s*-\s*A(\d+))?(?:\*\*)?(?=[\s:*])\s*(.*)$")
IDS = re.compile(r"\bA(\d+)(?:[a-z](?:-[a-z])?)?(?:\s*-\s*A(\d+))?\b")
QUOTE = re.compile(r"[\"“]([^\"”]+)[\"”]")
TAG = re.compile(r"\[(core|detail|constraint)\]")
MOVED = re.compile(
    r"handed to (?:[A-Z][\w-]* )?\(?(S\d+)\b"
    r"|(?:brief written as|added to) `?\d{4}-\d{2}-\d{2}-(S\d+)-"
)
MAX_NOTES = 40

# Most certain first: a line saying "done + checked" and also "not seen in
# the real window" is done and checked.
STATE_WORDS = (
    (
        "done+checked",
        re.compile(r"done\s*(?:\+|and|,)\s*(?:[\w-]*-)?checked|checked headless"),
    ),
    ("not done", re.compile(r"not done|not started|\btodo\b")),
    ("blocked", re.compile(r"blocked|waiting on|waits on|needs emerson|needs his")),
    ("in progress", re.compile(r"in progress|working on|started|part done")),
    ("done not checked", re.compile(r"\bdone\b")),
)
DONE = ("done+checked", "done not checked")


def classify(text: str) -> str | None:
    low = text.lower().replace("**", "")
    for name, pattern in STATE_WORDS:
        if pattern.search(low):
            return name
    return None


def ids_in(text: str) -> list[str]:
    """A-ids named in text, ranges spelled out; sub-items (A15a) as A15."""
    found = []
    for m in IDS.finditer(text):
        first = int(m.group(1))
        last = int(m.group(2)) if m.group(2) else first
        for n in range(first, max(first, last) + 1) if last - first < 30 else [first]:
            if f"A{n}" not in found:
                found.append(f"A{n}")
    return found


def sections(lines: list[str]) -> dict[str, list[str]]:
    """Lines under each `## ` heading, keyed by the heading's first word."""
    out: dict[str, list[str]] = {}
    key = ""
    for line in lines:
        if line.startswith("## "):
            key = line[3:].split()[0].lower() if line[3:].split() else ""
            out.setdefault(key, [])
        elif key:
            out[key].append(line)
    return out


def entries(lines: list[str]) -> list[tuple[str, str]]:
    """`- ` entries as (first line, whole text with wrapped lines joined)."""
    found: list[list[str]] = []
    for line in lines:
        if line.startswith("- "):
            found.append([line.rstrip()])
        elif found and found[-1] and line.startswith((" ", "\t")) and line.strip():
            found[-1].append(line.strip())
        elif not line.strip() and found:
            found.append([])
    return [(e[0], " ".join(e)) for e in found if e]


def parse_item(text: str) -> list[dict]:
    m = ITEM.match(text)
    if not m:
        return []
    start, end, rest = int(m.group(1)), int(m.group(2) or m.group(1)), m.group(3)
    quote = QUOTE.search(rest)
    label = rest[: quote.start()].strip().rstrip(":").strip() if quote else ""
    after = rest[quote.end() :] if quote else rest
    meaning = after.split("->", 1)[1] if "->" in after else after
    tags = TAG.findall(text)
    moved = MOVED.search(text)
    base = {
        "quote": quote.group(1).strip() if quote else "",
        "label": label,
        "meaning": TAG.sub("", meaning).strip(),
        "tag": tags[-1] if tags else "",
        "moved_to": (moved.group(1) or moved.group(2)) if moved else "",
    }
    if end - start > 30:
        end = start
    return [dict(base, id=f"A{n}") for n in range(start, end + 1)]


def line_states(first: str) -> dict[str, str]:
    """{id: state} for one State line's subjects."""
    body = first[2:].strip()
    cut = [i for i in (body.find(": "), body.find(". ")) if i >= 0]
    head = body[: min(cut)] if cut else body[:120]
    whole = classify(first)
    found: dict[str, str] = {}
    for part in head.split(";"):
        state = classify(part) or whole
        for aid in ids_in(part):
            if state and aid not in found:
                found[aid] = state
    return found


def combine(states: list[str]) -> str:
    if len(set(states)) == 1:
        return states[0]
    if any(s in DONE for s in states):
        return "in progress"
    return "blocked" if "blocked" in states else states[-1]


def parse_brief(path: Path) -> dict:
    m = BRIEF.match(path.name)
    text = path.read_text(errors="replace")
    lines = text.splitlines()
    title = lines[0].lstrip("#").strip() if lines else path.stem
    slot_m = re.match(r"(?:\d{4}-\d{2}-\d{2}\s*)?(S\d+)\b", title) or re.match(
        r"(S\d+)-", m.group(2) if m else ""
    )
    name_m = re.search(r'session\s+"([^"]+)"', title)
    topic = re.sub(r"^\d{4}-\d{2}-\d{2}\s*", "", title)
    topic = re.sub(r"^S\d+\s*[:\-—]\s*", "", topic)
    topic = re.split(r"\s+[—-]\s+session\s+\"", topic)[0].strip()
    parts = sections(lines)

    items: list[dict] = []
    for _first, whole in entries(parts.get("ledger", [])):
        for item in parse_item(whole):
            if item["id"] not in [i["id"] for i in items]:
                items.append(item)

    state_lines = entries(parts.get("state", []))
    seen: dict[str, list[str]] = {}
    notes: dict[str, str] = {}
    for first, whole in state_lines:
        for aid, state in line_states(first).items():
            seen.setdefault(aid, []).append(state)
            notes[aid] = whole[2:].strip()
    for item in items:
        got = seen.get(item["id"])
        item["state"] = combine(got) if got else "not done"
        item["note"] = notes.get(item["id"], "")
        item["own_state"] = bool(got)

    return {
        "file": path.name,
        "date": m.group(1) if m else "",
        "slot": slot_m.group(1) if slot_m else "",
        "name": name_m.group(1) if name_m else "",
        "title": title,
        "topic": topic,
        "items": items,
        "state": [whole[2:].strip() for _first, whole in state_lines],
    }


def follow_moves(briefs: list[dict]) -> None:
    """A handed-on item without State lines of its own shows the state of
    the same id in the session it went to (same date first)."""
    for brief in briefs:
        for item in brief["items"]:
            if not item["moved_to"] or item["own_state"]:
                continue
            targets = sorted(
                (b for b in briefs if b["slot"] == item["moved_to"] and b is not brief),
                key=lambda b: b["date"] != brief["date"],
            )
            for target in targets:
                twin = next((i for i in target["items"] if i["id"] == item["id"]), None)
                if twin:
                    item["state"], item["note"] = twin["state"], twin["note"]
                    break
            else:
                item["state"] = "moved"


def board_notes(board: Path | None) -> list[dict]:
    if board is None:
        return []
    try:
        data = json.loads(Path(board).read_text())
    except (OSError, ValueError):
        return []
    notes = data.get("notes") if isinstance(data, dict) else None
    open_notes = [
        {k: n.get(k) for k in ("id", "t", "from", "to", "text", "re")}
        for n in (notes if isinstance(notes, list) else [])
        if isinstance(n, dict) and not n.get("ack")
    ]
    open_notes.sort(key=lambda n: n.get("t") or 0, reverse=True)
    return open_notes[:MAX_NOTES]


def build(sessions: Path | None = None, board: Path | None = BOARD) -> dict:
    folder = Path(sessions) if sessions is not None else SESSIONS
    try:
        files = sorted(p for p in folder.iterdir() if BRIEF.match(p.name))
    except OSError:
        files = []
    briefs = [parse_brief(p) for p in files]
    follow_moves(briefs)
    for brief in briefs:
        tasks = [i for i in brief["items"] if i["tag"] != "constraint"]
        brief["counts"] = {
            "total": len(tasks),
            "done": sum(1 for i in tasks if i["state"] in DONE),
        }
        for item in brief["items"]:
            del item["own_state"]
    slot_no = lambda b: int(b["slot"][1:]) if b["slot"] else 0  # noqa: E731
    briefs.sort(key=lambda b: (b["date"], slot_no(b)), reverse=True)
    return {"sessions": briefs, "notes": board_notes(board)}
