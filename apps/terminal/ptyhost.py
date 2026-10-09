"""Shells on pseudo-terminals, kept alive between page reloads.

A `Term` is one shell started with `pty.fork()`. Its output is read on the
asyncio loop and fanned out to whichever WebSocket is attached, and the last
`SCROLLBACK` bytes are kept so a reloaded page (or a reopened Forge tab) gets
its screen back. Closing a tab sends SIGHUP to the shell's process group, as a
real terminal does when its window closes; stopping the app does the same for
all of them.
"""

from __future__ import annotations

import asyncio
import fcntl
import os
import pty
import signal
import struct
import subprocess
import termios
import time
import uuid
from pathlib import Path
from typing import Callable

SCROLLBACK = 256 * 1024
HOME = Path.home()


def default_shell() -> str:
    shell = os.environ.get("SHELL", "")
    return shell if shell and os.access(shell, os.X_OK) else "/bin/bash"


class Term:
    def __init__(
        self,
        cwd: str | None = None,
        cols: int = 100,
        rows: int = 30,
        argv: list[str] | None = None,
    ):
        self.id = uuid.uuid4().hex[:8]
        self.created = time.time()
        self.buffer = bytearray()
        self.listeners: set[Callable[[bytes | None], None]] = set()
        self.exit_code: int | None = None
        start = Path(cwd).expanduser() if cwd else HOME
        if not start.is_dir():
            start = HOME
        shell = default_shell()
        argv = argv or [shell, "-l"]
        env = {
            **os.environ,
            "TERM": "xterm-256color",
            "COLORTERM": "truecolor",
            "TERM_PROGRAM": "ForgeTerminal",
        }
        env.pop("VIRTUAL_ENV", None)  # the app's own venv must not leak into the shell
        env["PATH"] = os.pathsep.join(
            p
            for p in env.get("PATH", "").split(os.pathsep)
            if "/apps/terminal/.venv" not in p
        )
        # subprocess forks in C, which is safe in this multi-threaded server
        # (pty.fork() runs Python in the child and can deadlock). `setsid -c`
        # makes the pty the shell's controlling terminal, so Ctrl+C, job
        # control and SIGWINCH on resize all work.
        fd, slave = pty.openpty()
        self.proc = subprocess.Popen(
            ["setsid", "-c", *argv],
            stdin=slave,
            stdout=slave,
            stderr=slave,
            cwd=start,
            env=env,
            close_fds=True,
        )
        os.close(slave)
        self.pid, self.fd = self.proc.pid, fd
        self.resize(cols, rows)
        os.set_blocking(fd, False)
        self.loop = asyncio.get_running_loop()
        self.loop.add_reader(fd, self._on_readable)

    # ------------------------------------------------------------ io

    def _on_readable(self) -> None:
        try:
            data = os.read(self.fd, 65536)
        except BlockingIOError:
            return
        except OSError:
            data = b""
        if not data:
            self._finish()
            return
        self.buffer += data
        if len(self.buffer) > SCROLLBACK:
            del self.buffer[: len(self.buffer) - SCROLLBACK]
        for fn in list(self.listeners):
            fn(data)

    def _finish(self) -> None:
        try:
            self.loop.remove_reader(self.fd)
        except (ValueError, OSError):
            pass
        try:
            code = self.proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            code = -1
        self.exit_code = code
        try:
            os.close(self.fd)
        except OSError:
            pass
        for fn in list(self.listeners):
            fn(None)

    @property
    def alive(self) -> bool:
        return self.exit_code is None

    def write(self, data: bytes) -> None:
        if not self.alive:
            return
        view = memoryview(data)
        while view:
            try:
                n = os.write(self.fd, view)
                view = view[n:]
            except BlockingIOError:
                time.sleep(0.005)  # a big paste can fill the tty's input queue
            except OSError:
                return

    def resize(self, cols: int, rows: int) -> None:
        cols, rows = max(2, min(int(cols), 1000)), max(1, min(int(rows), 500))
        try:
            fcntl.ioctl(
                self.fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0)
            )
        except OSError:
            pass

    # ------------------------------------------------------------ what's running

    def foreground(self) -> str:
        """Name of the program in front (`vim`, `htop`), or the shell's."""
        try:
            pgid = os.tcgetpgrp(self.fd)
            return Path(f"/proc/{pgid}/comm").read_text().strip()
        except OSError:
            return ""

    def cwd(self) -> str:
        try:
            return os.readlink(f"/proc/{self.pid}/cwd")
        except OSError:
            return ""

    def public(self) -> dict:
        cwd = self.cwd()
        return {
            "id": self.id,
            "alive": self.alive,
            "exit_code": self.exit_code,
            "cwd": cwd,
            "program": self.foreground() if self.alive else "",
            "created": self.created,
        }

    def close(self) -> None:
        if self.alive:
            for sig in (signal.SIGHUP, signal.SIGCONT):
                try:
                    os.killpg(os.getpgid(self.pid), sig)
                except OSError:
                    pass
            # Anything that ignores the hang-up gets a TERM a moment later.
            self.loop.call_later(1.5, self._term_if_alive)

    def _term_if_alive(self) -> None:
        if self.alive:
            try:
                os.killpg(os.getpgid(self.pid), signal.SIGTERM)
            except OSError:
                pass


class Registry:
    def __init__(self) -> None:
        self.terms: dict[str, Term] = {}

    def create(self, cwd: str | None = None, cols: int = 100, rows: int = 30) -> Term:
        t = Term(cwd, cols, rows)
        self.terms[t.id] = t
        return t

    def get(self, tid: str) -> Term | None:
        return self.terms.get(tid)

    def remove(self, tid: str) -> bool:
        t = self.terms.pop(tid, None)
        if t is None:
            return False
        t.close()
        return True

    def list(self) -> list[dict]:
        # A shell that exited on its own (typed `exit`) is dropped once listed.
        out = [t.public() for t in self.terms.values()]
        for t in [t for t in self.terms.values() if not t.alive and not t.listeners]:
            self.terms.pop(t.id, None)
        return sorted(out, key=lambda d: d["created"])

    def close_all(self) -> None:
        for tid in list(self.terms):
            self.remove(tid)
