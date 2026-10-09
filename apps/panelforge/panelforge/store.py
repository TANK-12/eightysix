"""Atomic JSON files. Every chapter/series document goes through here.

A half-written JSON file would break every stage that reads it, so writes go
to a temp file in the same folder and are renamed into place. Each document
carries "schema": <int> so a later version can migrate old files.
"""

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock(path: Path) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(str(path), threading.Lock())


def read(path: Path, default: Any = None) -> Any:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock(path):
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=1, ensure_ascii=False)
            os.replace(tmp, path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise


def update(path: Path, fn, default: Any = None) -> Any:
    """Read, apply fn(doc) -> doc, write. Serialised per file within this process."""
    with _lock(path):
        doc = read(path, default)
    new = fn(doc)
    write(path, new)
    return new
