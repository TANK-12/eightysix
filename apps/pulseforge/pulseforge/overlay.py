"""
Numpy drawing toolkit shared by the scenes.

A scene is a generator that yields one RGB uint8 frame (H, W, 3) per output
frame. render.py pipes those to ffmpeg, which scales to the target format,
muxes the song, normalises loudness and encodes. Rendering internally at <=
1080p and letting ffmpeg upscale is what keeps 4K output cheap on a CPU-only
box.

Everything here is vectorised numpy -- no per-pixel Python loops.
"""

import numpy as np
from PIL import Image


# --------------------------------------------------------------------------
# colour
# --------------------------------------------------------------------------
def hex_rgb(s):
    s = s.lstrip("#")
    return tuple(int(s[i : i + 2], 16) for i in (0, 2, 4))


def lerp(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def vertical_gradient(h, w, top, bottom):
    t = np.linspace(0.0, 1.0, h)[:, None, None]
    top = np.array(top, dtype=np.float64)
    bottom = np.array(bottom, dtype=np.float64)
    grad = top * (1 - t) + bottom * t
    return np.repeat(grad, w, axis=1).astype(np.uint8)


def radial_gradient(h, w, inner, outer, cx=0.5, cy=0.5, power=1.0):
    ys = (np.linspace(0, 1, h) - cy)[:, None]
    xs = (np.linspace(0, 1, w) - cx)[None, :]
    r = np.sqrt(xs**2 + (ys * (h / w)) ** 2)
    r = np.clip(r / r.max(), 0, 1) ** power
    inner = np.array(inner, dtype=np.float64)
    outer = np.array(outer, dtype=np.float64)
    out = (
        inner[None, None, :] * (1 - r[..., None]) + outer[None, None, :] * r[..., None]
    )
    return out.astype(np.uint8)


# --------------------------------------------------------------------------
# compositing helpers (float RGB in [0,255])
# --------------------------------------------------------------------------
def screen(base, layer):
    b = base / 255.0
    l = layer / 255.0
    return (1 - (1 - b) * (1 - l)) * 255.0


def add(base, layer, amount=1.0):
    return np.clip(base + layer * amount, 0, 255)


def alpha_over(base, rgb, a):
    """a: (H,W) or (H,W,1) in [0,1]."""
    if a.ndim == 2:
        a = a[..., None]
    return base * (1 - a) + np.asarray(rgb, dtype=np.float64) * a


# --------------------------------------------------------------------------
# primitives, all as additive light on a float buffer
# --------------------------------------------------------------------------
def _grid(h, w):
    ys = np.arange(h)[:, None]
    xs = np.arange(w)[None, :]
    return ys, xs


_KERNEL_CACHE: dict = {}


def _glow_kernel(rr):
    """A cached normalised gaussian falloff of on-screen radius rr (bucketed to
    the nearest 2px so a whole render reuses a handful of arrays)."""
    rr = max(1, int(round(rr / 2) * 2))
    k = _KERNEL_CACHE.get(rr)
    if k is None:
        span = rr * 2  # ~2 sigma each side is plenty and keeps the paste small
        ax = np.arange(-span, span + 1, dtype=np.float64)
        d2 = ax[:, None] ** 2 + ax[None, :] ** 2
        k = np.exp(-d2 / (2.0 * rr * rr))
        _KERNEL_CACHE[rr] = k
    return k


def glow_dots(buf, xs, ys, radius, color, intensity):
    """Soft additive dots via a cached gaussian kernel paste -- no per-dot
    transcendental pass over the frame. xs/ys/radius/intensity are per-dot
    scalars or arrays; color is one RGB."""
    h, w = buf.shape[:2]
    xs = np.atleast_1d(xs).astype(np.float64)
    ys = np.atleast_1d(ys).astype(np.float64)
    radius = np.broadcast_to(np.atleast_1d(radius).astype(np.float64), xs.shape)
    intensity = np.broadcast_to(np.atleast_1d(intensity).astype(np.float64), xs.shape)
    color = np.array(color, dtype=np.float64)
    for x, y, rr, inten in zip(xs, ys, radius, intensity):
        if inten <= 0.001 or rr <= 0.5:
            continue
        k = _glow_kernel(min(rr, 90))
        kh = k.shape[0] // 2
        y0, y1 = int(y) - kh, int(y) + kh + 1
        x0, x1 = int(x) - kh, int(x) + kh + 1
        ky0, kx0 = max(0, -y0), max(0, -x0)
        dy0, dx0 = max(0, y0), max(0, x0)
        dy1, dx1 = min(h, y1), min(w, x1)
        if dy1 <= dy0 or dx1 <= dx0:
            continue
        sub = k[ky0 : ky0 + (dy1 - dy0), kx0 : kx0 + (dx1 - dx0)]
        buf[dy0:dy1, dx0:dx1] += sub[..., None] * (color * inten)
    return buf


def bars(buf, values, color, baseline=None, gap=0.15, glow=0.0):
    """A row of vertical bars along the bottom. values in [0,1]."""
    h, w = buf.shape[:2]
    n = len(values)
    if n == 0:
        return buf
    if baseline is None:
        baseline = int(h * 0.92)
    slot = w / n
    bw = slot * (1 - gap)
    color = np.array(color, dtype=np.float64)
    for i, v in enumerate(values):
        v = float(np.clip(v, 0, 1))
        bh = int(v * h * 0.7)
        if bh < 2:
            continue
        x0 = int(i * slot + (slot - bw) / 2)
        x1 = int(x0 + bw)
        y0 = max(0, baseline - bh)
        buf[y0:baseline, x0:x1] += color * (0.55 + 0.45 * v)
        if glow > 0:
            cx = (x0 + x1) / 2
            glow_dots(buf, cx, y0, min(bw * 0.5, 48) * (0.6 + v), color, glow * v)
    return buf


def ring(buf, cx, cy, radius, thickness, values, color):
    """A circular equaliser: `values` sampled around a ring."""
    h, w = buf.shape[:2]
    n = len(values)
    if n == 0:
        return buf
    color = np.array(color, dtype=np.float64)
    ang = np.linspace(0, 2 * np.pi, n, endpoint=False)
    for a, v in zip(ang, values):
        v = float(np.clip(v, 0, 1))
        r0 = radius
        r1 = radius + thickness * (0.2 + v)
        for rr in np.linspace(r0, r1, max(2, int((r1 - r0) / 2))):
            x = int(cx + np.cos(a) * rr)
            y = int(cy + np.sin(a) * rr)
            if 0 <= x < w and 0 <= y < h:
                buf[max(0, y - 1) : y + 2, max(0, x - 1) : x + 2] += color * (
                    0.4 + 0.6 * v
                )
    return buf


# --------------------------------------------------------------------------
# image layer with Ken Burns / parallax
# --------------------------------------------------------------------------
def load_image_cover(path, h, w):
    im = Image.open(path).convert("RGB")
    iw, ih = im.size
    scale = max(w / iw, h / ih)
    im = im.resize((int(iw * scale) + 2, int(ih * scale) + 2), Image.Resampling.LANCZOS)
    return np.asarray(im, dtype=np.float64)


def ken_burns(img, h, w, t, zoom_start=1.0, zoom_end=1.12, pan=(0.0, 0.0), fast=False):
    """Crop a (H2,W2,3) source to (h,w) with a zoom/pan animated by t in [0,1].
    `fast` uses nearest-neighbour resampling (draft quality)."""
    ih, iw = img.shape[:2]
    z = zoom_start + (zoom_end - zoom_start) * t
    cw, ch = w / z, h / z
    max_x = max(0, iw - cw)
    max_y = max(0, ih - ch)
    x = np.clip((iw - cw) / 2 + pan[0] * max_x * (t - 0.5) * 2, 0, max_x)
    y = np.clip((ih - ch) / 2 + pan[1] * max_y * (t - 0.5) * 2, 0, max_y)
    crop = img[int(y) : int(y + ch), int(x) : int(x + cw)]
    mode = Image.Resampling.NEAREST if fast else Image.Resampling.BILINEAR
    pil = Image.fromarray(np.clip(crop, 0, 255).astype(np.uint8)).resize((w, h), mode)
    return np.asarray(pil, dtype=np.float64)


_CLOUD_CACHE: dict = {}


def clouds(h, w, t, tint, density=0.5, speed=0.02, seed=7):
    """A soft, slow, low-frequency haze that scrolls sideways. Returns an RGB
    array in [0, 255] scale (0 where there is no haze). Blend it with screen()
    or alpha_over(); do not rescale it again."""
    key = (h, w, seed)
    tile = _CLOUD_CACHE.get(key)
    if tile is None:
        rng = np.random.default_rng(seed)
        # a handful of octaves of very-low-frequency noise -> smooth billows
        acc = np.zeros((h, w * 2), dtype=np.float64)
        for oct_ in (1, 2, 4):
            small = rng.random(
                (max(2, h // (48 * oct_)), max(2, (w * 2) // (48 * oct_)))
            )
            up = (
                np.asarray(
                    Image.fromarray((small * 255).astype(np.uint8)).resize(
                        (w * 2, h), Image.Resampling.BILINEAR
                    ),
                    dtype=np.float64,
                )
                / 255.0
            )
            acc += up / oct_
        acc = (acc - acc.min()) / max(1e-6, acc.max() - acc.min())
        tile = acc
        _CLOUD_CACHE[key] = tile
    off = int((t * speed * w * 40) % w)
    field = tile[:, off : off + w]
    # gentle contrast around the density point; never binary
    field = np.clip((field - (0.85 - 0.5 * density)) * 1.6, 0.0, 1.0) * (
        0.35 + 0.4 * density
    )
    return field[..., None] * np.array(tint, dtype=np.float64)


def to_uint8(buf):
    return np.clip(buf, 0, 255).astype(np.uint8)


# --------------------------------------------------------------------------
# ForgeArtData sprite rasteriser  (palette-indexed ASCII rows -> RGBA)
# --------------------------------------------------------------------------
def rasterize_sprite(rows, palette_colors, transparent=".", scale=1):
    """rows: list[str]. palette_colors: {char: '#rrggbb'}. Returns (H,W,4) uint8."""
    h = len(rows)
    w = max((len(r) for r in rows), default=0)
    out = np.zeros((h, w, 4), dtype=np.uint8)
    for y, line in enumerate(rows):
        for x, ch in enumerate(line):
            if ch == transparent or ch == " ":
                continue
            hexv = palette_colors.get(ch)
            if not hexv:
                continue
            r, g, b = hex_rgb(hexv)
            out[y, x] = (r, g, b, 255)
    if scale > 1:
        pil = Image.fromarray(out).resize(
            (w * scale, h * scale), Image.Resampling.NEAREST
        )
        out = np.asarray(pil)
    return out


def blit_rgba(buf, sprite, x, y, tint=(255, 255, 255), opacity=1.0):
    """Additive-ish alpha blit of an RGBA sprite onto a float RGB buffer,
    centred at (x, y). Out-of-bounds is clipped."""
    H, W = buf.shape[:2]
    sh, sw = sprite.shape[:2]
    x0, y0 = int(x - sw / 2), int(y - sh / 2)
    sx0, sy0 = max(0, -x0), max(0, -y0)
    dx0, dy0 = max(0, x0), max(0, y0)
    dx1, dy1 = min(W, x0 + sw), min(H, y0 + sh)
    if dx1 <= dx0 or dy1 <= dy0:
        return buf
    src = sprite[sy0 : sy0 + (dy1 - dy0), sx0 : sx0 + (dx1 - dx0)]
    a = (src[..., 3:4].astype(np.float64) / 255.0) * opacity
    rgb = src[..., :3].astype(np.float64) * (np.array(tint, dtype=np.float64) / 255.0)
    region = buf[dy0:dy1, dx0:dx1]
    buf[dy0:dy1, dx0:dx1] = region * (1 - a) + rgb * a
    return buf
