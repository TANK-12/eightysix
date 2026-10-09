"""Cinematic 3D-ish style: the panel becomes a layered scene with real depth.

Animation, not generation: the drawing is the base frame. The scene data
(inpainted background, 16-bit depth map, character cutouts) turns it into
layers, and the motion is the intelligent camera plus parallax, dolly and a
slow sway of a virtual camera:

- The background is warped by its depth map under the camera move: one
  cv2.remap whose displacement is proportional to (depth - focus) times the
  camera's image shift (pan) and log zoom (dolly), plus the sway.
- Each character cutout is its own layer at its mean depth, so it moves and
  scales more than the background behind it; edges are feathered.
- Depth of field: blur grows with distance from the focus depth. Focus
  follows the speaking character, else the saliency point nearest the camera
  key, and eases between targets.
- Atmosphere: haze by depth, a vignette and a subtle mood colour grade.
- Bubbles in "keep" mode are composited back from the original drawing,
  rigid and crisp, after the grade. The effects layer still applies on top.

Without scene data (or when a panel lacks a background or its cutouts) the
whole panel is one layer over a heuristic depth (bottom and dark = near)
with a milder parallax, so it always renders something.
"""

import math

import cv2
import numpy as np

from .base import Style

MOOD_GRADES = {
    # mood: (shadow tint BGR, highlight tint BGR, contrast, lift)
    "tense": ((1.06, 0.98, 0.92), (0.96, 0.98, 1.02), 1.18, 0.02),
    "calm": ((0.96, 0.99, 1.04), (0.97, 1.0, 1.05), 0.92, 0.05),
    "action": ((0.95, 0.95, 1.0), (0.9, 0.97, 1.08), 1.3, 0.0),
    "sad": ((1.1, 1.0, 0.9), (1.06, 1.0, 0.94), 0.9, 0.06),
    "comic": ((1.0, 1.0, 1.0), (1.02, 1.02, 1.02), 1.12, 0.03),
    "mystery": ((1.05, 1.03, 0.9), (1.06, 0.97, 1.02), 1.15, 0.03),
    None: ((1.02, 1.0, 0.98), (0.99, 1.0, 1.02), 1.08, 0.02),
}

HAZE_COLORS = {
    "tense": (120, 112, 104),
    "calm": (176, 186, 196),
    "action": (110, 130, 160),
    "sad": (150, 138, 124),
    "comic": (200, 205, 210),
    "mystery": (120, 96, 88),
    None: (150, 148, 144),
}


def _num(spec_min, spec_max, step, default, label):
    return {
        "type": "number",
        "label": label,
        "min": spec_min,
        "max": spec_max,
        "step": step,
        "default": default,
    }


class Depth3D(Style):
    name = "depth3d"
    label = "Cinematic 3D"
    description = (
        "Layered scene with real depth: the background parallaxes under the camera, "
        "characters float in front, with depth of field, haze and a mood grade."
    )
    version = 1
    settings = {
        "parallax_strength": _num(0.0, 2.0, 0.05, 1.0, "Parallax strength"),
        "dolly": _num(0.0, 2.0, 0.05, 1.0, "Dolly on zoom"),
        "sway": _num(0.0, 2.0, 0.05, 1.0, "Camera sway"),
        "dof": _num(0.0, 2.0, 0.05, 1.0, "Depth of field"),
        "atmosphere": _num(0.0, 1.5, 0.05, 0.8, "Atmosphere (haze, vignette, grade)"),
        "feather": _num(0.0, 12.0, 0.5, 3.0, "Cutout edge feather (px)"),
    }

    # ------------------------------------------------------------ frame

    def render(self, ctx, shot, t):
        sc = self.scene(ctx, shot)
        ow, oh = ctx.out
        m = ctx.matrix(shot, t)
        m0 = sc["m0"]
        focus = self.focus_at(ctx, shot, sc, t)
        strength = (
            float(self.option(ctx, shot, "parallax_strength")) * sc["strength_scale"]
        )
        dolly = float(self.option(ctx, shot, "dolly")) * sc["strength_scale"]
        sway = float(self.option(ctx, shot, "sway"))
        dof = float(self.option(ctx, shot, "dof"))
        atm = float(self.option(ctx, shot, "atmosphere"))

        # image shift of the panel centre since the shot started, in output px
        c = sc["centre"]
        now = m[:, :2] @ c + m[:, 2]
        was = m0[:, :2] @ c + m0[:, 2]
        pan = (now - was) * 0.35 * strength
        k = ctx.camera_at(shot, t)
        lz = math.log(max(1e-3, float(k["zoom"])) / sc["zoom0"]) * 0.6 * dolly
        sway_amp = 0.018 * ow * sway * sc["strength_scale"]
        pan = pan + np.array(
            [
                sway_amp * math.sin(2 * math.pi * t / 7.3 + sc["phase"]),
                0.5 * sway_amp * math.sin(2 * math.pi * t / 9.7 + sc["phase"] * 2),
            ],
            np.float32,
        )

        # displacement maps at half resolution (depth is smooth), in full-res units
        grid = self.grid(ctx)
        xx, yy = grid["xx"], grid["yy"]
        hw, hh = grid["half"]
        depth_half = cv2.warpAffine(
            sc["depth"],
            m * 0.5,
            (hw, hh),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REPLICATE,
        )
        rel = depth_half - np.float32(focus)
        dx = rel * (np.float32(pan[0]) + (xx - np.float32(ow / 2)) * np.float32(lz))
        dy = rel * (np.float32(pan[1]) + (yy - np.float32(oh / 2)) * np.float32(lz))
        inv = cv2.invertAffineTransform(m).astype(np.float32)
        sx = xx - dx
        sy = yy - dy
        map_x = inv[0, 0] * sx + inv[0, 1] * sy + inv[0, 2]
        map_y = inv[1, 0] * sx + inv[1, 1] * sy + inv[1, 2]
        # the panel silhouette stays rigid: inside it, sample inside the panel
        base_x = inv[0, 0] * xx + inv[0, 1] * yy + inv[0, 2]
        base_y = inv[1, 0] * xx + inv[1, 1] * yy + inv[1, 2]
        bw, bh = sc["size"]
        inside = (base_x >= 0) & (base_x <= bw - 1) & (base_y >= 0) & (base_y <= bh - 1)
        np.clip(map_x, 0, bw - 1, out=map_x, where=inside)
        np.clip(map_y, 0, bh - 1, out=map_y, where=inside)
        map_x = cv2.resize(map_x, ctx.out, interpolation=cv2.INTER_LINEAR)
        map_y = cv2.resize(map_y, ctx.out, interpolation=cv2.INTER_LINEAR)
        layer = cv2.remap(
            sc["bg"], map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT
        )
        alpha = cv2.remap(
            sc["bg_alpha"],
            map_x,
            map_y,
            cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
        )
        bgr = _over(sc["backdrop"], layer, alpha)

        # character layers, far to near
        for ch in sc["chars"]:
            d = ch["depth"] - focus
            s = 1.0 + d * lz * sc["layers"]
            shift = d * pan * sc["layers"]
            mc = _layer_matrix(m, ch["x"], ch["y"], s, shift, (ow / 2, oh / 2))
            _draw_layer(
                bgr, self.layer_image(ctx, shot, sc, ch, t), mc, depth_half, ch["depth"]
            )

        if dof > 0:
            bgr = self.depth_of_field(bgr, depth_half, focus, dof, ctx)
        if atm > 0:
            bgr = self.atmosphere(bgr, depth_half, atm, sc["mood"], grid, ctx)
        if sc["bubbles"] is not None:
            _draw_layer(bgr, sc["bubbles"], m, None, None)
        return cv2.cvtColor(bgr, cv2.COLOR_BGR2BGRA)

    def layer_image(self, ctx, shot, sc, ch, t) -> np.ndarray:
        """The picture drawn for a character layer at time t. The 2.5D puppet
        style overrides this to breathe, blink and move the mouth."""
        return ch["img"]

    # ------------------------------------------------------------ pieces

    def depth_of_field(self, bgr, depth_half, focus, dof, ctx):
        ow, oh = ctx.out
        coc = np.abs(depth_half - np.float32(focus)) * np.float32(
            1.7 * dof
        ) - np.float32(0.06)
        np.clip(coc, 0, 1, out=coc)
        if float(coc.max()) < 0.03:
            return bgr
        small = cv2.resize(bgr, (ow // 2, oh // 2), interpolation=cv2.INTER_AREA)
        sigma = max(0.8, 1.6 * dof * oh / 1080)
        small = cv2.GaussianBlur(small, (0, 0), sigma)
        blurred = cv2.resize(small, (ow, oh), interpolation=cv2.INTER_LINEAR)
        coc = cv2.resize(coc, (ow, oh), interpolation=cv2.INTER_LINEAR)
        return cv2.blendLinear(bgr, blurred, 1 - coc, coc)

    def atmosphere(self, bgr, depth_half, atm, mood, grid, ctx):
        ow, oh = ctx.out
        a = (np.float32(1.0) - depth_half) * np.float32(0.32 * min(1.0, atm))
        np.clip(a, 0, 1, out=a)
        a = cv2.resize(a, (ow, oh), interpolation=cv2.INTER_LINEAR)
        haze = grid["solid"](HAZE_COLORS.get(mood, HAZE_COLORS[None]))
        bgr = cv2.blendLinear(bgr, haze, 1 - a, a)
        bgr = cv2.multiply(bgr, grid["vig"](atm), dtype=cv2.CV_8U)
        return cv2.LUT(bgr, self.grade_lut(mood, atm))

    def grade_lut(self, mood, atm) -> np.ndarray:
        shadow, high, contrast, lift = MOOD_GRADES.get(mood, MOOD_GRADES[None])
        x = np.linspace(0, 1, 256, dtype=np.float32)
        s = 0.5 + (x - 0.5) * contrast
        s = s * (1 - lift) + lift
        s = np.clip(s, 0, 1)
        lut = np.zeros((256, 1, 3), np.float32)
        for ch in range(3):
            tint = shadow[ch] * (1 - x) + high[ch] * x
            lut[:, 0, ch] = np.clip(s * tint, 0, 1)
        k = min(1.0, 0.85 * atm)
        lut = (x[:, None, None] * (1 - k) + lut * k) * 255
        lut = np.maximum.accumulate(lut, axis=0)  # a grade never inverts tones
        return np.clip(lut, 0, 255).astype(np.uint8)

    def grid(self, ctx) -> dict:
        ck = ("d3d-grid", ctx.out)
        g = ctx.cache.get(ck)
        if g is None:
            ow, oh = ctx.out
            hw, hh = max(2, ow // 2), max(2, oh // 2)
            yy, xx = np.mgrid[0:hh, 0:hw].astype(np.float32)
            xx *= ow / hw
            yy *= oh / hh
            r2 = ((xx / ow - 0.5) ** 2 + (yy / oh - 0.5) ** 2) * 2.0
            vig1 = cv2.resize(
                np.clip(1.0 - 0.42 * r2**1.5, 0, 1).astype(np.float32), (ow, oh)
            )
            solids: dict = {}
            vigs: dict = {}

            def vig(atm):
                key = round(min(1.0, atm), 2)
                if key not in vigs:
                    v = vig1 if key >= 1.0 else vig1 ** np.float32(key)
                    vigs[key] = cv2.merge([v, v, v])
                return vigs[key]

            def solid(color):
                if color not in solids:
                    img = np.empty((oh, ow, 3), np.uint8)
                    img[:] = color
                    solids[color] = img
                return solids[color]

            g = ctx.cache[ck] = {
                "xx": xx,
                "yy": yy,
                "half": (hw, hh),
                "vig": vig,
                "solid": solid,
            }
        return g

    # ------------------------------------------------------------ focus

    def focus_at(self, ctx, shot, sc, t) -> float:
        """Focus depth at t, eased over 0.35 s between targets."""
        vals = [self._focus_target(ctx, shot, sc, t - 0.05 * i) for i in range(7)]
        return float(sum(vals) / len(vals))

    def _focus_target(self, ctx, shot, sc, t) -> float:
        t = max(0.0, t)
        for ev in sc["focus_events"]:
            if ev["at"] <= t < ev["end"]:
                return ev["depth"]
        k = ctx.camera_at(shot, t)
        small = sc["depth_small"]
        sh, sw = small.shape
        cx, cy = float(k["cx"]), float(k["cy"])
        if sc["saliency"]:
            best = min(
                sc["saliency"],
                key=lambda p: ((p[0] - cx) ** 2 + (p[1] - cy) ** 2) / max(0.15, p[2]),
            )
            if (best[0] - cx) ** 2 + (best[1] - cy) ** 2 < 0.2:
                cx, cy = best[0], best[1]
        x = min(sw - 1, max(0, int(cx * sw)))
        y = min(sh - 1, max(0, int(cy * sh)))
        return float(small[y, x])

    # ------------------------------------------------------------ layers

    def scene(self, ctx, shot) -> dict:
        opts = tuple(self.option(ctx, shot, k) for k in ("feather",))
        ck = (
            "d3d",
            shot.get("id"),
            shot["panel_id"],
            ctx.out,
            ctx.settings.get("bubbles"),
            opts,
            ctx.inp.stamp(),
        )
        sc = ctx.cache.get(ck)
        if sc is None:
            sc = self.build_scene(ctx, shot)
            ctx._evict("d3d", keep=3)
            ctx.cache[ck] = sc
        return sc

    def build_scene(self, ctx, shot) -> dict:
        pid = shot["panel_id"]
        src = ctx.source(shot)
        h, w = src.shape[:2]
        f = ctx.source_factor(shot)
        flip = bool((shot.get("camera") or {}).get("flip"))
        keep = ctx.settings.get("bubbles") != "erase"
        panel = ctx.inp.scene_panel(pid) if shot.get("kind") != "reveal" else {}
        feather = float(self.option(ctx, shot, "feather")) * f

        bg_img = _read(ctx, panel.get("background"), cv2.IMREAD_COLOR)
        depth_img = _read(ctx, panel.get("depth"), cv2.IMREAD_UNCHANGED)
        chars_all = list(panel.get("characters", []))
        chars_spec = [c for c in chars_all if c.get("box")]
        cut_imgs = [
            _read(ctx, c.get("cutout"), cv2.IMREAD_UNCHANGED) for c in chars_spec
        ]
        # the `layers` setting turns the cutout layering down or off: at 0
        # the drawing stays whole (an eye never drifts off its face) and only
        # the depth parallax moves; in between, the layers move less
        layers = float(ctx.settings.get("layers", 1.0))
        layered = (
            layers > 0.02
            and bg_img is not None
            and all(
                ci is not None and ci.ndim == 3 and ci.shape[2] == 4 for ci in cut_imgs
            )
        )

        depth = (
            _normalise_depth(depth_img, (w, h))
            if depth_img is not None
            else _heuristic_depth(src)
        )
        if flip and depth_img is not None:
            depth = cv2.flip(depth, 1)

        chars: list[dict] = []
        bubbles_layer = None
        if layered:
            assert bg_img is not None
            bg = cv2.resize(
                bg_img,
                (w, h),
                interpolation=cv2.INTER_AREA if f < 1 else cv2.INTER_CUBIC,
            )
            if flip:
                bg = cv2.flip(bg, 1)
            bg = cv2.cvtColor(bg, cv2.COLOR_BGR2BGRA)
            bg[..., 3] = src[..., 3]
            bg = np.ascontiguousarray(bg)
            pw, ph = ctx.source_size(shot)
            for spec, cut in zip(chars_spec, cut_imgs):
                assert cut is not None
                x, y, cw, chh = [float(v) for v in spec["box"]]
                if flip:
                    x = pw - x - cw
                    cut = cv2.flip(cut, 1)
                size = (max(1, int(round(cw * f))), max(1, int(round(chh * f))))
                cut = cv2.resize(
                    cut,
                    size,
                    interpolation=cv2.INTER_AREA if f < 1 else cv2.INTER_CUBIC,
                )
                cut = _feather(cut, feather)
                lx, ly = int(round(x * f)), int(round(y * f))
                if spec.get("placement") in ("rejected", "unplaced"):
                    # not a character (a gun, a hand, an emblem, a faceless
                    # crop nobody matched): it was cut out of the background
                    # at analysis, so paste it back where it was and let it
                    # stay put -- floating it on a thin mask made objects
                    # vanish (Emerson: "objects often disappear")
                    _paste(bg, cut, lx, ly)
                    continue
                d = _mean_depth(depth, cut, lx, ly)
                chars.append(
                    {
                        "img": cut,
                        "x": lx,
                        "y": ly,
                        "depth": d,
                        "cast_id": spec.get("cast_id") or spec.get("extra_id"),
                        # the panel-level index, so a style can find this
                        # character's rig (head, eyes, mouth, pivots)
                        "char_index": chars_all.index(spec),
                        "flip": flip,
                        "scale": f,
                        "box": [x, y, cw, chh],
                    }
                )
            chars.sort(key=lambda c: c["depth"])
            if keep:
                bubbles_layer = _bubble_layer(ctx, shot, pid, src, f, flip)
        else:
            bg = src
        strength_scale = 1.0 if layered else (0.6 if depth_img is not None else 0.45)

        small = cv2.resize(
            depth, (max(8, w // 8), max(8, h // 8)), interpolation=cv2.INTER_AREA
        )
        small = cv2.GaussianBlur(small, (0, 0), 1.5)
        sal = []
        pw, ph = ctx.source_size(shot)
        for p in panel.get("saliency", []) or []:
            px = float(p[0]) / max(1, pw)
            sal.append(
                [
                    1 - px if flip else px,
                    float(p[1]) / max(1, ph),
                    float(p[2]) if len(p) > 2 else 1.0,
                ]
            )
        m0 = ctx.matrix(shot, 0.0)
        return {
            "bg": np.ascontiguousarray(bg[..., :3]),
            "bg_alpha": np.ascontiguousarray(bg[..., 3]),
            "backdrop": cv2.cvtColor(ctx.backdrop(shot), cv2.COLOR_BGRA2BGR),
            "depth": depth,
            "depth_small": small,
            "chars": chars,
            "bubbles": bubbles_layer,
            "size": (w, h),
            "centre": np.array([w / 2, h / 2], np.float32),
            "m0": m0,
            "zoom0": max(1e-3, float(ctx.camera_at(shot, 0.0)["zoom"])),
            "phase": (hash(shot.get("id", "")) % 628) / 100.0,
            "mood": panel.get("mood"),
            "saliency": sal,
            "strength_scale": strength_scale,
            "layers": layers if layered else 0.0,
            "focus_events": _focus_events(ctx, shot, chars, depth, f),
            "layered": layered,
        }


# ---------------------------------------------------------------- helpers


def _read(ctx, rel, flag):
    if not rel:
        return None
    p = ctx.inp.dir / rel
    if not p.exists():
        return None
    return cv2.imread(str(p), flag)


def _normalise_depth(img: np.ndarray, size) -> np.ndarray:
    if img.ndim == 3:
        img = img[..., 0]
    d = img.astype(np.float32)
    lo, hi = np.percentile(d, 2), np.percentile(d, 98)
    d = (d - lo) / max(1e-6, hi - lo)
    np.clip(d, 0, 1, out=d)
    if d.shape[1] != size[0] or d.shape[0] != size[1]:
        d = cv2.resize(d, size, interpolation=cv2.INTER_LINEAR)
    return cv2.GaussianBlur(d, (0, 0), max(1.0, size[1] / 300))


def _heuristic_depth(src: np.ndarray) -> np.ndarray:
    """Bottom of the panel and darker areas count as nearer."""
    h, w = src.shape[:2]
    gray = cv2.cvtColor(src[..., :3], cv2.COLOR_BGR2GRAY).astype(np.float32) / 255
    dark = cv2.GaussianBlur(1 - gray, (0, 0), max(2.0, 0.06 * max(w, h)))
    vert = np.repeat(np.linspace(0, 1, h, dtype=np.float32)[:, None], w, 1)
    d = 0.6 * vert + 0.4 * dark
    lo, hi = np.percentile(d, 2), np.percentile(d, 98)
    d = (d - lo) / max(1e-6, hi - lo)
    return np.clip(d, 0, 1).astype(np.float32)


def _feather(cut: np.ndarray, px: float) -> np.ndarray:
    if px <= 0:
        return cut
    a = cut[..., 3]
    r = max(1, int(round(px / 2)))
    a = cv2.erode(
        a, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
    )
    a = cv2.GaussianBlur(a, (0, 0), max(0.5, px * 0.6))
    out = cut.copy()
    out[..., 3] = a
    return out


def _mean_depth(depth: np.ndarray, cut: np.ndarray, x: int, y: int) -> float:
    h, w = depth.shape
    ch, cw = cut.shape[:2]
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(w, x + cw), min(h, y + ch)
    if x1 <= x0 or y1 <= y0:
        return 0.5
    a = cut[y0 - y : y1 - y, x0 - x : x1 - x, 3] > 128
    region = depth[y0:y1, x0:x1]
    if a.sum() < 4:
        return float(region.mean())
    # characters stand in front of what they cover: bias toward the near part
    vals = region[a]
    return float(0.5 * vals.mean() + 0.5 * np.percentile(vals, 80))


def _bubble_layer(ctx, shot, pid, src, f, flip):
    """The original bubbles as a rigid RGBA layer (working resolution)."""
    from ..render import bubbles as B

    items = [b for b in ctx.inp.panel_bubbles(pid) if b.get("kind") != "sfx"]
    if not items:
        return None
    base = ctx.base_image(shot)
    bgr = cv2.cvtColor(base, cv2.COLOR_BGRA2BGR)
    if flip:
        bgr = cv2.flip(bgr, 1)
    pw = bgr.shape[1]
    mask = np.zeros(bgr.shape[:2], np.uint8)
    for b in items:
        box = ctx.inp.local_box(pid, b["box"])
        if flip:
            box = [pw - box[0] - box[2], box[1], box[2], box[3]]
        mask |= B.bubble_mask(bgr, box, b.get("kind", "speech"))
    if not mask.any():
        return None
    layer = cv2.cvtColor(bgr, cv2.COLOR_BGR2BGRA)
    layer[..., 3] = cv2.GaussianBlur(mask, (0, 0), 1.0)
    if f != 1.0:
        layer = cv2.resize(
            layer,
            (src.shape[1], src.shape[0]),
            interpolation=cv2.INTER_AREA if f < 1 else cv2.INTER_CUBIC,
        )
    return layer


def _focus_events(ctx, shot, chars, depth, f) -> list[dict]:
    """(at, end, depth) for each spoken line: the speaker's layer, else the bubble's spot."""
    events = []
    by_cast = {c["cast_id"]: c["depth"] for c in chars if c.get("cast_id")}
    pid = shot["panel_id"]
    bubbles = {b["id"]: b for b in ctx.inp.panel_bubbles(pid)}
    h, w = depth.shape
    for ln in shot.get("lines", []):
        line = ctx.inp.lines.get(ln.get("line_id")) or {}
        bubble = bubbles.get(ln.get("bubble_id") or line.get("bubble_id")) or {}
        speaker = line.get("speaker") or bubble.get("speaker")
        at = float(ln.get("at", 0.0))
        dur = float(ln.get("dur") or line.get("dur") or 0) or max(
            1.1,
            len((line.get("text") or bubble.get("text") or "").split()) / 2.6 + 0.35,
        )
        d = by_cast.get(speaker)
        if d is None and bubble.get("box"):
            bx, by, bw, bh = ctx.inp.local_box(pid, bubble["box"])
            tail = bubble.get("tail")
            if tail:
                px, py = (
                    tail[0] - ctx.inp.by_id[pid]["box"][0],
                    tail[1] - ctx.inp.by_id[pid]["box"][1],
                )
            else:
                px, py = bx + bw / 2, by + bh * 1.3
            x = min(w - 1, max(0, int(px * f)))
            y = min(h - 1, max(0, int(py * f)))
            d = float(depth[y, x])
        if d is None:
            continue
        events.append({"at": at, "end": at + dur + 0.3, "depth": d})
    return events


def _layer_matrix(m, x, y, s, shift, centre):
    """Camera matrix for a layer placed at (x, y) in working coords, scaled by
    s about the frame centre and shifted (parallax)."""
    mc = m.copy()
    mc[:, 2] += m[:, :2] @ np.array([x, y], np.float64)
    if s != 1.0:
        cx, cy = centre
        mc[:, :2] *= s
        mc[0, 2] = cx + (mc[0, 2] - cx) * s
        mc[1, 2] = cy + (mc[1, 2] - cy) * s
    mc[0, 2] += float(shift[0])
    mc[1, 2] += float(shift[1])
    return mc


def _draw_layer(frame, img, mc, depth_half, depth):
    """Warp a BGRA layer through mc onto frame (alpha over), limited to its
    destination box. Writes its depth into depth_half where it is opaque."""
    oh, ow = frame.shape[:2]
    h, w = img.shape[:2]
    corners = np.array([[0, 0], [w, 0], [0, h], [w, h]], np.float64)
    dst = corners @ mc[:, :2].T + mc[:, 2]
    x0, y0 = int(math.floor(dst[:, 0].min())) - 1, int(math.floor(dst[:, 1].min())) - 1
    x1, y1 = int(math.ceil(dst[:, 0].max())) + 1, int(math.ceil(dst[:, 1].max())) + 1
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(ow, x1), min(oh, y1)
    if x1 <= x0 or y1 <= y0:
        return
    local = mc.copy()
    local[0, 2] -= x0
    local[1, 2] -= y0
    warped = cv2.warpAffine(
        img,
        local,
        (x1 - x0, y1 - y0),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0, 0),
    )
    frame[y0:y1, x0:x1] = _over(frame[y0:y1, x0:x1], warped[..., :3], warped[..., 3])
    if depth_half is not None and depth is not None:
        hh, hw = depth_half.shape
        hx0, hy0 = x0 * hw // ow, y0 * hh // oh
        hx1, hy1 = max(hx0 + 1, x1 * hw // ow), max(hy0 + 1, y1 * hh // oh)
        a = cv2.resize(
            warped[..., 3], (hx1 - hx0, hy1 - hy0), interpolation=cv2.INTER_AREA
        )
        depth_half[hy0:hy1, hx0:hx1][a > 128] = depth


def _paste(bg: np.ndarray, cut: np.ndarray, x: int, y: int) -> None:
    """Alpha-composite a BGRA cutout onto the BGRA background at (x, y)."""
    h, w = bg.shape[:2]
    ch, cw = cut.shape[:2]
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(w, x + cw), min(h, y + ch)
    if x1 <= x0 or y1 <= y0:
        return
    part = cut[y0 - y : y1 - y, x0 - x : x1 - x]
    a = part[..., 3:4].astype(np.float32) / 255.0
    dst = bg[y0:y1, x0:x1]
    dst[..., :3] = (part[..., :3] * a + dst[..., :3] * (1 - a)).astype(np.uint8)
    dst[..., 3] = np.maximum(dst[..., 3], part[..., 3])


def _over(dst, layer, alpha):
    """layer (BGR) over dst (BGR) by alpha (uint8), on uint8 the whole way.

    blendLinear normalises by the weight sum, so the weights can stay 0..255."""
    a = alpha.astype(np.float32)
    return cv2.blendLinear(
        np.ascontiguousarray(dst), np.ascontiguousarray(layer), 255 - a, a
    )


STYLE = Depth3D()
