"""Keep caches under a healthy size, from the list in cache_trim.json.

Each cache entry names a folder, a size limit and a glob for the top-level
entries that may go. When the folder is over its limit, matching entries are
removed oldest first until it is under half the limit. Anything modified in the
last min_age_minutes is left alone so a program using it is not disturbed.
Adding a cache is one new entry in cache_trim.json.

    python3 tools/cache_trim.py [--dry-run] [--config PATH]

Run every few hours by the forge-cache-trim systemd user timer.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

CONFIG = Path(__file__).with_name("cache_trim.json")
MB = 1024 * 1024


def size_of(path: Path) -> int:
    """Bytes used by a file or folder, not following symlinks."""
    if path.is_symlink() or path.is_file():
        return path.lstat().st_size
    total = 0
    for child in path.rglob("*"):
        try:
            if not child.is_symlink() and child.is_file():
                total += child.stat().st_size
        except OSError:
            pass
    return total


def newest_mtime(path: Path) -> float:
    """Latest modification time of a path or anything inside it."""
    latest = path.lstat().st_mtime
    if path.is_dir() and not path.is_symlink():
        for child in path.rglob("*"):
            try:
                latest = max(latest, child.lstat().st_mtime)
            except OSError:
                pass
    return latest


def trim(entry: dict, dry_run: bool = False, now: float | None = None) -> dict:
    """Trim one cache entry; return what was found and removed."""
    root = Path(entry["path"]).expanduser()
    limit = int(entry["limit_mb"] * MB)
    report = {"name": entry["name"], "path": str(root), "removed": 0, "freed_mb": 0.0}
    if not root.is_dir():
        report["status"] = "missing"
        return report
    total = size_of(root)
    report["before_mb"] = round(total / MB, 1)
    if total <= limit:
        report["status"] = "under limit"
        return report
    cutoff = (now if now is not None else time.time()) - entry.get(
        "min_age_minutes", 60
    ) * 60
    candidates = []
    for child in root.glob(entry.get("pattern", "*")):
        try:
            mtime = newest_mtime(child)
        except OSError:
            continue
        if mtime < cutoff:
            candidates.append((mtime, child))
    candidates.sort()
    target = limit // 2
    for _, child in candidates:
        if total <= target:
            break
        size = size_of(child)
        if not dry_run:
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)
        total -= size
        report["removed"] += 1
        report["freed_mb"] += size / MB
    report["freed_mb"] = round(report["freed_mb"], 1)
    report["after_mb"] = round(total / MB, 1)
    report["status"] = "trimmed"
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Keep caches under a healthy size.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--config", type=Path, default=CONFIG)
    args = parser.parse_args(argv)
    caches = json.loads(args.config.read_text())["caches"]
    for entry in caches:
        r = trim(entry, dry_run=args.dry_run)
        line = f"{r['name']}: {r['status']}"
        if r["status"] == "trimmed":
            line += f", removed {r['removed']} ({r['freed_mb']} MB), {r['before_mb']} -> {r['after_mb']} MB"
        elif "before_mb" in r:
            line += f" ({r['before_mb']} MB)"
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
