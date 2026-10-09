"""The file protocol between AI Studio and a world worker process.

Stdlib only: world workers may run in another virtualenv (a PyTorch runtime)
and copy this file. One session = one folder:

- ``job.json``      written by the app before the worker starts (read-only).
- ``status.json``   written by the worker: {"state", "message", "chunk", ...}.
- ``actions.jsonl`` appended by the app, one {"seq", "actions"} per step.
- ``stop``          created by the app to ask the worker to finish.
- ``frames/``       the worker adds ``000001.png``, ``000002.png``, ... in order.
- ``worker.log``    the worker's output.

States: starting, working (making frames), waiting (ready for the next move),
stopped, done, failed.
"""

import json
import os
import shutil
import time
from pathlib import Path

JOB = "job.json"
STATUS = "status.json"
ACTIONS = "actions.jsonl"
STOP = "stop"
FRAMES = "frames"
LOG = "worker.log"

FINAL_STATES = ("stopped", "done", "failed")


def write_json(path, data):
    """Write JSON so a reader never sees half a file."""
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=1))
    os.replace(tmp, path)


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_status(session_dir, state, message="", **extra):
    data = read_json(Path(session_dir) / STATUS, {}) or {}
    data.update(extra, state=state, message=message, updated=time.time())
    write_json(Path(session_dir) / STATUS, data)


def read_actions(session_dir):
    path = Path(session_dir) / ACTIONS
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass  # a line still being written; it will be read next time
    return out


def append_actions(session_dir, seq, actions):
    with open(Path(session_dir) / ACTIONS, "a") as f:
        f.write(json.dumps({"seq": seq, "actions": list(actions)}) + "\n")


def stop_requested(session_dir):
    return (Path(session_dir) / STOP).exists()


def wait_for_actions(session_dir, after_seq, timeout, poll=0.2):
    """Next {"seq", "actions"} with seq > after_seq; "stop" or "timeout"."""
    end = time.monotonic() + timeout
    while True:
        if stop_requested(session_dir):
            return "stop"
        for rec in read_actions(session_dir):
            if rec.get("seq", 0) > after_seq:
                return rec
        if time.monotonic() >= end:
            return "timeout"
        time.sleep(poll)


def frame_names(session_dir):
    folder = Path(session_dir) / FRAMES
    if not folder.is_dir():
        return []
    return sorted(p.name for p in folder.glob("[0-9][0-9][0-9][0-9][0-9][0-9].png"))


def add_frame(session_dir, src):
    """Copy one finished frame into frames/ as the next number; return its name."""
    folder = Path(session_dir) / FRAMES
    folder.mkdir(exist_ok=True)
    name = f"{len(frame_names(session_dir)) + 1:06d}.png"
    tmp = folder / (name + ".tmp")
    shutil.copyfile(src, tmp)
    os.replace(tmp, folder / name)
    return name
