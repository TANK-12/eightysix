"""The Docs section: the text documents Emerson and Claude read (handoffs,
plans, briefs, results, rules), in folders, dated, newest first, read-only.

WHERE DOCS COME FROM
    doc_sources.json, one entry per source (folder, root, depth, ext, skip).
    Adding a source is one entry there. New documents go into the library,
    ~/Forge/docs/library/<topic>/<YYYY-MM-DD>-<name>.md (the rule in
    ~/.claude/CLAUDE.md); everything else is listed where it already is.

HOW A DOC IS DATED
    A YYYY-MM-DD in the file name first, then a "date: YYYY-MM-DD" style line
    near the top, then the file's last change. `dated_by` says which.

Nothing here writes or deletes a file. A doc is only read when its path is in
the current listing, so the API cannot be used to read anything else.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCES = Path(os.environ.get("FORGE_DOC_SOURCES", ROOT / "doc_sources.json"))
LIBRARY = Path.home() / "Forge/docs/library"

SKIP_DIRS = {
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".git",
    "site-packages",
    "wineprefix",
}
SKIP_FILES = re.compile(r"^(requirements.*|license.*|copying.*)\.txt$", re.I)
TEXT_EXT = (".md", ".txt")
MAX_BYTES = 2_000_000
HEAD_LINES = 40

NAME_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")
HEAD_DATE = re.compile(
    r"^\W*(?:date|dated|written|created|updated)\b[^0-9\n]{0,8}(\d{4}-\d{2}-\d{2})",
    re.I | re.M,
)


def _real_date(text: str) -> str | None:
    try:
        datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        return None
    return text


def load_sources(path: Path | None = None) -> list[dict]:
    data = json.loads((path or SOURCES).read_text())
    return list(data.get("sources", []))


def _walk(source: dict):
    root = Path(os.path.expanduser(source["root"]))
    if not root.is_dir():
        return
    depth = int(source.get("depth", 1))
    exts = tuple(e.lower() for e in source.get("ext", TEXT_EXT))
    skip = SKIP_DIRS | set(source.get("skip", []))
    for dirpath, dirnames, filenames in os.walk(root):
        level = len(Path(dirpath).relative_to(root).parts)
        dirnames[:] = sorted(
            d
            for d in dirnames
            if d not in skip and not d.startswith(".") and level + 1 < depth
        )
        for name in sorted(filenames):
            if name.lower().endswith(exts) and not SKIP_FILES.match(name):
                yield root, Path(dirpath) / name


def _head(path: Path) -> str:
    try:
        with path.open(encoding="utf-8", errors="replace") as f:
            return "".join(line for _, line in zip(range(HEAD_LINES), f))
    except OSError:
        return ""


def _front(head: str) -> dict:
    """The name and description from a --- front matter block, if any."""
    if not head.startswith("---"):
        return {}
    block = head[3:].split("\n---", 1)[0]
    found = {}
    for line in block.splitlines():
        key, _, value = line.partition(":")
        if key.strip() in ("name", "description") and value.strip():
            found[key.strip()] = value.strip()
    return found


def _title(head: str, front: dict, path: Path) -> str:
    for line in head.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return front.get("name") or path.stem


def _summary(head: str, front: dict) -> str:
    if front.get("description"):
        return front["description"][:200]
    body = head.split("\n---", 1)[1] if head.startswith("---") else head
    for line in body.splitlines():
        line = line.strip()
        if line and not line.startswith(("#", "---", "|", "```")):
            return line[:200]
    return ""


def _date(name: str, head: str, mtime: float) -> tuple[str, str]:
    for match in NAME_DATE.finditer(name):
        if _real_date(match.group(1)):
            return match.group(1), "name"
    for match in HEAD_DATE.finditer(head):
        if _real_date(match.group(1)):
            return match.group(1), "header"
    return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d"), "modified"


def describe(path: Path, folder: list[str]) -> dict:
    stat = path.stat()
    head = _head(path)
    front = _front(head)
    date, dated_by = _date(path.name, head, stat.st_mtime)
    return {
        "path": str(path),
        "folder": folder,
        "name": path.name,
        "title": _title(head, front, path),
        "summary": _summary(head, front),
        "date": date,
        "dated_by": dated_by,
        "updated": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
        "size": stat.st_size,
    }


def _matches(doc: dict, terms: list[str]) -> bool:
    hay = f"{doc['title']} {doc['path']} {doc['summary']}".lower()
    if all(t in hay for t in terms):
        return True
    try:
        text = Path(doc["path"]).read_text(errors="replace")[:MAX_BYTES].lower()
    except OSError:
        return False
    return all(t in hay or t in text for t in terms)


def listing(q: str = "", sources: list[dict] | None = None) -> dict:
    """Every doc from every source, newest first; `q` keeps the docs whose
    title, path or text holds every word of it."""
    sources = load_sources() if sources is None else sources
    seen: set[str] = set()
    docs = []
    for source in sources:
        top = [p for p in str(source["folder"]).split("/") if p]
        for root, path in _walk(source):
            key = str(path.resolve())
            if key in seen:
                continue
            seen.add(key)
            sub = path.parent.relative_to(root).parts
            folder = top + (list(sub) if source.get("subfolders", True) else [])
            try:
                docs.append(describe(path, folder))
            except OSError:
                continue
    terms = q.lower().split()
    if terms:
        docs = [d for d in docs if _matches(d, terms)]
    docs.sort(key=lambda d: (d["date"], d["updated"]), reverse=True)
    order = []
    for source in sources:
        first = str(source["folder"]).split("/")[0]
        if first not in order:
            order.append(first)
    return {"folders": order, "docs": docs, "library": str(LIBRARY)}


def read(path: str, sources: list[dict] | None = None) -> dict:
    """One listed doc with its text. KeyError for anything not in the listing."""
    wanted = str(Path(path).resolve())
    for doc in listing(sources=sources)["docs"]:
        if str(Path(doc["path"]).resolve()) == wanted:
            raw = Path(doc["path"]).read_bytes()[:MAX_BYTES]
            return {**doc, "text": raw.decode("utf-8", errors="replace")}
    raise KeyError(path)
