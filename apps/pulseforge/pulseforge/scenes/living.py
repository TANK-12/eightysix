"""
Living Still -- a background that mostly holds still while marked parts of it move.

This is the scene the whole living-still workflow renders through. A shot is a
background image, optionally some transparent images stacked on it, a set of
marked regions each running a motion effect, and some emitters throwing
particles or creatures across the frame. Everything is drawn in depth order, so
birds can pass behind a foreground branch, and then one look pass grades the
result.

Two ways in:

* the **Scenery editor**, which hands over a full shot dict as `_shot`;
* the plain **Compose** tab, which hands over nothing -- and then the scene
  builds a one-shot from the attached image and its own parameters, so it still
  does something sensible with no setup at all.

Nothing here reads the clock directly. Every moving part asks a `LoopClock` for
a phase, which is what lets a whole shot be rendered as a short bed and repeated
underneath a long song with no visible seam.
"""

import numpy as np

from .. import grades, imageops, masks, overlay
from ..emitters import registry as emitter_registry
from ..layers import Backdrop, Camera
from ..looping import LoopClock
from ..motion import registry as motion_registry

SCENE = {
    "id": "living",
    "label": "Living Still",
    "family": "scenery",
    # routes render.py to the shot-and-playlist pipeline instead of the plain
    # one-song frame path -- see render._render_living()
    "pipeline": "living",
    "description": "A still background with only the parts you mark moving -- "
    "clouds crossing the sky, water rippling, hair swaying -- "
    "plus stacked transparent images for real parallax and "
    "sprites drifting through. Built in the Scenery tab.",
    "params": [
        {
            "key": "loop_seconds",
            "group": "shot",
            "label": "Loop length",
            "type": "range",
            "default": 12.0,
            "min": 3.0,
            "max": 60.0,
            "step": 0.5,
            "unit": "s",
            "help": "How much unique motion gets rendered before it repeats.",
        },
        {
            "key": "push",
            "group": "camera",
            "label": "Camera push",
            "type": "range",
            "default": 0.06,
            "min": 0.0,
            "max": 0.4,
            "step": 0.01,
        },
        {
            "key": "drift",
            "group": "camera",
            "label": "Camera drift",
            "type": "range",
            "default": 0.35,
            "min": 0.0,
            "max": 1.0,
            "step": 0.01,
        },
        {
            "key": "parallax",
            "group": "camera",
            "label": "Parallax",
            "type": "range",
            "default": 0.5,
            "min": 0.0,
            "max": 1.0,
            "step": 0.01,
        },
        {
            "key": "focus",
            "group": "depth",
            "label": "Focus depth",
            "type": "range",
            "default": 1.0,
            "min": 0.0,
            "max": 1.0,
            "step": 0.01,
            "help": "Which depth is sharp. 0 is the background, 1 the nearest "
            "stacked layer. Only bites once Aperture is above zero.",
        },
        {
            "key": "aperture",
            "group": "depth",
            "label": "Aperture",
            "type": "range",
            "default": 0.0,
            "min": 0.0,
            "max": 1.0,
            "step": 0.01,
            "help": "How hard everything off the focus plane blurs.",
        },
        {
            "key": "haze",
            "group": "depth",
            "label": "Distance haze",
            "type": "range",
            "default": 0.0,
            "min": 0.0,
            "max": 1.0,
            "step": 0.01,
            "help": "Fades far layers toward the haze colour -- aerial "
            "perspective, and it costs almost nothing.",
        },
        {
            "key": "haze_color",
            "group": "depth",
            "label": "Haze colour",
            "type": "color",
            "default": "#b9c6de",
        },
        {
            "key": "vignette",
            "group": "grade",
            "label": "Vignette",
            "type": "range",
            "default": 0.3,
            "min": 0.0,
            "max": 1.0,
            "step": 0.01,
        },
        {
            "key": "grain",
            "group": "grade",
            "label": "Grain",
            "type": "range",
            "default": 0.08,
            "min": 0.0,
            "max": 1.0,
            "step": 0.01,
        },
        {
            "key": "bloom",
            "group": "grade",
            "label": "Bloom",
            "type": "range",
            "default": 0.15,
            "min": 0.0,
            "max": 1.0,
            "step": 0.01,
        },
        {
            "key": "saturation",
            "group": "grade",
            "label": "Saturation",
            "type": "range",
            "default": 1.0,
            "min": 0.0,
            "max": 2.0,
            "step": 0.01,
        },
        {
            "key": "warmth",
            "group": "grade",
            "label": "Warmth",
            "type": "range",
            "default": 0.0,
            "min": -1.0,
            "max": 1.0,
            "step": 0.01,
        },
        {
            "key": "grade",
            "group": "grade",
            "label": "Film grade",
            "type": "select",
            "default": "none",
            "options": [],  # filled from grades.py below
            "help": "A whole colour look in one choice.",
        },
        {
            "key": "grade_amount",
            "group": "grade",
            "label": "Grade strength",
            "type": "range",
            "default": 0.7,
            "min": 0.0,
            "max": 1.0,
            "step": 0.01,
        },
        {
            "key": "scanlines",
            "group": "analogue",
            "label": "Scanlines",
            "type": "range",
            "default": 0.0,
            "min": 0.0,
            "max": 1.0,
            "step": 0.01,
            "help": "Fine horizontal lines, the way an old screen or a tape looks.",
        },
        {
            "key": "fringing",
            "group": "analogue",
            "label": "Colour fringing",
            "type": "range",
            "default": 0.0,
            "min": 0.0,
            "max": 1.0,
            "step": 0.01,
            "help": "Red and blue pulled apart toward the edges -- cheap lens "
            "and tape character.",
        },
        {
            "key": "letterbox",
            "group": "analogue",
            "label": "Letterbox bars",
            "type": "range",
            "default": 0.0,
            "min": 0.0,
            "max": 0.3,
            "step": 0.005,
        },
        {
            "key": "leak",
            "group": "analogue",
            "label": "Light leak",
            "type": "range",
            "default": 0.0,
            "min": 0.0,
            "max": 1.0,
            "step": 0.01,
            "help": "A warm bloom drifting in from an edge, like film fog.",
        },
        {
            "key": "leak_color",
            "group": "analogue",
            "label": "Leak colour",
            "type": "color",
            "default": "#ffb066",
        },
        {
            "key": "sky_clouds",
            "group": "shot",
            "label": "Clouds over the top (no editing needed)",
            "type": "range",
            "default": 0.0,
            "min": 0.0,
            "max": 1.0,
            "step": 0.01,
            "help": "A quick cloud pass over the upper part of the frame, for "
            "when you have not marked a sky region yet.",
        },
    ],
}

# the grade picker's options come from the registry, so a new grade appears in
# the editor without touching this file
for _spec in SCENE["params"]:
    if _spec["key"] == "grade":
        _spec["options"] = grades.ids()

_LUMA = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


# --------------------------------------------------------------------------
# shot resolution
# --------------------------------------------------------------------------
def shot_from_ctx(ctx):
    """The shot to render: the editor's, or one improvised from the basics."""
    shot = ctx.p("_shot")
    if shot:
        return dict(shot)

    image = ""
    for a in ctx.assets:
        if str(a).lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp")):
            image = a
            break
    quick = float(ctx.p("sky_clouds") or 0.0)
    layers = []
    if quick > 0.001:
        layers.append(
            {
                "name": "sky",
                "effect": "sky_clouds",
                "region": {
                    "kind": "polygon",
                    "points": [[0, 0], [1, 0], [1, 0.55], [0, 0.55]],
                    "feather": 0.12,
                },
                "params": {"amount": quick * 0.6, "speed": 0.2},
            }
        )
    return {"image": image, "images": [], "layers": layers, "emitters": []}


def _schema_default(key):
    for spec in SCENE["params"]:
        if spec["key"] == key:
            return spec.get("default")
    return None


def _resolve(ctx, key):
    """The shot's value, else the tuned parameter, else the schema default.

    The last step matters: `still()` gets called with whatever the editor has
    saved so far, which is often nothing, and a half-filled parameter dict
    should still render rather than fail.
    """
    v = ctx.p(key)
    return _schema_default(key) if v is None else v


def _look(ctx, shot):
    look = dict(shot.get("look") or {})
    for key in (
        "vignette",
        "grain",
        "bloom",
        "saturation",
        "warmth",
        "focus",
        "aperture",
        "haze",
        "haze_color",
    ):
        if look.get(key) is None:
            look[key] = _resolve(ctx, key)
    return look


def _camera(ctx, shot, live):
    cam = dict(shot.get("camera") or {})
    for key in ("push", "drift", "parallax"):
        if cam.get(key) is None:
            cam[key] = _resolve(ctx, key)
    return Camera(cam, live=live)


class Focus:
    """Depth of field and distance haze.

    Stacked image layers already carry a depth, and until now nothing used it.
    A focus plane plus an aperture turns that number into something you can see:
    layers away from the focus blur in proportion, and far ones optionally fade
    toward a haze colour, which is aerial perspective for almost no cost.

    Region layers are treated as sitting *on* the background, because that is
    what they are -- marked parts of a flat photo. Their own depth still drives
    parallax; it does not pretend to be a separate focal plane.
    """

    def __init__(self, look, h, w):
        self.focus = float(look.get("focus", 1.0) or 0.0)
        self.aperture = float(look.get("aperture", 0.0) or 0.0)
        self.haze = float(look.get("haze", 0.0) or 0.0)
        self.haze_color = overlay.hex_rgb(str(look.get("haze_color", "#b9c6de")))
        self.max_radius = 0.045 * min(h, w)

    def defocus(self, depth):
        if self.aperture <= 0.001:
            return 0.0
        return abs(float(depth) - self.focus) * self.aperture * self.max_radius

    def haze_at(self, depth):
        if self.haze <= 0.001:
            return None
        return (self.haze * (1.0 - float(depth)), self.haze_color)


# --------------------------------------------------------------------------
# the look pass
# --------------------------------------------------------------------------
class Look:
    """Grade, bloom, vignette and grain, precomputed where it can be."""

    def __init__(self, look, h, w, loop_frames, seed=4):
        self.h, self.w = h, w
        self.vignette = float(look.get("vignette", 0.3) or 0.0)
        self.grain = float(look.get("grain", 0.08) or 0.0)
        self.bloom = float(look.get("bloom", 0.15) or 0.0)
        self.saturation = float(look.get("saturation", 1.0) or 1.0)
        self.warmth = float(look.get("warmth", 0.0) or 0.0)

        # the analogue pack: what actually makes output read as "a video" rather
        # than "a picture with an effect on it"
        self.grade = str(look.get("grade", "none") or "none")
        self.grade_amount = float(look.get("grade_amount", 0.7) or 0.0)
        self.scanlines = float(look.get("scanlines", 0.0) or 0.0)
        self.fringing = float(look.get("fringing", 0.0) or 0.0)
        self.letterbox = float(look.get("letterbox", 0.0) or 0.0)
        self.leak = float(look.get("leak", 0.0) or 0.0)
        self.leak_color = overlay.hex_rgb(str(look.get("leak_color", "#ffb066")))

        self._scan = None
        if self.scanlines > 0.001:
            rows = np.arange(h, dtype=np.float32)
            # every other line dimmed, softened so it does not alias into moire
            self._scan = (
                1.0 - self.scanlines * 0.35 * (0.5 + 0.5 * np.cos(np.pi * rows))
            )[:, None, None].astype(np.float32)

        self._bars = None
        if self.letterbox > 0.001:
            bar = max(1, int(self.letterbox * h))
            m = np.ones((h, 1, 1), dtype=np.float32)
            m[:bar] = 0.0
            m[h - bar :] = 0.0
            self._bars = m

        self._fringe = None
        if self.fringing > 0.001:
            # real chromatic aberration grows toward the edges, so this scales
            # red out and blue in about the centre rather than sliding the whole
            # channel sideways. The fields never change, so they are built once.
            amt = self.fringing * 0.005
            box = (0, h, 0, w)
            self._fringe = (
                imageops.zoom_field(box, 1.0 + amt),
                imageops.zoom_field(box, 1.0 - amt),
                box,
            )

        self._leak_field = None
        if self.leak > 0.001:
            gy, gx = imageops.grid((0, h, 0, w))
            # a soft wedge from one corner; the clock moves it, not this
            self._leak_field = (
                np.clip((1.0 - gx) * (1.0 - gy * 0.65), 0.0, 1.0).astype(np.float32)
                ** 2.2
            )

        self._warm = np.array(
            [1.0 + 0.10 * self.warmth, 1.0, 1.0 - 0.10 * self.warmth], dtype=np.float32
        )

        self.vmask = None
        self.vfactor = None
        if self.vignette > 0.001:
            self.vmask = (
                overlay.radial_gradient(h, w, (0, 0, 0), (255, 255, 255), power=1.5)[
                    ..., 0
                ].astype(np.float32)
                / 255.0
            )[..., None]
            self.vfactor = (1.0 - self.vmask * self.vignette).astype(np.float32)

        self.noise = None
        self.offsets = None
        if self.grain > 0.001:
            # one tiling noise field, re-rolled per frame by a fixed sequence:
            # the grain changes every frame but repeats exactly with the loop
            self.noise = imageops.periodic_noise(h, w, cells=64, seed=seed, octaves=1)
            rng = np.random.default_rng(seed + 3)
            # exactly one offset per frame of the *loop*, so the grain is a
            # different pattern every frame but the same sequence every repeat
            self.offsets = rng.integers(0, max(2, min(h, w)), size=(loop_frames, 2))

    _leak_phase = 0.0

    def apply(self, frame, i):
        """Grade in place wherever possible -- at 1080p every stray temporary
        here is eight megabytes, and this runs on every frame."""
        if abs(self.saturation - 1.0) > 0.001:
            grey = (frame @ _LUMA)[..., None]  # matmul beats multiply-then-sum
            frame -= grey
            frame *= self.saturation
            frame += grey
        if abs(self.warmth) > 0.001:
            frame *= self._warm
        if self.grade != "none":
            grades.apply_grade(frame, self.grade, self.grade_amount)
        if self.bloom > 0.001:
            small = frame[::4, ::4]
            bright = np.clip(small - 165.0, 0.0, None)
            blurred = imageops.box_blur(bright, max(2, int(0.006 * self.w)), passes=2)
            up = np.repeat(np.repeat(blurred, 4, axis=0), 4, axis=1)
            sh, sw = min(self.h, up.shape[0]), min(self.w, up.shape[1])
            frame[:sh, :sw] += up[:sh, :sw] * (self.bloom * 1.6)
        if self._fringe is not None:
            (rdx, rdy), (bdx, bdy), box = self._fringe
            frame[..., 0] = imageops.sample(frame, rdx, rdy, box, fast=True)[..., 0]
            frame[..., 2] = imageops.sample(frame, bdx, bdy, box, fast=True)[..., 2]
        if self._leak_field is not None:
            # drifts on the loop clock, so it never breaks the seam
            swing = 0.55 + 0.45 * self._leak_phase
            tint = np.array(self.leak_color, dtype=np.float32)
            frame += (self._leak_field * (self.leak * 95.0 * swing))[..., None] * (
                tint / 255.0
            )
        if self._scan is not None:
            frame *= self._scan
        if self.vmask is not None:
            frame *= self.vfactor
        if self._bars is not None:
            frame *= self._bars
        if self.noise is not None and self.offsets is not None:
            dy, dx = self.offsets[i % len(self.offsets)]
            g = np.roll(np.roll(self.noise, int(dy), axis=0), int(dx), axis=1)
            frame += (g[..., None] - 0.5) * (self.grain * 42.0)
        return frame


# --------------------------------------------------------------------------
# one frame
# --------------------------------------------------------------------------
def render_frame(ctx, shot, backdrop, camera, look, region_layers, tl, i, focus=None):
    frame = backdrop.draw_base(tl, camera, focus.defocus(0.0) if focus else 0.0)
    if focus is not None:
        far = focus.haze_at(0.0)
        if far is not None:
            frame *= 1.0 - far[0]
            frame += np.array(far[1], dtype=np.float32) * far[0]
    zoom, ox, oy = camera.at(tl, ctx.h, ctx.w)
    bgx, bgy = camera.depth_offset(ox, oy, 0.0)

    # marked regions on the background
    for k, (spec, mask, box) in enumerate(region_layers):
        if masks.is_empty(box):
            continue
        effect = spec.get("effect")
        if not effect:
            continue
        try:
            motion_registry.apply_effect(
                effect, frame, mask, box, tl.child(k + 1), spec.get("params"), ctx
            )
        except Exception:
            continue
        depth = float(spec.get("depth", 0.0) or 0.0)
        if depth > 0.001:
            # a few pixels of extra drift so a marked region separates a little
            # from the picture behind it. Stacked PNG layers do this properly;
            # this is the cheap version for a flat photo, kept small on purpose.
            dx, dy = camera.depth_offset(ox, oy, depth)
            imageops.displace(
                frame,
                dx=-(dx - bgx),
                dy=-(dy - bgy),
                mask=mask,
                box=box,
                fast=ctx.fast,
            )

    # stacked images and emitters, back to front
    items = [("image", im, im.depth) for im in backdrop.images]
    for n, spec in enumerate(shot.get("emitters") or []):
        items.append(("emitter", (n, spec), float(spec.get("depth", 0.5) or 0.0)))
    items.sort(key=lambda it: it[2])

    for kind, payload, depth in items:
        dx, dy = camera.depth_offset(ox, oy, depth)
        if kind == "image":
            payload.draw(
                frame,
                tl.child(hash(id(payload)) % 97),
                int(dx),
                int(dy),
                ctx,
                defocus=focus.defocus(depth) if focus else 0.0,
                haze=focus.haze_at(depth) if focus else None,
            )
        else:
            n, spec = payload
            eid = spec.get("id") or spec.get("emitter")
            if not eid:
                continue
            mask = None
            if spec.get("region"):
                mask = masks.build(
                    spec["region"],
                    ctx.h,
                    ctx.w,
                    ctx.p("_mask_dir") or ctx.p("_base_dir"),
                )
            try:
                emitter_registry.draw_emitter(
                    eid,
                    frame,
                    tl.child(200 + n),
                    spec.get("params"),
                    ctx,
                    mask,
                    (dx, dy),
                )
            except Exception:
                continue

    # the leak drifts on the loop clock, so it cannot break the seam
    look._leak_phase = tl.wave(tl.loop_s / 2.0, offset=0.1)
    return look.apply(frame, i)


# --------------------------------------------------------------------------
# the generator render.py drives
# --------------------------------------------------------------------------
def build(ctx):
    """Everything that only has to happen once for a shot."""
    shot = shot_from_ctx(ctx)
    live = str(shot.get("mode", "loop")) == "live"
    base_dir = ctx.p("_base_dir") or ""
    loop_s = float(shot.get("loop_seconds") or _resolve(ctx, "loop_seconds") or 12.0)
    if live:
        loop_s = ctx.duration
    loop_s = max(1.0, min(loop_s, max(1.0, ctx.duration)))

    backdrop = Backdrop(
        shot, ctx.h, ctx.w, base_dir, fps=ctx.fps, n_frames=max(1, ctx.n_frames)
    )
    camera = _camera(ctx, shot, live)
    loop_frames = max(1, int(round(loop_s * ctx.fps)))
    resolved_look = _look(ctx, shot)
    look = Look(resolved_look, ctx.h, ctx.w, loop_frames)
    focus = Focus(resolved_look, ctx.h, ctx.w)

    mask_dir = ctx.p("_mask_dir") or base_dir
    region_layers = []
    for spec in shot.get("layers") or []:
        mask = masks.build(spec.get("region"), ctx.h, ctx.w, mask_dir)
        region_layers.append((spec, mask, masks.bbox(mask, pad=10)))

    return (
        shot,
        backdrop,
        camera,
        look,
        region_layers,
        loop_s,
        live,
        loop_frames,
        focus,
    )


def frames(ctx):
    (
        shot,
        backdrop,
        camera,
        look,
        region_layers,
        loop_s,
        live,
        loop_frames,
        focus,
    ) = build(ctx)
    for i in range(ctx.n_frames):
        t = i / max(1.0, ctx.fps)
        tl = LoopClock(
            t % loop_s if not live else t,
            i,
            loop_s,
            ctx.fps,
            seed=7,
            feat=ctx.feat if live else None,
            frame_index=i,
        )
        yield overlay.to_uint8(
            render_frame(
                ctx,
                shot,
                backdrop,
                camera,
                look,
                region_layers,
                tl,
                i if live else i % loop_frames,
                focus,
            )
        )


def still(ctx, t):
    """One frame at time `t` -- what the editor's scrubber asks for."""
    (
        shot,
        backdrop,
        camera,
        look,
        region_layers,
        loop_s,
        live,
        loop_frames,
        focus,
    ) = build(ctx)
    i = int(round(t * ctx.fps))
    tl = LoopClock(
        t % loop_s if not live else t,
        i,
        loop_s,
        ctx.fps,
        seed=7,
        feat=ctx.feat if live else None,
        frame_index=i,
    )
    return overlay.to_uint8(
        render_frame(
            ctx,
            shot,
            backdrop,
            camera,
            look,
            region_layers,
            tl,
            i if live else i % loop_frames,
            focus,
        )
    )
