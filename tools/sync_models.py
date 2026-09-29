#!/usr/bin/env python3
"""Copy each model's game export into the game: assets/models/<name>/.

Sources are listed in tools/model_sources.json (one entry per model). Only files whose content
changed are copied; nothing in the game folder is ever deleted. Each synced folder gets a
SOURCE.json naming the source folder and each file's size and sha256, so the game always says
which export it holds. Run `godot --headless --path . --import` afterwards (this script does it
when anything changed) so Godot imports new glb files.

Usage: tools/sync_models.py [name ...]      (default: every entry)
"""

import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ROOT / "tools" / "model_sources.json"
DEST = ROOT / "assets" / "models"
SKIP_SUFFIXES = {".blend", ".blend1", ".import"}


def sha256(path: Path) -> str:
    """Hex sha256 of a file, read in chunks."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sync_one(name: str, source: Path, dest: Path) -> dict:
    """Copy changed files from source to dest; return a summary for SOURCE.json and the log."""
    files = sorted(
        p for p in source.iterdir() if p.is_file() and p.suffix not in SKIP_SUFFIXES
    )
    dest.mkdir(parents=True, exist_ok=True)
    copied, same = [], []
    listing = {}
    for src in files:
        digest = sha256(src)
        target = dest / src.name
        if target.is_file() and sha256(target) == digest:
            same.append(src.name)
        else:
            shutil.copy2(src, target)
            copied.append(src.name)
        listing[src.name] = {"bytes": src.stat().st_size, "sha256": digest}
    summary = {
        "name": name,
        "source": str(source),
        "synced": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "files": listing,
    }
    if copied:
        (dest / "SOURCE.json").write_text(json.dumps(summary, indent=2) + "\n")
    return {"copied": copied, "same": same}


def main() -> int:
    entries = json.loads(SOURCES.read_text())["entries"]
    wanted = sys.argv[1:] or list(entries)
    unknown = [n for n in wanted if n not in entries]
    if unknown:
        print(f"sync_models: unknown model(s): {', '.join(unknown)}", file=sys.stderr)
        return 2
    changed = False
    for name in wanted:
        source = Path(entries[name]["source"]).expanduser()
        if not source.is_dir():
            print(f"{name}: no export yet at {source}")
            continue
        result = sync_one(name, source, DEST / name)
        changed = changed or bool(result["copied"])
        print(
            f"{name}: copied {len(result['copied'])} {result['copied']}, unchanged {len(result['same'])}"
        )
    if changed:
        done = subprocess.run(
            ["godot", "--headless", "--path", str(ROOT), "--import"],
            capture_output=True,
            text=True,
        )
        errors = [
            line
            for line in (done.stdout + done.stderr).splitlines()
            if line.startswith("ERROR")
        ]
        print(f"godot import: exit {done.returncode}, {len(errors)} error line(s)")
        for line in errors[:10]:
            print("  " + line)
        return 0 if done.returncode == 0 else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
