"""Procedural SFX synth recipes: a dict of numbers each, the same idea as
~/Forge/shared/forge_sound.js's recipe format (wave/duration/gain/filter),
ported to numpy so it can render offline to a wav file instead of a live
Web Audio graph. One entry per sound; add a sound by adding one entry.

render(name, **overrides) -> (mono float32 samples, sr). overrides can set
"repeat", "stretch" (duration/spacing scale, from onomatopoeia length -- see
match.py) or any base spec field, e.g. "gain_db".
"""

from __future__ import annotations

import numpy as np

from ..audio import dsp

SR = dsp.SR


def _osc(
    wave: str, freq: float, freq_to: float | None, duration: float, sr: int
) -> np.ndarray:
    n = max(1, int(duration * sr))
    t = np.arange(n) / sr
    if freq_to and freq_to != freq and freq > 0:
        k = np.log(max(freq_to, 1) / freq) / max(duration, 1e-6)
        inst = freq * np.exp(k * t)
    else:
        inst = np.full(n, freq)
    phase = 2 * np.pi * np.cumsum(inst) / sr
    if wave == "sine":
        return np.sin(phase).astype(np.float32)
    if wave == "square":
        return np.sign(np.sin(phase)).astype(np.float32)
    if wave == "triangle":
        return (2 / np.pi * np.arcsin(np.sin(phase))).astype(np.float32)
    if wave == "saw":
        return (2 * ((phase / (2 * np.pi)) % 1) - 1).astype(np.float32)
    raise ValueError(f"unknown wave {wave!r}")


def _envelope(n: int, sr: int, attack: float, decay_tau: float) -> np.ndarray:
    t = np.arange(n) / sr
    env = np.exp(-t / max(decay_tau, 1e-4))
    att_n = min(n, int(attack * sr))
    if att_n > 0:
        env[:att_n] = np.minimum(env[:att_n], np.linspace(0, 1, att_n))
    return env.astype(np.float32)


def _swept_lowpass(
    sig: np.ndarray, sr: int, filt: float, filt_to: float | None
) -> np.ndarray:
    if not filt_to or filt_to == filt:
        return dsp.lowpass(sig, sr, filt)
    segs = 4
    n = sig.shape[0]
    seg_n = max(1, n // segs)
    parts = []
    for i in range(segs):
        cutoff = filt + (filt_to - filt) * (i / (segs - 1) if segs > 1 else 0)
        s0, s1 = i * seg_n, (n if i == segs - 1 else (i + 1) * seg_n)
        if s1 > s0:
            parts.append(dsp.lowpass(sig[s0:s1], sr, cutoff))
    out = np.concatenate(parts) if parts else sig
    if out.shape[0] < n:
        out = np.pad(out, (0, n - out.shape[0]))
    return out[:n]


def synth_hit(spec: dict, rng: np.random.Generator, sr: int = SR) -> np.ndarray:
    wave = spec.get("wave", "sine")
    duration = max(0.01, spec.get("duration", 0.2))
    n = max(1, int(duration * sr))
    if wave == "noise":
        sig = rng.uniform(-1, 1, n).astype(np.float32)
    else:
        sig = _osc(wave, spec.get("freq", 440.0), spec.get("freq_to"), duration, sr)[:n]
    env = _envelope(
        n, sr, spec.get("attack", 0.003), spec.get("decay_tau", duration / 3)
    )
    sig = sig * env
    if spec.get("filter"):
        sig = _swept_lowpass(sig, sr, spec["filter"], spec.get("filter_to"))
    sig = sig * float(spec.get("gain", 1.0))
    return sig.astype(np.float32)


# name -> (unit spec, default repeat, default interval seconds)
# "unit" is one hit; multi-hit sounds (gunfire, footsteps) repeat it.
RECIPES: dict[str, tuple[dict, int, float]] = {
    "clank": (
        {
            "wave": "square",
            "freq": 900,
            "freq_to": 300,
            "duration": 0.18,
            "attack": 0.001,
            "decay_tau": 0.05,
            "filter": 4000,
            "filter_to": 800,
            "gain": 0.9,
        },
        1,
        0.0,
    ),
    "boom": (
        {
            "wave": "sine",
            "freq": 90,
            "freq_to": 35,
            "duration": 0.9,
            "attack": 0.005,
            "decay_tau": 0.35,
            "filter": 900,
            "filter_to": 150,
            "gain": 1.0,
        },
        1,
        0.0,
    ),
    "blam": (
        {
            "wave": "noise",
            "duration": 0.35,
            "attack": 0.001,
            "decay_tau": 0.09,
            "filter": 3500,
            "filter_to": 400,
            "gain": 1.0,
        },
        1,
        0.0,
    ),
    "bang": (
        {
            "wave": "noise",
            "duration": 0.22,
            "attack": 0.001,
            "decay_tau": 0.06,
            "filter": 5000,
            "filter_to": 600,
            "gain": 1.0,
        },
        1,
        0.0,
    ),
    "ratatata": (
        {
            "wave": "noise",
            "duration": 0.09,
            "attack": 0.001,
            "decay_tau": 0.025,
            "filter": 4500,
            "filter_to": 900,
            "gain": 0.85,
        },
        6,
        0.09,
    ),
    "whoosh": (
        {
            "wave": "noise",
            "duration": 0.5,
            "attack": 0.08,
            "decay_tau": 0.25,
            "filter": 400,
            "filter_to": 3500,
            "gain": 0.7,
        },
        1,
        0.0,
    ),
    "fsssh": (
        {
            "wave": "noise",
            "duration": 0.6,
            "attack": 0.02,
            "decay_tau": 0.4,
            "filter": 6000,
            "filter_to": 5000,
            "gain": 0.55,
        },
        1,
        0.0,
    ),
    "clap": (
        {
            "wave": "noise",
            "duration": 0.12,
            "attack": 0.001,
            "decay_tau": 0.035,
            "filter": 4000,
            "filter_to": 1500,
            "gain": 0.9,
        },
        1,
        0.0,
    ),
    "ting": (
        {
            "wave": "triangle",
            "freq": 2600,
            "freq_to": 2400,
            "duration": 0.5,
            "attack": 0.001,
            "decay_tau": 0.3,
            "gain": 0.6,
        },
        1,
        0.0,
    ),
    "slash": (
        {
            "wave": "noise",
            "duration": 0.22,
            "attack": 0.002,
            "decay_tau": 0.06,
            "filter": 7000,
            "filter_to": 2000,
            "gain": 0.85,
        },
        1,
        0.0,
    ),
    "stomp": (
        {
            "wave": "sine",
            "freq": 130,
            "freq_to": 55,
            "duration": 0.28,
            "attack": 0.001,
            "decay_tau": 0.09,
            "filter": 500,
            "gain": 0.95,
        },
        1,
        0.0,
    ),
    "lunge": (
        {
            "wave": "saw",
            "freq": 220,
            "freq_to": 480,
            "duration": 0.24,
            "attack": 0.005,
            "decay_tau": 0.1,
            "filter": 2500,
            "gain": 0.75,
        },
        1,
        0.0,
    ),
    "glow_hum": (
        {
            "wave": "sine",
            "freq": 220,
            "duration": 1.2,
            "attack": 0.15,
            "decay_tau": 0.9,
            "filter": 1200,
            "gain": 0.4,
        },
        1,
        0.0,
    ),
    "crash": (
        {
            "wave": "noise",
            "duration": 1.1,
            "attack": 0.002,
            "decay_tau": 0.5,
            "filter": 6000,
            "filter_to": 500,
            "gain": 1.0,
        },
        1,
        0.0,
    ),
    "footsteps": (
        {
            "wave": "noise",
            "duration": 0.1,
            "attack": 0.002,
            "decay_tau": 0.04,
            "filter": 900,
            "filter_to": 250,
            "gain": 0.7,
        },
        3,
        0.35,
    ),
    "thud": (
        {
            "wave": "sine",
            "freq": 100,
            "freq_to": 45,
            "duration": 0.22,
            "attack": 0.002,
            "decay_tau": 0.08,
            "filter": 400,
            "gain": 0.85,
        },
        1,
        0.0,
    ),
}


def names() -> list[str]:
    return sorted(RECIPES.keys())


def render(
    name: str,
    repeat: int | None = None,
    stretch: float = 1.0,
    gain_db: float = 0.0,
    interval: float | None = None,
    seed: int = 0,
    **spec_overrides,
) -> tuple[np.ndarray, int]:
    if name not in RECIPES:
        raise KeyError(f"no sfx recipe {name!r}")
    base, def_repeat, def_interval = RECIPES[name]
    spec = dict(base)
    spec.update(spec_overrides)
    spec["duration"] = spec["duration"] * stretch
    if "decay_tau" in spec:
        spec["decay_tau"] = spec["decay_tau"] * stretch
    reps = repeat if repeat is not None else def_repeat
    reps = max(1, min(reps, 40))
    step = (interval if interval is not None else def_interval) * stretch
    rng = np.random.default_rng(seed)
    if reps == 1:
        sig = synth_hit(spec, rng)
    else:
        total_n = int((step * (reps - 1) + spec["duration"] + 0.05) * SR)
        sig = np.zeros(max(1, total_n), dtype=np.float32)
        for i in range(reps):
            hit = synth_hit(spec, rng)
            off = int(i * step * SR)
            end = off + hit.shape[0]
            if end > sig.shape[0]:
                sig = np.pad(sig, (0, end - sig.shape[0]))
            sig[off:end] += hit
    if gain_db:
        sig = dsp.gain_db(sig, gain_db)
    sig = dsp.limiter(sig, ceiling=0.95)
    return sig, SR
