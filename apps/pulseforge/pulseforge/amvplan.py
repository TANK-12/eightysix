"""
The planner: a song, a folder of clips and an editing style in -- an edit out.

This is where the three new layers meet. `musicmap` says where the beats, bars,
sections and drops are; `shotdna` says what every stretch of every clip looks
like; `editstyles` says what this style wants at each moment. The planner turns
that into an edit decision list -- which piece of which clip plays when, what
effects fire on it, what goes between it and the next shot.

Two parts are worth reading before changing anything.

**Where the cuts go.** Shot lengths are measured in *bars*, not seconds, and
every cut is snapped to the beat grid. That is the difference between an edit
that sits in the music and one that drifts against it: at 128 BPM a "two second"
shot is 4.27 beats and is wrong every single time, while two bars is right at
any tempo. The style names a pace per section kind, so the same style tightens
into the chorus and lets go through the breakdown without anything special
being written for that song.

**Which shot goes where.** Not greedily. Every slot is scored against every
candidate stretch of footage -- how well its business matches the music's energy
at that moment, whether it is the close-up or the wide shot the style asked for,
whether it is sharp enough to be worth showing -- and then the whole assignment
is solved *at once* with the Hungarian algorithm, which finds the arrangement
with the lowest total cost over the entire video. A greedy pass takes the best
shot for the first slot and leaves the second slot with whatever is left; solving
it globally will happily give slot one its second-best shot when that frees the
perfect one for slot two. The practical effect is that the same clips get spread
across the video instead of the strongest few being used up in the first chorus.

Continuity -- matching the direction the camera is already travelling across a
cut -- cannot go in that matrix, because the cost of a shot then depends on its
neighbour and the problem stops being an assignment. It is a second pass:
adjacent shots are swapped where the swap improves the join, and the transitions
are chosen afterwards from the motion that ended up either side of each cut.
"""

import math

import numpy as np

from . import beatfx, clips as clipmod, editstyles, shotdna

try:  # scipy is a dependency, but a missing one must not take the app down
    from scipy.optimize import linear_sum_assignment
except Exception:  # pragma: no cover
    linear_sum_assignment = None

MAX_SLOTS = 900  # a 5-minute video cut every third of a second
MAX_CANDIDATES = 1400
CANDIDATE_STRIDE = 0.75  # seconds between candidate start points within a clip


# --------------------------------------------------------------------------
# where the cuts go
# --------------------------------------------------------------------------
def _snap(t, grid):
    """The grid time nearest `t`, or `t` itself if the grid is empty."""
    if grid is None or len(grid) == 0:
        return t
    i = int(np.searchsorted(grid, t))
    best = None
    for j in (i - 1, i, i + 1):
        if 0 <= j < len(grid):
            d = abs(grid[j] - t)
            if best is None or d < best[0]:
                best = (d, float(grid[j]))
    return best[1] if best else t


def cut_points(music, style, duration, min_shot=0.25, max_shot=12.0, intensity=1.0):
    """Times, in seconds, where a shot starts. Always begins at 0 and ends at
    `duration`.

    Shot length comes from the style in bars and is scaled by `intensity`:
    turning intensity up shortens every shot in proportion, which is the one
    control that changes the feel of the whole edit."""
    bar = float(music.get("bar_seconds") or 0.0)
    beats = np.asarray(music.get("beats") or [], dtype=float)
    downbeats = np.asarray(music.get("downbeats") or [], dtype=float)
    sections = music.get("sections") or []

    if bar <= 0.05 or beats.size < 4:
        # No usable pulse: fall back to an even grid rather than refusing.
        step = float(np.clip(2.0 / max(0.2, intensity), min_shot, max_shot))
        pts = list(np.arange(0.0, max(step, duration), step))
        return sorted(set([0.0] + [p for p in pts if 0 < p < duration - 0.05])) + [
            duration
        ]

    # Snap to the bar line where a shot is a whole number of bars, to the beat
    # where it is a fraction of one; a half-bar cut that snapped to the bar
    # would collapse back onto the downbeat and halve the cut rate silently.
    pts = [0.0]
    t = 0.0
    guard = 0
    while t < duration - min_shot and guard < MAX_SLOTS * 2:
        guard += 1
        sec = None
        for s in sections:
            if s["start"] <= t < s["end"]:
                sec = s
                break
        kind = (sec or {}).get("kind", "verse")
        bars = editstyles.pace_for(style, kind) / max(0.15, intensity)
        step = float(np.clip(bars * bar, min_shot, max_shot))
        nxt = t + step
        grid = downbeats if bars >= 1.0 else beats
        snapped = _snap(nxt, grid)
        # never let snapping stall or reverse the walk
        if snapped <= t + min_shot * 0.5:
            snapped = t + step
        t = snapped
        if t < duration - min_shot * 0.5:
            pts.append(float(t))

    if style.get("cut_on_vocal"):
        pts = _add_vocal_entries(pts, music, min_shot, duration)

    pts = sorted(set(round(p, 4) for p in pts if 0 <= p < duration))
    pts.append(float(duration))
    return pts[: MAX_SLOTS + 1]


def _add_vocal_entries(pts, music, min_shot, duration):
    """Extra cuts where the singing comes back in after a gap.

    A lyric-led edit changes picture when the voice changes, not when the drum
    hits. `musicmap.vocal` is a rough per-frame flag, so only the *entries* are
    used -- the moment it turns on after being off for a while, which is
    reliable even when the flag itself is noisy."""
    vocal = np.asarray(
        music.get("vocal") if music.get("vocal") is not None else [], dtype=bool
    )
    fps = float(music.get("fps") or 30.0)
    if vocal.size < 4:
        return pts
    beats = np.asarray(music.get("beats") or [], dtype=float)
    on = np.where((~vocal[:-1]) & (vocal[1:]))[0] + 1
    gap = int(fps * 1.5)
    last = -gap
    extra = []
    for i in on:
        if i - last < gap:
            continue
        last = int(i)
        extra.append(_snap(float(i) / fps, beats))
    out = list(pts)
    for e in extra:
        if 0 < e < duration - min_shot and all(abs(e - p) >= min_shot for p in out):
            out.append(float(e))
    return sorted(out)


# --------------------------------------------------------------------------
# candidates
# --------------------------------------------------------------------------
MIN_USABLE = 0.4  # a stretch of footage shorter than this is never worth a shot


def build_candidates(dna_by_path, stat_window, stride=CANDIDATE_STRIDE):
    """Every stretch of footage that could fill a slot, with how much of the
    clip is left after it.

    Starts are taken from each clip's own scene changes first -- a shot that
    begins where the footage begins reads as deliberate -- and then from an even
    grid so a clip with no detected cuts still contributes.

    `available` is the important field. Candidates are deliberately *not*
    filtered by length here: a clip too short for the four-bar shots in an
    intro may be exactly right for the half-bar shots in the chorus, and
    throwing it out of the pool loses it everywhere. `slot_cost` prices the
    shortfall per slot instead."""
    out = []
    for path, dna in (dna_by_path or {}).items():
        segs = dna.get("segments") or []
        if not segs:
            continue
        dur = float(dna.get("duration") or 0.0)
        if dur < MIN_USABLE:
            continue
        starts = [c for c in (dna.get("cuts") or []) if dur - c >= MIN_USABLE]
        g = 0.0
        while dur - g >= MIN_USABLE:
            starts.append(g)
            g += stride
        seen = set()
        for s in sorted(starts):
            k = round(s, 2)
            if k in seen:
                continue
            seen.add(k)
            st = shotdna.window_stats(dna, s, min(stat_window, dur - s))
            if not st:
                continue
            out.append(
                {
                    "path": path,
                    "start": float(s),
                    "stats": st,
                    "letterbox": dna.get("letterbox") or {},
                    "clip_duration": dur,
                    "available": float(dur - s),
                }
            )
    if len(out) > MAX_CANDIDATES:
        idx = np.linspace(0, len(out) - 1, MAX_CANDIDATES).astype(int)
        out = [out[i] for i in idx]
    return out


# --------------------------------------------------------------------------
# scoring
# --------------------------------------------------------------------------
SCALE_ORDER = {"close": 0, "medium": 1, "wide": 2}


def slot_cost(slot, cand):
    """How badly this stretch of footage suits this moment of the song.

    Every term is on the same 0..1 footing before it is weighted, so the weights
    below are readable as priorities: matching the energy matters most, then
    showing the kind of shot the style asked for, then not showing something
    blurry or black."""
    st = cand["stats"]
    want = slot["prefer"]
    cost = 0.0

    target = float(want.get("action", 0.5))
    cost += 2.0 * abs(float(st.get("action", 0.5)) - target)

    scale = want.get("scale")
    if scale and scale != "any":
        got = SCALE_ORDER.get(st.get("shot_scale", "medium"), 1)
        cost += 0.45 * abs(SCALE_ORDER.get(scale, 1) - got)

    cost += float(want.get("quality", 0.7)) * (1.0 - float(st.get("quality", 0.5)))

    # Not enough footage left in the clip to fill this slot. Priced steeply,
    # because the consequence is not a slightly worse match: the shot runs out
    # and the picture freezes, or -- when it is being cross-faded into the next
    # one -- the whole chain stops there and the video ends early. That is
    # exactly what happened on the first end-to-end render.
    need = float(slot.get("need", slot.get("dur", 0.0)))
    have = float(cand.get("available", 1e9))
    if have < need:
        cost += 4.0 + 2.0 * (need - have) / max(0.2, need)

    # Nothing black and nothing white: both are usually a fade caught mid-way.
    b = float(st.get("brightness", 0.5))
    if b < 0.06:
        cost += 1.2
    elif b > 0.97:
        cost += 0.8

    return float(cost)


def _continuity(a, b):
    """0 (a jarring join) .. 1 (movement carries across the cut).

    Two shots travelling the same way cut together cleanly; two travelling
    opposite ways fight. Still shots are neutral rather than good, so this never
    pushes the edit towards using nothing but locked-off footage."""
    if not a or not b:
        return 0.5
    ax, ay = float(a.get("flow_dx", 0)), float(a.get("flow_dy", 0))
    bx, by = float(b.get("flow_dx", 0)), float(b.get("flow_dy", 0))
    ma, mb = math.hypot(ax, ay), math.hypot(bx, by)
    if ma < 0.02 or mb < 0.02:
        return 0.5
    dot = (ax * bx + ay * by) / (ma * mb)
    return float((dot + 1.0) / 2.0)


def assign_shots(slots, cands, reuse_penalty=0.55, no_repeat=True):
    """Which candidate fills which slot, solved for the whole video at once.

    The matrix is widened by repeating the candidate list until there are at
    least as many columns as slots, each repeat costing `reuse_penalty` more
    than the last. That is what lets a nine-clip folder fill a two-hundred-shot
    edit: reuse is allowed, it is just never free, so the solver spends the
    fresh footage first and comes back round only when it has to."""
    n, m = len(slots), len(cands)
    if n == 0 or m == 0:
        return []
    reps = max(1, math.ceil(n / m) + 1)
    base = np.array([[slot_cost(s, c) for c in cands] for s in slots], dtype=np.float64)
    cost = np.concatenate([base + reuse_penalty * r for r in range(reps)], axis=1)

    if linear_sum_assignment is not None and cost.size <= 4_000_000:
        rows, cols = linear_sum_assignment(cost)
        picked = [int(c % m) for _, c in sorted(zip(rows, cols))]
    else:  # pragma: no cover - only without scipy or on an enormous edit
        picked, used = [], {}
        for i in range(n):
            row = base[i] + np.array([reuse_penalty * used.get(j, 0) for j in range(m)])
            j = int(np.argmin(row))
            used[j] = used.get(j, 0) + 1
            picked.append(j)

    if no_repeat:
        picked = spread_repeats(picked, cands, slots, base)
    return picked


def spread_repeats(picked, cands, slots, base=None, tolerance=0.9):
    """Stop the same footage appearing twice running.

    The assignment cannot see this: the cost of a shot depends on the shot
    before it, which is exactly what an assignment problem is not allowed to
    do. So it is repaired afterwards, and repaired by *re-picking* rather than
    by swapping. Swapping only helps when some other slot happens to want the
    shot being moved; on a small clip folder -- four clips filling seventy
    shots -- there is nothing to swap with and every cut lands on the same
    footage.

    Three attempts, in order of how much they cost the edit:

    1. a stretch of a **different clip** whose score is within `tolerance`;
    2. failing that, a **distant part of the same clip**, which at least
       changes the picture;
    3. failing that, mark it to be **mirrored**, so a genuinely unavoidable
       repeat is at least not the identical frame twice.

    A folder with one usable clip still produces an edit. It just produces an
    honest one, and `summary.repeats_back_to_back` says so."""
    out = list(picked)
    if base is None:
        base = np.array(
            [[slot_cost(sl, c) for c in cands] for sl in slots], dtype=np.float64
        )
    mirrored = set()
    by_path = {}
    for j, c in enumerate(cands):
        by_path.setdefault(c["path"], []).append(j)

    for i in range(1, len(out)):
        prev, cur = cands[out[i - 1]], cands[out[i]]
        same_clip = cur["path"] == prev["path"]
        overlapping = same_clip and abs(cur["start"] - prev["start"]) < max(
            0.5, slots[i]["dur"] * 0.75
        )
        if not same_clip:
            continue

        # 1. a different clip. Tried twice: first only if it is nearly as good
        # a match, and then, if nothing was, at a much looser bar. The second
        # pass is the important one -- when the choice is between footage whose
        # energy is wrong and the identical footage twice in a row, the wrong
        # energy is the smaller mistake, and refusing it is how a four-clip
        # folder ends up cutting seventy shots from one clip.
        row = base[i]
        best = None
        for limit in (tolerance, tolerance * 3.0):
            best_cost = row[out[i]] + limit
            for path, idxs in by_path.items():
                if path == prev["path"]:
                    continue
                for j in idxs:
                    if row[j] < best_cost:
                        best, best_cost = j, row[j]
            if best is not None:
                break
        if best is not None:
            out[i] = best
            continue

        # 2. a different part of the same clip
        if overlapping:
            far = [
                j
                for j in by_path.get(cur["path"], [])
                if abs(cands[j]["start"] - prev["start"]) >= max(1.0, slots[i]["dur"])
            ]
            if far:
                out[i] = min(far, key=lambda j: row[j])
                continue

        # 3. nothing else available -- flip it so it is not the same frames
        mirrored.add(i)

    for i in mirrored:
        slots[i]["mirror"] = True
    return out


# --------------------------------------------------------------------------
# effects and transitions
# --------------------------------------------------------------------------
def _events_in(times, t0, t1):
    return [round(float(t) - t0, 4) for t in (times or []) if t0 - 1e-6 <= t < t1]


def events_for(on, music, t0, t1, starts_section):
    """The times, relative to the shot, that this trigger fires at."""
    if on == "shot_start":
        return [0.0]
    if on == "section_start":
        return [0.0] if starts_section else []
    if on == "none":
        return []
    if on == "beat":
        return _events_in(music.get("beats"), t0, t1)
    if on == "downbeat":
        return _events_in(music.get("downbeats"), t0, t1)
    if on == "bar2":
        return _events_in(music.get("downbeats"), t0, t1)[::2]
    if on == "hit":
        return _events_in(music.get("hits"), t0, t1)
    if on == "drop":
        return _events_in(music.get("drops"), t0, t1)
    return []


def _scaled(params, intensity):
    """Turn every strength-like parameter up or down together."""
    out = dict(params or {})
    for k in ("amount", "degrees", "sigma", "height"):
        if k in out:
            try:
                out[k] = float(out[k]) * intensity
            except (TypeError, ValueError):
                pass
    return out


def pick_transition(style, starts_section, has_drop, prev_stats):
    """Which transition goes into this shot, and how long it lasts."""
    tr = style.get("transition") or {}
    name = tr.get("default", "cut")
    if has_drop and tr.get("on_drop"):
        name = tr["on_drop"]
    elif starts_section and tr.get("on_section"):
        name = tr["on_section"]
    if name == "whip":
        # Match the direction the outgoing shot was already travelling, so the
        # wipe reads as one continuous movement rather than as an effect.
        dx = float((prev_stats or {}).get("flow_dx", 0.0))
        name = "whip_left" if dx < 0 else "whip_right"
    meta = editstyles.TRANSITIONS.get(name) or editstyles.TRANSITIONS["cut"]
    return meta["id"], int(meta["ms"])


# --------------------------------------------------------------------------
# the whole plan
# --------------------------------------------------------------------------
def plan(music, dna_by_path, style, duration, opts=None):
    """The edit decision list, plus a summary of what was decided and why."""
    opts = dict(opts or {})
    intensity = float(np.clip(opts.get("intensity", 1.0), 0.2, 2.5))
    min_shot = float(opts.get("min_shot", 0.25))
    max_shot = float(opts.get("max_shot", 12.0))
    fit = opts.get("fit", "cover")
    crop_bars = bool(opts.get("crop_letterbox", True))

    pts = cut_points(music, style, duration, min_shot, max_shot, intensity)
    sections = music.get("sections") or []
    section_starts = {round(float(s["start"]), 2) for s in sections}
    drops = list(music.get("drops") or [])

    slots = []
    for i in range(len(pts) - 1):
        t0, t1 = float(pts[i]), float(pts[i + 1])
        if t1 - t0 < min_shot * 0.5:
            continue
        kind = "verse"
        for s in sections:
            if s["start"] <= t0 < s["end"]:
                kind = s.get("kind", "verse")
                break
        sp = style.get("speed") or {}
        slot_speed = (
            float(sp["drop"])
            if (any(t0 <= d < t1 for d in drops) and "drop" in sp)
            else 1.0
        )
        slots.append(
            {
                "t0": t0,
                "t1": t1,
                "dur": t1 - t0,
                "speed": slot_speed,
                "need": (t1 - t0) * slot_speed,
                "kind": kind,
                "prefer": editstyles.prefer_for(style, kind),
                "starts_section": any(abs(t0 - x) < 0.12 for x in section_starts),
                "has_drop": any(t0 <= d < t1 for d in drops),
            }
        )
    if not slots:
        return {"shots": [], "summary": {"reason": "no cut points"}}

    # One candidate pool, sized for the commonest slot length. Slots longer than
    # that reuse the same starts and simply run on further into the clip.
    want = float(np.median([s["dur"] for s in slots]))
    cands = build_candidates(dna_by_path, max(0.4, min(want, 4.0)))
    longest_available = max((c["available"] for c in cands), default=0.0)
    if not cands:
        return {"shots": [], "summary": {"reason": "no usable clips"}}

    picked = assign_shots(
        slots, cands, reuse_penalty=float(opts.get("reuse_penalty", 0.55))
    )

    shots = []
    prev_stats = None
    short_shots = 0
    for i, slot in enumerate(slots):
        cand = cands[picked[i]]
        st = cand["stats"]
        speed = float(slot.get("speed", 1.0))
        src_need = slot["dur"] * speed
        # Pull the start back if that is all it takes to fit the shot in.
        start = min(cand["start"], max(0.0, cand["clip_duration"] - src_need))
        short = max(0.0, src_need - (cand["clip_duration"] - start))
        if short > 0.02:
            short_shots += 1

        fx = []
        for entry in editstyles.fx_for(style, slot["kind"]):
            ev = events_for(
                entry.get("on", "shot_start"),
                music,
                slot["t0"],
                slot["t1"],
                slot["starts_section"],
            )
            if (
                entry.get("on") not in ("none", "shot_start", "section_start")
                and not ev
            ):
                continue
            if entry.get("on") == "section_start" and not ev:
                continue
            fx.append(
                {
                    "id": entry["id"],
                    "events": ev,
                    "params": _scaled(entry.get("params"), intensity),
                }
            )

        if slot.get("mirror"):
            fx.append({"id": "mirror", "events": [], "params": {"on": True}})

        tname, tms = pick_transition(
            style, slot["starts_section"], slot["has_drop"], prev_stats
        )
        if i == 0:
            tname, tms = "cut", 0

        shots.append(
            {
                "path": cand["path"],
                "start": round(float(start), 3),
                "dur": round(float(slot["dur"]), 3),
                "src_dur": round(float(src_need), 3),
                "speed": round(float(speed), 4),
                "fit": fit,
                "letterbox": cand["letterbox"] if crop_bars else {},
                "fx": fx,
                "transition": tname,
                "transition_ms": tms,
                "section": slot["kind"],
                "starts_section": slot["starts_section"],
                "at": round(slot["t0"], 3),
                "continuity": round(_continuity(prev_stats, st), 3),
                "short_by": round(float(short), 3),
                "look": shotdna.describe(st),
                "action": round(float(st.get("action", 0)), 3),
                "target_action": round(float(slot["prefer"].get("action", 0.5)), 3),
            }
        )
        prev_stats = st

    used = {s["path"] for s in shots}
    summary = {
        "shots": len(shots),
        "clips_used": len(used),
        "clips_available": len(dna_by_path or {}),
        "bpm": music.get("bpm"),
        "bar_seconds": music.get("bar_seconds"),
        "sections": len(sections),
        "mean_shot": round(float(np.mean([s["dur"] for s in shots])), 3),
        "shortest": round(float(np.min([s["dur"] for s in shots])), 3),
        "longest": round(float(np.max([s["dur"] for s in shots])), 3),
        "mean_continuity": round(float(np.mean([s["continuity"] for s in shots])), 3),
        "repeats_back_to_back": sum(
            1 for i in range(1, len(shots)) if shots[i]["path"] == shots[i - 1]["path"]
        ),
        "style": style.get("id"),
        "intensity": intensity,
        "solver": "hungarian" if linear_sum_assignment is not None else "greedy",
        # Shots the footage could not fill. The render holds the last frame
        # rather than ending early, but it is worth saying out loud: it means
        # the clips are shorter than the shot length this style asks for.
        "shots_short_of_footage": short_shots,
        "longest_clip_seconds": round(longest_available, 2),
    }
    return {"shots": shots, "summary": summary}


def scan_and_analyse(pool_dir, progress=None, max_seconds=0):
    """Every clip in a folder, measured. The slow step, and fully cached."""
    paths = clipmod.scan_pool(pool_dir)
    if not paths:
        return {}
    return shotdna.analyse_pool(paths, max_seconds=max_seconds, progress=progress)


__all__ = [
    "plan",
    "cut_points",
    "build_candidates",
    "assign_shots",
    "spread_repeats",
    "slot_cost",
    "events_for",
    "pick_transition",
    "scan_and_analyse",
]
