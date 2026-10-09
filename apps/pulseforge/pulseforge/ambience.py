"""
Rain, fire and vinyl crackle under the music.

Nearly every background-music video has an ambient bed mixed low under the
track, and it does a lot of work: it glues songs together, covers the joins, and
makes a loop feel like a place rather than a file.

These are **generated**, not shipped as audio. Each one is a few lines of numpy
-- shape a noise spectrum, add whatever transients belong (fire crackles, vinyl
clicks), fade the ends into each other so it can be repeated forever. That costs
no disk, which matters here, and it makes adding "café" or "thunder" later one
function in a table rather than a hunt for a clip with a usable licence.

Thirty seconds is generated and then looped underneath the whole mix by ffmpeg,
so an eight-hour video costs the same thirty seconds of synthesis.
"""

import wave

import numpy as np

SR = 48000
DEFAULT_SECONDS = 30.0
BLEND_SECONDS = 1.5
TARGET_RMS = 0.16  # the ends are dissolved together so it repeats invisibly


def _rms(x):
    return max(1e-9, float(np.sqrt((np.asarray(x) ** 2).mean())))


def _shaped_noise(n, rng, tilt=1.0, lowpass=None, highpass=None):
    """Noise with a shaped spectrum.

    Filtering through an FFT rather than a recursive filter: a one-pole in a
    Python loop over a million samples would be unusable, and this gives exact
    control over the curve for one transform.
    """
    spec = np.fft.rfft(rng.standard_normal(n))
    freqs = np.fft.rfftfreq(n, 1.0 / SR)
    gain = np.ones_like(freqs)
    # a tilt with no high-pass piles almost all the energy into sub-bass, which
    # is why every bed here is band-limited rather than only tilted
    gain = 1.0 / np.maximum(1.0, freqs) ** float(tilt)
    if lowpass:
        gain = gain / (1.0 + (freqs / float(lowpass)) ** 2)
    if highpass:
        gain = gain * (freqs**2) / (freqs**2 + float(highpass) ** 2)
    gain[0] = 0.0
    return np.fft.irfft(spec * gain, n)


def _bursts(n, rng, rate, decay, strength, darken=1):
    """Sparse transients -- fire crackles, vinyl pops, drips on a window.

    `darken` smooths each burst, because a raw noise click is a bright tick that
    drags the whole bed's brightness up with it; real crackles are duller.
    """
    out = np.zeros(n, dtype=np.float64)
    count = max(1, int(rate * n / SR))
    at = rng.integers(0, n, size=count)
    length = max(4, int(decay * SR))
    env = np.exp(-np.linspace(0, 6, length))
    for pos in at:
        end = min(n, pos + length)
        out[pos:end] += env[: end - pos] * rng.standard_normal(end - pos) * rng.random()
    if darken > 1:
        k = np.ones(int(darken)) / float(darken)
        out = np.convolve(out, k, mode="same")
    return out * strength


def _rain(n, rng):
    body = _shaped_noise(n, rng, tilt=0.0, lowpass=4000, highpass=150)
    drops = _bursts(n, rng, rate=70, decay=0.012, strength=0.35, darken=6)
    return body / _rms(body) + drops * 0.30


def _fire(n, rng):
    body = _shaped_noise(n, rng, tilt=0.0, lowpass=900, highpass=80)
    crackle = _bursts(n, rng, rate=8, decay=0.04, strength=1.0, darken=10)
    # fires breathe -- a slow swell keeps it from sounding like flat hiss
    t = np.arange(n) / SR
    breathe = 0.75 + 0.25 * np.sin(2 * np.pi * t / 11.0)
    return (body / _rms(body)) * breathe + crackle * 0.55


def _vinyl(n, rng):
    hiss = _shaped_noise(n, rng, tilt=0.0, lowpass=6000, highpass=300)
    pops = _bursts(n, rng, rate=3.2, decay=0.005, strength=0.9, darken=4)
    # one soft thump per revolution, the way a warped record ticks at 33rpm
    period = int(SR * 60.0 / 33.3)
    ticks = np.zeros(n)
    for pos in range(0, n, period):
        end = min(n, pos + 240)
        ticks[pos:end] += np.exp(-np.linspace(0, 6, end - pos)) * 0.25
    return hiss / _rms(hiss) + pops * 0.5 + ticks


def _wind(n, rng):
    body = _shaped_noise(n, rng, tilt=0.5, lowpass=1200, highpass=120)
    t = np.arange(n) / SR
    gust = 0.55 + 0.45 * (
        0.6 * np.sin(2 * np.pi * t / 17.0) + 0.4 * np.sin(2 * np.pi * t / 6.5 + 1.1)
    )
    return (body / _rms(body)) * gust


def _waves(n, rng):
    body = _shaped_noise(n, rng, tilt=0.2, lowpass=1500, highpass=100)
    t = np.arange(n) / SR
    # one swell every ten seconds, sharper on the way in than the way out
    phase = (t / 10.0) % 1.0
    swell = np.clip(np.sin(np.pi * phase) ** 2.2, 0.05, 1.0)
    return (body / _rms(body)) * swell


BEDS = [
    {"id": "rain", "label": "Rain", "description": "Steady rainfall.", "fn": _rain},
    {"id": "fire", "label": "Fireplace", "description": "Crackling logs.", "fn": _fire},
    {
        "id": "vinyl",
        "label": "Vinyl crackle",
        "description": "Record hiss, pops and a tick each revolution.",
        "fn": _vinyl,
    },
    {"id": "wind", "label": "Wind", "description": "Gusts through trees.", "fn": _wind},
    {"id": "waves", "label": "Waves", "description": "Slow surf.", "fn": _waves},
]
BY_ID = {b["id"]: b for b in BEDS}


def beds_as_list():
    return [{k: v for k, v in b.items() if k != "fn"} for b in BEDS]


def _loopable(mono, blend_samples):
    """Dissolve the tail into the head so repeating it is inaudible.

    Always trims `blend_samples` off the end, so the caller can rely on getting
    exactly the length it sized the buffer for.
    """
    if blend_samples <= 0 or blend_samples >= len(mono):
        return mono
    head = mono[:blend_samples].copy()
    tail = mono[-blend_samples:]
    ramp = np.linspace(0.0, 1.0, blend_samples)
    mono = mono[:-blend_samples]
    mono[:blend_samples] = head * ramp + tail * (1.0 - ramp)
    return mono


def generate(bed_id, seconds=DEFAULT_SECONDS, seed=0):
    """A stereo float array in [-1, 1] that can be looped forever."""
    bed = BY_ID.get(str(bed_id))
    if not bed:
        raise KeyError(f"no such ambience: {bed_id}")
    body = int(float(seconds) * SR)
    # the blend is taken off the end, so it can never be more than the request
    # can spare -- otherwise a short preview would come back the wrong length
    blend = min(int(BLEND_SECONDS * SR), max(0, body // 3))
    n = body + blend
    channels = []
    for c in range(2):
        rng = np.random.default_rng(int(seed) * 7919 + c * 104729 + 11)
        mono = _loopable(bed["fn"](n, rng), blend)
        # level by loudness, not by the single loudest click -- normalising to
        # peak makes a crackly bed like vinyl almost inaudible
        mono = mono / _rms(mono) * TARGET_RMS
        channels.append(mono)
    stereo = np.stack(channels, axis=1)
    # soft-knee limit so the transients round off instead of clipping square
    return np.tanh(stereo * 1.6) / np.tanh(1.6)


def write_wav(bed_id, path, seconds=DEFAULT_SECONDS, seed=0):
    audio = generate(bed_id, seconds, seed)
    pcm = (audio * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return str(path)
