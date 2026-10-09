"""Manga fetch helpers shared by MediaForge's Tk module and its web backend.

Kept apart from ``manga.py`` because that file imports customtkinter at the
top; the FastAPI backend must not pull a Tk toolkit into a headless server.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
from pathlib import Path

import requests

try:
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except Exception:  # pragma: no cover - optional
    HTTPAdapter = None  # type: ignore[assignment]
    Retry = None  # type: ignore[assignment]


def robust_session():
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (X11; Linux x86_64) MediaForge"
    if Retry:
        s.mount(
            "https://",
            HTTPAdapter(
                max_retries=Retry(total=5, backoff_factor=1.2), pool_maxsize=30
            ),
        )
    return s


# comix.to draws its pages on a canvas that a plain scrape never sees;
# PanelForge's fetcher captures them through headless Chrome. This app calls
# it through tools/fetch_cli.py so there is one engine for both apps.
PANELFORGE = Path.home() / "Forge" / "apps" / "panelforge"
CDP_SITES = ("comix.to",)


def uses_panelforge_fetcher(url: str) -> bool:
    return (
        any(site in (url or "") for site in CDP_SITES)
        and (PANELFORGE / ".venv" / "bin" / "python").exists()
    )


def panelforge_fetch(args: list[str], log, should_stop=None, progress=None) -> dict:
    """Run tools/fetch_cli.py; LOG lines go to the app log, PROGRESS lines to
    ``progress(frac)``, the last JSON line is the result. ``should_stop()``
    is polled per line; when it turns true the fetcher (and its headless
    Chrome, in the same process group) is killed and RuntimeError raised."""
    proc = subprocess.Popen(
        [
            str(PANELFORGE / ".venv" / "bin" / "python"),
            str(PANELFORGE / "tools" / "fetch_cli.py"),
            *args,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(PANELFORGE),
        start_new_session=True,
    )
    result: dict = {}
    assert proc.stdout is not None
    for line in proc.stdout:
        if should_stop is not None and should_stop():
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            proc.wait()
            raise RuntimeError("stopped")
        line = line.rstrip("\n")
        if line.startswith("LOG "):
            log(line[4:])
        elif line.startswith("PROGRESS ") and progress is not None:
            try:
                progress(float(line[9:]))
            except ValueError:
                pass
        elif line.startswith("{"):
            try:
                result = json.loads(line)
            except json.JSONDecodeError:
                pass
    code = proc.wait()
    if code != 0:
        err = (proc.stderr.read() if proc.stderr else "").strip().splitlines()[-3:]
        raise RuntimeError(f"PanelForge fetcher failed ({code}): {' | '.join(err)}")
    return result
