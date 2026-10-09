"""One headless Claude session per run: start it, watch it, stop it by PID.

Each run keeps runs/<session id>/ with run.json, prompt.md (fed on stdin),
output.jsonl (stream-json, one event per line) and stderr.log. Sessions start
in their own process group and outlive the boss, which finds them again after
a restart from run.json (PID plus process start time, so a reused PID is not
mistaken for the session).
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import time
import uuid
from pathlib import Path

import meters
import store
from claude_launch import find_claude, headless_command

MODE = "bypassPermissions"  # Emerson, 2026-09-29: "all permission"
TAIL_BYTES = 256_000


def run_dir(run_id: str) -> Path:
    return store.path("runs", run_id)


def proc_start(pid: int, proc: str = "/proc") -> int | None:
    """Start time of `pid` in clock ticks; None when it is gone or a zombie."""
    try:
        fields = Path(proc, str(pid), "stat").read_text().rsplit(")", 1)[1].split()
    except (OSError, IndexError):
        return None
    if fields[0] in ("Z", "X"):
        return None
    try:
        return int(fields[19])
    except (IndexError, ValueError):
        return None


def start(
    task: dict,
    kind: str,
    account: str,
    effort: str,
    prompt: str,
    folder: str,
    model: str = "",
    resume: str = "",
) -> dict:
    claude = find_claude("RELAY_CLAUDE_BIN")
    if not claude:
        raise RuntimeError("Claude Code (the claude command) is not installed")
    if not os.path.isdir(folder):  # before the run folder, so none is left over
        raise RuntimeError(f"the folder {folder} does not exist")
    run_id = str(uuid.uuid4())
    home = run_dir(run_id)
    home.mkdir(parents=True)
    (home / "prompt.md").write_text(prompt, encoding="utf-8")
    name = f"relay-{task.get('id') or task.get('slug')}-{kind}"
    args = headless_command(
        claude,
        run_id,
        MODE,
        model=store.model_id(model),
        effort=effort,
        name=name,
        resume=resume,
    )
    with open(home / "prompt.md", "rb") as stdin, open(
        home / "output.jsonl", "wb"
    ) as out, open(home / "stderr.log", "wb") as err:
        proc = subprocess.Popen(
            args,
            cwd=folder,
            stdin=stdin,
            stdout=out,
            stderr=err,
            env={
                **meters.env_for(account),
                "RELAY_RUN_KIND": kind,
                "RELAY_RUN_ID": run_id,
            },
            start_new_session=True,
        )
    run = {
        "id": run_id,
        "session": resume or run_id,
        "task": task.get("id") or "",
        "goal": task.get("goal") or task.get("slug") or "",
        "kind": kind,
        "account": account,
        "effort": effort,
        "folder": folder,
        "pid": proc.pid,
        "proc_start": proc_start(proc.pid),
        "started": time.time(),
        "command": args,
    }
    store.write_json(home / "run.json", run)
    return run


def save(run: dict) -> None:
    store.write_json(run_dir(run["id"]) / "run.json", run)


def all_runs() -> list[dict]:
    runs = []
    for file in store.path("runs").glob("*/run.json"):
        run = store.read_json(file)
        if isinstance(run, dict) and run.get("id"):
            runs.append(run)
    runs.sort(key=lambda r: r.get("started") or 0)
    return runs


def active() -> list[dict]:
    return [r for r in all_runs() if not r.get("ended")]


def alive(run: dict, proc: str = "/proc") -> bool:
    pid = run.get("pid")
    if not pid:
        return False
    started = proc_start(int(pid), proc)
    return started is not None and run.get("proc_start") in (None, started)


def stop(run: dict) -> None:
    """SIGTERM to the session's process group, SIGKILL after 10 s."""
    if not alive(run):
        return
    pid = int(run["pid"])
    for sig, wait in ((signal.SIGTERM, 10.0), (signal.SIGKILL, 2.0)):
        try:
            os.killpg(pid, sig)
        except OSError:
            return
        end = time.time() + wait
        while time.time() < end:
            reap()
            if not alive(run):
                return
            time.sleep(0.2)


def reap() -> None:
    """Collect exited children so they do not linger as zombies."""
    while True:
        try:
            pid, _ = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            return
        if pid == 0:
            return


def _tail_events(file: Path, whole: bool = False) -> list[dict]:
    """Events from the last TAIL_BYTES of `file`, or all of it."""
    try:
        with open(file, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            limit = size if whole else TAIL_BYTES
            fh.seek(max(0, size - limit))
            raw = fh.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return []
    if size > limit:
        raw = raw[1:]  # the first line is probably cut
    events = []
    for line in raw:
        try:
            data = json.loads(line)
        except ValueError:
            continue
        if isinstance(data, dict):
            events.append(data)
    return events


def describe_tool(block: dict) -> str:
    name = block.get("name") or "tool"
    args = block.get("input") or {}
    detail = (
        args.get("description")
        or args.get("command")
        or args.get("file_path")
        or args.get("pattern")
        or args.get("prompt")
        or ""
    )
    detail = " ".join(str(detail).split())
    return f"{name}: {detail[:90]}" if detail else name


def _context_of(usage: dict) -> int:
    return sum(
        int(usage.get(k) or 0)
        for k in (
            "input_tokens",
            "cache_read_input_tokens",
            "cache_creation_input_tokens",
        )
    )


def _main_context(events: list[dict]) -> int:
    """The main session's context in its latest assistant event, 0 if none."""
    for event in reversed(events):
        if event.get("type") == "assistant" and not event.get("parent_tool_use_id"):
            ctx = _context_of((event.get("message") or {}).get("usage") or {})
            if ctx:
                return ctx
    return 0


def summary(run: dict) -> dict:
    """What the page and the boss need from a run's output.

    Events of a subagent the session launched carry `parent_tool_use_id`;
    context_tokens, last_action and last_text come from the main session
    only, output_tokens counts every event (it is all spend).
    """
    home = run_dir(run["id"])
    out = home / "output.jsonl"
    events = _tail_events(out)
    info: dict = {
        "last_action": "",
        "last_text": "",
        "context_tokens": 0,
        "output_tokens": 0,
        "result": None,
    }
    try:
        info["last_at"] = out.stat().st_mtime
    except OSError:
        info["last_at"] = run.get("started") or 0
    for event in events:
        kind = event.get("type")
        if kind == "assistant":
            message = event.get("message") or {}
            usage = message.get("usage") or {}
            info["output_tokens"] += int(usage.get("output_tokens") or 0)
            if event.get("parent_tool_use_id"):
                continue  # a subagent's event, not the session's own
            for block in message.get("content") or []:
                if block.get("type") == "tool_use":
                    info["last_action"] = describe_tool(block)
                elif block.get("type") == "text" and block.get("text", "").strip():
                    info["last_text"] = block["text"].strip()[-400:]
        elif kind == "result":
            info["result"] = {
                "is_error": bool(event.get("is_error")),
                "text": str(event.get("result") or ""),
                "subtype": event.get("subtype"),
                "cost_usd": event.get("total_cost_usd"),
                "turns": event.get("num_turns"),
                "usage": event.get("usage") or {},
            }
    info["context_tokens"] = _main_context(events)
    if not info["context_tokens"] and _has_subagent(events):
        # a busy subagent can fill the whole tail; read the file once
        info["context_tokens"] = _main_context(_tail_events(out, whole=True))
    return info


def _has_subagent(events: list[dict]) -> bool:
    return any(event.get("parent_tool_use_id") for event in events)


def stderr_tail(run: dict, limit: int = 1500) -> str:
    try:
        text = (run_dir(run["id"]) / "stderr.log").read_text("utf-8", "replace")
    except OSError:
        return ""
    return text[-limit:].strip()


def tail_lines(run: dict, limit: int = 40) -> list[str]:
    """Plain-words lines for the page's live tail."""
    lines = []
    for event in _tail_events(run_dir(run["id"]) / "output.jsonl"):
        if event.get("type") == "assistant":
            for block in (event.get("message") or {}).get("content") or []:
                if block.get("type") == "tool_use":
                    lines.append("› " + describe_tool(block))
                elif block.get("type") == "text" and block.get("text", "").strip():
                    lines.append(" ".join(block["text"].split())[:300])
        elif event.get("type") == "result":
            lines.append("= " + " ".join(str(event.get("result") or "").split())[:300])
    return lines[-limit:]


def hit_limit(text: str) -> bool:
    low = text.lower()
    return "limit" in low and any(
        w in low for w in ("usage", "reached", "rate", "5-hour", "weekly")
    )
