"""The intelligent camera: an ordered list of rules that plan one shot.

Each rule is a function `rule(ctx: PlanContext) -> None` that reads the panel
facts and edits the plan in place. Adding a rule is one function plus one
entry in RULES. Rules leave a short plain-language note in `plan.notes` so
the editor can show why the camera did what it did.

All boxes here are panel pixels `[x, y, w, h]`.
"""

import math
from dataclasses import dataclass, field

from . import keys as K

WORDS_PER_SECOND = 2.6


@dataclass
class Line:
    line_id: str
    bubble_id: str
    box: list[float]
    text: str = ""
    kind: str = "speech"
    speaker: str | None = None
    dur: float | None = None  # from script.json when voiced
    pause_after: float = 0.25
    tail: list[float] | None = None


@dataclass
class Character:
    box: list[float]
    face: list[float] | None = None
    facing: str | None = None  # left | right | front
    cast_id: str | None = None


@dataclass
class PanelInfo:
    id: str
    w: int
    h: int
    kind: str = "panel"
    lines: list[Line] = field(default_factory=list)
    characters: list[Character] = field(default_factory=list)
    saliency: list[list[float]] = field(default_factory=list)
    mood: str | None = None
    action: float = 0.0
    scene_id: str | None = None
    location: str | None = None
    has_text: bool = False  # bubbles or captions drawn in the art


@dataclass
class CameraSettings:
    out: tuple[int, int] = (1920, 1080)
    pace: float = 1.0  # >1 faster
    motion_strength: float = 1.0
    allow_flip: bool = False  # mirror a panel to keep screen direction
    text_kept: bool = True  # bubbles kept in the picture (no mirroring then)
    reading: str = "ttb"
    # False for a silent or music-only film: dwell by reading pace, not by
    # the voice clip, so a "just watch" render moves at a readable speed
    voiced: bool = True


@dataclass
class DirectionState:
    """Screen memory across shots: which side each character was on."""

    scene_id: str | None = None
    sides: dict[str, float] = field(default_factory=dict)  # cast_id -> x 0..1
    last_screen_x: float = 0.5


@dataclass
class ShotPlan:
    dur: float = 2.5
    keys: list[dict] = field(default_factory=list)
    lines: list[dict] = field(default_factory=list)  # {line_id, at, dur}
    shake: float = 0.0
    impacts: list[float] = field(default_factory=list)
    flip: bool = False
    notes: list[str] = field(default_factory=list)

    def camera(self) -> dict:
        return {
            "keys": self.keys,
            "shake": round(self.shake, 3),
            "impacts": [round(t, 3) for t in self.impacts],
            "flip": self.flip,
            "auto": True,
            "notes": self.notes,
        }


@dataclass
class PlanContext:
    panel: PanelInfo
    settings: CameraSettings
    state: DirectionState
    next_panel: PanelInfo | None = None
    plan: ShotPlan = field(default_factory=ShotPlan)

    @property
    def src(self) -> tuple[int, int]:
        return (self.panel.w, self.panel.h)

    @property
    def zmax(self) -> float:
        return K.max_zoom_for(
            self.src, self.settings.out, self.settings.motion_strength
        )

    def frame_box(self, box, margin=1.45) -> dict:
        """A key centred on a box, zoomed to fit it."""
        x, y, w, h = box
        z = K.zoom_to_fit(w, h, self.src, self.settings.out, margin)
        return {
            "cx": (x + w / 2) / self.panel.w,
            "cy": (y + h / 2) / self.panel.h,
            "zoom": z,
        }


def line_duration(line: Line, voiced: bool = True) -> float:
    if line.dur and voiced:
        return float(line.dur)
    words = max(1, len(line.text.split()))
    return max(1.1, words / WORDS_PER_SECOND + 0.35)


def _union(a, b):
    x0, y0 = min(a[0], b[0]), min(a[1], b[1])
    x1, y1 = max(a[0] + a[2], b[0] + b[2]), max(a[1] + a[3], b[1] + b[3])
    return [x0, y0, x1 - x0, y1 - y0]


def _center(b):
    return (b[0] + b[2] / 2, b[1] + b[3] / 2)


def _face_or_head(c: Character):
    if c.face:
        return c.face
    x, y, w, h = c.box
    return [x + w * 0.2, y, w * 0.6, max(h * 0.35, 1)]


def _speaker_character(p: PanelInfo, line: Line) -> Character | None:
    if line.speaker:
        for c in p.characters:
            if c.cast_id and c.cast_id == line.speaker:
                return c
    if line.tail and p.characters:
        tx, ty = line.tail
        return min(
            p.characters,
            key=lambda c: math.dist(_center(_face_or_head(c)), (tx, ty)),
        )
    return None


# ---------------------------------------------------------------- rules


def rule_screen_direction(ctx: PlanContext) -> None:
    """Keep screen direction: don't cross the 180-degree line within a scene.

    If two characters seen before swap sides, mirror the panel when that is
    allowed (no text kept in the picture), otherwise open on a single
    character so the swap reads as a new angle rather than a jump.
    """
    p, st = ctx.panel, ctx.state
    if p.scene_id != st.scene_id:
        st.scene_id, st.sides = p.scene_id, {}
    known = [c for c in p.characters if c.cast_id and c.cast_id in st.sides]
    crossed = False
    if len(known) >= 2:
        a, b = known[0], known[1]
        was = st.sides[a.cast_id or ""] - st.sides[b.cast_id or ""]
        now = _center(a.box)[0] - _center(b.box)[0]
        crossed = was * now < 0 and abs(was) > 0.05 and abs(now) > 0.05 * p.w
    if crossed:
        can_flip = ctx.settings.allow_flip and not (
            ctx.settings.text_kept and p.has_text
        )
        if can_flip:
            ctx.plan.flip = True
            _mirror_panel(p)
            ctx.plan.notes.append("mirrored to keep screen direction")
        else:
            ctx.plan.notes.append("characters swapped sides: opening on one character")
            ctx.plan.keys.append({"_single": True})
    for c in p.characters:
        if c.cast_id:
            st.sides[c.cast_id] = _center(c.box)[0] / p.w


def _mirror_panel(p: PanelInfo) -> None:
    def mx(b):
        return [p.w - b[0] - b[2], b[1], b[2], b[3]] if b else b

    for c in p.characters:
        c.box, c.face = mx(c.box), mx(c.face)
        c.facing = {"left": "right", "right": "left"}.get(c.facing or "", c.facing)
    for ln in p.lines:
        ln.box = mx(ln.box)
        if ln.tail:
            ln.tail = [p.w - ln.tail[0], ln.tail[1]]
    p.saliency = [[p.w - s[0], s[1], *s[2:]] for s in p.saliency]


def rule_timing(ctx: PlanContext) -> None:
    """Dwell on each line for its voiced duration (or words per second)."""
    p, pace = ctx.panel, max(0.2, ctx.settings.pace)
    lead = (0.5 if p.action < 0.6 else 0.35) / pace
    t = lead
    for ln in p.lines:
        d = line_duration(ln, ctx.settings.voiced)
        ctx.plan.lines.append(
            {
                "line_id": ln.line_id,
                "bubble_id": ln.bubble_id,
                "at": round(t, 3),
                "dur": d,
            }
        )
        t += d + max(0.1, ln.pause_after) / pace
    tail = 0.45 / pace
    base = {"splash": 3.4, "transition": 1.2, "caption-only": 2.0}.get(p.kind, 2.4)
    if p.action >= 0.6 and not p.lines:
        base = 1.9
    ctx.plan.dur = round(max(base / pace, t + tail), 3)


def rule_establish(ctx: PlanContext) -> None:
    """Open on the whole panel, or tilt down a tall webtoon panel."""
    single = bool(ctx.plan.keys and ctx.plan.keys[0].get("_single"))
    ctx.plan.keys = []
    src, out = ctx.src, ctx.settings.out
    tall = (src[1] / src[0]) > (out[1] / out[0]) * 1.6
    if tall:
        z = min(K.cover_zoom(src, out), ctx.zmax)
        ctx.plan.keys = [
            {"t": 0.0, "cx": 0.5, "cy": 0.0, "zoom": z, "_tilt": True},
            {"t": ctx.plan.dur, "cx": 0.5, "cy": 1.0, "zoom": z, "ease": "inout"},
        ]
        ctx.plan.notes.append("tall panel: vertical tilt")
        return
    first = {"t": 0.0, "cx": 0.5, "cy": 0.5, "zoom": 1.0}
    if single and ctx.panel.characters:
        c = ctx.panel.characters[0]
        first = {"t": 0.0, **ctx.frame_box(_face_or_head(c), 2.2), "_subject": 0}
    ctx.plan.keys = [first]


def rule_bubble_walk(ctx: PlanContext) -> None:
    """Walk through the bubbles in reading order, framing each with its speaker."""
    p, plan = ctx.panel, ctx.plan
    if not p.lines:
        return
    tilt = plan.keys and plan.keys[0].get("_tilt")
    z_tilt = plan.keys[0]["zoom"] if tilt else None
    move = min(0.6, 0.45 / max(0.2, ctx.settings.pace))
    keys = [plan.keys[0]]
    for ln, placed in zip(p.lines, plan.lines):
        region = list(ln.box)
        subject = None
        who = _speaker_character(p, ln)
        if who is not None:
            region = _union(region, _face_or_head(who))
            subject = p.characters.index(who)
        k = ctx.frame_box(region, 1.35)
        k["zoom"] = max(1.0, min(k["zoom"], ctx.zmax))
        if z_tilt:
            k["zoom"] = max(k["zoom"], z_tilt)
            k["cx"] = 0.5
        arrive = max(keys[-1]["t"] + move, placed["at"] - 0.05)
        hold = max(arrive + 0.2, placed["at"] + placed["dur"] * 0.9)
        drift = 1 + 0.03 * ctx.settings.motion_strength
        keys.append({"t": arrive, **k, "_subject": subject})
        keys.append(
            {
                "t": hold,
                **k,
                "zoom": k["zoom"] * drift,
                "ease": "linear",
                "_subject": subject,
            }
        )
    end = {**keys[-1], "t": plan.dur, "ease": "inout"}
    if tilt:
        end.update(cy=1.0, zoom=z_tilt)
        cy = 0.0
        for k in keys:  # a webtoon tilt only ever travels down
            cy = max(cy, k["cy"])
            k["cy"] = cy
    keys.append(end)
    plan.keys = [k for k in keys if k["t"] <= plan.dur + 1e-6]
    plan.notes.append(f"walks {len(p.lines)} bubble(s) in reading order")


def rule_subjects(ctx: PlanContext) -> None:
    """With no bubbles: push in on faces, else on the most salient area."""
    p, plan = ctx.panel, ctx.plan
    if p.lines or len(plan.keys) != 1 or plan.keys[0].get("_tilt"):
        return
    region, subject = None, None
    if p.characters:
        faces = [_face_or_head(c) for c in p.characters]
        region = faces[0]
        for f in faces[1:]:
            region = _union(region, f)
        subject = 0 if len(p.characters) == 1 else None
    elif p.saliency:
        pts = sorted(p.saliency, key=lambda s: -(s[2] if len(s) > 2 else 1))[:3]
        sx = sum(s[0] for s in pts) / len(pts)
        sy = sum(s[1] for s in pts) / len(pts)
        region = [sx - p.w * 0.2, sy - p.h * 0.2, p.w * 0.4, p.h * 0.4]
    start = plan.keys[0]
    if region is None:
        end = {
            **start,
            "zoom": start["zoom"] * (1 + 0.08 * ctx.settings.motion_strength),
        }
    else:
        k = ctx.frame_box(region, 1.9)
        z = (
            start["zoom"]
            + (k["zoom"] - start["zoom"]) * 0.45 * ctx.settings.motion_strength
        )
        end = {**k, "zoom": max(1.0, min(z, ctx.zmax)), "_subject": subject}
        u = 0.45 * min(1.0, ctx.settings.motion_strength)
        end["cx"] = start["cx"] + (end["cx"] - start["cx"]) * u
        end["cy"] = start["cy"] + (end["cy"] - start["cy"]) * u
    end.update(t=plan.dur, ease="inout")
    plan.keys.append(end)


def rule_lead_room(ctx: PlanContext) -> None:
    """Leave space in front of a character who faces left or right."""
    p = ctx.panel
    for k in ctx.plan.keys:
        i = k.get("_subject")
        if i is None or i >= len(p.characters):
            continue
        facing = p.characters[i].facing
        if facing not in ("left", "right"):
            continue
        vw, _ = K.view_size(k["zoom"], ctx.src, ctx.settings.out)
        shift = 0.1 * vw / p.w
        k["cx"] = k["cx"] + (shift if facing == "right" else -shift)
    if any(k.get("_subject") is not None for k in ctx.plan.keys):
        ctx.plan.notes.append("lead room toward facing direction")


def rule_mood(ctx: PlanContext) -> None:
    """Calm drifts, action punches in with shake, splash panels reveal."""
    p, plan, s = ctx.panel, ctx.plan, ctx.settings.motion_strength
    keys = plan.keys
    if p.kind == "splash" and not keys[0].get("_tilt"):
        target = keys[1] if len(keys) > 1 else keys[0]
        tight = {**target, "zoom": min(ctx.zmax, max(target["zoom"], 1.0 + 0.9 * s))}
        reveal_t = plan.dur * 0.55
        plan.keys = [{**tight, "t": 0.0}, {**keys[0], "t": reveal_t, "zoom": 1.0}]
        plan.keys += [
            {**k, "t": max(k["t"], reveal_t + 0.3)}
            for k in keys[1:]
            if k["t"] > reveal_t
        ]
        if plan.keys[-1]["t"] < plan.dur:
            plan.keys.append({**plan.keys[-1], "t": plan.dur, "ease": "linear"})
        plan.notes.append("splash: reveal")
        return
    if p.action >= 0.6 or p.mood == "action":
        a = max(p.action, 0.6)
        plan.shake = round(0.15 + 0.5 * a * s, 3)
        k0 = keys[0]
        hit = min(0.25, plan.dur * 0.15)
        punch = {**k0, "t": hit, "zoom": k0["zoom"] * (1 + 0.22 * s), "ease": "out"}
        punch["rot"] = 1.2 * s * (1 if len(p.id) % 2 else -1)
        settle = {**k0, "t": hit + 0.35, "zoom": k0["zoom"] * (1 + 0.1 * s), "rot": 0}
        rest = [k for k in keys[1:] if k["t"] > settle["t"]]
        plan.keys = [k0, punch, settle] + rest
        if plan.keys[-1]["t"] < plan.dur:
            plan.keys.append({**plan.keys[-1], "t": plan.dur})
        plan.impacts = [hit]
        plan.notes.append("action: punch-in and shake")
        return
    if p.mood in ("calm", "sad", "tense", "mystery") and len(keys) >= 2:
        last = keys[-1]
        rate = {"calm": 0.04, "sad": 0.05, "tense": 0.08, "mystery": -0.06}[
            p.mood or ""
        ]
        if p.mood == "mystery" and len(keys) == 2:
            keys[0], keys[1] = {**keys[1], "t": 0.0}, {**keys[0], "t": plan.dur}
            plan.notes.append("mystery: slow pull-back")
        else:
            last["zoom"] = last["zoom"] * (1 + rate * s)
            for k in keys[1:]:
                k.setdefault("ease", "inout")
            plan.notes.append(f"{p.mood}: slow drift")


def rule_eye_trace(ctx: PlanContext) -> None:
    """Start near where the eye was; end leaning toward what comes next."""
    keys, st = ctx.plan.keys, ctx.state
    if len(keys) >= 2 and not keys[0].get("_tilt"):
        keys[0]["cx"] += (st.last_screen_x - 0.5) * 0.08 * ctx.settings.motion_strength
    nxt = ctx.next_panel
    if nxt is not None and nxt.characters and len(keys) >= 2:
        nx = _center(_face_or_head(nxt.characters[0]))[0] / max(1, nxt.w)
        keys[-1]["cx"] += (nx - 0.5) * 0.06 * ctx.settings.motion_strength


TEXT_SAFE_MARGIN = 1.06  # a little air around a bubble or caption
WIDE_STRIP_ASPECT = 2.4  # wider than this, a panel is a title or caption bar
TEXT_SAFE_LEAD = 0.35  # the camera must already hold the text this long before


def _lines_at(ctx: PlanContext, t: float) -> list[Line]:
    """The bubbles or captions being read at time t.

    Uses the timing rule's plan lines when it has run; with no timings every
    line in the panel counts, because any of them could be on screen.
    """
    timed = ctx.plan.lines
    if not timed:
        return list(ctx.panel.lines)
    by_id = {ln.line_id: ln for ln in ctx.panel.lines}
    out = []
    for item in timed:
        at = float(item.get("at", 0.0))
        dur = float(item.get("dur", 0.0))
        if at - TEXT_SAFE_LEAD <= t <= at + dur + 0.2:
            ln = by_id.get(str(item.get("line_id") or ""))
            if ln is not None:
                out.append(ln)
    return out


def _overlaps(box, rect) -> bool:
    x, y, w, h = box
    x0, y0, x1, y1 = rect
    return x < x1 and x + w > x0 and y < y1 and y + h > y0


def _safe_margin(plan: ShotPlan) -> float:
    """The margin the text needs, allowing for what the renderer adds later.

    A shot with shake is drawn about 6% larger than the planned frame, and the
    frame wanders by a further percent or two (see RenderContext.matrix and
    keys.shake_offset). Without this, a caption framed to the pixel comes back
    sliced in the finished film.
    """
    margin = TEXT_SAFE_MARGIN
    shake = max(0.0, float(plan.shake))
    if shake > 0 or plan.impacts:
        margin *= 1.0 + 0.06 * min(1.0, shake + 0.3)
        margin *= 1.0 + 0.02 + (0.05 if plan.impacts else 0.0)
    return margin


def rule_strip_stays_whole(ctx: PlanContext) -> None:
    """A short, very wide panel is shown whole and still.

    A strip wider than about 2.4:1 is nearly always a title, a credit line or a
    caption bar, and it already spans the frame edge to edge, so any push-in
    or shake cuts its ends off -- the film's own logo lost its last letter this
    way. Lettering the OCR cannot read (a stylised logo) has no text box for
    the text-safe rule to protect, so the shape of the panel decides instead.
    """
    src = ctx.src
    if src[1] <= 0 or src[0] / src[1] < WIDE_STRIP_ASPECT or not ctx.plan.keys:
        return
    out = ctx.settings.out
    portrait = out[1] > out[0]
    for k in ctx.plan.keys:
        k["cx"], k["cy"], k["zoom"] = 0.5, 0.5, 1.0
        if portrait:
            # in a 9:16 frame a wide strip fills the width exactly and its
            # lettering touches the frame edge; a little air fixes that
            k["zoom"], k["_air"] = 0.94, True
    ctx.plan.shake = 0.0
    ctx.plan.impacts = []
    ctx.plan.notes.append("wide strip: held whole" + (" with air" if portrait else ""))


def rule_text_safe(ctx: PlanContext) -> None:
    """Never crop the words.

    A push-in planned for the drawing can leave a caption box half outside the
    frame, which makes the line unreadable and looks like a mistake. For every
    key this pulls the zoom back (never in) and nudges the centre until two
    things hold: the text being read at that moment is fully in view, and no
    other bubble is sliced by the frame edge. Text far outside the view is
    left alone, so a close push-in on a face still happens when no text is
    near it. With bubbles erased and subtitles burned in instead, the drawn
    text does not matter and this rule does nothing.
    """
    if not ctx.settings.text_kept or not ctx.panel.lines or not ctx.plan.keys:
        return
    src, out = ctx.src, ctx.settings.out
    margin = _safe_margin(ctx.plan)
    changed = False
    for k in ctx.plan.keys:
        reading = _lines_at(ctx, float(k.get("t", 0.0)))
        for _ in range(3):  # pulling back can bring another bubble into view
            vw, vh = K.view_size(float(k.get("zoom", 1.0)), src, out)
            cx, cy = float(k.get("cx", 0.5)) * src[0], float(k.get("cy", 0.5)) * src[1]
            rect = (cx - vw / 2, cy - vh / 2, cx + vw / 2, cy + vh / 2)
            want = [
                ln for ln in ctx.panel.lines if ln in reading or _overlaps(ln.box, rect)
            ]
            if not want:
                break
            box = want[0].box
            for ln in want[1:]:
                box = _union(box, ln.box)
            x, y, w, h = box
            zoom = float(k.get("zoom", 1.0))
            fit = K.zoom_to_fit(w, h, src, out, margin)
            new_zoom = max(1.0, min(zoom, fit))
            vw, vh = K.view_size(new_zoom, src, out)
            for name, c, lo, hi, size, middle in (
                ("cx", cx, x + w - vw / 2, x + vw / 2, src[0], x + w / 2),
                ("cy", cy, y + h - vh / 2, y + vh / 2, src[1], y + h / 2),
            ):
                # lo > hi means the box is still bigger than the view (the zoom
                # floor of 1.0 bound); then centre on it and show what fits.
                k[name] = round((middle if lo > hi else min(hi, max(lo, c))) / size, 4)
            done = abs(new_zoom - zoom) < 1e-6
            if not done:
                changed = True
            k["zoom"] = round(new_zoom, 4)
            if done:
                break
    if changed:
        ctx.plan.notes.append("pulled back so the text stays in frame")


def rule_clamp(ctx: PlanContext) -> None:
    """Final pass: every key inside the panel, in time order, rounded."""
    out = []
    for k in sorted(ctx.plan.keys, key=lambda k: k.get("t", 0.0)):
        c = K.clamp_key(k, ctx.src, ctx.settings.out, ctx.zmax)
        key = {
            "t": round(min(max(0.0, k.get("t", 0.0)), ctx.plan.dur), 3),
            "cx": round(c["cx"], 4),
            "cy": round(c["cy"], 4),
            "zoom": round(c["zoom"], 4),
            "rot": round(c["rot"], 2),
        }
        if k.get("ease") and k.get("ease") != "inout":
            key["ease"] = k["ease"]
        if k.get("_air"):
            key["_air"] = True
        out.append(
            K.clamp_key(key, ctx.src, ctx.settings.out, ctx.zmax) | {"t": key["t"]}
        )
    for k in out:
        k.pop("_air", None)
        for f in ("cx", "cy", "zoom"):
            k[f] = round(k[f], 4)
    ctx.state.last_screen_x = out[-1]["cx"] if out else 0.5
    ctx.plan.keys = out


RULES = (
    rule_screen_direction,
    rule_timing,
    rule_establish,
    rule_bubble_walk,
    rule_subjects,
    rule_lead_room,
    rule_mood,
    rule_eye_trace,
    rule_text_safe,
    rule_strip_stays_whole,  # after text_safe: the whole strip is always text-safe
    rule_clamp,
)


def plan_shot(
    panel: PanelInfo,
    settings: CameraSettings,
    state: DirectionState | None = None,
    next_panel: PanelInfo | None = None,
) -> ShotPlan:
    ctx = PlanContext(panel, settings, state or DirectionState(), next_panel)
    for rule in RULES:
        rule(ctx)
    return ctx.plan
