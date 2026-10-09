"""Starting Claude Code sessions from the Crew Room. This is the only part of
the app that writes or starts anything; reading the room stays read-only.

Two kinds, both asked for by Emerson on 2026-09-16:

- In a terminal: `gnome-terminal --working-directory=<folder> -- claude`. The
  new session writes ~/.claude/sessions/<pid>.json itself, so its character
  walks in with no extra wiring.
- In the background: a headless `claude -p` started by this backend, always in
  auto mode (his choice), with the prompt on stdin. Checked on this laptop
  (Claude Code 2.1.273): a headless run writes a session file too, with
  entrypoint "sdk-cli", and removes it when it exits, so it appears as a
  character while it runs. Each task keeps task.json, a pid file,
  output.jsonl (stream-json) and stderr.log in tasks/<session id>/.

There is no stop or message button on purpose: a misclick would cut off work.
"""

from __future__ import annotations

import glob
import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path

import transcripts
from claude_launch import find_claude, headless_command
from context import Context, proc_start_ticks

APPS_DIR = Path(__file__).resolve().parent.parent
MODE = "auto"
MODELS = {
    "": "Claude Code's default",
    "haiku": "Haiku",
    "sonnet": "Sonnet",
    "opus": "Opus",
    "fable": "Fable",
}
# Terminal program -> the arguments before the command; "{folder}" is filled
# in. Only gnome-terminal is checked on this laptop; one line adds another.
TERMINALS = {
    "gnome-terminal": ["gnome-terminal", "--working-directory={folder}", "--"],
}
SESSION_ID = re.compile(r"^[\w-]{1,64}$")
RECENT_TASKS = 20
RECENT_FOLDERS = 12
RESULT_CHARS = 300


class LaunchError(ValueError):
    """Something the person can fix, said in plain words."""


def data_dir() -> Path:
    return Path(
        os.environ.get("CREWROOM_DATA_DIR")
        or Path.home() / ".local" / "share" / "forge" / "crewroom"
    )


def tasks_dir() -> Path:
    return data_dir() / "tasks"


def claude_path() -> str | None:
    return find_claude("CREWROOM_CLAUDE_BIN")


def find_terminal() -> str | None:
    return next((name for name in TERMINALS if shutil.which(name)), None)


def resolve_folder(text: str) -> str:
    text = str(text or "").strip()
    if not text:
        raise LaunchError("Choose a folder first")
    folder = os.path.abspath(os.path.expanduser(text))
    if not os.path.isdir(folder):
        raise LaunchError(f"That folder does not exist: {folder}")
    return folder


def terminal_command(terminal: str, folder: str, claude: str) -> list[str]:
    return [part.replace("{folder}", folder) for part in TERMINALS[terminal]] + [claude]


def task_command(claude: str, session_id: str, model: str) -> list[str]:
    return headless_command(claude, session_id, MODE, model=model)


def _need_claude() -> str:
    claude = claude_path()
    if not claude:
        raise LaunchError("Claude Code (the claude command) is not installed")
    return claude


def open_terminal(folder_text: str) -> dict:
    folder = resolve_folder(folder_text)
    terminal = find_terminal()
    if not terminal:
        raise LaunchError(
            "No supported terminal program found (looked for "
            + ", ".join(TERMINALS)
            + ")"
        )
    args = terminal_command(terminal, folder, _need_claude())
    proc = subprocess.Popen(
        args,
        cwd=folder,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    threading.Thread(target=proc.wait, daemon=True).start()
    return {"terminal": terminal, "folder": folder, "command": args}


def start_task(
    prompt: str, folder_text: str, model: str = "", background: bool = True
) -> dict:
    """Start a headless task. `background=False` waits for it to finish,
    which only the tests use."""
    prompt = str(prompt or "").strip()
    if not prompt:
        raise LaunchError("Write what the task should do")
    if model not in MODELS:
        raise LaunchError(f"Unknown model: {model}")
    folder = resolve_folder(folder_text)
    claude = _need_claude()
    session_id = str(uuid.uuid4())
    home = tasks_dir() / session_id
    home.mkdir(parents=True)
    with open(home / "output.jsonl", "wb") as out, open(
        home / "stderr.log", "wb"
    ) as err:
        proc = subprocess.Popen(
            task_command(claude, session_id, model),
            cwd=folder,
            stdin=subprocess.PIPE,
            stdout=out,
            stderr=err,
            start_new_session=True,
        )
    record = {
        "id": session_id,
        "pid": proc.pid,
        "proc_start": proc_start_ticks("/proc", proc.pid),
        "prompt": prompt,
        "folder": folder,
        "model": model,
        "mode": MODE,
        "started_at": time.time(),
    }
    _write_json(home / "task.json", record)
    (home / "pid").write_text(f"{proc.pid}\n", encoding="utf-8")
    if background:
        threading.Thread(target=_finish, args=(proc, home, prompt), daemon=True).start()
    else:
        _finish(proc, home, prompt)
    return record


def _finish(proc: subprocess.Popen, home: Path, prompt: str) -> None:
    try:
        if proc.stdin is not None:
            proc.stdin.write(prompt.encode("utf-8"))
            proc.stdin.close()
    except (OSError, ValueError):
        pass  # it exited before reading; stderr.log says why
    code = proc.wait()
    record = _read_json(home / "task.json") or {}
    record.update(returncode=code, ended_at=time.time())
    _write_json(home / "task.json", record)


def find_task(session_id: str) -> dict | None:
    if not SESSION_ID.match(session_id or ""):
        return None
    return _read_json(tasks_dir() / session_id / "task.json")


def list_tasks(proc_dir: str = "/proc", limit: int = RECENT_TASKS) -> list[dict]:
    records = [
        r
        for r in (
            _read_json(Path(p)) for p in glob.glob(str(tasks_dir() / "*" / "task.json"))
        )
        if r and r.get("id")
    ]
    records.sort(key=lambda r: r.get("started_at") or 0, reverse=True)
    return [task_status(r, proc_dir) for r in records[:limit]]


def task_status(record: dict, proc_dir: str = "/proc") -> dict:
    home = tasks_dir() / str(record["id"])
    result: dict = {}
    for entry in reversed(transcripts.read_tail(str(home / "output.jsonl"))):
        if entry.get("type") == "result":
            result = entry
            break
    running = False
    if "returncode" not in record and record.get("pid"):
        started = proc_start_ticks(proc_dir, int(record["pid"]))
        running = started is not None and record.get("proc_start") in (None, started)
    if running:
        status = "running"
    elif result:
        status = "failed" if result.get("is_error") else "done"
    else:
        status = "done" if record.get("returncode") == 0 else "failed"
    text = str(result.get("result") or "")
    shown = {
        key: record.get(key)
        for key in ("id", "prompt", "folder", "model", "mode", "started_at")
    }
    shown.update(
        ended_at=record.get("ended_at"),
        status=status,
        result=text if len(text) <= RESULT_CHARS else text[: RESULT_CHARS - 1] + "…",
        cost_usd=result.get("total_cost_usd"),
        error=_stderr_tail(home) if status == "failed" else "",
    )
    return shown


def _stderr_tail(home: Path) -> str:
    try:
        with open(home / "stderr.log", "rb") as fh:
            fh.seek(0, os.SEEK_END)
            fh.seek(max(0, fh.tell() - 2048))
            lines = fh.read().decode("utf-8", "replace").strip().splitlines()
    except OSError:
        return ""
    return lines[-1] if lines else ""


def recent_folders(ctx: Context, limit: int = RECENT_FOLDERS) -> list[str]:
    """Folders of live sessions, then of the most recently written transcripts."""
    found: list[str] = []

    def add(folder: object) -> None:
        if isinstance(folder, str) and folder not in found and os.path.isdir(folder):
            found.append(folder)

    for path in glob.glob(os.path.join(ctx.claude_dir, "sessions", "*.json")):
        add((_read_json(Path(path)) or {}).get("cwd"))
    written = sorted(
        glob.glob(os.path.join(ctx.claude_dir, "projects", "*", "*.jsonl")),
        key=_mtime,
        reverse=True,
    )
    for path in written[: limit * 3]:
        if len(found) >= limit:
            break
        add(next((e["cwd"] for e in transcripts.read_head(path) if e.get("cwd")), None))
    return found[:limit]


def forge_apps() -> list[dict]:
    apps = []
    for path in sorted(APPS_DIR.glob("*/forge_app.json")):
        manifest = _read_json(path) or {}
        root = os.path.expanduser(str(manifest.get("root") or ""))
        folder = root if root and os.path.isdir(root) else str(path.parent)
        apps.append(
            {"folder": folder, "label": manifest.get("label") or path.parent.name}
        )
    return apps


def options(ctx: Context) -> dict:
    return {
        "terminal": find_terminal(),
        "claude": claude_path() is not None,
        "mode": MODE,
        "models": [{"id": k, "label": v} for k, v in MODELS.items()],
        "recent": recent_folders(ctx),
        "apps": forge_apps(),
        "home": str(Path.home()),
    }


def _mtime(path: str) -> float:
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0


def _read_json(path: Path) -> dict | None:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _write_json(path: Path, data: dict) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)
