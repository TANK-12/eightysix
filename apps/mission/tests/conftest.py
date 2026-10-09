"""A fake laptop: ~/.claude (sessions, transcripts, helpers, crew boards),
/proc entries for the "live" pids, and a Relay data folder."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

LIVE_PIDS = {"busy": 4000001, "wait": 4000002, "idle": 4000003, "stale": 4000004}
DEAD_PID = 4999999  # above pid_max, so os.kill always says gone
SIDS = {
    "busy": "11111111-aaaa-bbbb-cccc-000000000001",
    "wait": "11111111-aaaa-bbbb-cccc-000000000002",
    "idle": "11111111-aaaa-bbbb-cccc-000000000003",
    "stale": "11111111-aaaa-bbbb-cccc-000000000004",
    "ended": "11111111-aaaa-bbbb-cccc-000000000005",
}
START_TICKS = "777"


def stat_line(pid: int) -> str:
    after = ["S", "1"] + ["0"] * 17 + [START_TICKS] + ["0"] * 10
    return f"{pid} (claude) " + " ".join(after)


def assistant(model: str, tool: str, desc: str, ctx: int, ts: str) -> dict:
    return {
        "type": "assistant",
        "timestamp": ts,
        "effort": "high",
        "message": {
            "id": f"m-{ctx}",
            "model": model,
            "usage": {
                "input_tokens": 10,
                "cache_read_input_tokens": ctx - 10,
                "output_tokens": 50,
            },
            "content": [
                {
                    "type": "tool_use",
                    "id": f"t{ctx}",
                    "name": tool,
                    "input": {"description": desc, "file_path": "/x/" + desc},
                }
            ],
        },
    }


def write_jsonl(path: Path, entries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(e) + "\n" for e in entries))


@pytest.fixture
def laptop(tmp_path, monkeypatch):
    now = time.time()
    claude = tmp_path / "claude"
    proc = tmp_path / "proc"
    project = claude / "projects" / "-home-x"
    for key, pid in LIVE_PIDS.items():
        (proc / str(pid)).mkdir(parents=True)
        (proc / str(pid) / "stat").write_text(stat_line(pid))
    status = {"busy": "busy", "wait": "waiting", "idle": "idle", "stale": "busy"}
    updated = {"busy": now - 5, "wait": now - 30, "idle": now - 60, "stale": now - 900}
    (claude / "sessions").mkdir(parents=True)
    for key, pid in LIVE_PIDS.items():
        info = {
            "pid": pid,
            "sessionId": SIDS[key],
            "cwd": "/home/x/Forge" if key == "busy" else "/home/x",
            "startedAt": (now - 3600) * 1000,
            "procStart": START_TICKS,
            "name": f"ejb-{key}",
            "status": status[key],
            "updatedAt": updated[key] * 1000,
            "kind": "interactive",
        }
        (claude / "sessions" / f"{pid}.json").write_text(json.dumps(info))
        transcript = project / f"{SIDS[key]}.jsonl"
        write_jsonl(
            transcript,
            [
                {
                    "type": "user",
                    "timestamp": "2026-10-07T10:00:00Z",
                    "message": {"content": "do the thing"},
                },
                assistant(
                    "claude-opus-5-5",
                    "Bash",
                    "run the tests",
                    120_000,
                    "2026-10-07T10:00:05Z",
                ),
                assistant(
                    "claude-opus-5-5", "Edit", "app.py", 130_000, "2026-10-07T10:00:09Z"
                ),
            ],
        )
        os.utime(transcript, (updated[key], updated[key]))
    ended_file = claude / "sessions" / f"{DEAD_PID}.json"
    ended_file.write_text(
        json.dumps(
            {
                "pid": DEAD_PID,
                "sessionId": SIDS["ended"],
                "cwd": "/home/x/old",
                "startedAt": (now - 7200) * 1000,
                "updatedAt": (now - 3000) * 1000,
                "name": "ejb-old",
            }
        )
    )
    write_jsonl(
        project / f"{SIDS['ended']}.jsonl",
        [
            assistant(
                "claude-sonnet-4-5", "Read", "notes.md", 40_000, "2026-10-07T09:00:00Z"
            )
        ],
    )
    (claude / "sessions" / "broken.json").write_text("{not json")

    # the busy session leads crew "wave" with one helper agent working on task 1
    sub = project / SIDS["busy"] / "subagents"
    write_jsonl(
        sub / "agent-abc123.jsonl",
        [
            assistant(
                "claude-opus-5-5", "Write", "web_app.py", 30_000, "2026-10-07T10:00:07Z"
            )
        ],
    )
    (sub / "agent-abc123.meta.json").write_text(
        json.dumps({"agentType": "crew-deep", "description": "H1 Mission Control"})
    )
    crew_home = claude / "crew"
    board = {
        "crew": "wave",
        "commander": "ejb-busy",
        "goal": "build it",
        "members": {
            "ejb-busy": {
                "role": "commander",
                "last_seen": now - 10,
                "session": SIDS["busy"],
                "persona": "Kaito",
            },
            "helper-1": {"role": "worker", "last_seen": now - 20, "persona": "Izumi"},
        },
        "tasks": [
            {
                "id": 1,
                "title": "H1 Mission Control app",
                "files": ["/x"],
                "owner": "helper-1",
                "status": "taken",
                "note": "",
            }
        ],
        "claims": [{"path": "/x", "owner": "helper-1", "since": now}],
        "log": [{"t": now - 50, "text": "started"}],
        "notes": [
            {
                "id": 1,
                "t": now - 100,
                "from": "ejb-busy",
                "to": "Emerson",
                "text": "pick a colour",
            },
            {
                "id": 2,
                "t": now - 3 * 86400,
                "from": "ejb-busy",
                "to": "Emerson",
                "text": "old question",
            },
            {
                "id": 3,
                "t": now - 50,
                "from": "ejb-busy",
                "to": None,
                "text": "hello all",
            },
        ],
    }
    (crew_home / "wave").mkdir(parents=True)
    (crew_home / "wave" / "board.json").write_text(json.dumps(board))
    (crew_home / "forge").mkdir()
    (crew_home / "forge" / "board.json").write_text(
        json.dumps(
            {
                "crew": "forge",
                "commander": None,
                "goal": "",
                "members": {
                    "ejb-idle": {
                        "role": "solo",
                        "last_seen": now,
                        "session": SIDS["idle"],
                    }
                },
                "tasks": [],
                "claims": [],
                "log": [],
                "notes": [],
            }
        )
    )

    relay = tmp_path / "relay"
    (relay / "tasks" / "inbox").mkdir(parents=True)
    (relay / "goals").mkdir()
    (relay / "state.json").write_text(
        json.dumps(
            {
                "heartbeat": now - 20,
                "wait_reason": "usage",
                "meters": {
                    "hey": {"five": 81.0, "week": 40.0},
                    "default": {"five": None, "error": "stale"},
                },
            }
        )
    )
    (relay / "settings.json").write_text(json.dumps({"paused": True}))
    for n, status_, title in (
        (1, "queued", "first job"),
        (2, "blocked", "needs a decision"),
        (3, "done", "old job"),
        (4, "running", "live job"),
    ):
        (relay / "tasks" / "inbox" / f"{n:04d}-job.md").write_text(
            f"---\nid: {n}\ntitle: {title}\nstatus: {status_}\ncreated: {now - n}\n---\n\n# {title}\n"
        )
    run = relay / "runs" / "r1"
    run.mkdir(parents=True)
    (run / "run.json").write_text(
        json.dumps(
            {
                "id": "r1",
                "session": SIDS["busy"],
                "task": "4",
                "kind": "work",
                "account": "hey",
                "effort": "high",
                "pid": DEAD_PID,
                "started": now - 60,
            }
        )
    )
    write_jsonl(
        run / "output.jsonl",
        [assistant("claude-opus-5-5", "Bash", "build", 50_000, "2026-10-07T10:00:00Z")],
    )

    monkeypatch.setenv("CREW_HOME", str(crew_home))
    monkeypatch.setenv("CLAUDE_SESSIONS_DIR", str(claude / "sessions"))
    monkeypatch.setenv("RELAY_DATA_DIR", str(relay))
    monkeypatch.setenv("CREWROOM_CLAUDE_DIR", str(claude))
    monkeypatch.setenv("CREWROOM_PROC_DIR", str(proc))
    monkeypatch.setenv("MISSION_DATA_DIR", str(tmp_path / "mission"))

    from mc import overview

    src = overview.Sources(
        claude_dir=str(claude),
        proc_dir=str(proc),
        forge_apps_dir="",
        conversations=lambda: {
            SIDS["idle"]: {"id": "conv-9", "name": "Hina", "title": "Tidy docs"}
        },
    )
    return {
        "src": src,
        "claude": claude,
        "proc": proc,
        "relay": relay,
        "crew_home": crew_home,
        "now": now,
        "project": project,
    }
