"""Acchan's own headless Firefox, for web work out of sight.

Emerson (2026-09-27): headless is the default. This Firefox has its own
profile (never his, so his logins and his launcher are untouched), runs with
--headless, and speaks WebDriver BiDi through shared/forge_bidi.py like the
account windows do. It starts on first use and goes through `background`, so
it closes with Acchan, even after a crash.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

from . import background, conversation

sys.path.insert(
    0, os.environ.get("FORGE_SHARED_DIR", str(Path.home() / "Forge" / "shared"))
)
import forge_bidi  # noqa: E402

# Quiet first run: no welcome page, default-browser question or telemetry.
PREFS = {
    "browser.shell.checkDefaultBrowser": False,
    "browser.aboutwelcome.enabled": False,
    "browser.startup.homepage_override.mstone": "ignore",
    "datareporting.policy.dataSubmissionEnabled": False,
    "toolkit.telemetry.reportingpolicy.firstRun": False,
    "trailhead.firstrun.didSeeAboutWelcome": True,
}
_proc: subprocess.Popen | None = None
_port = 0
_lock = threading.Lock()


def profile():
    return conversation.DATA / "headless-firefox"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def running() -> bool:
    return _proc is not None and _proc.poll() is None


def port(wait: float = 30.0) -> int:
    """The BiDi port of the headless Firefox, starting it if needed."""
    global _proc, _port
    with _lock:
        if running() and forge_bidi.port_open(_port):
            return _port
        if _proc is not None:
            background.stop(_proc)
        firefox = shutil.which("firefox")
        if not firefox:
            raise RuntimeError("Firefox is not installed")
        folder = profile()
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "user.js").write_text(
            "".join(
                f'user_pref("{k}", {str(v).lower() if isinstance(v, bool) else v!r});\n'
                for k, v in PREFS.items()
            )
        )
        _port = _free_port()
        _proc = background.start(
            [firefox, "--headless", "--no-remote", "--profile", str(folder)]
            + ["--remote-debugging-port", str(_port)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline:
            if forge_bidi.port_open(_port):
                return _port
            if _proc.poll() is not None:
                break
            time.sleep(0.2)
        background.stop(_proc)
        _proc = None
        raise RuntimeError("The headless Firefox did not start")


def close() -> bool:
    """Stop the headless Firefox; False when it was not running."""
    global _proc
    with _lock:
        was = running()
        if _proc is not None:
            background.stop(_proc)
        _proc = None
        return was
