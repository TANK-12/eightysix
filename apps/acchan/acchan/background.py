"""Everything headless Acchan starts, and the one place that stops it.

Emerson (2026-09-27): closing Acchan must close every headless thing it
started. So every background child goes through `start()`:

* It gets its own session, and `close_all()` (run at exit, including
  uvicorn's normal SIGTERM shutdown) kills everything in each session.
* The kernel is told to SIGKILL it if Acchan dies (PR_SET_PDEATHSIG), so a
  crash or `kill -9` leaves nothing behind either. That signal fires when the
  *thread* that forked the child ends, and FastAPI runs tools on pool threads
  that come and go, so all forks happen on one launcher thread that lives as
  long as the process.
"""

from __future__ import annotations

import atexit
import ctypes
import os
import queue
import signal
import subprocess
import threading
import time
from concurrent.futures import Future
from pathlib import Path
from typing import Any

PR_SET_PDEATHSIG = 1
_children: list[subprocess.Popen] = []
_lock = threading.Lock()
_requests: queue.Queue[tuple[list[str], dict, Future]] = queue.Queue()
_launcher: threading.Thread | None = None


def _die_with_parent() -> None:
    ctypes.CDLL(None, use_errno=True).prctl(PR_SET_PDEATHSIG, signal.SIGKILL)


def _launch_loop() -> None:
    while True:
        cmd, kwargs, done = _requests.get()
        try:
            done.set_result(
                subprocess.Popen(
                    cmd, start_new_session=True, preexec_fn=_die_with_parent, **kwargs
                )
            )
        except Exception as error:  # handed back to the caller's thread
            done.set_exception(error)


def start(cmd: list[str], **kwargs: Any) -> subprocess.Popen:
    """Start a child that lives and dies with Acchan. Takes Popen's keywords."""
    global _launcher
    with _lock:
        if _launcher is None or not _launcher.is_alive():
            _launcher = threading.Thread(
                target=_launch_loop, name="acchan-launcher", daemon=True
            )
            _launcher.start()
    done: Future = Future()
    _requests.put((cmd, kwargs, done))
    proc = done.result(timeout=30)
    with _lock:
        _children.append(proc)
    return proc


def session(sid: int) -> list[int]:
    """Every live process in session `sid`: a child started here plus all it
    started, even ones that moved to a process group of their own."""
    pids = []
    for stat in Path("/proc").glob("[0-9]*/stat"):
        try:
            fields = stat.read_text().rsplit(")", 1)[1].split()
        except (OSError, IndexError):
            continue
        if int(fields[3]) == sid and fields[0] != "Z":
            pids.append(int(stat.parent.name))
    return pids


def _signal(pids: list[int], sig: int) -> None:
    for pid in pids:
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            pass


def stop(proc: subprocess.Popen, grace: float = 2.0) -> None:
    """Stop one child and everything it started."""
    for sig, wait in ((signal.SIGTERM, grace), (signal.SIGKILL, 5.0)):
        pids = session(proc.pid)
        if not pids:
            break
        _signal(pids, sig)
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline:
            proc.poll()  # reap it so it stops counting as alive
            if not session(proc.pid):
                break
            time.sleep(0.05)
    proc.poll()
    with _lock:
        if proc in _children:
            _children.remove(proc)


def running() -> list[subprocess.Popen]:
    with _lock:
        return [p for p in _children if p.poll() is None]


def close_all() -> int:
    """Stop every background child; returns how many were still running."""
    live = running()
    for proc in live:
        stop(proc, grace=0.5)
    with _lock:
        _children.clear()
    return len(live)


atexit.register(close_all)
