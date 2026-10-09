"""Applies and undoes single-literal edits to keybind/variables Lua files.

Every write goes through the same path: back up the whole file, patch only
the exact byte span that was matched, syntax-check with `luac -p`, and roll
back immediately on failure. A file this tool touches is one Hyprland loads
live, so a half-broken write is not an acceptable failure mode -- the file
must always come out of this either correctly changed or byte-identical to
before.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
BACKUPS_DIR = DATA_DIR / "backups"
HISTORY_FILE = DATA_DIR / "history.jsonl"


class EditConflict(Exception):
    """The file no longer contains old_text at the expected line -- someone
    else (or a previous edit) changed it since the caller last read it."""


class SyntaxCheckFailed(Exception):
    def __init__(self, luac_output: str):
        super().__init__(luac_output)
        self.luac_output = luac_output


@dataclass
class HistoryEntry:
    id: str
    timestamp: float
    action: str  # "edit" | "revert"
    file: str
    line: int
    old_text: str
    new_text: str
    description: str | None
    scopes: list[str]


def _ensure_dirs() -> None:
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _backup(file: Path) -> Path:
    _ensure_dirs()
    ts = time.strftime("%Y%m%d-%H%M%S")
    dest = BACKUPS_DIR / f"{ts}-{uuid.uuid4().hex[:8]}-{file.name}"
    shutil.copy2(file, dest)
    return dest


def _syntax_check(file: Path) -> str | None:
    """Returns None if the file is valid Lua, else the luac error output."""
    result = subprocess.run(
        ["luac", "-p", str(file)], capture_output=True, text=True, timeout=10
    )
    return None if result.returncode == 0 else (result.stderr or result.stdout)


def _append_history(entry: HistoryEntry) -> None:
    _ensure_dirs()
    with HISTORY_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(entry)) + "\n")


def read_history() -> list[dict]:
    if not HISTORY_FILE.exists():
        return []
    entries = []
    with HISTORY_FILE.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue  # one damaged line never hides the rest of the history
            if _well_formed(entry):
                entries.append(entry)
    entries.sort(key=lambda e: e["timestamp"], reverse=True)
    return entries


def _well_formed(entry: object) -> bool:
    """A history line Undo and the History tab can use (a hand-edited or
    half-written line is skipped rather than breaking either)."""
    if not isinstance(entry, dict):
        return False
    stamp, line = entry.get("timestamp"), entry.get("line")
    return (
        isinstance(entry.get("id"), str)
        and isinstance(stamp, (int, float))
        and not isinstance(stamp, bool)
        and isinstance(line, int)
        and not isinstance(line, bool)
        and all(isinstance(entry.get(k), str) for k in ("file", "old_text", "new_text"))
    )


def apply_edit(
    file: Path,
    line: int,
    old_text: str,
    new_text: str,
    description: str | None,
    scopes: list[str],
    action: str = "edit",
) -> HistoryEntry:
    """Replaces the first occurrence of old_text found starting on `line`
    with new_text, after backing up the file, and rejects the write if the
    resulting file doesn't parse as valid Lua."""
    text = file.read_text(encoding="utf-8")
    lines = text.split("\n")
    if line < 1 or line > len(lines):
        raise EditConflict(f"{file} no longer has a line {line}")

    target_line = lines[line - 1]
    if old_text not in target_line:
        raise EditConflict(
            f"{file}:{line} no longer contains {old_text!r} -- it may have "
            "changed since this bind was listed. Refresh and try again."
        )

    _backup(file)

    lines[line - 1] = target_line.replace(old_text, new_text, 1)
    new_full_text = "\n".join(lines)
    file.write_text(new_full_text, encoding="utf-8")

    error = _syntax_check(file)
    if error is not None:
        # Restore the exact previous bytes rather than trusting a second patch.
        file.write_text(text, encoding="utf-8")
        raise SyntaxCheckFailed(error)

    entry = HistoryEntry(
        id=uuid.uuid4().hex,
        timestamp=time.time(),
        action=action,
        file=str(file),
        line=line,
        old_text=old_text,
        new_text=new_text,
        description=description,
        scopes=scopes,
    )
    _append_history(entry)
    return entry


def undo(history_id: str) -> HistoryEntry:
    entries = read_history()
    target = next((e for e in entries if e["id"] == history_id), None)
    if target is None:
        raise KeyError(f"no history entry {history_id}")

    return apply_edit(
        file=Path(target["file"]),
        line=target["line"],
        old_text=target["new_text"],
        new_text=target["old_text"],
        description=target.get("description"),
        scopes=target.get("scopes") or [],
        action="revert",
    )
