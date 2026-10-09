"""Audio analysis on synthetic signals with known answers."""

import os
import subprocess
import tempfile

import numpy as np
import pytest

from pulseforge import analyze
from pulseforge.config import ffmpeg_caps

pytestmark = pytest.mark.skipif(not ffmpeg_caps()["ffmpeg"], reason="ffmpeg required")


def _write_wav(samples, sr, path):
    """samples: float32 in [-1,1] mono -> wav via ffmpeg from raw f32le."""
    raw = np.asarray(samples, dtype=np.float32).tobytes()
    subprocess.run(
        [
            ffmpeg_caps()["ffmpeg"],
            "-v",
            "error",
            "-y",
            "-f",
            "f32le",
            "-ar",
            str(sr),
            "-ac",
            "1",
            "-i",
            "pipe:0",
            path,
        ],
        input=raw,
        check=True,
    )


def test_sine_energy_in_expected_band(tmp_path):
    sr = 44100
    dur = 3.0
    t = np.arange(int(sr * dur)) / sr
    tone = 0.6 * np.sin(2 * np.pi * 440 * t)
    wav = str(tmp_path / "sine.wav")
    _write_wav(tone, sr, wav)

    feat = analyze.analyze(wav, fps=30)
    bands = feat["bands"]
    assert feat["n_frames"] == pytest.approx(90, abs=2)
    # 440 Hz should light one band far more than the DC-ish and the very-high ones
    mean_bands = bands.mean(axis=0)
    peak = int(np.argmax(mean_bands))
    edges = analyze._log_band_edges(analyze.N_BANDS)
    assert edges[peak] <= 440 <= edges[peak + 1] * 1.6
    assert mean_bands[peak] > mean_bands[0] * 2
    assert mean_bands[peak] > mean_bands[-1] * 2


def test_click_track_produces_beats(tmp_path):
    sr = 44100
    bpm = 120
    dur = 8.0
    n = int(sr * dur)
    sig = np.zeros(n, dtype=np.float32)
    step = int(sr * 60 / bpm)
    click_positions = list(range(0, n - 200, step))
    for p in click_positions:
        sig[p : p + 200] = np.hanning(200) * 0.9
    wav = str(tmp_path / "click.wav")
    _write_wav(sig, sr, wav)

    feat = analyze.analyze(wav, fps=30)
    beats = int(feat["beat"].sum())
    # 120 bpm over 8s = 16 beats; allow generous slack for edge effects
    assert 10 <= beats <= 20, f"expected ~16 beats, got {beats}"


def test_features_cache_roundtrip(tmp_path):
    sr = 22050
    sig = (0.3 * np.sin(2 * np.pi * 200 * np.arange(sr) / sr)).astype(np.float32)
    wav = str(tmp_path / "s.wav")
    _write_wav(sig, sr, wav)
    feat = analyze.analyze(wav, fps=24)
    p = str(tmp_path / "f.npz")
    analyze.save_features(p, feat)
    back = analyze.load_features(p)
    assert back["n_frames"] == feat["n_frames"]
    assert np.allclose(back["bands"], feat["bands"])
    assert back["beat"].dtype == feat["beat"].dtype
