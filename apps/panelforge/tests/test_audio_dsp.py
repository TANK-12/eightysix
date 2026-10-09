"""Voice-acting DSP effects (panelforge/audio/dsp.py): every effect is a pure
function on float32 arrays that preserves length, never clips a sane input,
and is the identity at amount 0 so a neutral line sounds the same as before.
No model load required."""

import numpy as np
import pytest

from panelforge.audio import dsp

SR = 48000


def _sine(freq: float, seconds: float = 1.0, amp: float = 0.8, sr: int = SR):
    t = np.arange(int(sr * seconds)) / sr
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def _voice_like(sr: int = SR):
    """A rough voiced signal: a 160 Hz pulse train with a few harmonics and
    an on/off envelope, so envelope-based effects have something to follow."""
    t = np.arange(int(sr * 1.0)) / sr
    x = np.zeros_like(t)
    for h in range(1, 8):
        x += np.sin(2 * np.pi * 160 * h * t) / h
    env = (np.sin(2 * np.pi * 3 * t) > 0).astype(np.float32)
    return (0.6 * x / np.max(np.abs(x)) * env).astype(np.float32)


def _peak_freq(x: np.ndarray, sr: int) -> float:
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    return float(np.fft.rfftfreq(len(x), 1 / sr)[np.argmax(spec)])


def _sane(y: np.ndarray, x: np.ndarray):
    assert y.dtype == np.float32
    assert y.shape == x.shape
    assert np.all(np.isfinite(y))
    assert dsp.peak(y) <= 1.0


EFFECTS_IDENTITY_AT_ZERO = [
    ("pitch_shift", lambda x: dsp.pitch_shift(x, SR, 0.0)),
    ("tremolo", lambda x: dsp.tremolo(x, SR, 0.0)),
    ("grit", lambda x: dsp.grit(x, 0.0)),
    ("breath", lambda x: dsp.breath(x, SR, 0.0)),
    ("room_reverb", lambda x: dsp.room_reverb(x, SR, "hall", 0.0)),
    ("radio_eq", lambda x: dsp.radio_eq(x, SR, 0.0)),
    ("void_voice", lambda x: dsp.void_voice(x, SR, 0.0)),
]


@pytest.mark.parametrize("name,fn", EFFECTS_IDENTITY_AT_ZERO)
def test_identity_at_zero(name, fn):
    x = _voice_like()
    y = fn(x)
    _sane(y, x)
    assert np.array_equal(y, x), f"{name} at amount 0 must not touch the signal"


EFFECTS_ACTIVE = [
    ("pitch_shift", lambda x: dsp.pitch_shift(x, SR, 3.0)),
    ("tremolo", lambda x: dsp.tremolo(x, SR, 0.6)),
    ("grit", lambda x: dsp.grit(x, 0.8)),
    ("breath", lambda x: dsp.breath(x, SR, 0.7)),
    ("room small", lambda x: dsp.room_reverb(x, SR, "small-room", 0.5)),
    ("room hall", lambda x: dsp.room_reverb(x, SR, "hall", 1.0)),
    ("room vehicle", lambda x: dsp.room_reverb(x, SR, "vehicle", 0.5)),
    ("radio_eq", lambda x: dsp.radio_eq(x, SR, 1.0)),
    ("void_voice", lambda x: dsp.void_voice(x, SR, 1.0)),
]


@pytest.mark.parametrize("name,fn", EFFECTS_ACTIVE)
def test_active_effect_changes_signal_without_clipping(name, fn):
    x = _voice_like()
    y = fn(x)
    _sane(y, x)
    assert not np.array_equal(y, x), f"{name} did nothing"


@pytest.mark.parametrize("name,fn", EFFECTS_ACTIVE)
def test_effects_handle_empty_and_stereo(name, fn):
    empty = np.zeros(0, dtype=np.float32)
    assert fn(empty).shape == (0,)
    st = np.stack([_voice_like(), _voice_like() * 0.5], axis=1)
    y = fn(st)
    assert y.shape == st.shape
    assert np.all(np.isfinite(y))


@pytest.mark.parametrize(
    "semitones,expected", [(12.0, 880.0), (-12.0, 220.0), (5.0, 587.3)]
)
def test_pitch_shift_moves_spectral_peak(semitones, expected):
    x = _sine(440.0)
    y = dsp.pitch_shift(x, SR, semitones)
    assert y.shape == x.shape
    f = _peak_freq(y[SR // 10 : -SR // 10], SR)
    assert abs(f - expected) / expected < 0.03, f"peak at {f:.1f} Hz, wanted {expected}"


def test_pitch_shift_is_time_preserving_and_bounded():
    x = _voice_like()
    for st in (-4.0, -1.0, 1.0, 4.0):
        y = dsp.pitch_shift(x, SR, st)
        assert y.shape == x.shape
        assert dsp.peak(y) <= 1.0


def test_tremolo_modulates_amplitude():
    x = _sine(440.0, amp=0.5)
    y = dsp.tremolo(x, SR, 1.0, rate_hz=5.0)
    # 5 Hz over one second: the envelope dips to near zero several times
    env = np.abs(y).reshape(50, -1).max(axis=1)
    assert env.min() < 0.1 and env.max() > 0.45
    assert dsp.peak(y) <= dsp.peak(x) + 1e-6


def test_grit_flattens_peaks_but_keeps_level():
    x = _sine(200.0, amp=0.8)
    y = dsp.grit(x, 1.0)
    assert dsp.peak(y) <= dsp.peak(x) + 1e-6
    # soft clipping raises the crest-to-rms ratio toward a square wave
    assert np.sqrt(np.mean(y**2)) > np.sqrt(np.mean(x**2))


def test_breath_is_gated_by_the_voice_envelope():
    silence = np.zeros(SR, dtype=np.float32)
    assert dsp.peak(dsp.breath(silence, SR, 1.0)) == 0.0
    x = _voice_like()
    y = dsp.breath(x, SR, 1.0)
    # where the voice is off (10 ms clear of a transition, past the
    # envelope follower's window), breath noise stays off
    off = np.abs(x) < 1e-6
    edge = int(0.010 * SR)
    for k in range(1, edge + 1):
        off &= np.roll(np.abs(x) < 1e-6, k) & np.roll(np.abs(x) < 1e-6, -k)
    assert off.sum() > SR // 4
    assert dsp.peak(y[off]) < 0.02


def test_room_reverb_adds_a_tail_sized_by_space():
    click = np.zeros(SR, dtype=np.float32)
    click[1000] = 0.8
    tail = slice(SR // 2, SR)
    dry = float(np.sum(click[tail] ** 2))
    small = float(np.sum(dsp.room_reverb(click, SR, "small-room", 1.0)[tail] ** 2))
    hall = float(np.sum(dsp.room_reverb(click, SR, "hall", 1.0)[tail] ** 2))
    outdoor = float(np.sum(dsp.room_reverb(click, SR, "outdoor", 1.0)[tail] ** 2))
    assert dry == 0.0
    assert hall > small
    assert outdoor <= small
    # bigger size means more tail
    half = float(np.sum(dsp.room_reverb(click, SR, "hall", 0.4)[tail] ** 2))
    assert hall > half


def test_room_reverb_unknown_space_is_dry():
    x = _voice_like()
    assert np.array_equal(dsp.room_reverb(x, SR, "nowhere", 1.0), x)


def test_radio_eq_is_a_voice_band_pass():
    lo = _sine(100.0, amp=0.4)
    mid = _sine(1000.0, amp=0.4)
    y = dsp.radio_eq(lo + mid, SR, 1.0)
    spec = np.abs(np.fft.rfft(y))
    freqs = np.fft.rfftfreq(len(y), 1 / SR)
    lo_i = int(np.argmin(np.abs(freqs - 100)))
    mid_i = int(np.argmin(np.abs(freqs - 1000)))
    db_drop = 20 * np.log10(spec[lo_i] / spec[mid_i])
    assert db_drop < -12.0


def test_join_crossfade_lengths_and_smoothness():
    a = _sine(440.0, seconds=0.5)
    b = _sine(660.0, seconds=0.5)
    y = dsp.join_crossfade([a, b], SR, overlap_s=0.015)
    n = int(0.015 * SR)
    assert y.shape[0] == a.shape[0] + b.shape[0] - n
    assert dsp.peak(y) <= 1.0
    assert np.array_equal(dsp.join_crossfade([a], SR, 0.015), a)
    assert dsp.join_crossfade([], SR, 0.015).shape == (0,)
