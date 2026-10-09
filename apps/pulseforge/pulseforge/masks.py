"""
Regions -- the marked-off parts of a background image that are allowed to move.

A region is stored in `project.json` as a small dict and rasterised here into a
feathered `(H, W)` float mask in [0, 1]. Two ways to draw one, because neither
alone covers the job:

* **polygon** -- normalised corner points, straight in the JSON. Right for a
  sky, a window, a clean waterline; hand-editable and diffable.
* **brush** -- a greyscale PNG in the project's `masks/` folder, painted in the
  editor. Right for hair, foliage and shorelines, where clicking corners is
  miserable.

Both kinds go through the same feather and the same bounding box, so nothing
downstream needs to know which one it got. `feather` is a fraction of the
image's short side, so a region keeps its softness when the same project is
rendered at a different size.
"""

import hashlib
import json
import os

import numpy as np
from PIL import Image, ImageDraw

from . import imageops

_CACHE: dict = {}
_CACHE_ORDER: list = []
_CACHE_MAX = 48

FULL_REGION = {"kind": "all", "feather": 0.0}


def region_key(region, h, w, base_dir=None):
    """A cache key that changes whenever the mask would render differently --
    including when a brush PNG is repainted, via its mtime."""
    payload = json.dumps(region or {}, sort_keys=True)
    stamp = ""
    name = (region or {}).get("brush")
    if name and base_dir:
        p = os.path.join(str(base_dir), str(name))
        try:
            stamp = f"{os.path.getmtime(p)}:{os.path.getsize(p)}"
        except OSError:
            stamp = "missing"
    digest = hashlib.sha1(f"{payload}|{stamp}".encode()).hexdigest()[:16]
    return (digest, int(h), int(w))


def _rasterize(region, h, w, base_dir):
    kind = (region or {}).get("kind", "all")

    if kind == "brush":
        name = region.get("brush")
        path = os.path.join(str(base_dir or ""), str(name or ""))
        if not name or not os.path.exists(path):
            return np.zeros((h, w), dtype=np.float32)
        im = Image.open(path).convert("L").resize((w, h), Image.Resampling.BILINEAR)
        return np.asarray(im, dtype=np.float32) / 255.0

    if kind in ("polygon", "rect"):
        im = Image.new("L", (w, h), 0)
        d = ImageDraw.Draw(im)
        shapes = region.get("shapes")
        if not shapes:
            pts = region.get("points") or []
            shapes = [pts] if pts else []
        for pts in shapes:
            if kind == "rect" and len(pts) == 2:
                (ax, ay), (bx, by) = pts
                d.rectangle(
                    [
                        (min(ax, bx) * w, min(ay, by) * h),
                        (max(ax, bx) * w, max(ay, by) * h),
                    ],
                    fill=255,
                )
            elif len(pts) >= 3:
                d.polygon([(float(x) * w, float(y) * h) for x, y in pts], fill=255)
        return np.asarray(im, dtype=np.float32) / 255.0

    # "all" -- the whole frame moves
    return np.ones((h, w), dtype=np.float32)


def build(region, h, w, base_dir=None):
    """The feathered mask for a region, cached. Never mutate what you get back."""
    key = region_key(region, h, w, base_dir)
    hit = _CACHE.get(key)
    if hit is not None:
        return hit

    m = _rasterize(region or FULL_REGION, h, w, base_dir)
    feather = float((region or {}).get("feather", 0.0) or 0.0)
    if feather > 0:
        r = max(1, int(round(feather * min(h, w))))
        m = imageops.box_blur(m, r)
    if (region or {}).get("invert"):
        m = 1.0 - m
    m = np.clip(m, 0.0, 1.0).astype(np.float32)

    _CACHE[key] = m
    _CACHE_ORDER.append(key)
    while len(_CACHE_ORDER) > _CACHE_MAX:
        _CACHE.pop(_CACHE_ORDER.pop(0), None)
    return m


def bbox(mask, pad=0, threshold=0.004):
    """The box worth doing work in: (y0, y1, x0, x1), padded and clamped.

    Effects run over this instead of the full frame, which is most of why a
    three-layer shot costs barely more than a one-layer one -- a region is
    usually a fraction of the picture.
    """
    h, w = mask.shape[:2]
    rows = np.nonzero(mask.max(axis=1) > threshold)[0]
    cols = np.nonzero(mask.max(axis=0) > threshold)[0]
    if len(rows) == 0 or len(cols) == 0:
        return (0, 0, 0, 0)
    pad = int(pad)
    y0 = max(0, int(rows[0]) - pad)
    y1 = min(h, int(rows[-1]) + 1 + pad)
    x0 = max(0, int(cols[0]) - pad)
    x1 = min(w, int(cols[-1]) + 1 + pad)
    return (y0, y1, x0, x1)


def is_empty(box):
    return box[1] <= box[0] or box[3] <= box[2]
