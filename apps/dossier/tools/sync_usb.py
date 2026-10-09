"""Keep a plain copy of the app source beside its data on the AN3 drive.

The working install stays on the internal disk, because a virtualenv on exfat
is unreliable - no symlinks, no executable bits the way Python expects them.
What goes on the USB is the source itself, so the drive carries both the
research and the thing that produced it, and a rebuild elsewhere is a venv away.

Usage:
    .venv/bin/python tools/sync_usb.py            # copy source to AN3
    .venv/bin/python tools/sync_usb.py --check    # say what would change
"""

from __future__ import annotations

import filecmp
import shutil
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".venv", "__pycache__", ".pytest_cache", ".git", "node_modules"}
SKIP_SUFFIX = {".pyc", ".pyo", ".log", ".tmp"}


def target_root() -> Path:
    import store

    root = store.data_root()
    if not root.on_usb:
        raise SystemExit(
            "AN3 is not mounted, so there is nowhere to sync to.\n" f"({root.detail})"
        )
    return root.path.parent / "Dossier-app"


def wanted(path: Path) -> bool:
    if any(part in SKIP_DIRS for part in path.parts):
        return False
    return path.suffix not in SKIP_SUFFIX


def sync(check_only: bool = False) -> dict:
    sys.path.insert(0, str(APP_ROOT))
    destination = target_root()
    copied = skipped = 0
    for source in sorted(APP_ROOT.rglob("*")):
        if not source.is_file():
            continue
        relative = source.relative_to(APP_ROOT)
        if not wanted(relative):
            continue
        out = destination / relative
        if out.exists() and filecmp.cmp(source, out, shallow=False):
            skipped += 1
            continue
        copied += 1
        if not check_only:
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, out)
    if not check_only:
        (destination / "HOW-TO-RUN.txt").write_text(
            "Dossier - portable source copy\n"
            "==============================\n\n"
            "This is the app that produced ../DossierData. It has no virtualenv,\n"
            "because one does not survive on this filesystem. To run it anywhere:\n\n"
            "    python3 -m venv --system-site-packages .venv\n"
            "    .venv/bin/pip install fastapi uvicorn httpx beautifulsoup4 lxml feedparser\n"
            "    .venv/bin/python -m uvicorn web_app:app --port 8437\n\n"
            "It will find the research in ../DossierData automatically when this\n"
            "drive is mounted at /run/media/<user>/AN3, and fall back to a local\n"
            "directory otherwise. Point DOSSIER_USB_ROOT at the data directory if\n"
            "the drive mounts somewhere else.\n",
            encoding="utf-8",
        )
    return {"destination": str(destination), "copied": copied, "unchanged": skipped}


if __name__ == "__main__":
    result = sync(check_only="--check" in sys.argv)
    verb = "would copy" if "--check" in sys.argv else "copied"
    print(f"{verb} {result['copied']} files, {result['unchanged']} already current")
    print(f"-> {result['destination']}")
