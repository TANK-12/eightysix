"""Camera view math: key frames, clamping, easing, sampling and the affine map.

A camera key looks at a *source* image (a panel, or a strip region for a
page reveal) and is stored in timeline.json as

    {"t": 0.0, "cx": 0.5, "cy": 0.5, "zoom": 1.0, "rot": 0, "ease": "inout"}

- `cx`, `cy`: the view centre as a fraction of the source width and height.
- `zoom`: 1.0 shows the whole source fitted inside the frame ("contain").
  2.0 shows half as much in each direction.
- `rot`: degrees, small values only (action tilts).
- `ease`: how the move that *ends* at this key accelerates
  (`linear`, `in`, `out`, `inout`; default `inout`).

A key is "inside the panel" when, on every axis where the view is smaller
than the source, the view rectangle lies within the source. On an axis where
the view is larger (letterboxing at low zoom) the view is centred.
"""

import math

Size = tuple[int, int]

EASES = ("linear", "in", "out", "inout")


def contain_scale(src: Size, out: Size) -> float:
    return min(out[0] / src[0], out[1] / src[1])


def cover_zoom(src: Size, out: Size) -> float:
    """The zoom at which the source fills the whole frame with no letterbox."""
    return max(out[0] / src[0], out[1] / src[1]) / contain_scale(src, out)


def view_size(zoom: float, src: Size, out: Size) -> tuple[float, float]:
    """Width and height of the visible area, in source pixels."""
    s = contain_scale(src, out) * zoom
    return out[0] / s, out[1] / s


def zoom_to_fit(box_w: float, box_h: float, src: Size, out: Size, margin=1.4) -> float:
    """Zoom at which a box (source px) plus margin just fits in the view."""
    bw, bh = max(box_w * margin, 1.0), max(box_h * margin, 1.0)
    return min(out[0] / bw, out[1] / bh) / contain_scale(src, out)


def max_zoom_for(src: Size, out: Size, strength: float, cap=2.4, max_upscale=4.0):
    """How far the camera may push in: set by motion strength and source pixels."""
    by_strength = 1.0 + (cap - 1.0) * max(0.0, min(1.5, strength))
    by_pixels = max_upscale / contain_scale(src, out)
    return max(1.0, min(by_strength, by_pixels))


def _clamp_axis(c: float, view: float, size: float) -> float:
    if view >= size:
        return 0.5
    lo, hi = view / 2 / size, 1 - view / 2 / size
    return min(hi, max(lo, c))


def clamp_key(key: dict, src: Size, out: Size, max_zoom: float) -> dict:
    """Return the key moved and zoomed just enough to stay inside the source."""
    k = dict(key)
    # zoom below 1 is allowed only as a deliberate "air" key (a wide strip
    # in a portrait frame); ordinary keys never pull out past the panel
    floor = 0.9 if key.get("_air") else 1.0
    k["zoom"] = min(max_zoom, max(floor, float(k.get("zoom", 1.0))))
    vw, vh = view_size(k["zoom"], src, out)
    k["cx"] = _clamp_axis(float(k.get("cx", 0.5)), vw, src[0])
    k["cy"] = _clamp_axis(float(k.get("cy", 0.5)), vh, src[1])
    k["rot"] = float(k.get("rot", 0.0))
    return k


def key_inside(key: dict, src: Size, out: Size, eps_px=0.75) -> bool:
    """True when the view stays within the source (to within eps_px pixels)."""
    vw, vh = view_size(key["zoom"], src, out)
    for c, v, n in ((key["cx"], vw, src[0]), (key["cy"], vh, src[1])):
        if v >= n:
            if abs(c - 0.5) * n > eps_px:
                return False
        elif c * n - v / 2 < -eps_px or c * n + v / 2 > n + eps_px:
            return False
    return True


def ease(u: float, kind: str = "inout") -> float:
    u = min(1.0, max(0.0, u))
    if kind == "linear":
        return u
    if kind == "in":
        return u * u * u
    if kind == "out":
        return 1 - (1 - u) ** 3
    return u * u * (3 - 2 * u) if u < 1 else 1.0


def sample(keys: list[dict], t: float, src: Size, out: Size, max_zoom: float) -> dict:
    """Camera at time t: eased interpolation, zoom in log space, then clamped."""
    if not keys:
        return clamp_key({"cx": 0.5, "cy": 0.5, "zoom": 1.0}, src, out, max_zoom)
    ks = sorted(keys, key=lambda k: k.get("t", 0.0))
    if t <= ks[0].get("t", 0.0):
        return clamp_key(ks[0], src, out, max_zoom)
    for a, b in zip(ks, ks[1:]):
        ta, tb = a.get("t", 0.0), b.get("t", 0.0)
        if t <= tb:
            u = ease((t - ta) / (tb - ta) if tb > ta else 1.0, b.get("ease", "inout"))
            za, zb = max(1e-3, a.get("zoom", 1.0)), max(1e-3, b.get("zoom", 1.0))
            k = {
                "cx": a.get("cx", 0.5) + (b.get("cx", 0.5) - a.get("cx", 0.5)) * u,
                "cy": a.get("cy", 0.5) + (b.get("cy", 0.5) - a.get("cy", 0.5)) * u,
                "zoom": math.exp(math.log(za) + (math.log(zb) - math.log(za)) * u),
                "rot": a.get("rot", 0.0) + (b.get("rot", 0.0) - a.get("rot", 0.0)) * u,
            }
            return clamp_key(k, src, out, max_zoom)
    return clamp_key(ks[-1], src, out, max_zoom)


def affine(
    key: dict, src: Size, out: Size, offset=(0.0, 0.0), extra_zoom=1.0
) -> list[list[float]]:
    """2x3 matrix mapping source pixels to output pixels for this key."""
    s = contain_scale(src, out) * key["zoom"] * extra_zoom
    a = math.radians(key.get("rot", 0.0))
    ca, sa = math.cos(a) * s, math.sin(a) * s
    px, py = key["cx"] * src[0], key["cy"] * src[1]
    tx = out[0] / 2 + offset[0] - (ca * px - sa * py)
    ty = out[1] / 2 + offset[1] - (sa * px + ca * py)
    return [[ca, -sa, tx], [sa, ca, ty]]


def shake_offset(t: float, amount: float, impacts: list[float], height: int):
    """Deterministic hand-held shake plus decaying jolts after each impact."""
    base = amount * 0.004 * height
    x = base * (math.sin(t * 13.1) + 0.6 * math.sin(t * 29.7 + 1.3))
    y = base * (math.sin(t * 11.3 + 0.7) + 0.6 * math.sin(t * 31.9 + 2.1))
    for ti in impacts:
        d = t - ti
        if 0 <= d < 0.6:
            amp = 0.022 * height * max(amount, 0.4) * math.exp(-d * 7)
            x += amp * math.sin(d * 71.0)
            y += amp * math.cos(d * 63.0)
    return x, y
