"""Procedural mood music: scales, tempo, a chord progression, a pad and a
percussion pattern per mood, rendered to a seamlessly-loopable stereo clip.
No samples, no MIDI -- just numpy oscillators and noise, the same spirit as
panelforge/sfx/recipes.py.

`generate(mood, ...)` returns one exact-bar loop, already made seamless by
crossfading its true continuation into its own start (see `_loopify`).
`tile_to_length` repeats a loop out to an arbitrary duration.
`crossfade_moods` blends from one mood's loop into another's, for a mood
change mid-chapter.
"""

from __future__ import annotations

import numpy as np

from ..audio import dsp

SR = dsp.SR

SCALES = {
    "major": [0, 2, 4, 5, 7, 9, 11],
    "minor": [0, 2, 3, 5, 7, 8, 10],
    "dorian": [0, 2, 3, 5, 7, 9, 10],
    "phrygian": [0, 1, 3, 5, 7, 8, 10],
    "wholetone": [0, 2, 4, 6, 8, 10],
}

# mood -> scale, root Hz, tempo, a 4-chord diatonic progression (scale
# degrees), beats per chord, the pad's oscillator shape and a percussion
# pattern name.
MOODS = {
    "tense": {
        "scale": "phrygian",
        "root": 196.0,
        "bpm": 72,
        "chords": [0, 0, 5, 4],
        "beats_per_chord": 4,
        "pad": "triangle",
        "perc": "sparse",
    },
    "calm": {
        "scale": "major",
        "root": 220.0,
        "bpm": 60,
        "chords": [0, 3, 4, 0],
        "beats_per_chord": 4,
        "pad": "sine",
        "perc": "none",
    },
    "action": {
        "scale": "minor",
        "root": 220.0,
        "bpm": 140,
        "chords": [0, 2, 3, 4],
        "beats_per_chord": 2,
        "pad": "saw",
        "perc": "driving",
    },
    "sad": {
        "scale": "minor",
        "root": 196.0,
        "bpm": 55,
        "chords": [0, 5, 3, 4],
        "beats_per_chord": 4,
        "pad": "sine",
        "perc": "none",
    },
    "comic": {
        "scale": "major",
        "root": 261.63,
        "bpm": 118,
        "chords": [0, 4, 5, 3],
        "beats_per_chord": 2,
        "pad": "square",
        "perc": "bouncy",
    },
    "mystery": {
        "scale": "wholetone",
        "root": 207.65,
        "bpm": 64,
        "chords": [0, 2, 4, 0],
        "beats_per_chord": 4,
        "pad": "triangle",
        "perc": "sparse",
    },
}

PERC_PATTERNS = {
    "none": [],
    "sparse": [(0.0, "kick")],
    "driving": [(0.0, "kick"), (0.5, "hat"), (1.0, "kick"), (1.5, "hat")],
    "bouncy": [(0.0, "kick"), (0.75, "hat"), (1.5, "kick")],
}


def moods() -> list[str]:
    return sorted(MOODS.keys())


def _degree_freq(root: float, scale: list[int], degree: int) -> float:
    octave, idx = divmod(degree, len(scale))
    semitone = scale[idx] + 12 * octave
    return root * (2.0 ** (semitone / 12.0))


def _osc(wave: str, freq: float, n: int, sr: int) -> np.ndarray:
    t = np.arange(n) / sr
    phase = 2 * np.pi * freq * t
    if wave == "sine":
        return np.sin(phase)
    if wave == "triangle":
        return 2 / np.pi * np.arcsin(np.sin(phase))
    if wave == "square":
        return np.sign(np.sin(phase))
    if wave == "saw":
        return 2 * ((freq * t) % 1) - 1
    raise ValueError(wave)


def _pad_chord(
    root: float, scale: list[int], degree: int, wave: str, n: int, sr: int, gain: float
) -> np.ndarray:
    tones = [_degree_freq(root, scale, degree + step) for step in (0, 2, 4)]
    sig = np.zeros(n, dtype=np.float64)
    for f in tones:
        sig += _osc(wave, f, n, sr) / len(tones)
    # slow attack/release so chord changes are pads, not stabs
    attack = min(n, int(0.35 * sr))
    release = min(n, int(0.35 * sr))
    env = np.ones(n)
    env[:attack] = np.linspace(0, 1, attack)
    env[n - release :] = np.minimum(env[n - release :], np.linspace(1, 0, release))
    return (sig * env * gain).astype(np.float32)


def _kick(n_beat_samples: int, sr: int) -> np.ndarray:
    n = min(n_beat_samples, int(0.22 * sr))
    t = np.arange(n) / sr
    freq = 110 * np.exp(-t / 0.05) + 40
    phase = 2 * np.pi * np.cumsum(freq) / sr
    env = np.exp(-t / 0.09)
    return (np.sin(phase) * env * 0.9).astype(np.float32)


def _hat(n_beat_samples: int, sr: int, rng: np.random.Generator) -> np.ndarray:
    n = min(n_beat_samples, int(0.05 * sr))
    sig = rng.uniform(-1, 1, n).astype(np.float32)
    sig = dsp.lowpass(sig, sr, 9000)
    env = np.exp(-np.arange(n) / sr / 0.015)
    return (sig * env * 0.4).astype(np.float32)


def generate(
    mood: str, seed: int = 0, gain_db: float = -14.0
) -> tuple[np.ndarray, int]:
    """One seamless loop covering the mood's full 4-chord progression."""
    if mood not in MOODS:
        raise KeyError(f"unknown mood {mood!r}")
    cfg = MOODS[mood]
    scale = SCALES[cfg["scale"]]
    beat_s = 60.0 / cfg["bpm"]
    beat_n = int(beat_s * SR)
    chord_n = beat_n * cfg["beats_per_chord"]
    rng = np.random.default_rng(seed)
    perc = PERC_PATTERNS[cfg["perc"]]

    # render one extra chord past the loop point so the loop can crossfade
    # into its own true continuation (see _loopify).
    chords = cfg["chords"] + [cfg["chords"][0]]
    total_n = chord_n * (len(chords) - 1) + chord_n
    buf = np.zeros((total_n, 2), dtype=np.float32)
    for i, degree in enumerate(chords):
        start = i * chord_n
        pad = _pad_chord(cfg["root"], scale, degree, cfg["pad"], chord_n, SR, gain=0.5)
        dsp.mix_into(buf, dsp.to_stereo(pad), start)
        for beats in range(cfg["beats_per_chord"]):
            beat_start = start + beats * beat_n
            for offset_beats, kind in perc:
                pos = beat_start + int(offset_beats * beat_n)
                hit = _kick(beat_n, SR) if kind == "kick" else _hat(beat_n, SR, rng)
                dsp.mix_into(buf, dsp.to_stereo(hit), pos)

    loop_len = chord_n * (len(cfg["chords"]))
    overlap_s = min(1.0, beat_s)
    out = _loopify(buf, loop_len, SR, overlap_s)
    out = dsp.gain_db(out, gain_db)
    out = dsp.limiter(out, ceiling=0.95)
    return out, SR


def _loopify(raw: np.ndarray, loop_len: int, sr: int, overlap_s: float) -> np.ndarray:
    n = min(int(overlap_s * sr), loop_len // 4, raw.shape[0] - loop_len)
    if n <= 0:
        return raw[:loop_len]
    head = raw[:n]
    cont = raw[loop_len : loop_len + n]
    t = np.linspace(0, np.pi / 2, n)
    blended = head * np.cos(t)[:, None] + cont * np.sin(t)[:, None]
    out = raw[:loop_len].copy()
    out[:n] = blended.astype(np.float32)
    return out


def tile_to_length(
    loop: np.ndarray, sr: int, seconds: float, overlap_s: float = 0.15
) -> np.ndarray:
    """Repeat a loop out to at least `seconds`, crossfading each repeat so
    the seam that isn't already the loop's own wraparound is smooth too."""
    target_n = int(seconds * sr)
    if loop.shape[0] == 0:
        return loop
    out = loop.copy()
    while out.shape[0] < target_n:
        out = dsp.crossfade_concat(out, loop, sr, overlap_s)
    return out[:target_n]


def crossfade_moods(
    a: np.ndarray, b: np.ndarray, sr: int, overlap_s: float = 1.5
) -> np.ndarray:
    return dsp.crossfade_concat(a, b, sr, overlap_s)
