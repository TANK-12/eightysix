"""
Montage / AMV -- cut a folder of video clips to the beat of the song.

Attach a folder of clips in the Compose tab. This builds an edit decision list
where every cut lands on a detected beat (respecting a min/max shot length).
With `match_energy` on (default), each slot is filled by the clip segment whose
**motion** best matches the song's **energy** at that moment -- busy footage on
the loud parts, calm footage on the quiet parts -- with a penalty for reusing a
clip two shots running. render.py turns the EDL into one ffmpeg filter_complex
(trim -> fit -> concat, or an xfade chain for crossfades) and muxes the song.

Next phase (see WIP.md): face detection to prefer character shots (needs a model
dependency), and a local model reordering shots from your text notes.
"""

import os

import numpy as np

from .. import clips as clipmod

SCENE = {
    "id": "montage",
    "label": "Beat-Cut Montage (AMV)",
    "family": "montage",
    "description": "Cuts a folder of video clips to the song's beat. Attach a "
    "clips folder in Compose. Every cut lands on a beat; shots "
    "start on scene changes where possible.",
    "params": [
        {
            "key": "min_shot",
            "label": "Min shot (seconds)",
            "type": "float",
            "default": 0.5,
            "min": 0.15,
            "max": 4.0,
        },
        {
            "key": "max_shot",
            "label": "Max shot (seconds)",
            "type": "float",
            "default": 3.0,
            "min": 0.5,
            "max": 12.0,
        },
        {
            "key": "order",
            "label": "Shot order",
            "type": "select",
            "default": "sequential",
            "options": ["sequential", "shuffle"],
        },
        {
            "key": "on_beat",
            "label": "Cut on",
            "type": "select",
            "default": "every_beat",
            "options": ["every_beat", "every_2nd", "every_4th"],
        },
        {
            "key": "fit",
            "label": "Fit",
            "type": "select",
            "default": "cover",
            "options": ["cover", "contain"],
        },
        {
            "key": "match_energy",
            "label": "Match shot motion to the music's energy",
            "type": "bool",
            "default": True,
        },
        {
            "key": "transition",
            "label": "Transition",
            "type": "select",
            "default": "cut",
            "options": ["cut", "crossfade", "dip_black", "dip_white"],
        },
        {
            "key": "transition_ms",
            "label": "Transition length (ms)",
            "type": "int",
            "default": 250,
            "min": 60,
            "max": 1500,
        },
    ],
}


def _beat_times(feat):
    beat = feat.get("beat")
    fps = float(feat.get("fps", 30.0))
    if beat is None:
        return []
    return [i / fps for i in np.where(np.asarray(beat))[0]]


def _slot_energy(feat, t0, t1):
    """Mean song energy over [t0, t1] seconds, 0..1."""
    energy = feat.get("energy")
    fps = float(feat.get("fps", 30.0))
    if energy is None or len(energy) == 0:
        return 0.5
    a, b = int(t0 * fps), max(int(t0 * fps) + 1, int(t1 * fps))
    seg = np.asarray(energy)[a:b]
    return float(seg.mean()) if len(seg) else 0.5


def build_edl(ctx):
    """Return list[{path, start, dur}] covering ctx.duration, or [] if no pool."""
    pool_dir = None
    for a in ctx.assets:
        if a and os.path.isdir(a):
            pool_dir = a
            break
    if not pool_dir:
        return []
    paths = clipmod.scan_pool(pool_dir)
    if not paths:
        return []
    pool = [clipmod.probe_clip(p) for p in paths]
    pool = [c for c in pool if c["duration"] > 0.3]
    if not pool:
        return []

    cuts_cache = {}

    def cuts_for(c):
        if c["path"] not in cuts_cache:
            cuts_cache[c["path"]] = clipmod.scene_cuts(c["path"])
        return cuts_cache[c["path"]]

    stride = {"every_beat": 1, "every_2nd": 2, "every_4th": 4}[
        ctx.p("on_beat", "every_beat")
    ]
    beats = _beat_times(ctx.feat)[::stride]
    min_shot = float(ctx.p("min_shot", 0.5))
    max_shot = float(ctx.p("max_shot", 3.0))
    total = ctx.duration

    # cut points: start at 0, then each beat that is >= min_shot past the last
    points = [0.0]
    for bt in beats:
        if bt - points[-1] >= min_shot and bt < total - 0.1:
            if bt - points[-1] > max_shot:
                # no beat for a while -- force interim cuts on the grid
                g = points[-1] + max_shot
                while g < bt - 0.05:
                    points.append(g)
                    g += max_shot
            points.append(bt)
    points.append(total)

    order = list(range(len(pool)))
    if ctx.p("order", "sequential") == "shuffle":
        np.random.default_rng(1).shuffle(order)

    match_energy = bool(ctx.p("match_energy", True))
    motion_cache = {}

    def motion_for(path):
        if path not in motion_cache:
            motion_cache[path] = clipmod.motion_curve(path) if match_energy else None
        return motion_cache[path]

    fit = ctx.p("fit", "cover")
    edl = []
    cursor = {}
    recent = []  # clip paths used in the last 2 shots
    for k in range(len(points) - 1):
        t0, t1 = points[k], points[k + 1]
        want = t1 - t0
        if want < 0.05:
            continue

        if match_energy:
            target = _slot_energy(ctx.feat, t0, t1)
            best = None
            for ci in order:
                clip = pool[ci]
                cprev = cursor.get(clip["path"], 0.0)
                start, dur = clipmod.pick_segment(clip, want, cuts_for(clip), cprev)
                mot = clipmod.segment_motion(motion_for(clip["path"]), start, dur)
                score = abs(mot - target) + (0.4 if clip["path"] in recent else 0.0)
                if best is None or score < best[0]:
                    best = (score, clip, start, dur, mot, target)
            if best is None:
                continue
            _s, clip, start, dur, mot, target = best
        else:
            clip = pool[order[k % len(order)]]
            cprev = cursor.get(clip["path"], 0.0)
            start, dur = clipmod.pick_segment(clip, want, cuts_for(clip), cprev)
            mot, target = None, None

        cursor[clip["path"]] = start + dur
        recent = ([clip["path"]] + recent)[:2]
        edl.append(
            {
                "path": clip["path"],
                "start": round(start, 3),
                "dur": round(min(dur, want), 3),
                "fit": fit,
                "motion": round(mot, 3) if mot is not None else None,
                "target_energy": round(target, 3) if target is not None else None,
            }
        )
    return edl


def frames(ctx):  # pragma: no cover - montage uses build_edl, not frames()
    raise RuntimeError("montage is rendered from build_edl(), not frames()")
