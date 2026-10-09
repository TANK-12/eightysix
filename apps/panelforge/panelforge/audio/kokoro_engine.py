"""Loads Kokoro TTS once and keeps it. Same package and model files NovelForge
uses (novelforge/audiobook.py): kokoro-onnx, reading
~/NovelMakerData/tts_voices/{kokoro-v1.0.onnx,voices-v1.0.bin}. Never copied
-- both apps point at the same files on disk.

Kokoro's own output is 24 kHz mono float. Everything above this module works
in the project's standard 48 kHz, so `synthesize` resamples before returning.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

import numpy as np

from . import dsp
from . import voices as voices_mod
from . import emotion
from .emotion import MAX_BLEND_WEIGHT

SEGMENT_CROSSFADE_S = 0.015

MODEL_PATH = Path(
    os.environ.get("KOKORO_MODEL")
    or Path.home() / "NovelMakerData/tts_voices/kokoro-v1.0.onnx"
)
VOICES_PATH = Path(
    os.environ.get("KOKORO_VOICES")
    or Path.home() / "NovelMakerData/tts_voices/voices-v1.0.bin"
)

NATIVE_SR = 24000

_lock = threading.Lock()
_kokoro = None
_load_error: str | None = None


def available() -> bool:
    return MODEL_PATH.exists() and VOICES_PATH.exists()


def _load():
    global _kokoro, _load_error
    with _lock:
        if _kokoro is not None or _load_error is not None:
            return _kokoro
        if not available():
            _load_error = (
                f"Kokoro model files not found at {MODEL_PATH} / {VOICES_PATH}"
            )
            return None
        try:
            from kokoro_onnx import Kokoro

            _kokoro = Kokoro(str(MODEL_PATH), str(VOICES_PATH))
        except Exception as e:  # reported to caller, never fatal to the app
            _load_error = f"{type(e).__name__}: {e}"
        return _kokoro


def load_error() -> str | None:
    _load()
    return _load_error


def voice_names() -> list[str]:
    k = _load()
    if k is None:
        return []
    voices: object = k.voices
    keys_fn = getattr(voices, "keys", None)
    names = list(keys_fn()) if keys_fn is not None else list(voices)  # type: ignore[arg-type]
    return sorted(names)


def style_vector(voice: str, blend: dict | None = None) -> np.ndarray | None:
    """The style vector Kokoro will speak with: the chosen voice's own, or a
    weighted mix with a brighter/darker/softer partner (voices.BLEND_PARTNERS)
    when the emotion asks for one. The chosen voice keeps at least 75%.
    None when no blend applies, so the caller passes the plain voice id."""
    if not blend or not blend.get("tone") or not blend.get("weight"):
        return None
    k = _load()
    if k is None:
        return None
    weight = max(0.0, min(MAX_BLEND_WEIGHT, float(blend["weight"])))
    partner = voices_mod.blend_partner(voice, blend["tone"], voice_names())
    if partner is None or weight <= 0:
        return None
    base = np.asarray(k.get_voice_style(voice), dtype=np.float32)
    other = np.asarray(k.get_voice_style(partner), dtype=np.float32)
    if base.shape != other.shape:
        return None
    return ((1.0 - weight) * base + weight * other).astype(np.float32)


def synthesize(
    text: str, voice: str, speed: float = 1.0, style: np.ndarray | None = None
) -> tuple[np.ndarray, int]:
    """Returns (mono float32 samples, sample_rate=48000). Raises RuntimeError
    if Kokoro isn't available -- callers decide whether that's fatal.
    `style` is an optional blended style vector (see style_vector); the
    voice id is still what was picked."""
    k = _load()
    if k is None:
        raise RuntimeError(_load_error or "Kokoro not loaded")
    speed = max(0.5, min(2.0, speed))
    samples, sr = k.create(
        text, voice=style if style is not None else voice, speed=speed, lang="en-us"
    )
    arr = np.asarray(samples, dtype=np.float32)
    arr = np.clip(arr, -1.0, 1.0)
    arr = dsp.resample(arr, sr, dsp.SR)
    return arr, dsp.SR


def synthesize_line(text: str, voice: str, em: dict) -> tuple[np.ndarray, int]:
    """Speak one script line the way its emotion asks: Kokoro speed, a
    blended style vector by expression, and bold-word emphasis. A line with
    no bold word present is one synthesis call, exactly as before; a line
    with bold words is split at them (emotion.segments_for), each segment
    synthesised with its own speed and gain, and joined with short
    crossfades. Everything after Kokoro (pitch, grit, room...) is
    emotion.apply's job."""
    speed = float(em.get("speed", 1.0) or 1.0)
    segments = emotion.segments_for(text, em.get("emphasis") or [])
    style = style_vector(voice, em.get("blend"))
    if len(segments) == 1:
        if style is None:
            return synthesize(text, voice, speed=speed)
        return synthesize(text, voice, speed=speed, style=style)
    parts = []
    sr = dsp.SR
    for seg in segments:
        seg_speed = speed * seg["speed_mul"]
        if style is None:
            audio, sr = synthesize(seg["text"], voice, speed=seg_speed)
        else:
            audio, sr = synthesize(seg["text"], voice, speed=seg_speed, style=style)
        if seg["gain_db"]:
            audio = dsp.gain_db(audio, seg["gain_db"])
        parts.append(audio)
    return dsp.join_crossfade(parts, sr, SEGMENT_CROSSFADE_S), sr
