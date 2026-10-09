"""Small shared helpers for tools: running commands, paths, trimming text."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from .registry import ToolError

HOME = Path.home()
CACHE = Path(os.environ.get("ACCHAN_CACHE", HOME / ".cache" / "acchan"))


def path(text: str) -> Path:
    """A user-given path, with ~ and $VARS expanded and relative paths taken
    from the working folder."""
    text = (text or ".").strip().strip("'\"")
    return Path(os.path.expandvars(os.path.expanduser(text))).resolve()


def folder(text: str) -> Path:
    """A folder the user named, however loosely: a real path, or a bare name
    like "Forge" / "my uni folder" found by searching near home (newest,
    shallowest match first)."""
    direct = path(text)
    if direct.is_dir():
        return direct
    name = re.sub(
        r"^(my|the)\s+|\s+(folder|directory|dir)$",
        "",
        text.strip().strip("'\"").lower(),
    )
    name = name.strip().strip("/")
    if not name or "/" in name:
        return direct
    for candidate in (HOME / name, HOME / name.capitalize(), HOME / name.upper()):
        if candidate.is_dir():
            return candidate
    if shutil.which("fd"):
        done = subprocess.run(
            [
                "fd",
                "-i",
                "-t",
                "d",
                "--max-depth",
                "4",
                "-E",
                "winbuild",
                "-E",
                ".venv",
                "-E",
                "node_modules",
                f"^{re.escape(name)}$",
                str(HOME),
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
        hits = [Path(p) for p in done.stdout.splitlines() if p.strip()]
        if hits:
            return sorted(hits, key=lambda p: (len(p.parts), -p.stat().st_mtime))[0]
    return direct


def run(
    cmd: list[str] | str,
    timeout: float = 30.0,
    cwd: str | Path | None = None,
    input_text: str | None = None,
    check: bool = False,
) -> tuple[int, str]:
    """Run a command, return (exit code, stdout+stderr). Never raises for a
    non-zero exit unless check=True."""
    shell = isinstance(cmd, str)
    if not shell and not shutil.which(cmd[0]):
        raise ToolError(f"{cmd[0]} is not installed.")
    try:
        done = subprocess.run(
            cmd,
            shell=shell,
            executable="/bin/bash" if shell else None,
            cwd=cwd,
            input=input_text,
            capture_output=True,
            text=True,
            timeout=timeout,
            errors="replace",
        )
    except subprocess.TimeoutExpired as exc:
        out = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        raise ToolError(f"Timed out after {timeout:g}s. Partial output:\n{out[-2000:]}")
    output = (done.stdout or "") + (done.stderr or "")
    if check and done.returncode != 0:
        raise ToolError(
            f"{cmd if shell else cmd[0]} failed ({done.returncode}): {output.strip()[-1500:]}"
        )
    return done.returncode, output


def spawn(cmd: list[str], cwd: str | Path | None = None) -> None:
    """Start a program detached from us, so it outlives the assistant."""
    if not shutil.which(cmd[0]):
        raise ToolError(f"{cmd[0]} is not installed.")
    subprocess.Popen(
        cmd,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def clip(text: str, limit: int) -> str:
    """Keep the start and end of a long text, with a note of what was cut."""
    if len(text) <= limit:
        return text
    head = int(limit * 0.7)
    tail = limit - head
    cut = len(text) - limit
    return f"{text[:head]}\n... [{cut} characters cut] ...\n{text[-tail:]}"


def json_line(output: str) -> dict:
    """The last JSON object line in mixed output (helpers print one; GLib
    warnings can surround it)."""
    import json

    for line in reversed(output.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                value = json.loads(line)
            except ValueError:
                continue
            if isinstance(value, dict):
                return value
    raise ValueError("no JSON object in output")
