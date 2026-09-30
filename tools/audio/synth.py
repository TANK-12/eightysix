#!/usr/bin/env python3
"""Sound synthesizer for Eighty Six (lane B4): every sound is a recipe in tools/audio/recipes.json.

A recipe is layers (filtered noise, pitch sweeps, ringing partials, hums) with envelopes, then an
optional reverb tail. Each recipe renders `variants` takes with small random differences, so repeated
events do not sound identical. Loops are cross-faded end into start so they repeat without a click.
Output: 48 kHz 16-bit mono WAV in assets/audio/review/synth/<id>_<n>.wav (mono so Godot can place it
in 3D). Deterministic: the same recipe and seed always give the same file.

Usage: tools/audio/synth.py [ids...]   (no ids: render every recipe)
"""

import json
import pathlib
import sys
import wave

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
RECIPES = ROOT / "tools/audio/recipes.json"
OUT = ROOT / "assets/audio/review/synth"
RATE = 48000


def envelope(n: int, env: dict) -> np.ndarray:
    """Attack (linear), hold, then exponential decay with time constant `decay` seconds."""
    t = np.arange(n) / RATE
    a = max(float(env.get("attack", 0.002)), 1e-4)
    hold = float(env.get("hold", 0.0))
    d = max(float(env.get("decay", 0.2)), 1e-4)
    out = np.where(t < a, t / a, np.exp(-np.maximum(t - a - hold, 0.0) / d))
    return out.astype(np.float64)


def shape_spectrum(x: np.ndarray, band: list | None, tilt: float = 0.0) -> np.ndarray:
    """Band-pass by a smooth mask in the frequency domain; tilt (dB/octave) colours the noise."""
    spec = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1.0 / RATE)
    f[0] = 1.0
    mask = np.ones_like(f)
    if band:
        lo, hi = float(band[0]), float(band[1])
        if lo > 0:
            mask *= 1.0 / (1.0 + (lo / f) ** 4)
        if hi > 0:
            mask *= 1.0 / (1.0 + (f / hi) ** 4)
    if tilt:
        mask *= (f / 1000.0) ** (tilt / 6.02)
    return np.fft.irfft(spec * mask, n=len(x))


def layer_noise(n: int, spec: dict, rng: np.random.Generator) -> np.ndarray:
    x = rng.standard_normal(n)
    x = shape_spectrum(x, spec.get("band"), float(spec.get("tilt", 0.0)))
    x /= np.max(np.abs(x)) + 1e-9
    return x * envelope(n, spec.get("env", {})) * lfo(n, spec.get("lfo"), rng)


def layer_sweep(n: int, spec: dict, rng: np.random.Generator, jit: float) -> np.ndarray:
    """A tone gliding exponentially from f0 to f1 over `glide` seconds, with harmonics."""
    t = np.arange(n) / RATE
    f0 = float(spec["f0"]) * (1.0 + rng.uniform(-jit, jit))
    f1 = float(spec["f1"]) * (1.0 + rng.uniform(-jit, jit))
    glide = float(spec.get("glide", 0.3))
    k = np.clip(t / glide, 0.0, 1.0)
    freq = f0 * (f1 / f0) ** k
    phase = 2.0 * np.pi * np.cumsum(freq) / RATE
    x = np.zeros(n)
    for i, g in enumerate(spec.get("harmonics", [1.0])):
        x += float(g) * np.sin(phase * (i + 1))
    x /= np.max(np.abs(x)) + 1e-9
    return x * envelope(n, spec.get("env", {}))


def layer_partials(
    n: int, spec: dict, rng: np.random.Generator, jit: float
) -> np.ndarray:
    """Ringing metal: inharmonic partials each with its own decay, struck at each `hits` time."""
    t = np.arange(n) / RATE
    ring = np.zeros(n)
    for f, d, g in zip(
        spec["freqs"], spec["decays"], spec.get("gains", [1.0] * len(spec["freqs"]))
    ):
        fj = float(f) * (1.0 + rng.uniform(-jit, jit))
        ring += (
            float(g)
            * np.sin(2 * np.pi * fj * t + rng.uniform(0, 6.28))
            * np.exp(-t / float(d))
        )
    ring /= np.max(np.abs(ring)) + 1e-9
    out = np.zeros(n)
    for when, gain in spec.get("hits", [[0.0, 1.0]]):
        s = int((float(when) + rng.uniform(-jit, jit) * float(when)) * RATE)
        if s < n:
            out[s:] += float(gain) * ring[: n - s]
    return out


def layer_hum(n: int, spec: dict, rng: np.random.Generator) -> np.ndarray:
    """A motor or servo: harmonic tone with slow wobble, plus a gear-noise band on top."""
    t = np.arange(n) / RATE
    f = float(spec["f"])
    wob = 1.0 + float(spec.get("wobble", 0.01)) * np.sin(
        2 * np.pi * float(spec.get("wobble_hz", 3.0)) * t
    )
    phase = 2 * np.pi * np.cumsum(f * wob) / RATE
    x = np.zeros(n)
    for i, g in enumerate(spec.get("harmonics", [1.0, 0.5, 0.25])):
        x += float(g) * np.sin(phase * (i + 1))
    x /= np.max(np.abs(x)) + 1e-9
    if spec.get("grit"):
        grit = shape_spectrum(rng.standard_normal(n), spec["grit"]["band"])
        grit /= np.max(np.abs(grit)) + 1e-9
        x = x + float(spec["grit"].get("gain", 0.3)) * grit * (
            0.6 + 0.4 * np.sin(phase)
        )
    return x * envelope(n, spec.get("env", {"attack": 0.01, "hold": 99.0}))


def lfo(n: int, spec: dict | None, rng: np.random.Generator) -> np.ndarray:
    """Slow random swells (gusts): smoothed noise between 1 - depth and 1."""
    if not spec:
        return np.ones(n)
    hz = float(spec.get("hz", 0.2))
    depth = float(spec.get("depth", 0.5))
    pts = max(4, int(n / RATE * hz * 2) + 2)
    ctrl = rng.uniform(0.0, 1.0, pts)
    curve = np.interp(np.linspace(0, pts - 1, n), np.arange(pts), ctrl)
    curve = shape_spectrum(curve - curve.mean(), [0, hz * 2]) + curve.mean()
    curve = (curve - curve.min()) / (np.ptp(curve) + 1e-9)
    return 1.0 - depth + depth * curve


def reverb(x: np.ndarray, spec: dict, rng: np.random.Generator) -> np.ndarray:
    """Exponentially decaying noise as an impulse response (an outdoor slap and tail), mixed in."""
    length = int(float(spec.get("time_s", 1.2)) * RATE)
    # filter the noise first, then shape the decay: FFT filtering is circular, and filtering an
    # already-decayed tail wrapped its loud start onto its end (an echo of every attack, lane B4)
    ir = shape_spectrum(
        rng.standard_normal(length), [0, float(spec.get("lowpass", 3000))]
    )
    ir *= np.exp(-np.arange(length) / RATE / (float(spec.get("time_s", 1.2)) / 6.9))
    pre = int(float(spec.get("predelay_s", 0.02)) * RATE)
    ir = np.concatenate([np.zeros(pre), ir])
    wet = np.fft.irfft(
        np.fft.rfft(x, len(x) + len(ir)) * np.fft.rfft(ir, len(x) + len(ir))
    )[: len(x) + len(ir)]
    wet /= np.max(np.abs(wet)) + 1e-9
    dry = np.concatenate([x, np.zeros(len(ir))])
    mix = float(spec.get("mix", 0.3))
    return dry * (1.0 - mix) + wet * mix * np.max(np.abs(x))


def render(recipe: dict, variant: int) -> np.ndarray:
    rng = np.random.default_rng(int(recipe.get("seed", 86)) * 1000 + variant)
    jit = float(recipe.get("jitter", 0.04)) if variant else 0.0
    dur = float(recipe["duration_s"])
    loop = bool(recipe.get("loop", False))
    xf = int(float(recipe.get("crossfade_s", 0.5)) * RATE) if loop else 0
    n = int(dur * RATE) + xf
    mix = np.zeros(n)
    for spec in recipe["layers"]:
        start = int(float(spec.get("start_s", 0.0)) * RATE)
        m = n - start
        kind = spec["type"]
        if kind == "noise":
            y = layer_noise(m, spec, rng)
        elif kind == "sweep":
            y = layer_sweep(m, spec, rng, jit)
        elif kind == "partials":
            y = layer_partials(m, spec, rng, jit)
        elif kind == "hum":
            y = layer_hum(m, spec, rng)
        else:
            raise ValueError(f"unknown layer type {kind}")
        mix[start:] += float(spec.get("gain", 1.0)) * (1.0 + rng.uniform(-jit, jit)) * y
    if not loop:
        # one-shots fade out over their last 15 % (before any reverb): cutting a still-ringing
        # layer at the end of duration_s clicked (a vertical line in the spectrogram)
        tail = max(int(float(recipe.get("fade_share", 0.15)) * n), 1)
        mix[-tail:] *= np.linspace(1.0, 0.0, tail) ** 2
    if recipe.get("reverb"):
        mix = reverb(mix, recipe["reverb"], rng)
    if loop:
        body = mix[: n - xf].copy()
        fade = np.linspace(0.0, 1.0, xf)
        body[:xf] = body[:xf] * fade + mix[n - xf :] * (1.0 - fade)
        mix = body
    peak = 10 ** (float(recipe.get("peak_db", -1.0)) / 20.0)
    return mix / (np.max(np.abs(mix)) + 1e-9) * peak


def write_wav(path: pathlib.Path, x: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = np.clip(x * 32767.0, -32768, 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())


def main(ids: list[str]) -> None:
    recipes = json.loads(RECIPES.read_text())["entries"]
    for rid, recipe in recipes.items():
        if ids and rid not in ids:
            continue
        for v in range(int(recipe.get("variants", 1))):
            path = OUT / f"{rid}_{v + 1}.wav"
            write_wav(path, render(recipe, v))
            print(path.relative_to(ROOT))


if __name__ == "__main__":
    main(sys.argv[1:])
