"""
Audio analysis -> a per-frame feature track.

Decodes the audio with ffmpeg to mono float PCM, then computes, for every
output video frame:

    energy      RMS loudness, 0..1 (normalised over the track)
    sub         sub-bass energy (20-90 Hz), 0..1
    bands       N log-spaced frequency-band magnitudes, 0..1 each
    centroid    spectral centroid, 0..1 (brightness)
    onset       spectral-flux onset strength, 0..1
    beat        bool, a debounced peak in the onset signal

The band split + one-pole envelope + peak-picking are ported from Arcade's
`AudioReactive` and `Downbeat.onsets` (apps/arcade/static/index.html). No
librosa / scipy -- numpy's rfft is enough.
"""

import hashlib
import subprocess

import numpy as np

from .config import ffmpeg_caps

SR = 22050  # analysis sample rate -- plenty for music features, cheap
N_BANDS = 12
_FFT = 2048


def audio_fingerprint(path, fps):
    h = hashlib.sha1()
    h.update(str(path).encode())
    try:
        st = __import__("os").stat(path)
        h.update(f"{st.st_size}:{int(st.st_mtime)}:{fps}".encode())
    except OSError:
        h.update(f"?:{fps}".encode())
    return h.hexdigest()[:16]


def _decode_pcm(path):
    ff = ffmpeg_caps()
    if not ff["ffmpeg"]:
        raise RuntimeError("ffmpeg not found on PATH")
    cmd = [
        ff["ffmpeg"],
        "-v",
        "error",
        "-i",
        str(path),
        "-ac",
        "1",
        "-ar",
        str(SR),
        "-f",
        "f32le",
        "-",
    ]
    raw = subprocess.run(cmd, capture_output=True, timeout=600).stdout
    if not raw:
        raise RuntimeError(f"ffmpeg produced no audio for {path}")
    return np.frombuffer(raw, dtype=np.float32)


def _log_band_edges(n, lo=40.0, hi=SR / 2):
    return np.geomspace(lo, hi, n + 1)


def _norm(x, p=99.0):
    """Scale so the p-th percentile maps to ~1.0, then soft-clip to [0, 1]."""
    x = np.nan_to_num(np.asarray(x, dtype=np.float64))
    ref = np.percentile(x, p) if x.size else 1.0
    if ref <= 1e-9:
        return np.zeros_like(x)
    y = x / ref
    return np.clip(y, 0.0, 1.0)


def analyze(path, fps, duration=None, progress=None):
    """Return a dict of 1-D arrays (and `bands` as (frames, N_BANDS))."""
    pcm = _decode_pcm(path)
    total = len(pcm) / SR
    if duration:
        total = min(total, duration)
    n_frames = max(1, int(round(total * fps)))

    hop = SR / fps
    win = np.hanning(_FFT).astype(np.float32)
    freqs = np.fft.rfftfreq(_FFT, 1.0 / SR)
    edges = _log_band_edges(N_BANDS)
    band_idx = [
        np.where((freqs >= edges[b]) & (freqs < edges[b + 1]))[0]
        for b in range(N_BANDS)
    ]
    sub_idx = np.where((freqs >= 20) & (freqs < 90))[0]

    energy = np.zeros(n_frames)
    sub = np.zeros(n_frames)
    centroid = np.zeros(n_frames)
    bands = np.zeros((n_frames, N_BANDS))
    flux = np.zeros(n_frames)
    prev_mag = None

    for i in range(n_frames):
        start = int(i * hop)
        seg = pcm[start : start + _FFT]
        if len(seg) < _FFT:
            seg = np.pad(seg, (0, _FFT - len(seg)))
        energy[i] = np.sqrt(np.mean(seg.astype(np.float64) ** 2))
        spec = np.abs(np.fft.rfft(seg * win))
        if spec.sum() > 1e-9:
            centroid[i] = float(np.sum(freqs * spec) / np.sum(spec))
        sub[i] = spec[sub_idx].mean() if sub_idx.size else 0.0
        for b, idx in enumerate(band_idx):
            bands[i, b] = spec[idx].mean() if idx.size else 0.0
        if prev_mag is not None:
            flux[i] = np.sum(np.maximum(spec - prev_mag, 0.0))
        prev_mag = spec
        if progress and (i % 128 == 0):
            progress(i / n_frames)

    # --- normalise ---
    energy = _norm(energy)
    sub = _norm(sub)
    centroid = np.clip(centroid / (SR / 2) * 4.0, 0.0, 1.0)  # brightness, expanded
    for b in range(N_BANDS):
        bands[:, b] = _norm(bands[:, b])
    onset = _norm(flux, p=95.0)

    # --- beat picking: one-pole smoothed onset, local-max above rolling mean ---
    beat = np.zeros(n_frames, dtype=bool)
    env = np.zeros(n_frames)
    a = 0.35
    for i in range(1, n_frames):
        env[i] = a * onset[i] + (1 - a) * env[i - 1]
    w = max(3, int(fps * 0.4))
    last = -w
    for i in range(1, n_frames - 1):
        lo = max(0, i - w)
        local_mean = env[lo : i + w].mean() if i + w <= n_frames else env[lo:].mean()
        if (
            env[i] > local_mean * 1.4 + 0.04
            and env[i] >= env[i - 1]
            and env[i] >= env[i + 1]
            and i - last >= int(fps * 0.18)
        ):
            beat[i] = True
            last = i
    if progress:
        progress(1.0)

    return {
        "fps": float(fps),
        "n_frames": int(n_frames),
        "duration": float(total),
        "energy": energy,
        "sub": sub,
        "centroid": centroid,
        "bands": bands,
        "onset": onset,
        "beat": beat,
    }


def save_features(path, feats):
    np.savez_compressed(path, **feats)


def load_features(path):
    d = np.load(path, allow_pickle=False)
    return {k: d[k] for k in d.files}
