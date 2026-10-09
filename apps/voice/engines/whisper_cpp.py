"""STT through whisper.cpp's `whisper-cli` on a ggml model file.

The binary is env FORGE_WHISPER_CLI, else Nyarch's build. Each call writes a
temporary 16 kHz wav and runs the binary with no timestamps; nothing stays
loaded between calls.

A row with "short_ctx": true reads a short clip with a cut audio context: the
encoder covers 30 s (1500 frames, 50 a second) whatever the clip, so a 1 s
command takes 0.8 s instead of 1.9 s. A cut context can make whisper repeat
itself, so such an answer is read again with the full context
(docs/library/voice/2026-10-08-stt-under-100mb.md, audio context section).
"""

from __future__ import annotations

import math
import os
import re
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from engines import pick_file, wav_bytes

NYARCH_CLI = (
    Path.home()
    / ".var/app/moe.nyarchlinux.assistant/config/models/whisper/whisper.cpp"
    / "build/bin/whisper-cli"
)
RATE = 16000


def cli_path() -> Path:
    return Path(os.environ.get("FORGE_WHISPER_CLI") or NYARCH_CLI)


def short_ctx(seconds: float) -> int:
    """Audio context for a clip: 512 at least and a 256 margin kept WER equal
    to the full context on the 10 test clips; a 128 margin looped once."""
    return min(1500, max(512, math.ceil(seconds * 50) + 256))


def looped(text: str, seconds: float) -> bool:
    """Too many words for the audio, or one sentence of 3+ words twice."""
    if len(text.split()) > 5 * seconds + 3:
        return True
    seen: set[str] = set()
    for part in re.split(r"(?<=[.!?])\s+", text.lower()):
        key = " ".join(re.findall(r"[a-z0-9']+", part))
        if len(key.split()) >= 3:
            if key in seen:
                return True
            seen.add(key)
    return False


class Engine:
    def __init__(self, row: dict, files: dict[str, Path], threads: int):
        self.model = pick_file(files, ("model", "ggml"), ".bin")
        self.cli = cli_path()
        if not self.cli.exists():
            raise FileNotFoundError(f"whisper-cli not found at {self.cli}")
        if not self.model.exists():
            raise FileNotFoundError(f"model not found at {self.model}")
        self.threads = max(1, int(threads))
        self.language = row.get("language") or "en"
        self.short_ctx = bool(row.get("short_ctx"))

    def transcribe(self, audio: np.ndarray) -> str:
        seconds = audio.size / RATE
        with tempfile.NamedTemporaryFile(suffix=".wav", prefix="forge-voice-") as f:
            f.write(wav_bytes(audio, RATE))
            f.flush()
            if self.short_ctx and short_ctx(seconds) < 1500:
                text = self._run(f.name, short_ctx(seconds))
                if not looped(text, seconds):
                    return text
            return self._run(f.name, 0)

    def _run(self, path: str, ctx: int) -> str:
        cmd = [str(self.cli), "-m", str(self.model), "-f", path]
        cmd += ["-t", str(self.threads), "-l", self.language, "-nt", "-np"]
        if ctx:
            cmd += ["-ac", str(ctx)]
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if out.returncode != 0:
            raise RuntimeError(f"whisper-cli failed: {out.stderr.strip()[-300:]}")
        return " ".join(out.stdout.split())

    def close(self) -> None:
        pass
