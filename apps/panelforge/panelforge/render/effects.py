"""Effects layer drawn over a style's frame, driven by the panel's facts.

Each effect is `fx(ctx, shot, t, frame, facts) -> frame` and is listed in
EFFECTS; adding one is one function plus one entry. `facts` holds the panel's
action score (0..1), mood and speed-line angle from scene.json, scaled by the
timeline's `effects` strength. Everything is a pure function of time (seeded
per shot), so any frame can be rendered on its own and resumed renders match.
"""

import math
import zlib

import cv2
import numpy as np


def facts_for(ctx, shot) -> dict:
    sc = ctx.inp.scene_panel(shot["panel_id"])
    action = float(sc.get("action") or 0.0)
    if not sc:  # no scene analysis yet: loud lettering hints at action
        bubbles = ctx.inp.panel_bubbles(shot["panel_id"])
        loud = sum(1 for b in bubbles if b.get("kind") in ("sfx", "shout"))
        action = min(0.8, 0.35 * loud)
    sl = sc.get("speed_lines") or {}
    return {
        "action": action,
        "mood": sc.get("mood"),
        "speed_angle": sl.get("angle_deg") if sl.get("present") else None,
        "strength": float(ctx.settings.get("effects", 1.0)),
        "seed": zlib.crc32(shot.get("id", "x").encode()),
    }


_solids: dict = {}


def _solid(shape, color) -> np.ndarray:
    key = (shape[0], shape[1], tuple(color))
    img = _solids.get(key)
    if img is None:
        if len(_solids) > 16:
            _solids.clear()
        img = _solids[key] = np.empty((shape[0], shape[1], 3), np.uint8)
        img[:] = color
    return img


def _alpha_blend(frame, color, alpha):
    """frame[:3] = frame*(1-a) + color*a, alpha HxW float32 0..1.

    Stays on uint8 through cv2.blendLinear (threaded); a contiguous copy of
    the BGR planes is far cheaper than blending through the strided view."""
    bgr = np.ascontiguousarray(frame[..., :3])
    frame[..., :3] = cv2.blendLinear(bgr, _solid(frame.shape, color), 1 - alpha, alpha)
    return frame


def speed_lines(ctx, shot, t, frame, f):
    """Parallel speed lines at scene.json's angle, or focus lines on big action."""
    strength = f["strength"]
    if strength <= 0:
        return frame
    angle = f["speed_angle"]
    focus = angle is None and f["action"] >= 0.75
    if angle is None and not focus:
        return frame
    h, w = frame.shape[:2]
    sw, sh = w // 2, h // 2
    step = int(t * 12)  # lines redraw 12 times a second, like hand-drawn boils
    rng = np.random.default_rng(f["seed"] + step)
    layer = np.zeros((sh, sw), np.uint8)
    if focus:
        cx, cy = sw / 2, sh / 2
        r_in = min(sw, sh) * 0.36
        r_out = math.hypot(sw, sh)
        for _ in range(int(90 * strength)):
            a = rng.uniform(0, 2 * math.pi)
            r0 = r_in * rng.uniform(0.95, 1.5)
            thick = int(rng.integers(1, 4))
            pts = [
                (int(cx + math.cos(a) * r0), int(cy + math.sin(a) * r0)),
                (int(cx + math.cos(a) * r_out), int(cy + math.sin(a) * r_out)),
            ]
            cv2.line(
                layer, pts[0], pts[1], int(rng.integers(120, 255)), thick, cv2.LINE_AA
            )
    else:
        a = math.radians(float(angle or 0.0))
        dx, dy = math.cos(a), math.sin(a)
        diag = math.hypot(sw, sh)
        for _ in range(int(45 * strength * max(0.4, f["action"]))):
            off = rng.uniform(-diag / 2, diag / 2)
            px, py = sw / 2 - dy * off, sh / 2 + dx * off
            ln = rng.uniform(0.15, 0.45) * diag
            shift = (t * 900 + rng.uniform(0, diag)) % diag - diag / 2
            x0, y0 = px + dx * shift, py + dy * shift
            cv2.line(
                layer,
                (int(x0), int(y0)),
                (int(x0 + dx * ln), int(y0 + dy * ln)),
                int(rng.integers(90, 200)),
                int(rng.integers(1, 3)),
                cv2.LINE_AA,
            )
        yy, xx = np.ogrid[:sh, :sw]
        edge = np.clip(
            np.hypot((xx - sw / 2) / (sw / 2), (yy - sh / 2) / (sh / 2)) - 0.35, 0, 1
        )
        layer = (layer * edge).astype(np.uint8)
    alpha = (
        cv2.resize(layer, (w, h), interpolation=cv2.INTER_LINEAR).astype(np.float32)
        / 255
    )
    alpha *= 0.85 * min(1.0, strength)
    return _alpha_blend(frame, (255, 255, 255), alpha)


def impact_frames(ctx, shot, t, frame, f):
    """Two stark inverted frames and a white flash at each impact."""
    impacts = (shot.get("camera") or {}).get("impacts") or []
    if f["strength"] <= 0 or not impacts:
        return frame
    for ti in impacts:
        d = t - float(ti)
        if 0 <= d < 2.0 / ctx.fps:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGRA2GRAY)
            gray = cv2.equalizeHist(gray)
            _, stark = cv2.threshold(
                gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
            )
            tint = np.stack([stark * 0.92, stark * 0.94, stark], -1).astype(np.uint8)
            frame[..., :3] = tint
            return frame
        if 2.0 / ctx.fps <= d < 0.22:
            k = (1 - (d - 2.0 / ctx.fps) / 0.16) * 0.55 * min(1.0, f["strength"])
            if k > 0:
                frame[..., :3] = cv2.addWeighted(
                    frame[..., :3], 1 - k, np.full_like(frame[..., :3], 255), k, 0
                )
            return frame
    return frame


MOOD_PARTICLES = {
    # mood: (count, size px @1080, speed px/s, direction deg, color BGR, glow)
    "action": (70, 3.0, 520, -80, (80, 170, 255), True),
    "tense": (40, 2.2, 60, -95, (170, 170, 180), False),
    "calm": (35, 2.6, 25, -60, (230, 240, 250), True),
    "sad": (140, 1.4, 1400, 100, (220, 205, 190), False),
    "mystery": (45, 2.4, 30, -90, (255, 210, 170), True),
    "comic": (0, 0, 0, 0, (0, 0, 0), False),
}


def particles(ctx, shot, t, frame, f):
    """Embers for action, dust for calm, rain for sad, glowing motes for mystery."""
    mood = f["mood"] or ("action" if f["action"] >= 0.7 else None)
    spec = MOOD_PARTICLES.get(mood or "")
    if not spec or f["strength"] <= 0 or not spec[0]:
        return frame
    count, size, speed, deg, color, glow = spec
    h, w = frame.shape[:2]
    k = h / 1080
    rng = np.random.default_rng(f["seed"] ^ 0x5EED)
    n = int(count * min(1.5, f["strength"]))
    x0 = rng.uniform(0, w, n)
    y0 = rng.uniform(0, h, n)
    sp = rng.uniform(0.5, 1.3, n) * speed * k
    wob = rng.uniform(0, 2 * math.pi, n)
    a = math.radians(deg)
    xs = (x0 + math.cos(a) * sp * t + np.sin(t * 1.3 + wob) * 12 * k) % w
    ys = (y0 + math.sin(a) * sp * t) % h
    layer = np.zeros((h, w), np.uint8)
    for x, y, s in zip(xs, ys, rng.uniform(0.6, 1.4, n)):
        if mood == "sad":
            cv2.line(
                layer,
                (int(x), int(y)),
                (int(x - 6 * k), int(y + 26 * k)),
                150,
                1,
                cv2.LINE_AA,
            )
        else:
            cv2.circle(
                layer, (int(x), int(y)), max(1, int(size * s * k)), 255, -1, cv2.LINE_AA
            )
    alpha = layer.astype(np.float32) / 255
    if glow:
        halo = cv2.GaussianBlur(alpha, (0, 0), 6 * k)
        alpha = np.clip(alpha + halo * 2.2, 0, 1)
    alpha *= 0.8 * min(1.0, f["strength"])
    return _alpha_blend(frame, color, alpha)


def light_glow(ctx, shot, t, frame, f):
    """Bloom on bright areas: pulses with action, soft for mystery and calm."""
    if f["strength"] <= 0:
        return frame
    mood = f["mood"]
    amount = 0.0
    if f["action"] >= 0.5:
        amount = 0.35 + 0.25 * math.sin(t * 9) ** 2
    elif mood in ("mystery", "calm", "sad"):
        amount = 0.22 + 0.06 * math.sin(t * 1.5)
    amount *= min(1.5, f["strength"])
    if amount <= 0.01:
        return frame
    h, w = frame.shape[:2]
    small = cv2.resize(frame[..., :3], (w // 4, h // 4), interpolation=cv2.INTER_AREA)
    luma = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    bright = cv2.bitwise_and(small, small, mask=(luma > 185).astype(np.uint8))
    bloom = cv2.GaussianBlur(bright, (0, 0), max(3, w // 160))
    bloom = cv2.resize(bloom, (w, h), interpolation=cv2.INTER_LINEAR)
    frame[..., :3] = cv2.addWeighted(
        np.ascontiguousarray(frame[..., :3]), 1.0, bloom, amount, 0
    )
    return frame


GRAIN_MOODS = {"tense": 0.8, "mystery": 1.0, "sad": 0.7}  # mood: grain amount


def film_grain(ctx, shot, t, frame, f):
    """Fine moving grain for tense, mysterious and sad panels, like old film.

    The grain is a pure function of the frame number (seeded per shot), so a
    single frame renders the same on its own and in a resumed render."""
    amount = GRAIN_MOODS.get(f["mood"] or "", 0.0) * min(1.5, f["strength"])
    if amount <= 0:
        return frame
    h, w = frame.shape[:2]
    n = int(round(t * ctx.fps))
    rng = np.random.default_rng((f["seed"] ^ 0x6A41) + n)
    gh, gw = max(1, h // 2), max(1, w // 2)  # grain a little coarser than a pixel
    noise = rng.normal(0.0, 14.0 * amount, (gh, gw)).astype(np.float32)
    noise = cv2.resize(noise, (w, h), interpolation=cv2.INTER_LINEAR)
    bgr = frame[..., :3].astype(np.float32)
    # grain shows most in the mid-tones and hardly in paper white or ink black
    luma = bgr.mean(axis=2, keepdims=True) / 255.0
    weight = 4.0 * luma * (1.0 - luma)
    frame[..., :3] = np.clip(bgr + noise[..., None] * weight, 0, 255).astype(np.uint8)
    return frame


RGB_SPLIT_SECONDS = 0.18


def rgb_split(ctx, shot, t, frame, f):
    """Red and blue pull apart for a moment at each impact, then snap back."""
    impacts = (shot.get("camera") or {}).get("impacts") or []
    if f["strength"] <= 0 or not impacts:
        return frame
    for ti in impacts:
        d = t - float(ti)
        if 0 <= d < RGB_SPLIT_SECONDS:
            h, w = frame.shape[:2]
            k = (1 - d / RGB_SPLIT_SECONDS) ** 2
            px = int(round(w / 160 * k * min(1.5, f["strength"])))
            if px < 1:
                return frame
            b = frame[..., 0].copy()
            r = frame[..., 2].copy()
            frame[..., 0] = np.roll(b, -px, axis=1)
            frame[..., 2] = np.roll(r, px, axis=1)
            return frame
    return frame


# drawn in this order; a shot can switch any of them off by name in
# style_settings.effects_off
EFFECTS = (light_glow, particles, speed_lines, film_grain, impact_frames, rgb_split)


def apply(ctx, shot, t, frame):
    if float(ctx.settings.get("effects", 1.0)) <= 0:
        return frame
    ck = ("facts", shot.get("id"), shot.get("panel_id"))
    f = ctx.cache.get(ck)
    if f is None:
        f = ctx.cache[ck] = facts_for(ctx, shot)
    off = set((shot.get("style_settings") or {}).get("effects_off") or [])
    for fx in EFFECTS:
        if fx.__name__ not in off:
            frame = fx(ctx, shot, t, frame, f)
    return frame
