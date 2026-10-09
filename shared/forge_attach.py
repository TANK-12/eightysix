"""Files Emerson attaches to a message (pasted, dropped, picked, or sent on
WhatsApp), saved to disk and handed to a Claude session as paths.

WHY
    Claude Code opens files by path (its Read tool shows pictures too), so an
    attachment only has to land somewhere on this laptop and be named in the
    message. Every place he talks to Claude (Relay's WhatsApp bridge, Mission
    Control, Relay's page) saves the same way and writes the same note, which
    is also the shape the Claude app has always used ("Attached files:" and
    one "- /path" line each).

    save() never overwrites: a second "pasted.png" becomes "pasted (1).png".
    Names are cut down to safe characters, so a name can never climb out of
    the folder. day_folder() keeps each day's files together.
"""

from __future__ import annotations

import base64
import binascii
import re
import time
from pathlib import Path

MAX_BYTES = 200 * 1024 * 1024
HEAD = "Attached files:"
TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/heic": ".heic",
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
    "video/3gpp": ".3gp",
    "audio/ogg": ".ogg",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
    "application/pdf": ".pdf",
    "text/plain": ".txt",
    "text/markdown": ".md",
}


def safe_name(name: str) -> str:
    """The last part of `name` with only safe characters; never empty, never
    a dot file, at most 120 bytes in UTF-8 (the extension is kept), so a long
    name in Japanese still fits the file system's 255-byte limit with room
    for " (12)"."""
    base = Path(str(name or "").replace("\\", "/")).name
    cleaned = re.sub(r"[^\w.\- ()]+", "_", base).strip(" .") or "file"
    if len(cleaned.encode()) > 120:
        stem, dot, ext = cleaned.rpartition(".")
        ext = ext[:16] if dot and stem else ""
        room = 120 - len(ext.encode()) - (1 if ext else 0)
        stem = (stem if ext else cleaned).encode()[:room].decode(errors="ignore")
        stem = stem.rstrip(" .") or "file"
        cleaned = f"{stem}.{ext}" if ext else stem
    return cleaned


def ext_for(media_type: str) -> str:
    """ ".png" for "image/png"; "" for a type not known here."""
    return TYPES.get((media_type or "").split(";")[0].strip().lower(), "")


def day_folder(root: Path | str, now: float | None = None) -> Path:
    """`root`/YYYY-MM-DD for today (local time)."""
    return Path(root) / time.strftime("%Y-%m-%d", time.localtime(now))


def save(
    folder: Path | str, name: str, data: bytes, max_bytes: int = MAX_BYTES
) -> Path:
    """Write `data` as `name` in `folder` (made if missing) without replacing
    anything already there. ValueError when it is over `max_bytes`."""
    if len(data) > max_bytes:
        raise ValueError(f"That file is larger than {max_bytes // (1024 * 1024)} MB")
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / safe_name(name)
    stem, suffix, n = target.stem, target.suffix, 1
    while True:
        try:
            with open(target, "xb") as f:  # "x": never two writers on one name
                f.write(data)
            return target
        except FileExistsError:
            target = folder / f"{stem} ({n}){suffix}"
            n += 1


def decode_base64(data: str, max_bytes: int = MAX_BYTES) -> bytes:
    """The bytes of base64 text (what a page sends). ValueError when it is not
    base64 or is too big (checked before decoding)."""
    if len(data or "") > max_bytes * 4 // 3 + 4:
        raise ValueError(f"That file is larger than {max_bytes // (1024 * 1024)} MB")
    try:
        return base64.b64decode(data or "", validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("The file data is not base64")


def save_base64(
    folder: Path | str, name: str, data: str, max_bytes: int = MAX_BYTES
) -> Path:
    """save() for base64 text. ValueError when it is not base64 or too big."""
    return save(folder, name, decode_base64(data, max_bytes), max_bytes)


def note(paths: list) -> str:
    """The lines that hand files to a session; "" for none."""
    if not paths:
        return ""
    return HEAD + "\n" + "\n".join(f"- {p}" for p in paths)


def with_note(text: str, paths: list) -> str:
    """`text` with the attached files' note under it."""
    text = (text or "").strip()
    listed = note(paths)
    if not listed:
        return text
    return f"{text}\n\n{listed}" if text else listed


def has_files(text: str) -> bool:
    """Whether `text` carries an attached-files note (an "- /path" line under
    the head)."""
    return bool(re.search(r"^Attached files:\n- /", text or "", re.M))


def inside(root: Path | str, path: str) -> Path | None:
    """`path` as a file inside `root`, or None (missing, or outside it: a page
    may only name files it uploaded there)."""
    try:
        base = Path(root).resolve()
        found = Path(path).expanduser().resolve()
    except (OSError, ValueError):
        return None
    if not found.is_file() or not found.is_relative_to(base):
        return None
    return found
