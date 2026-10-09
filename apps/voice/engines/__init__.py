"""Speech engines, one file each, found by a registry row's `engine` name.

Adding an engine is one new file here with a class `Engine`:

    Engine(row: dict, files: dict[str, Path], threads: int)
    STT: transcribe(audio: float32 mono 16 kHz numpy array) -> str
    TTS: voices() -> list[str]; synthesize(text, voice, speed) -> (float32 array, rate)
         optional: used_voice, set by synthesize to the voice that really spoke
    both: close()
    raise InputError for a line or voice that cannot be spoken: the service
    answers 400 and keeps the model loaded (any other error unloads a heavy one)
    optional, at module level: clear_stale(row, files) stops what a dead
    backend left running for the row (called before a heavy row's memory check)

An engine needing another venv runs its own subprocess inside its file.
"""

from __future__ import annotations

import importlib
import io
import re
import wave
from pathlib import Path

import numpy as np


class InputError(ValueError):
    """The text or voice asked for cannot be spoken; the model is fine."""


_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


def _module(name: str):
    if not _NAME.match(name or ""):
        raise ValueError(f"bad engine name: {name!r}")
    return importlib.import_module(f"engines.{name}")


def engine_class(name: str):
    """The Engine class of engines/<name>.py."""
    return _module(name).Engine


def load(row: dict, files: dict[str, Path], threads: int):
    return engine_class(row["engine"])(row, files, threads)


def clear_stale(row: dict, files: dict[str, Path]) -> None:
    """The row's engine stops what a dead backend left running, if it can."""
    fn = getattr(_module(row["engine"]), "clear_stale", None)
    if fn is not None:
        fn(row, files)


def wav_bytes(audio: np.ndarray, rate: int) -> bytes:
    """Mono float32 [-1, 1] to 16-bit PCM wav bytes."""
    pcm = (np.clip(np.asarray(audio, dtype=np.float32), -1.0, 1.0) * 32767).astype(
        "<i2"
    )
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(rate))
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


def pick_file(files: dict[str, Path], names: tuple[str, ...], suffix: str) -> Path:
    """The file under one of `names`, else the first with `suffix`."""
    for n in names:
        if n in files:
            return files[n]
    for p in files.values():
        if str(p).endswith(suffix):
            return p
    raise FileNotFoundError(f"no {suffix} file among {sorted(files)}")
