"""
Musical structure -- what the song is *doing*, not just how loud it is.

`analyze.py` gives a per-frame feature track: energy, onset strength, twelve
frequency bands. That is enough to make something pulse, but not enough to
*edit*. An editor needs to know where the beats are even when a bar is quiet,
which beat starts the bar, where the verse stops and the chorus begins, and
where the drop lands.

This module adds that layer:

    bpm            tempo in beats per minute, plus how sure of it we are
    beats          a steady grid of beat times, in seconds
    downbeats      the first beat of every bar
    beats_per_bar  3 or 4
    bar_seconds    how long one bar lasts
    sections       [{start, end, kind, label, energy, ...}] -- the song's shape
    hits           individual transients worth landing a cut or a flash on
    drops          where a build releases
    vocal          per frame: is someone singing here
    novelty        per beat: how much the song just changed

Three pieces of maths do the work, and each is here for a reason:

**Tempo** is the peak of the autocorrelation of the onset strength, weighted by
a log-normal prior centred on 120 BPM. Without the prior, half-time and
double-time score just as well as the real tempo, so the answer flips between
songs and the cuts come out at twice the intended rate.

**Beats** come from Ellis's dynamic-programming beat tracker: pick the set of
times maximising (onset strength at each beat) minus (a penalty for spacing that
is not the tempo period), solved exactly by working forwards and then tracing
back. This is why the grid keeps going through a quiet bar -- a beat with no
transient under it still costs nothing if it sits exactly one period after the
last one. Plain peak-picking, which is what `analyze.beat` does, drops out
entirely there, and a montage cut on it stalls.

**Sections** use Foote's novelty curve: build a self-similarity matrix over
beat-synchronous band features, slide a checkerboard kernel down its diagonal,
and its peaks are the moments where the song stops sounding like what came
before. Sections that sound alike are then given the same letter, and the
letters are named by loudness and repetition -- the loudest thing that happens
more than once is the chorus.

Everything degrades: a two-second clip, a silent file or a track with no
discernible pulse returns a map with sensible fallbacks rather than raising, and
`ok` says whether the structure is trustworthy.
"""

import numpy as np

# Reference numbers used by the tempo prior and the section grammar.
PRIOR_BPM = 120.0  # most music sits within an octave of this
PRIOR_OCTAVES = 1.0  # width of the log-normal tempo prior
BPM_MIN, BPM_MAX = 50.0, 210.0
TIGHTNESS = 100.0  # how hard the beat tracker insists on even spacing
MIN_SECTION_BEATS = 8  # two bars of four; shorter "sections" are noise
KERNEL_BEATS = 16  # half-width of the checkerboard, in beats
SAME_SECTION_SIM = 0.86  # cosine similarity at which two sections are "the same"

# Which of analyze.py's twelve log-spaced bands carry a voice. The edges are
# geomspace(40, 11025, 13), so bands 4..8 span roughly 260 Hz - 4.3 kHz, which
# is where a sung melody and its first formants live.
VOCAL_BANDS = (4, 5, 6, 7, 8)


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------
def _smooth(x, w):
    """Moving average of odd width `w`, edges held rather than zero-padded."""
    x = np.asarray(x, dtype=np.float64)
    w = int(max(1, w)) | 1
    if w <= 1 or x.size == 0:
        return x
    pad = w // 2
    padded = np.concatenate([np.full(pad, x[0]), x, np.full(pad, x[-1])])
    kern = np.ones(w) / w
    return np.convolve(padded, kern, mode="valid")


def _unit(v):
    n = float(np.linalg.norm(v))
    return v / n if n > 1e-9 else v


def _peaks(x, distance, height=None):
    """Indices of local maxima at least `distance` apart, tallest first.

    Written out rather than taken from scipy so the ordering is ours: peaks are
    claimed strongest-first, which keeps a tall peak from being suppressed by a
    slightly earlier short one."""
    x = np.asarray(x, dtype=np.float64)
    if x.size < 3:
        return np.array([], dtype=int)
    cand = np.where((x[1:-1] >= x[:-2]) & (x[1:-1] > x[2:]))[0] + 1
    if height is not None:
        cand = cand[x[cand] >= height]
    if cand.size == 0:
        return np.array([], dtype=int)
    order = cand[np.argsort(-x[cand])]
    kept = []
    for i in order:
        if all(abs(i - k) >= distance for k in kept):
            kept.append(int(i))
    return np.array(sorted(kept), dtype=int)


# --------------------------------------------------------------------------
# tempo
# --------------------------------------------------------------------------
def estimate_tempo(onset, fps):
    """(bpm, confidence 0..1) from the onset envelope's autocorrelation.

    The autocorrelation of an onset track peaks at the beat period *and* at
    every multiple and division of it. The log-normal prior around 120 BPM is
    what decides between them; it is the whole reason this returns 128 rather
    than 64 or 256 for a house track."""
    o = np.asarray(onset, dtype=np.float64)
    if o.size < int(fps * 2):
        return 0.0, 0.0
    o = o - o.mean()
    if o.std() < 1e-9:
        return 0.0, 0.0
    o = o / o.std()

    max_lag = int(min(len(o) - 1, fps * 60.0 / BPM_MIN * 1.05))
    min_lag = int(max(1, fps * 60.0 / BPM_MAX))
    if max_lag <= min_lag + 2:
        return 0.0, 0.0

    # unbiased autocorrelation via FFT
    n = 1 << int(np.ceil(np.log2(len(o) * 2)))
    spec = np.fft.rfft(o, n)
    ac = np.fft.irfft(spec * np.conj(spec), n)[: max_lag + 1]
    counts = np.arange(len(o), len(o) - len(ac), -1).astype(np.float64)
    ac = ac / np.maximum(counts, 1.0)
    if ac[0] > 1e-9:
        ac = ac / ac[0]

    lags = np.arange(min_lag, max_lag + 1)
    bpms = 60.0 * fps / lags
    prior = np.exp(-0.5 * (np.log2(bpms / PRIOR_BPM) / PRIOR_OCTAVES) ** 2)
    score = ac[min_lag : max_lag + 1] * prior

    best = int(np.argmax(score))
    bpm = float(bpms[best])
    # Confidence: how far the winning peak stands above the rest of the curve.
    rest = np.delete(score, best)
    spread = float(rest.std()) if rest.size else 0.0
    conf = (
        0.0
        if spread < 1e-9
        else float(np.clip((score[best] - rest.mean()) / (4 * spread), 0.0, 1.0))
    )
    return bpm, conf


# --------------------------------------------------------------------------
# beats
# --------------------------------------------------------------------------
def track_beats(onset, fps, bpm):
    """Beat frame indices, by dynamic programming (Ellis 2007).

    Score of a beat sequence = sum of onset strength at each beat, minus
    TIGHTNESS times the squared log-ratio of each gap to the tempo period. The
    best sequence ending at every frame is computed once, forwards; the answer
    is then read back from the best ending. Exact, not greedy."""
    o = np.asarray(onset, dtype=np.float64)
    n = o.size
    if n < 4 or bpm <= 0:
        return np.array([], dtype=int)
    if o.std() > 1e-9:
        o = (o - o.mean()) / o.std()

    tau = 60.0 * fps / bpm
    lo = max(1, int(round(tau * 0.5)))
    hi = max(lo + 1, int(round(tau * 2.0)))
    lags = np.arange(lo, hi + 1)
    # cost of a gap: zero at exactly one period, falling away either side
    txcost = -TIGHTNESS * (np.log(lags / tau) ** 2)

    score = np.zeros(n)
    back = np.full(n, -1, dtype=np.int64)
    for t in range(n):
        idx = t - lags
        ok = idx >= 0
        if not ok.any():
            score[t] = o[t]
            continue
        cand = score[idx[ok]] + txcost[ok]
        j = int(np.argmax(cand))
        score[t] = o[t] + cand[j]
        back[t] = idx[ok][j]

    # Start the trace at the best score in the last couple of periods, so a
    # loud fade-out tail cannot drag the whole grid off the beat.
    tail = max(0, n - int(round(tau * 2)))
    end = tail + int(np.argmax(score[tail:]))
    beats = []
    while end >= 0:
        beats.append(int(end))
        end = int(back[end])
    beats.reverse()
    return np.array(beats, dtype=int)


def _beat_norm(x):
    x = np.asarray(x, dtype=np.float64)
    if x.size == 0:
        return x
    lo, hi = float(x.min()), float(x.max())
    return (x - lo) / (hi - lo) if hi - lo > 1e-9 else np.zeros_like(x)


def find_meter(beats, onset, sub, fps, bf=None):
    """(beats_per_bar, phase). The downbeat is the beat that is consistently
    heaviest; try 4 then 3 and take whichever splits the beats most decisively.

    Deliberately *not* scored on raw onset strength. A snare is broadband and
    produces far more spectral flux than a kick, so flux alone lands the
    downbeat on beat two or four -- which is exactly what it did on the first
    test track. What actually marks a bar is the low end arriving (`sub`) and
    the harmony changing (`bf`, the beat-to-beat timbre distance), so those
    carry the weight and flux only breaks ties."""
    if len(beats) < 8:
        return 4, 0
    strength = 0.35 * _beat_norm(np.asarray(onset)[beats]) + 1.0 * _beat_norm(
        np.asarray(sub)[beats]
    )
    if bf is not None and len(bf) == len(beats) and len(bf) > 1:
        change = np.concatenate([[0.0], np.linalg.norm(np.diff(bf, axis=0), axis=1)])
        strength = strength + 0.6 * _beat_norm(change)
    best = (4, 0, -1.0)
    for m in (4, 3):
        if len(beats) < m * 3:
            continue
        means = []
        for phase in range(m):
            sel = strength[phase::m]
            means.append(float(sel.mean()) if sel.size else 0.0)
        means = np.array(means)
        phase = int(np.argmax(means))
        others = np.delete(means, phase)
        contrast = float(means[phase] - others.mean()) if others.size else 0.0
        if contrast > best[2]:
            best = (m, phase, contrast)
    return best[0], best[1]


# --------------------------------------------------------------------------
# sections
# --------------------------------------------------------------------------
def _beat_features(feat, beats):
    """One feature vector per beat: the mean of the twelve bands plus energy
    and brightness over that beat's span, unit-normalised so the comparison is
    about *timbre* rather than loudness."""
    bands = np.asarray(feat["bands"], dtype=np.float64)
    energy = np.asarray(feat["energy"], dtype=np.float64)
    centroid = np.asarray(feat["centroid"], dtype=np.float64)
    n = bands.shape[0]
    rows = []
    for i, b in enumerate(beats):
        b2 = beats[i + 1] if i + 1 < len(beats) else min(n, b + 1)
        a, z = int(b), int(max(b + 1, b2))
        z = min(z, n)
        if a >= n:
            rows.append(np.zeros(bands.shape[1] + 2))
            continue
        # Timbre is unit-normalised on its own so a loud and a quiet chorus
        # still look alike; loudness and brightness are then appended with
        # their own weight, so a quiet intro is not silently folded into the
        # verse that follows it. Both matter, and neither should dominate.
        v = np.concatenate(
            [
                _unit(bands[a:z].mean(axis=0)),
                [0.85 * energy[a:z].mean(), 0.5 * centroid[a:z].mean()],
            ]
        )
        rows.append(_unit(v))
    return np.array(rows)


def _checkerboard(L):
    """A 2L x 2L kernel, positive on the diagonal quadrants and negative off
    them, tapered by a Gaussian so far-away beats matter less. Sliding it down
    the diagonal of a self-similarity matrix scores "everything before here is
    like itself, everything after is like itself, and the two are unalike" --
    which is exactly a section boundary."""
    g = np.arange(-L, L)
    gauss = np.exp(-0.5 * (g / (L * 0.5)) ** 2)
    taper = np.outer(gauss, gauss)
    sign = np.sign(np.outer(np.sign(g + 0.5), np.sign(g + 0.5)))
    return sign * taper


def energy_step(beat_energy, span):
    """How much the loudness level shifts at each beat and stays shifted.

    Foote novelty is about *timbre*, so it is almost blind to an intro that
    plays the same instruments as the verse but quieter -- and that is one of
    the commonest boundaries in a song. This is the missing half: the size of
    the step between the average level before a beat and after it."""
    e = np.asarray(beat_energy, dtype=np.float64)
    n = e.size
    if n < 4:
        return np.zeros(max(n, 1))
    L = int(max(2, min(span, n // 4)))
    out = np.zeros(n)
    for i in range(n):
        a0, a1 = max(0, i - L), i
        b0, b1 = i, min(n, i + L)
        if a1 - a0 < 2 or b1 - b0 < 2:
            continue
        out[i] = abs(e[b0:b1].mean() - e[a0:a1].mean())
    if out.max() > 1e-9:
        out = out / out.max()
    return out


def novelty_curve(bf, kernel_beats=KERNEL_BEATS, beat_energy=None):
    """Where the song stops sounding like what came before.

    Foote's checkerboard novelty over timbre, plus a loudness-step term, because
    the two catch different boundaries: timbre catches the chorus arriving,
    level catches the intro ending."""
    n = len(bf)
    if n < 4:
        return np.zeros(max(n, 1))
    L = int(min(kernel_beats, max(2, n // 4)))
    K = _checkerboard(L)
    sim = bf @ bf.T
    nov = np.zeros(n)
    for i in range(n):
        a, z = i - L, i + L
        pa, pz = max(0, a), min(n, z)
        block = np.zeros((2 * L, 2 * L))
        block[pa - a : pa - a + (pz - pa), pa - a : pa - a + (pz - pa)] = sim[
            pa:pz, pa:pz
        ]
        nov[i] = float((block * K).sum())
    nov = nov - nov.min()
    if nov.max() > 1e-9:
        nov = nov / nov.max()
    nov = _smooth(nov, 3)
    if beat_energy is not None and len(beat_energy) == n:
        nov = nov + 0.7 * _smooth(energy_step(beat_energy, L), 3)
        if nov.max() > 1e-9:
            nov = nov / nov.max()
    return nov


def pick_boundaries(nov, min_distance=MIN_SECTION_BEATS, max_sections=24):
    """Beat indices where a section starts, from a novelty curve.

    A flat percentile threshold does not work here. On a track with one
    towering boundary -- the chorus arriving -- every other real boundary sits
    below the 68th percentile and is thrown away; the first test song lost its
    intro that way. What matters is whether a peak stands above *its own
    neighbourhood*, so the curve is measured against a wide moving average of
    itself and the peaks are picked out of what is left."""
    nov = np.asarray(nov, dtype=np.float64)
    if nov.size < 4:
        return []
    baseline = _smooth(nov, max(3, min_distance * 4 + 1))
    resid = nov - baseline
    top = float(resid.max())
    if top <= 1e-9:
        return []
    height = max(0.05 * top, 0.15 * top)
    peaks = _peaks(resid, distance=min_distance, height=height)
    if len(peaks) > max_sections:
        peaks = np.array(sorted(peaks[np.argsort(-resid[peaks])][:max_sections]))
    return [int(i) for i in peaks]


def _label_sections(bounds, bf, beats, fps, feat):
    """Turn beat-index boundaries into named sections.

    Two passes. First, sections whose average sound is close enough get the
    same letter -- that is what makes a repeat recognisable as a repeat.
    Second, the letters are given names from how loud they are and how often
    they come back, because that is what the words verse and chorus actually
    mean in an arrangement."""
    energy = np.asarray(feat["energy"], dtype=np.float64)
    onset = np.asarray(feat["onset"], dtype=np.float64)
    n_frames = len(energy)

    segs = []
    for i in range(len(bounds) - 1):
        b0, b1 = bounds[i], bounds[i + 1]
        f0 = int(beats[b0]) if b0 < len(beats) else n_frames
        f1 = int(beats[b1]) if b1 < len(beats) else n_frames
        f1 = min(max(f1, f0 + 1), n_frames)
        segs.append(
            {
                "beat0": int(b0),
                "beat1": int(b1),
                "start": f0 / fps,
                "end": f1 / fps,
                "energy": float(energy[f0:f1].mean()),
                "density": float(onset[f0:f1].mean()),
                "vec": _unit(bf[b0:b1].mean(axis=0)) if b1 > b0 else bf[b0] * 0,
            }
        )
    if not segs:
        return []

    # --- pass one: which sections sound like each other ---
    centroids = []
    for s in segs:
        placed = False
        for li, c in enumerate(centroids):
            if float(np.dot(s["vec"], c["vec"])) >= SAME_SECTION_SIM:
                s["label"] = chr(ord("A") + li)
                c["n"] += 1
                c["vec"] = _unit(c["vec"] * (c["n"] - 1) / c["n"] + s["vec"] / c["n"])
                placed = True
                break
        if not placed:
            s["label"] = chr(ord("A") + len(centroids))
            centroids.append({"vec": s["vec"].copy(), "n": 1})

    counts = {}
    label_energy = {}
    for s in segs:
        counts[s["label"]] = counts.get(s["label"], 0) + 1
        label_energy.setdefault(s["label"], []).append(s["energy"])
    label_energy = {k: float(np.mean(v)) for k, v in label_energy.items()}

    # --- pass two: names ---
    repeated = [k for k, c in counts.items() if c >= 2]
    repeated.sort(key=lambda k: -label_energy[k])
    chorus = repeated[0] if repeated else None
    verse = repeated[1] if len(repeated) > 1 else None

    # Loudness is measured across the *sections*, not across the labels. With
    # one label the spread between labels is zero, so the relative-energy test
    # divides by nothing and every position rule misfires.
    seg_energy = [x["energy"] for x in segs]
    lo = min(seg_energy)
    hi = max(seg_energy)
    span = max(1e-6, hi - lo)

    # When a track keeps the same instruments all the way through -- which is
    # most of the background music this is for -- the timbre clustering finds
    # one label for the whole song and every section comes back a chorus. The
    # boundaries are still right; only the naming has collapsed. So fall back
    # to naming purely by how loud each section is relative to the rest, which
    # is what the words mean anyway on a track with no change of arrangement.
    degenerate = len(counts) <= 1 or (
        chorus is not None and counts[chorus] > 0.6 * len(segs)
    )

    for i, s in enumerate(segs):
        lab = s["label"]
        rel = (s["energy"] - lo) / span
        first, last = i == 0, i == len(segs) - 1
        # Position beats the timbre match. A stripped-back reprise of the
        # chorus at the end of a track is an outro to anyone editing to it,
        # however much it sounds like the chorus -- and on the first test song
        # it was being called a chorus, which would have put the fastest cuts
        # over the fade-out.
        if first and rel < 0.55:
            kind = "intro"
        elif last and rel < 0.6:
            kind = "outro"
        elif degenerate:
            kind = (
                "chorus"
                if rel >= 0.72
                else "verse" if rel >= 0.42 else "bridge" if rel >= 0.2 else "breakdown"
            )
        elif lab == chorus:
            kind = "chorus"
        elif lab == verse:
            kind = "verse"
        elif rel < 0.3:
            kind = "breakdown"
        else:
            kind = "bridge"
        # A quiet stretch that climbs into a loud one is a build, whatever it
        # sounded like on its own.
        nxt = segs[i + 1] if i + 1 < len(segs) else None
        if nxt and kind in ("breakdown", "bridge", "verse"):
            f0, f1 = int(beats[s["beat0"]]), int(min(n_frames, beats[s["beat1"]]))
            if f1 - f0 > 4:
                half = (f0 + f1) // 2
                rising = energy[half:f1].mean() - energy[f0:half].mean()
                if rising > 0.08 and nxt["energy"] - s["energy"] > 0.12:
                    kind = "build"
        s["kind"] = kind
        s.pop("vec", None)
    return segs


# --------------------------------------------------------------------------
# events
# --------------------------------------------------------------------------
def find_hits(onset, fps, percentile=88.0):
    """Transients big enough to be worth landing something on."""
    o = np.asarray(onset, dtype=np.float64)
    if o.size < 3:
        return np.array([], dtype=int)
    thresh = float(np.percentile(o, percentile))
    return _peaks(o, distance=max(2, int(fps * 0.12)), height=thresh)


def find_drops(energy, sub, fps):
    """Frames where a quiet stretch gives way to a loud one.

    Measured as the jump in (energy + sub-bass) across a moving boundary, which
    is what a drop is: the low end arrives all at once."""
    e = _smooth(
        np.asarray(energy, float) + 0.7 * np.asarray(sub, float), int(fps * 0.4)
    )
    w = int(fps * 1.5)
    if e.size < 2 * w + 4:
        return np.array([], dtype=int)
    before = np.array(
        [e[max(0, i - w) : i].mean() if i > 0 else e[0] for i in range(e.size)]
    )
    after = np.array([e[i : min(e.size, i + w)].mean() for i in range(e.size)])
    jump = after - before
    return _peaks(
        jump, distance=int(fps * 4), height=max(0.18, float(np.percentile(jump, 97)))
    )


def vocal_track(bands, fps):
    """Per frame: is the mid-range carrying a voice.

    A sung line puts most of its energy in the 260 Hz - 4 kHz bands and moves
    around within them. Instrumental sections either sit lower (bass, kick) or
    are steadier. This is a ratio with a floor, not a classifier -- it is right
    often enough to bias a cut towards a lyric and never used for anything that
    breaks if it is wrong."""
    b = np.asarray(bands, dtype=np.float64)
    if b.ndim != 2 or b.shape[0] == 0:
        return np.zeros(0, dtype=bool)
    total = b.sum(axis=1) + 1e-9
    mid = b[:, list(VOCAL_BANDS)].sum(axis=1)
    ratio = _smooth(mid / total, int(fps * 0.5))
    if ratio.size == 0:
        return np.zeros(0, dtype=bool)
    thresh = float(np.percentile(ratio, 55))
    return ratio > max(thresh, ratio.mean() * 0.9)


# --------------------------------------------------------------------------
# the whole map
# --------------------------------------------------------------------------
def map_music(feat):
    """Everything above, from one `analyze.analyze()` result.

    Never raises on odd input: a song too short or too flat to have a structure
    comes back with `ok: False`, an empty beat grid and one section covering the
    whole thing, which every caller already handles as "just use the clock"."""
    fps = float(feat.get("fps", 30.0))
    onset = np.asarray(feat.get("onset", []), dtype=np.float64)
    energy = np.asarray(feat.get("energy", []), dtype=np.float64)
    sub = np.asarray(feat.get("sub", []), dtype=np.float64)
    bands = np.asarray(feat.get("bands", np.zeros((len(onset), 12))), dtype=np.float64)
    duration = float(feat.get("duration", len(onset) / fps if fps else 0.0))

    blank = {
        "ok": False,
        "fps": fps,
        "duration": duration,
        "bpm": 0.0,
        "bpm_confidence": 0.0,
        "beats": [],
        "beat_frames": [],
        "downbeats": [],
        "beats_per_bar": 4,
        "bar_seconds": 0.0,
        "sections": [
            {
                "start": 0.0,
                "end": duration,
                "kind": "verse",
                "label": "A",
                "energy": float(energy.mean()) if energy.size else 0.5,
                "density": float(onset.mean()) if onset.size else 0.5,
                "beat0": 0,
                "beat1": 0,
            }
        ],
        "hits": [],
        "drops": [],
        "vocal": np.zeros(len(onset), dtype=bool),
        "novelty": [],
    }
    if onset.size < int(fps * 3):
        return blank

    bpm, conf = estimate_tempo(onset, fps)
    if bpm <= 0:
        return blank
    beat_frames = track_beats(onset, fps, bpm)
    if len(beat_frames) < 4:
        return blank

    # The tracked grid is the honest tempo; the autocorrelation peak can still
    # be an octave out, so re-read the tempo from the spacing we actually used.
    #
    # Averaged, not median. Beats land on whole frames, so at 30 fps every gap
    # is quantised to a thirty-third of a second and the median simply returns
    # whichever whole frame count is commonest -- a 118 BPM track whose beat is
    # 15.25 frames reports as a flat 120. That is a 0.3% error, which sounds
    # like nothing until something is asked to cycle in time with it: over a
    # three-minute shot it drifts more than three seconds, which is a whole
    # bar and a half out. Averaging the gaps that agree with the median keeps
    # the median's robustness against a dropped or doubled beat while
    # recovering the sub-frame precision.
    gaps = np.diff(beat_frames).astype(np.float64)
    if gaps.size:
        med = float(np.median(gaps))
        keep = gaps[np.abs(gaps - med) <= max(1.0, 0.25 * med)]
        period = float(keep.mean()) if keep.size else med
        bpm = float(60.0 * fps / period)

    bf = _beat_features(feat, beat_frames)
    meter, phase = find_meter(beat_frames, onset, sub, fps, bf)
    downbeat_frames = beat_frames[phase::meter]

    beat_energy = np.array(
        [
            float(
                energy[
                    int(f) : int(
                        min(len(energy), f + max(1, gaps.min() if gaps.size else 1))
                    )
                ].mean()
            )
            for f in beat_frames
        ]
    )
    nov = novelty_curve(bf, beat_energy=beat_energy)
    bounds = pick_boundaries(nov)
    # snap every boundary to the nearest downbeat -- sections start on bars
    db_idx = set(range(phase, len(beat_frames), meter))
    snapped = []
    for b in bounds:
        near = min(db_idx, key=lambda d: abs(d - b)) if db_idx else b
        if abs(near - b) <= meter:
            b = near
        if not snapped or b - snapped[-1] >= MIN_SECTION_BEATS:
            snapped.append(int(b))
    bounds = [0] + [b for b in snapped if 0 < b < len(beat_frames)] + [len(beat_frames)]
    bounds = sorted(set(bounds))

    sections = _label_sections(bounds, bf, beat_frames, fps, feat)

    return {
        "ok": True,
        "fps": fps,
        "duration": duration,
        "bpm": round(bpm, 2),
        "bpm_confidence": round(float(conf), 3),
        "beats": [round(float(f) / fps, 4) for f in beat_frames],
        "beat_frames": [int(f) for f in beat_frames],
        "downbeats": [round(float(f) / fps, 4) for f in downbeat_frames],
        "beats_per_bar": int(meter),
        "bar_seconds": round(60.0 / bpm * meter, 4) if bpm > 0 else 0.0,
        "sections": sections,
        "hits": [round(float(f) / fps, 4) for f in find_hits(onset, fps)],
        "drops": [round(float(f) / fps, 4) for f in find_drops(energy, sub, fps)],
        "vocal": vocal_track(bands, fps),
        "novelty": [round(float(v), 4) for v in nov],
    }


def section_at(mapping, t):
    """The section covering time `t`, or None."""
    for s in mapping.get("sections", []):
        if s["start"] <= t < s["end"]:
            return s
    secs = mapping.get("sections") or []
    return secs[-1] if secs else None


def jsonable(mapping):
    """The map with numpy types replaced, ready for the API."""
    out = {}
    for k, v in mapping.items():
        if isinstance(v, np.ndarray):
            out[k] = v.tolist()
        else:
            out[k] = v
    return out


__all__ = [
    "map_music",
    "estimate_tempo",
    "track_beats",
    "find_meter",
    "novelty_curve",
    "pick_boundaries",
    "energy_step",
    "find_hits",
    "find_drops",
    "vocal_track",
    "section_at",
    "jsonable",
]
