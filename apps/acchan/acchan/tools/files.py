"""Files and folders: look, read, write, edit, find, search."""

from __future__ import annotations

import os
import shutil
from typing import Annotated

from ..registry import ToolError, tool
from ..sysutil import clip, run
from ..sysutil import folder as find_folder
from ..sysutil import path as to_path

TOOLSET = "files"
TOOLSET_SUMMARY = "list, read, write, edit, find and search files and folders"

TOOLSET_KEYWORDS = (
    "file",
    "files",
    "folder",
    "directory",
    "find",
    "where is",
    "save",
    "write",
    "create",
    "edit",
    "rename",
    "move",
    "delete",
    "trash",
    "code",
    "script",
    ".py",
    ".js",
    ".md",
    ".txt",
    "project",
    "function",
    "bug",
)
# (what a person says, tool, arguments): few-shot lines for the prompt
TOOLSET_EXAMPLES = [
    ("what's in my Downloads folder", "list_dir", {"path": "~/Downloads"}),
    ("find my tax return", "find_files", {"name": "tax"}),
]

TEXT_LIMIT = 400_000  # bytes read before a file counts as too big to open whole


@tool(TOOLSET, example={"path": "~/Documents"}, show=True, voice="ok")
def list_dir(
    path: Annotated[str, "Folder to list. ~ is home."] = ".",
    show_hidden: Annotated[bool, "Include dot-files"] = False,
) -> str:
    """Show what is inside one folder the user named (sub-folders end in /). To look for a file whose location is unknown, use find_files instead."""
    folder = find_folder(path)
    if not folder.is_dir():
        raise ToolError(f"{folder} is not a folder.")
    entries = sorted(folder.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    lines = []
    for entry in entries:
        if entry.name.startswith(".") and not show_hidden:
            continue
        if entry.is_dir():
            lines.append(entry.name + "/")
        else:
            try:
                size = entry.stat().st_size
            except OSError:
                size = 0
            lines.append(f"{entry.name}  ({_size(size)})")
    if not lines:
        return f"{folder} is empty."
    shown = lines[:200]
    more = f"\n... and {len(lines) - 200} more" if len(lines) > 200 else ""
    return f"{folder}:\n" + "\n".join(shown) + more


def _size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


@tool(TOOLSET, example={"path": "~/notes.txt"}, voice="ok")
def read_file(
    path: Annotated[str, "Path of the file"],
    start_line: Annotated[int, "First line to show, 1-based"] = 1,
    max_lines: Annotated[int, "How many lines to show"] = 250,
) -> str:
    """Read a text file with line numbers. For PDF, Word or other documents use read_document instead."""
    target = to_path(path)
    if target.is_dir():
        raise ToolError(f"{target} is a folder. Use list_dir.")
    if target.suffix.lower() in (".pdf", ".docx", ".odt", ".epub", ".pptx", ".xlsx"):
        raise ToolError(f"{target.name} is a document. Use read_document.")
    raw = target.read_bytes()[:TEXT_LIMIT]
    if b"\0" in raw[:4096]:
        raise ToolError(f"{target.name} is a binary file, not text.")
    lines = raw.decode("utf-8", "replace").splitlines()
    start = max(1, start_line)
    chunk = lines[start - 1 : start - 1 + max(1, max_lines)]
    body = "\n".join(f"{n:>5}  {line}" for n, line in enumerate(chunk, start))
    total = len(lines)
    end = start + len(chunk) - 1
    note = f"\n[lines {start}-{end} of {total}]" if total > len(chunk) else ""
    return (body or "(empty file)") + note


@tool(TOOLSET, example={"path": "~/todo.md", "content": "- buy milk\n"}, risky=True)
def write_file(
    path: Annotated[str, "Path of the file to create or replace"],
    content: Annotated[str, "The complete new text of the file"],
) -> str:
    """Create a file, or replace a whole file, with the given text. To change part of a file use edit_file."""
    target = to_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    existed = target.exists()
    target.write_text(content, encoding="utf-8")
    verb = "Replaced" if existed else "Created"
    return f"{verb} {target} ({len(content.splitlines())} lines)."


@tool(
    TOOLSET,
    example={"path": "~/game/index.html", "content": "function loop() {}\n"},
    risky=True,
)
def append_file(
    path: Annotated[str, "Path of the file to add to (made if missing)"],
    content: Annotated[str, "The text to add at the end"],
) -> str:
    """Add text to the end of a file. Write a long file in parts: write_file with the first part, then append_file for each next part."""
    target = to_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as f:
        f.write(content)
    total = len(target.read_text(encoding="utf-8").splitlines())
    return f"Added to {target}: now {total} lines."


@tool(
    TOOLSET,
    example={"path": "app.py", "old": "print('hi')", "new": "print('hello')"},
    risky=True,
)
def edit_file(
    path: Annotated[str, "Path of the file"],
    old: Annotated[
        str,
        "Exact existing text to replace (copy it from read_file, without line numbers)",
    ],
    new: Annotated[str, "Text to put in its place"],
) -> str:
    """Replace one exact piece of text in a file. Read the file first so `old` matches exactly."""
    target = to_path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count == 1:
        target.write_text(text.replace(old, new, 1), encoding="utf-8")
        return f"Edited {target.name}: replaced 1 block."
    if count > 1:
        raise ToolError(
            f"`old` appears {count} times in {target.name}. Include more surrounding lines so it is unique."
        )
    # Small models drop or add indentation. Try a whitespace-tolerant match
    # line by line before giving up.
    want = [line.strip() for line in old.strip("\n").splitlines()]
    lines = text.splitlines(keepends=True)
    hits = [
        i
        for i in range(len(lines) - len(want) + 1)
        if [lines[i + j].strip() for j in range(len(want))] == want
    ]
    if len(hits) == 1:
        i = hits[0]

        def indent_of(line: str) -> str:
            return line[: len(line) - len(line.lstrip())]

        originals = [indent_of(lines[i + j]) for j in range(len(want))]
        new_lines = new.strip("\n").splitlines()
        if len(new_lines) == len(want):
            # Same shape: each line keeps the indentation of the line it replaces.
            fixed = [
                originals[k] + line.lstrip() if line.strip() else line
                for k, line in enumerate(new_lines)
            ]
        else:
            # Different shape: keep the new text's own relative indentation,
            # anchored where the old block started.
            base = indent_of(new_lines[0]) if new_lines else ""
            fixed = [
                (
                    originals[0]
                    + (line[len(base) :] if line.startswith(base) else line.lstrip())
                    if line.strip()
                    else line
                )
                for line in new_lines
            ]
        replacement = "".join(line + "\n" for line in fixed)
        lines[i : i + len(want)] = [replacement]
        target.write_text("".join(lines), encoding="utf-8")
        return f"Edited {target.name}: replaced 1 block (indentation adjusted)."
    first = want[0] if want else ""
    near = [n + 1 for n, line in enumerate(lines) if first and first in line][:3]
    hint = f" The first line appears near line(s) {near}." if near else ""
    raise ToolError(
        f"`old` was not found in {target.name}.{hint} Use read_file and copy the text exactly."
    )


@tool(TOOLSET, example={"name": "invoice", "folder": "~"}, voice="ok")
def find_files(
    name: Annotated[str, "Part of the file or folder name to look for"],
    folder: Annotated[str, "Where to look"] = "~",
    kind: Annotated[str, "file, folder or any"] = "any",
) -> str:
    """Search every folder for files or folders by name (partial names work, newest first). Use this whenever the user says find, where is, locate, or names a file without its folder."""
    root = find_folder(folder)
    cmd = [
        "fd",
        "-i",
        "--max-results",
        "60",
        "-E",
        "winbuild/wineprefix",
        "-E",
        ".venv",
        "-E",
        "node_modules",
    ]
    if kind == "file":
        cmd += ["-t", "f"]
    elif kind == "folder":
        cmd += ["-t", "d"]
    cmd += [name, str(root)]
    code, out = run(cmd, timeout=40)
    found = [line for line in out.splitlines() if line.strip()]
    if not found:
        return f"Nothing named like {name!r} under {root}."
    found.sort(
        key=lambda p: os.path.getmtime(p) if os.path.exists(p) else 0, reverse=True
    )
    return "\n".join(found)


@tool(TOOLSET, example={"text": "def main", "folder": "~/project"}, voice="ok")
def search_text(
    text: Annotated[str, "Words or regex to search for inside files"],
    folder: Annotated[str, "Folder (or single file) to search"] = ".",
    file_glob: Annotated[str, "Only files matching this, like *.py"] = "",
) -> str:
    """Search inside files for text. Returns file:line: matching line."""
    cmd = [
        "rg",
        "-n",
        "-i",
        "--max-count",
        "5",
        "--max-columns",
        "200",
        "-g",
        "!winbuild/wineprefix",
    ]
    if file_glob:
        cmd += ["-g", file_glob]
    cmd += ["--", text, str(to_path(folder))]
    code, out = run(cmd, timeout=40)
    if code == 1 or not out.strip():
        return f"No matches for {text!r}."
    return clip(out, 6000)


@tool(
    TOOLSET,
    example={"source": "~/Downloads/a.pdf", "destination": "~/Documents/"},
    risky=True,
)
def move_path(
    source: Annotated[str, "File or folder to move or rename"],
    destination: Annotated[str, "New path, or an existing folder to move it into"],
) -> str:
    """Move or rename a file or folder."""
    src, dst = to_path(source), to_path(destination)
    if not src.exists():
        raise ToolError(f"{src} does not exist.")
    final = shutil.move(str(src), str(dst))
    return f"Moved to {final}."


@tool(TOOLSET, example={"target": "~/Downloads/old.zip"}, risky=True)
def trash(target: Annotated[str, "File or folder to move to the trash"]) -> str:
    """Move a file or folder to the trash (recoverable). Never deletes permanently."""
    item = to_path(target)
    if not item.exists():
        raise ToolError(f"{item} does not exist.")
    run(["gio", "trash", str(item)], check=True)
    return f"Moved {item} to the trash."


@tool(TOOLSET, example={"folder": "~/projects/new"}, voice="ok")
def make_folder(folder: Annotated[str, "Folder to create (parents too)"]) -> str:
    """Create a folder."""
    target = to_path(folder)
    target.mkdir(parents=True, exist_ok=True)
    return f"Folder ready: {target}"
