"""Small numpy DSP toolkit shared by TTS emotion FX, SFX synthesis, music and
the final mix. Audio is float32 in roughly [-1, 1]; mono is a 1-D array,
stereo is (n, 2). No per-sample Python loops -- everything is vectorised so a
whole music track filters in milliseconds.

The whole pipeline standardises on 48 kHz (CONTRACTS.md: "48 kHz stereo").
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

SR = 48000


def resample(x: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
    """Linear-interpolation resample. Good enough for speech/SFX/music at
    these rates; not used in any tight loop."""
    if src_sr == dst_sr or len(x) == 0:
        return x.astype(np.float32)
    n = max(1, round(len(x) * dst_sr / src_sr))
    xp = np.arange(len(x))
    fp_new = np.linspace(0, len(x) - 1, n)
    if x.ndim == 1:
        return np.interp(fp_new, xp, x).astype(np.float32)
    return np.stack(
        [np.interp(fp_new, xp, x[:, c]) for c in range(x.shape[1])], axis=1
    ).astype(np.float32)


def to_mono(x: np.ndarray) -> np.ndarray:
    if x.ndim == 1:
        return x.astype(np.float32)
    return x.mean(axis=1).astype(np.float32)


def to_stereo(x: np.ndarray) -> np.ndarray:
    if x.ndim == 2:
        return x.astype(np.float32)
    return np.stack([x, x], axis=1).astype(np.float32)


def gain_db(x: np.ndarray, db: float) -> np.ndarray:
    if db == 0:
        return x.astype(np.float32)
    return (x * (10.0 ** (db / 20.0))).astype(np.float32)


def peak(x: np.ndarray) -> float:
    if x.size == 0:
        return 0.0
    return float(np.max(np.abs(x)))


def lowpass(x: np.ndarray, sr: int, cutoff_hz: float) -> np.ndarray:
    """Gentle brick-wall-ish low-pass done in the frequency domain (zero-phase,
    fully vectorised): rfft, taper bins above cutoff, irfft back."""
    if x.size == 0:
        return x.astype(np.float32)
    mono = x.ndim == 1
    chans = [x] if mono else [x[:, c] for c in range(x.shape[1])]
    out = []
    n = chans[0].shape[0]
    freqs = np.fft.rfftfreq(n, d=1.0 / sr)
    # half-cosine taper from cutoff to 1.5x cutoff instead of a hard cut,
    # so it sounds like a soft filter rather than ringing.
    edge = max(cutoff_hz * 1.5, cutoff_hz + 50)
    mask = np.ones_like(freqs)
    taper = (freqs > cutoff_hz) & (freqs < edge)
    mask[taper] = 0.5 * (
        1 + np.cos(np.pi * (freqs[taper] - cutoff_hz) / (edge - cutoff_hz))
    )
    mask[freqs >= edge] = 0.0
    for ch in chans:
        spec = np.fft.rfft(ch)
        out.append(np.fft.irfft(spec * mask, n=n).astype(np.float32))
    return out[0] if mono else np.stack(out, axis=1)


def pre_emphasis_lift(x: np.ndarray, amount: float = 0.25) -> np.ndarray:
    """A small high-shelf brightening used as a stand-in for a true pitch
    lift on '?' lines. Kokoro has no pitch knob (see NovelForge's adapter),
    and a real time-preserving pitch shift needs a phase vocoder we don't
    have budget for here, so this approximates the perceptual "lift" with
    brightness instead: y[n] = x[n] - amount * x[n-1]."""
    if x.size == 0:
        return x.astype(np.float32)
    if x.ndim == 1:
        y = np.empty_like(x)
        y[0] = x[0]
        y[1:] = x[1:] - amount * x[:-1]
        return y.astype(np.float32)
    y = np.empty_like(x)
    y[0, :] = x[0, :]
    y[1:, :] = x[1:, :] - amount * x[:-1, :]
    return y.astype(np.float32)


def echo(
    x: np.ndarray, sr: int, delay_s: float = 0.09, decay: float = 0.35, taps: int = 3
) -> np.ndarray:
    """Shift-and-add echo/slight reverb, vectorised (no per-sample loop)."""
    if x.size == 0:
        return x.astype(np.float32)
    y = x.astype(np.float32).copy()
    d = int(delay_s * sr)
    for i in range(1, taps + 1):
        off = d * i
        if off >= x.shape[0]:
            break
        amp = decay**i
        if x.ndim == 1:
            y[off:] += x[:-off] * amp
        else:
            y[off:, :] += x[:-off, :] * amp
    return y


def fade(x: np.ndarray, sr: int, in_s: float = 0.0, out_s: float = 0.0) -> np.ndarray:
    y = x.astype(np.float32).copy()
    n = y.shape[0]
    ni = min(n, int(in_s * sr))
    no = min(n, int(out_s * sr))
    if ni > 0:
        ramp = np.linspace(0, 1, ni)
        if y.ndim == 1:
            y[:ni] *= ramp
        else:
            y[:ni] *= ramp[:, None]
    if no > 0:
        ramp = np.linspace(1, 0, no)
        if y.ndim == 1:
            y[n - no :] *= ramp
        else:
            y[n - no :] *= ramp[:, None]
    return y


def limiter(x: np.ndarray, ceiling: float = 0.98) -> np.ndarray:
    """Soft-knee peak limiter: tanh soft-clip scaled to a ceiling, so a mix
    that peaks over 1.0 never hard-clips."""
    if x.size == 0:
        return x.astype(np.float32)
    pk = peak(x)
    if pk <= ceiling:
        return x.astype(np.float32)
    return (np.tanh(x / pk * 1.4) * ceiling).astype(np.float32)


def mix_into(buf: np.ndarray, clip: np.ndarray, start_sample: int) -> None:
    """Add `clip` (stereo) into `buf` (stereo) at start_sample, in place,
    clipping/padding to buf's length."""
    n = clip.shape[0]
    end = start_sample + n
    if end <= 0 or start_sample >= buf.shape[0]:
        return
    src0 = max(0, -start_sample)
    dst0 = max(0, start_sample)
    dst1 = min(buf.shape[0], end)
    src1 = src0 + (dst1 - dst0)
    if dst1 <= dst0:
        return
    buf[dst0:dst1] += clip[src0:src1]


def duck(
    buf: np.ndarray,
    sr: int,
    regions: list[tuple[float, float]],
    amount_db: float = -10.0,
    edge_s: float = 0.12,
) -> np.ndarray:
    """Sidechain-style ducking: attenuate `buf` under the given [start,end]
    second regions (e.g. voice lines), with a short ramp in/out."""
    if not regions or buf.size == 0:
        return buf
    n = buf.shape[0]
    env = np.ones(n, dtype=np.float32)
    target = 10.0 ** (amount_db / 20.0)
    edge_n = max(1, int(edge_s * sr))
    for start, dur in regions:
        s = max(0, int(start * sr))
        e = min(n, int((start + dur) * sr))
        if e <= s:
            continue
        env[s:e] = np.minimum(env[s:e], target)
        # ramp down into the region, ramp up out of it
        r0 = max(0, s - edge_n)
        if s > r0:
            ramp = np.linspace(1.0, target, s - r0)
            env[r0:s] = np.minimum(env[r0:s], ramp)
        r1 = min(n, e + edge_n)
        if r1 > e:
            ramp = np.linspace(target, 1.0, r1 - e)
            env[e:r1] = np.minimum(env[e:r1], ramp)
    if buf.ndim == 2:
        return (buf * env[:, None]).astype(np.float32)
    return (buf * env).astype(np.float32)


def crossfade_concat(
    a: np.ndarray, b: np.ndarray, sr: int, overlap_s: float
) -> np.ndarray:
    """Concatenate two stereo clips with an equal-power crossfade."""
    n = min(int(overlap_s * sr), a.shape[0], b.shape[0])
    if n <= 0:
        return np.concatenate([a, b], axis=0)
    t = np.linspace(0, np.pi / 2, n)
    fout, fin = np.cos(t), np.sin(t)
    head = a[: a.shape[0] - n]
    mid = a[a.shape[0] - n :] * fout[:, None] + b[:n] * fin[:, None]
    tail = b[n:]
    return np.concatenate([head, mid.astype(np.float32), tail], axis=0)


def write_wav(path: Path, x: np.ndarray, sr: int = SR) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    x = to_stereo(x) if x.ndim == 1 else x.astype(np.float32)
    ints = np.clip(x, -1.0, 1.0)
    ints = (ints * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(ints.shape[1] if ints.ndim == 2 else 1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(ints.tobytes())


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as w:
        sr = w.getframerate()
        ch = w.getnchannels()
        n = w.getnframes()
        raw = w.readframes(n)
    arr = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32767.0
    if ch > 1:
        arr = arr.reshape(-1, ch)
    return arr, sr


# ------------------------------------------------------ voice-acting FX --#
# Every function below is pure: float32 in, float32 out, same shape, mono or
# (n, 2) stereo, and the identity when its amount is 0 so a neutral line is
# bit-identical to what it was before these existed. Levels never exceed the
# input peak (or 1.0 for additive effects), so nothing here clips; the
# limiter downstream stays a safety net rather than a tone control.


def _per_channel(fn, x: np.ndarray) -> np.ndarray:
    if x.ndim == 1:
        return fn(x.astype(np.float32)).astype(np.float32)
    return np.stack(
        [fn(x[:, c].astype(np.float32)) for c in range(x.shape[1])], axis=1
    ).astype(np.float32)


def _cap_peak(y: np.ndarray, ceiling: float) -> np.ndarray:
    pk = peak(y)
    if pk > ceiling > 0:
        y = y * (ceiling / pk)
    return y.astype(np.float32)


def _fft_mask(x: np.ndarray, sr: int, lo_hz: float | None, hi_hz: float | None):
    """Zero-phase band shaping in the frequency domain with raised-cosine
    edges (half an octave wide) instead of hard cuts."""
    n = x.shape[0]
    freqs = np.fft.rfftfreq(n, d=1.0 / sr)
    mask = np.ones_like(freqs)
    if lo_hz:
        lo_edge = lo_hz * 0.7
        ramp = (freqs > lo_edge) & (freqs < lo_hz)
        mask[freqs <= lo_edge] = 0.0
        mask[ramp] = 0.5 * (
            1 - np.cos(np.pi * (freqs[ramp] - lo_edge) / (lo_hz - lo_edge))
        )
    if hi_hz:
        hi_edge = hi_hz * 1.4
        ramp = (freqs > hi_hz) & (freqs < hi_edge)
        mask[freqs >= hi_edge] = 0.0
        mask[ramp] = np.minimum(
            mask[ramp],
            0.5 * (1 + np.cos(np.pi * (freqs[ramp] - hi_hz) / (hi_edge - hi_hz))),
        )
    return np.fft.irfft(np.fft.rfft(x) * mask, n=n).astype(np.float32)


def bandpass(x: np.ndarray, sr: int, lo_hz: float, hi_hz: float) -> np.ndarray:
    if x.size == 0:
        return x.astype(np.float32)
    return _per_channel(lambda ch: _fft_mask(ch, sr, lo_hz, hi_hz), x)


# -- phase vocoder -----------------------------------------------------------
_N_FFT = 2048
_HOP = 512


def _hann(n: int) -> np.ndarray:
    return np.hanning(n + 1)[:-1].astype(np.float32)


def _stft(x: np.ndarray) -> np.ndarray:
    win = _hann(_N_FFT)
    pad = _N_FFT // 2
    xp = np.pad(x, (pad, pad + _N_FFT))
    n_frames = 1 + (len(xp) - _N_FFT) // _HOP
    idx = np.arange(_N_FFT)[None, :] + _HOP * np.arange(n_frames)[:, None]
    return np.fft.rfft(xp[idx] * win, axis=1)


def _istft(spec: np.ndarray, length: int) -> np.ndarray:
    win = _hann(_N_FFT)
    frames = np.fft.irfft(spec, n=_N_FFT, axis=1) * win
    n_frames = spec.shape[0]
    out_len = _N_FFT + _HOP * (n_frames - 1)
    y = np.zeros(out_len, dtype=np.float64)
    wsum = np.zeros(out_len, dtype=np.float64)
    idx = np.arange(_N_FFT)[None, :] + _HOP * np.arange(n_frames)[:, None]
    np.add.at(y, idx, frames)
    np.add.at(wsum, idx, np.broadcast_to(win**2, frames.shape))
    y = y / np.maximum(wsum, 1e-6)
    pad = _N_FFT // 2
    out = y[pad : pad + length]
    if out.shape[0] < length:
        out = np.pad(out, (0, length - out.shape[0]))
    return out.astype(np.float32)


def _stretch_mono(x: np.ndarray, rate: float) -> np.ndarray:
    """Phase-vocoder time stretch: output is len(x)/rate samples at the same
    pitch. Fully vectorised (phase accumulation is a cumsum over frames)."""
    n_out = max(1, round(len(x) / rate))
    if len(x) < _N_FFT:
        # too short for a frame: plain interpolation is inaudible at this size
        return np.interp(
            np.linspace(0, len(x) - 1, n_out), np.arange(len(x)), x
        ).astype(np.float32)
    spec = _stft(x)
    n_frames = spec.shape[0]
    steps = np.arange(0.0, n_frames - 1, rate)
    lo = np.floor(steps).astype(int)
    hi = np.minimum(lo + 1, n_frames - 1)
    frac = (steps - lo)[:, None]
    mag = (1 - frac) * np.abs(spec[lo]) + frac * np.abs(spec[hi])
    expected = (2 * np.pi * _HOP / _N_FFT) * np.arange(spec.shape[1])[None, :]
    dev = np.angle(spec[hi]) - np.angle(spec[lo]) - expected
    dev = dev - 2 * np.pi * np.round(dev / (2 * np.pi))
    advance = expected + dev
    phase = np.empty_like(advance)
    phase[0] = np.angle(spec[0])
    if advance.shape[0] > 1:
        phase[1:] = phase[0] + np.cumsum(advance[:-1], axis=0)
    y = _istft(mag * np.exp(1j * phase), n_out)
    return y


def time_stretch(x: np.ndarray, sr: int, rate: float) -> np.ndarray:
    """Same pitch, different length: rate 2.0 is twice as fast (half as long)."""
    if x.size == 0 or rate == 1.0:
        return x.astype(np.float32)
    return _per_channel(lambda ch: _stretch_mono(ch, rate), x)


def pitch_shift(x: np.ndarray, sr: int, semitones: float) -> np.ndarray:
    """Time-preserving pitch shift: stretch by the ratio with the phase
    vocoder, then resample back to the original length."""
    if x.size == 0 or semitones == 0.0:
        return x.astype(np.float32)
    ratio = 2.0 ** (semitones / 12.0)
    n = x.shape[0]

    def one(ch: np.ndarray) -> np.ndarray:
        stretched = _stretch_mono(ch, 1.0 / ratio)
        y = np.interp(
            np.linspace(0, len(stretched) - 1, n), np.arange(len(stretched)), stretched
        )
        return y.astype(np.float32)

    y = _per_channel(one, x)
    return _cap_peak(y, max(peak(x), 1e-6))


# -- modulation and colour ---------------------------------------------------
def tremolo(x: np.ndarray, sr: int, depth: float, rate_hz: float = 6.5) -> np.ndarray:
    """Fear/weakness: amplitude wobble at a slightly unsteady rate. depth 1
    dips all the way to silence; 0.3 is a nervous flutter."""
    if x.size == 0 or depth <= 0:
        return x.astype(np.float32)
    depth = min(1.0, depth)
    t = np.arange(x.shape[0]) / sr
    inst_rate = rate_hz * (1 + 0.12 * np.sin(2 * np.pi * 0.7 * t))
    phase = 2 * np.pi * np.cumsum(inst_rate) / sr
    env = (1 - depth * 0.5 * (1 - np.cos(phase))).astype(np.float32)
    if x.ndim == 2:
        env = env[:, None]
    return (x * env).astype(np.float32)


def grit(x: np.ndarray, amount: float) -> np.ndarray:
    """Shouting: tanh soft clip mixed in by amount, renormalised so the peak
    never rises above the input's (loudness is the gain's job)."""
    if x.size == 0 or amount <= 0:
        return x.astype(np.float32)
    amount = min(1.0, amount)
    pk = max(peak(x), 1e-6)
    drive = 1.0 + 6.0 * amount
    clipped = np.tanh(x / pk * drive) / np.tanh(drive) * pk
    y = (1 - amount) * x + amount * clipped
    return _cap_peak(y.astype(np.float32), pk)


def _envelope(x: np.ndarray, sr: int, window_s: float = 0.006) -> np.ndarray:
    n = max(1, int(window_s * sr))
    kernel = np.ones(n, dtype=np.float32) / n
    return np.convolve(np.abs(x), kernel, mode="same").astype(np.float32)


def breath(x: np.ndarray, sr: int, amount: float, seed: int = 1234) -> np.ndarray:
    """Whisper/sadness: band-limited noise shaped by the voice's own envelope,
    so it only breathes while the voice is sounding. Deterministic (seeded)
    so the audio cache stays valid."""
    if x.size == 0 or amount <= 0:
        return x.astype(np.float32)
    amount = min(1.0, amount)
    rng = np.random.default_rng(seed)

    def one(ch: np.ndarray) -> np.ndarray:
        noise = rng.uniform(-1.0, 1.0, ch.shape[0]).astype(np.float32)
        noise = _fft_mask(noise, sr, 1500.0, 8000.0)
        env = _envelope(ch, sr)
        return (ch + noise * env * (1.2 * amount)).astype(np.float32)

    y = _per_channel(one, x)
    return _cap_peak(y, 1.0)


# -- rooms -------------------------------------------------------------------
# Registry of acoustic spaces (CONTRACTS.md scene.json `acoustics.space`).
# early_ms: discrete reflections; t60: tail decay time at size 1; wet: wet
# gain at amount 1; damp_hz: tail low-pass. Adding a space is one entry here.
ROOMS: dict[str, dict] = {
    "small-room": {
        "early_ms": [7, 11, 17, 23],
        "t60": 0.28,
        "wet": 0.18,
        "damp_hz": 6000,
    },
    "hall": {
        "early_ms": [19, 31, 47, 67, 89],
        "t60": 1.7,
        "wet": 0.35,
        "damp_hz": 4500,
    },
    "outdoor": {"early_ms": [53], "t60": 0.0, "wet": 0.06, "damp_hz": 8000},
    "vehicle": {"early_ms": [3, 5, 8], "t60": 0.09, "wet": 0.15, "damp_hz": 2500},
    "comms": {"early_ms": [], "t60": 0.0, "wet": 0.0, "damp_hz": 3400},
    "void": {"early_ms": [40, 90, 150], "t60": 2.4, "wet": 0.45, "damp_hz": 3000},
}


def _impulse_response(sr: int, room: dict, amount: float, seed: int = 99) -> np.ndarray:
    t60 = room["t60"] * (0.5 + 0.5 * amount)
    early = [int(ms * sr / 1000) for ms in room["early_ms"]]
    n_tail = int(t60 * sr)
    n = max(max(early, default=0) + 1, n_tail, 1)
    ir = np.zeros(n, dtype=np.float32)
    for i, off in enumerate(early):
        ir[off] += 0.7 * (0.75**i)
    if n_tail > 1:
        rng = np.random.default_rng(seed)
        t = np.arange(n_tail) / sr
        tail = rng.uniform(-1, 1, n_tail).astype(np.float32) * np.exp(-6.9 * t / t60)
        tail = _fft_mask(tail, sr, None, room["damp_hz"])
        ir[:n_tail] += 0.35 * tail
    return ir


def _fft_convolve(x: np.ndarray, ir: np.ndarray) -> np.ndarray:
    n = x.shape[0] + ir.shape[0] - 1
    size = 1 << (n - 1).bit_length()
    y = np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(ir, size), size)
    return y[: x.shape[0]].astype(np.float32)


def room_reverb(x: np.ndarray, sr: int, space: str | None, amount: float) -> np.ndarray:
    """Convolution reverb with a synthetic impulse response for the panel's
    acoustic space. amount (0..1) scales both wet level and tail length; an
    unknown space or amount 0 is dry."""
    room = ROOMS.get(space or "")
    if x.size == 0 or amount <= 0 or room is None or room["wet"] <= 0:
        return x.astype(np.float32)
    amount = min(1.0, amount)
    ir = _impulse_response(sr, room, amount)
    wet_gain = room["wet"] * amount

    def one(ch: np.ndarray) -> np.ndarray:
        return (ch + wet_gain * _fft_convolve(ch, ir)).astype(np.float32)

    return _cap_peak(_per_channel(one, x), 0.98)


def radio_eq(x: np.ndarray, sr: int, amount: float) -> np.ndarray:
    """Comms: 300-3400 Hz band-pass with a touch of grit, mixed in by amount."""
    if x.size == 0 or amount <= 0:
        return x.astype(np.float32)
    amount = min(1.0, amount)
    wet = grit(bandpass(x, sr, 300.0, 3400.0), 0.35)
    y = (1 - amount) * x + amount * wet
    return _cap_peak(y.astype(np.float32), max(peak(x), 1e-6))


def void_voice(x: np.ndarray, sr: int, amount: float) -> np.ndarray:
    """Inner voice for thought bubbles and the `void` space: darker, with a
    long soft tail, mixed in by amount."""
    if x.size == 0 or amount <= 0:
        return x.astype(np.float32)
    amount = min(1.0, amount)
    wet = room_reverb(lowpass(x, sr, 3400.0), sr, "void", amount)
    y = (1 - amount) * x + amount * wet
    return _cap_peak(y.astype(np.float32), 0.98)


def join_crossfade(segments: list[np.ndarray], sr: int, overlap_s: float) -> np.ndarray:
    """Concatenate mono (or stereo) clips with short linear crossfades;
    used to join per-segment syntheses (bold-word emphasis)."""
    segs = [s.astype(np.float32) for s in segments if s.size > 0]
    if not segs:
        return np.zeros(0, dtype=np.float32)
    out = segs[0]
    for nxt in segs[1:]:
        n = min(int(overlap_s * sr), out.shape[0], nxt.shape[0])
        if n <= 0:
            out = np.concatenate([out, nxt], axis=0)
            continue
        # linear (not equal-power): the weights sum to 1, so joining two
        # correlated segments can never exceed the louder one's peak.
        fin = np.linspace(0.0, 1.0, n, dtype=np.float32)
        fout = 1.0 - fin
        if out.ndim == 2:
            fout, fin = fout[:, None], fin[:, None]
        mid = out[out.shape[0] - n :] * fout + nxt[:n] * fin
        out = np.concatenate(
            [out[: out.shape[0] - n], mid.astype(np.float32), nxt[n:]], axis=0
        )
    return out.astype(np.float32)
