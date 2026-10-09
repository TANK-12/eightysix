"""AI model downloads under a hard 15 GB budget.

Emerson's rule (2026-09-17): the crew may download models without asking each
time, but only from a verified, actively maintained source (official GitHub
release or Hugging Face repo of the named project), and never past 15 GB in
total. Every download is appended to ~/PanelForgeData/models/MODELS.jsonl with
name, source URL, size and the helper/module that wanted it.

    path = models.ensure("depth-anything-v2-small", url, filename="model.onnx",
                         approx_mb=100, source="https://huggingface.co/...",
                         wanted_by="scene")
"""

import fcntl
import json
import os
import time
import urllib.request
from pathlib import Path

from . import paths

BUDGET_BYTES = 15 * 1024**3


class BudgetExceeded(RuntimeError):
    pass


def used_bytes() -> int:
    total = 0
    if paths.MODELS_ROOT.exists():
        for p in paths.MODELS_ROOT.rglob("*"):
            if p.is_file():
                total += p.stat().st_size
    return total


def path_for(name: str, filename: str) -> Path:
    return paths.MODELS_ROOT / name / filename


def ensure(
    name: str,
    url: str,
    filename: str,
    approx_mb: int,
    source: str,
    wanted_by: str,
) -> Path:
    """Return the local path, downloading once if missing. Budget-checked under a lock."""
    dest = path_for(name, filename)
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    paths.MODELS_ROOT.mkdir(parents=True, exist_ok=True)
    with open(paths.MODELS_ROOT / ".lock", "w") as lockf:
        fcntl.flock(lockf, fcntl.LOCK_EX)
        if dest.exists() and dest.stat().st_size > 0:
            return dest
        if used_bytes() + approx_mb * 1024**2 > BUDGET_BYTES:
            raise BudgetExceeded(
                f"{name} (~{approx_mb} MB) would pass the 15 GB model budget"
            )
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        req = urllib.request.Request(url, headers={"User-Agent": "PanelForge/1"})
        with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
            while chunk := r.read(1 << 20):
                f.write(chunk)
                if used_bytes() > BUDGET_BYTES:
                    f.close()
                    tmp.unlink()
                    raise BudgetExceeded(f"{name} passed the 15 GB budget mid-download")
        os.replace(tmp, dest)
        with open(paths.MODELS_ROOT / "MODELS.jsonl", "a") as log:
            log.write(
                json.dumps(
                    {
                        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "name": name,
                        "file": str(dest),
                        "bytes": dest.stat().st_size,
                        "url": url,
                        "source": source,
                        "wanted_by": wanted_by,
                    }
                )
                + "\n"
            )
    return dest
