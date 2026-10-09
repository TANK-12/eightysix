"""Directional camera motion between video keyframes.

A diffusion model chained through img2img cannot reliably invent camera
movement on its own -- ask it for "pan left" and it mostly just redraws the
same framing. So the actual camera motion here is a real 2D affine warp
(pan/zoom/rotate) applied with Pillow *before* the frame goes into img2img.
img2img then "heals" the warp: it fills in the edge a pan exposes and
restores detail a zoom softened, while staying faithful to the prompt. This
is the same trick classic AI-animation tools (Deforum etc.) use.

Two rules keep the warp clean (rebuilt 2026-10-08, see docs/AUDIT.md):

- Any number of steps is ONE resample from the base frame (`warp(..., steps=n)`),
  not n chained resamples, so repeated warps do not blur.
- Whatever the camera moves past the frame's edge is filled with a mirror
  image of the frame, never black. The old pan filled the wrong side and left
  a black strip growing 3% a step; zoom-out crashed outright.
"""

import io
import math

from PIL import Image, ImageOps, ImageStat

# name -> (dx_frac, dy_frac, zoom_per_frame, rotate_deg_per_frame)
# dx/dy are the fraction of width/height the camera moves per step (content
# appears to move the opposite way, so "pan-right" reveals new content on
# the right). Positive rotation turns the content counter-clockwise.
PRESETS = {
    "static": (0.0, 0.0, 1.000, 0.0),
    "pan-left": (-0.03, 0.0, 1.000, 0.0),
    "pan-right": (0.03, 0.0, 1.000, 0.0),
    "pan-up": (0.0, -0.03, 1.000, 0.0),
    "pan-down": (0.0, 0.03, 1.000, 0.0),
    "zoom-in": (0.0, 0.0, 1.025, 0.0),
    "zoom-out": (0.0, 0.0, 0.975, 0.0),
    "orbit-cw": (0.0, 0.0, 1.008, 0.6),
    "orbit-ccw": (0.0, 0.0, 1.008, -0.6),
}


def _png(img):
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def _mirror_mosaic(img, kx, ky):
    """The frame surrounded by `kx` / `ky` rings of its own mirror images,
    so a camera that moves past any edge still sees plausible content."""
    w, h = img.size
    tiles = {
        (False, False): img,
        (True, False): ImageOps.mirror(img),
        (False, True): ImageOps.flip(img),
        (True, True): ImageOps.flip(ImageOps.mirror(img)),
    }
    big = Image.new("RGB", ((2 * kx + 1) * w, (2 * ky + 1) * h))
    for j in range(-ky, ky + 1):
        for i in range(-kx, kx + 1):
            big.paste(tiles[(i % 2 == 1, j % 2 == 1)], ((i + kx) * w, (j + ky) * h))
    return big


def _fold(offset, size):
    """A mirror tiling repeats every two frames: fold a centre offset into
    (-size, size] so a long pan never needs a bigger mosaic."""
    off = offset % (2 * size)
    return off - 2 * size if off > size else off


def camera(direction, steps=1.0, strength=1.0):
    """Total (dx, dy, zoom, rotate_deg) after `steps` steps of a preset.
    Unknown names are static."""
    dx, dy, zoom, rot = PRESETS.get(direction, PRESETS["static"])
    zoom = 1.0 + (zoom - 1.0) * strength
    return (
        dx * strength * steps,
        dy * strength * steps,
        zoom**steps,
        rot * strength * steps,
    )


def warp(image_bytes, direction, steps=1.0, strength=1.0):
    """The frame as the camera sees it after `steps` steps of `direction`.

    One affine resample, edges mirror-filled. `strength` scales the preset
    (0 = no motion, 1 = the preset as listed)."""
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    dx, dy, zoom, rot = camera(direction, steps, strength)
    if dx == 0 and dy == 0 and zoom == 1.0 and rot == 0:
        return _png(img)
    w, h = img.size
    s = 1.0 / zoom  # the camera sees a window `s` times the frame's size
    src = img
    if s > 1.0:
        # zooming out: shrink the frame first, so the mosaic stays small and
        # the resample below is close to 1:1
        src = img.resize(
            (max(1, round(w / s)), max(1, round(h / s))), Image.Resampling.LANCZOS
        )
    sw, sh = src.size
    fx, fy = sw / w, sh / h  # frame coords -> src coords
    t = math.radians(-rot)  # positive turns the content counter-clockwise
    cos_t, sin_t = math.cos(t), math.sin(t)
    # Output pixel (x, y) samples the frame at
    #   centre + R(t) * s * ((x, y) - (w/2, h/2)),   centre = middle + pan.
    off_x = _fold((dx * w) * fx, sw)
    off_y = _fold((dy * h) * fy, sh)
    half_x = s * fx * (abs(cos_t) * w / 2 + abs(sin_t) * h / 2)
    half_y = s * fy * (abs(sin_t) * w / 2 + abs(cos_t) * h / 2)
    kx = max(0, math.ceil((abs(off_x) + half_x - sw / 2) / sw)) + 1
    ky = max(0, math.ceil((abs(off_y) + half_y - sh / 2) / sh)) + 1
    big = _mirror_mosaic(src, kx, ky)
    cx = sw / 2 + off_x + kx * sw
    cy = sh / 2 + off_y + ky * sh
    a, b = cos_t * s * fx, sin_t * s * fx
    d, e = -sin_t * s * fy, cos_t * s * fy
    c = cx - a * (w / 2) - b * (h / 2)
    f = cy - d * (w / 2) - e * (h / 2)
    out = big.transform(
        (w, h), Image.Transform.AFFINE, (a, b, c, d, e, f), Image.Resampling.BICUBIC
    )
    return _png(out)


def apply_motion(image_bytes, direction, strength=1.0):
    """One step of camera motion (kept for callers of the old API)."""
    return warp(image_bytes, direction, steps=1.0, strength=strength)


def color_match(image_bytes, ref_bytes, weight):
    """Pull a frame's colours toward a reference frame's by `weight` (0-1):
    each channel's mean and spread are moved toward the reference's. This is
    what stops colour drift when frames are chained through img2img, without
    blending the reference's *picture* in (which ghosts a moving camera)."""
    if weight <= 0:
        return image_bytes
    weight = min(weight, 1.0)
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    ref = Image.open(io.BytesIO(ref_bytes)).convert("RGB")
    st, sr = ImageStat.Stat(img), ImageStat.Stat(ref)
    bands = []
    for band, m, sd, mr, sdr in zip(
        img.split(), st.mean, st.stddev, sr.mean, sr.stddev
    ):
        gain = (sdr / sd) if sd > 1e-6 else 1.0
        lut = []
        for v in range(256):
            target = (v - m) * gain + mr
            lut.append(max(0, min(255, round(v + weight * (target - v)))))
        bands.append(band.point(lut))
    return _png(Image.merge("RGB", bands))
