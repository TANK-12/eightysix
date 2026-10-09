"""Headless shells: a real bash on a pseudo-terminal that Acchan owns.

State carries over between commands (cd, exported variables, a venv that was
activated), which is what a coding agent needs and a one-shot `run_command`
cannot give. Each command is followed by a marker line carrying its exit
code, so `run()` knows exactly when it finished and what it printed.

Everything a shell prints is also written to a transcript file. "Show me the
terminal" opens a window that follows that file, so Emerson can watch a
headless shell at any time without the shell depending on the window.
Shells are started through `background`, so they close with Acchan.
"""

from __future__ import annotations

import fcntl
import os
import re
import struct
import termios
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from . import background, conversation

ANSI = re.compile(
    r"\x1b(\[[0-9;?]*[ -/]*[@-~]|\][^\x07\x1b]*(\x07|\x1b\\)|[()][0-9A-Za-z])"
)
ENV = {
    "TERM": "dumb",
    "PS1": "",
    "PS2": "",
    "PAGER": "cat",
    "GIT_PAGER": "cat",
    "SYSTEMD_PAGER": "",
    "MANPAGER": "cat",
    "NO_COLOR": "1",
    "HISTFILE": "/dev/null",
    "PYTHONUNBUFFERED": "1",
    "DEBIAN_FRONTEND": "noninteractive",
}
MARKER = re.compile(r"\n?\x1f[0-9a-f]{12}:\d+\n?")
KEEP = 400_000  # characters of output kept in memory per shell


def transcripts() -> Path:
    return conversation.DATA / "shells"


def clean(text: str) -> str:
    """Terminal output as plain text: colours and cursor codes gone, \\r\\n -> \\n."""
    text = ANSI.sub("", text).replace("\r\n", "\n")
    return "\n".join(line.rsplit("\r", 1)[-1] for line in text.split("\n"))


@dataclass
class Result:
    output: str
    code: int | None  # None: still running when the wait ran out

    def __str__(self) -> str:
        status = (
            f"exit code {self.code}"
            if self.code is not None
            else "still running (read it later with shell_read, or stop it with shell_send ctrl+c)"
        )
        return f"{status}\n{self.output or '(no output)'}"


@dataclass
class Shell:
    name: str
    folder: Path
    log: Path = field(init=False)
    _buf: str = field(default="", init=False)
    _cut: int = field(default=0, init=False)  # characters dropped from _buf's start
    _read_to: int = field(default=0, init=False)
    _cond: threading.Condition = field(default_factory=threading.Condition, init=False)

    def __post_init__(self) -> None:
        master, slave = os.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 50, 200, 0, 0))
        attrs = termios.tcgetattr(slave)
        attrs[3] &= ~termios.ECHO  # the log shows "$ command" itself, once
        termios.tcsetattr(slave, termios.TCSANOW, attrs)
        self.master = master
        self.log = transcripts() / f"{self.name}.log"
        self.log.parent.mkdir(parents=True, exist_ok=True)
        self.log.write_text(f"# Acchan shell '{self.name}' in {self.folder}\n")
        self.proc = background.start(
            ["bash", "--norc", "--noprofile", "--noediting", "-i"],
            stdin=slave,
            stdout=slave,
            stderr=slave,
            cwd=self.folder,
            env={**os.environ, **ENV},
        )
        os.close(slave)
        threading.Thread(target=self._pump, daemon=True).start()
        # No job control: "cmd &" jobs stay in bash's process group, so the
        # hang-up bash's death sends to that group takes them down too, even
        # when Acchan is killed too hard for close_all to run.
        self.run("set +m", timeout=10)

    # -- output ---------------------------------------------------------
    def _pump(self) -> None:
        while True:
            try:
                data = os.read(self.master, 65536)
            except OSError:
                data = b""
            if not data:
                break
            text = data.decode("utf-8", "replace")
            with self._cond:
                self._buf += text
                if len(self._buf) > KEEP:
                    drop = len(self._buf) - KEEP
                    self._buf, self._cut = self._buf[drop:], self._cut + drop
                self._cond.notify_all()
            with self.log.open("a") as out:
                out.write(clean(MARKER.sub("\n", text)))
        with self._cond:
            self._cond.notify_all()

    _marker_prefix = "\x1f"  # never printed by a normal program

    def _end(self) -> int:
        return self._cut + len(self._buf)

    def _since(self, pos: int) -> str:
        return self._buf[max(0, pos - self._cut) :]

    def alive(self) -> bool:
        return self.proc.poll() is None

    # -- input ----------------------------------------------------------
    def _write(self, text: str) -> None:
        if not self.alive():
            raise RuntimeError(f"shell '{self.name}' has ended")
        os.write(self.master, text.encode())

    def _note(self, line: str) -> None:
        with self.log.open("a") as out:
            out.write(line + "\n")

    def run(self, command: str, timeout: float = 60) -> Result:
        """Run one command line and wait for it; its output and exit code."""
        token = uuid.uuid4().hex[:12]
        marker = f"{self._marker_prefix}{token}:"
        with self._cond:
            start = self._end()
        self._note(f"$ {command}")
        self._write(f"{command}\nprintf '\\n{marker}%s\\n' \"$?\"\n")
        found = re.compile(re.escape(marker) + r"(\d+)")
        deadline = time.monotonic() + timeout
        with self._cond:
            while True:
                seen = self._since(start)
                hit = found.search(seen)
                if hit or not self.alive():
                    break
                left = deadline - time.monotonic()
                if left <= 0:
                    self._read_to = self._end()
                    return Result(clean(seen).strip(), None)
                self._cond.wait(min(left, 0.5))
            self._read_to = self._end()
        if not hit:
            return Result(clean(seen).strip() + "\n(the shell ended)", -1)
        output = clean(seen[: hit.start()]).strip()
        return Result(output, int(hit.group(1)))

    def send(self, text: str, enter: bool = True, wait: float = 1.0) -> str:
        """Type into whatever is running (a prompt, a REPL, ctrl+c) and return
        what it printed within `wait` seconds."""
        with self._cond:
            start = self._end()
        self._note(f"> {text!r}" if text in CONTROL.values() else f"> {text}")
        self._write(text + ("\n" if enter and text not in CONTROL.values() else ""))
        time.sleep(max(0.1, min(wait, 30)))
        return self.read(start)

    def read(self, start: int | None = None) -> str:
        """Output not yet returned to the model (or since `start`)."""
        with self._cond:
            text = self._since(self._read_to if start is None else start)
            self._read_to = self._end()
        return clean(MARKER.sub("\n", text)).strip()

    def close(self) -> None:
        background.stop(self.proc)
        try:
            os.close(self.master)
        except OSError:
            pass


# No ctrl+z: without job control a stopped program would hang the shell.
CONTROL = {"ctrl+c": "\x03", "ctrl+d": "\x04", "ctrl+\\": "\x1c"}
SHELLS: dict[str, Shell] = {}
_lock = threading.Lock()


def get(name: str = "main", folder: str | Path | None = None) -> tuple[Shell, bool]:
    """The named shell, started in `folder` if new. Returns (shell, is_new)."""
    name = re.sub(r"[^\w.-]+", "-", (name or "main").strip()).strip("-") or "main"
    with _lock:
        shell = SHELLS.get(name)
        if shell and shell.alive():
            return shell, False
        shell = Shell(name, Path(folder or Path.home()))
        SHELLS[name] = shell
        return shell, True


def close(name: str) -> bool:
    with _lock:
        shell = SHELLS.pop(name, None)
    if shell:
        shell.close()
    return shell is not None


def close_all() -> None:
    with _lock:
        names = list(SHELLS)
    for name in names:
        close(name)
