"""Per-line audio cache, keyed by text + voice + emotion so re-running the
voice job after an unrelated edit doesn't re-synthesise every line."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def key(text: str, voice: str, emotion: dict) -> str:
    payload = json.dumps(
        {"text": text, "voice": voice, "emotion": emotion}, sort_keys=True
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def cache_path(work_dir: Path, cache_key: str) -> Path:
    return work_dir / "audio" / "cache" / f"{cache_key}.wav"
