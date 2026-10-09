"""Start Jan's model router when a step needs a model and none is running.

Emerson (2026-09-19): "have Jan run when needed". Jan's engine is llama.cpp
in router mode, started with the preset Jan itself writes
(`router.preset.ini`, one section per downloaded model); a model loads on
the first request naming it and is released when idle (shared/forge_jan.py).
This only *starts* a router when there is none; a running one, Jan's own or
another session's, is never touched -- Jan is shared.
"""

from __future__ import annotations

import os
import subprocess
import time
import urllib.request
from pathlib import Path

JAN_DATA = Path.home() / ".var/app/ai.jan.Jan/data/Jan/data/llamacpp"
PORT = 1337
LOG = Path.home() / "Forge" / "outputs" / "jan-router.log"


def _server_binary() -> Path | None:
    backends = JAN_DATA / "backends"
    if not backends.exists():
        return None
    # newest build; prefer the Vulkan build (the iGPU) over CPU-only ones
    builds = sorted(backends.iterdir(), reverse=True)
    for build in builds:
        for flavour in (
            "linux-vulkan-common_cpus-x64",
            "linux-avx-x64",
            "linux-common_cpus-x64",
        ):
            exe = build / flavour / "build" / "bin" / "llama-server"
            if exe.exists():
                return exe
    return None


def _alive(port: int = PORT, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/v1/models", timeout=timeout
        ):
            return True
    except Exception:
        return False


def ensure_router(log=None, wait: float = 40.0) -> bool:
    """True when a router answers on the Jan port, starting one if needed."""
    if _alive():
        return True
    exe = _server_binary()
    preset = JAN_DATA / "router.preset.ini"
    if exe is None or not preset.exists():
        if log:
            log("Jan is not installed here (no llama-server build or preset)")
        return False
    LOG.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, LD_LIBRARY_PATH=str(exe.parent))
    with open(LOG, "ab") as out:
        subprocess.Popen(
            [
                str(exe),
                "--models-preset",
                str(preset),
                "--host",
                "127.0.0.1",
                "--port",
                str(PORT),
            ],
            stdout=out,
            stderr=subprocess.STDOUT,
            cwd=str(exe.parent),
            env=env,
            start_new_session=True,
        )
    if log:
        log(f"started Jan's model router ({exe.parent.parent.parent.name})")
    t0 = time.time()
    while time.time() - t0 < wait:
        if _alive():
            return True
        time.sleep(0.5)
    if log:
        log("Jan's router did not answer in time; see " + str(LOG))
    return False
