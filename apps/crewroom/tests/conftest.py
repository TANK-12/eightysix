import json
import os
import sys

import pytest

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = os.path.join(APP, "..", "..", "shared")
for path in (APP, SHARED):
    if path not in sys.path:
        sys.path.insert(0, path)

from context import Context  # noqa: E402


def write_proc(
    proc, pid, comm, args, utime=0, stime=0, start=1000, rss=2560, ppid=1, fd0=None
):
    """A fake /proc/<pid> with stat, comm and cmdline; `fd0` makes fd/0 a
    link to that path (a terminal device)."""
    folder = proc / str(pid)
    folder.mkdir(parents=True, exist_ok=True)
    if fd0:
        (folder / "fd").mkdir(exist_ok=True)
        (folder / "fd" / "0").unlink(missing_ok=True)
        (folder / "fd" / "0").symlink_to(fd0)
    # fields 3..24: state ppid pgrp session tty tpgid flags minflt cminflt
    # majflt cmajflt utime stime cutime cstime priority nice threads itreal
    # starttime vsize rss
    rest = ["S", str(ppid), "1", "1", "0", "-1", "0", "0", "0", "0", "0"]
    rest += [str(utime), str(stime), "0", "0", "20", "0", "4", "0"]
    rest += [str(start), "1000000", str(rss)]
    (folder / "stat").write_text(f"{pid} ({comm}) " + " ".join(rest) + "\n")
    (folder / "comm").write_text(comm + "\n")
    (folder / "cmdline").write_bytes(b"\0".join(a.encode() for a in args) + b"\0")


def write_jsonl(path, entries):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(e) + "\n" for e in entries))


def assistant(model, blocks, usage=None, effort="high", mid="m1", ts="t"):
    return {
        "type": "assistant",
        "effort": effort,
        "timestamp": ts,
        "message": {
            "id": mid,
            "model": model,
            "content": blocks,
            "usage": usage
            or {
                "input_tokens": 10,
                "cache_read_input_tokens": 1000,
                "cache_creation_input_tokens": 90,
                "output_tokens": 200,
            },
        },
    }


def tool(name, **tool_input):
    return {"type": "tool_use", "name": name, "input": tool_input}


@pytest.fixture
def tree(tmp_path):
    """A ~/.claude and /proc with two sessions (one dead), a crew helper, a
    board and a Jan router plus one model child."""
    claude = tmp_path / "claude"
    proc = tmp_path / "proc"
    (claude / "sessions").mkdir(parents=True)
    project = claude / "projects" / "-home-ejb"

    alive = {
        "pid": 111,
        "sessionId": "sess-a",
        "cwd": "/home/ejb/Forge",
        "procStart": "5000",
        "kind": "interactive",
        "name": "forge-builder",
        "status": "busy",
        "startedAt": 1000,
        "updatedAt": 2000,
    }
    dead = dict(alive, pid=222, sessionId="sess-b", name="gone", procStart="1")
    (claude / "sessions" / "111.json").write_text(json.dumps(alive))
    (claude / "sessions" / "222.json").write_text(json.dumps(dead))
    write_proc(proc, 111, "claude", ["claude"], start=5000)
    write_proc(proc, 222, "claude", ["claude"], start=9999)  # pid reused

    write_jsonl(
        project / "sess-a.jsonl",
        [
            {"type": "user", "message": {"content": "build it"}},
            assistant(
                "claude-opus-5", [tool("Read", file_path="/x/plan.md")], mid="m1"
            ),
            assistant(
                "claude-opus-5", [tool("Edit", file_path="/x/web_app.py")], mid="m2"
            ),
            {"type": "user", "message": {"content": [{"type": "tool_result"}]}},
        ],
    )
    subagents = project / "sess-a" / "subagents"
    write_jsonl(
        subagents / "agent-abc123.jsonl",
        [
            assistant(
                "claude-sonnet-5",
                [tool("Bash", description="Run the app tests")],
                effort="medium",
            )
        ],
    )
    (subagents / "agent-abc123.meta.json").write_text(
        json.dumps({"agentType": "crew-worker", "description": "Write the jan source"})
    )
    (claude / "agents").mkdir()
    (claude / "agents" / "crew-worker.md").write_text(
        "---\nname: crew-worker\ndescription: Standard helper\nmodel: sonnet\n"
        "effort: medium\n---\n\nbody\n"
    )

    board = {
        "crew": "forge",
        "commander": "forge-builder",
        "goal": "build the room",
        "members": {"forge-builder": {"role": "commander", "last_seen": 1}},
        "tasks": [
            {
                "id": 1,
                "title": "jan source",
                "files": ["a.py"],
                "owner": "w1",
                "status": "taken",
                "note": "",
            }
        ],
        "claims": [{"path": "/x/web_app.py", "owner": "forge-builder", "since": 1}],
        "log": [{"t": i, "text": f"line {i}"} for i in range(12)],
    }
    (claude / "crew" / "forge").mkdir(parents=True)
    (claude / "crew" / "forge" / "board.json").write_text(json.dumps(board))

    write_proc(
        proc,
        300,
        "llama-server",
        ["llama-server", "--models-preset", "p.ini", "--port", "5"],
    )
    write_proc(
        proc,
        301,
        "llama-server",
        ["llama-server", "-m", "/m/Qwen3_5-9B-Q4_K_M/model.gguf", "--port", "6"],
        utime=100,
        stime=0,
        rss=256000,
    )
    write_proc(proc, 400, "bash", ["bash"])

    now = os.path.getmtime(subagents / "agent-abc123.jsonl") + 5
    ctx = Context(
        claude_dir=str(claude),
        proc_dir=str(proc),
        now=now,
        clock_ticks=100,
        cpu_count=4,
    )
    return {"ctx": ctx, "claude": claude, "proc": proc, "tmp": tmp_path}
