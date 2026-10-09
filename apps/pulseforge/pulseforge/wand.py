"""
Click a colour, get a region.

Painting a region by hand is the slow part of building a shot, and the
automatic detector in `autoregions.py` only knows four things: sky, water,
foliage and lights. Everything else -- a wall, one window, a jacket, a single
tree -- is a wand job: click a pixel, grow outward through everything close
enough in colour, stop at the edges.

Two modes, because both are genuinely useful. **Contiguous** takes only the
patch you clicked, so clicking one window does not select every window in the
building. **Everything similar** takes all of them, which is what you want for
foliage scattered across a frame.

The result is an ordinary brush PNG in the project's `masks/` folder, so the
brush and the eraser work on it afterwards exactly like any other region. This
gets you 90% of the way and then you fix the rest by hand, which is a much
better deal than starting from nothing.
"""

import numpy as np
from PIL import Image, ImageDraw

from . import imageops

WORK_W = 480  # the growth runs here; the saved mask is full size


def _work_image(path):
    im = Image.open(path).convert("RGB")
    w, h = im.size
    tw = min(WORK_W, w)
    th = max(8, int(round(h * tw / max(1, w))))
    return np.asarray(
        im.resize((tw, th), Image.Resampling.BILINEAR), dtype=np.float32
    ), (w, h)


def select(path, x, y, tolerance=0.12, contiguous=True, sample=2):
    """A mask grown from the pixel at (x, y), both given as 0..1 of the image.

    Returns a float mask at working resolution. `sample` averages a small patch
    around the click instead of trusting one pixel, so landing on a stray bright
    speck does not ruin the selection.
    """
    small, _full = _work_image(path)
    h, w = small.shape[:2]
    sx = int(np.clip(round(float(x) * w), 0, w - 1))
    sy = int(np.clip(round(float(y) * h), 0, h - 1))

    r = max(0, int(sample))
    patch = small[
        max(0, sy - r) : min(h, sy + r + 1), max(0, sx - r) : min(w, sx + r + 1)
    ]
    seed = patch.reshape(-1, 3).mean(axis=0)

    # 441.7 is the longest possible distance in RGB, so tolerance reads 0..1
    dist = np.linalg.norm(small - seed, axis=2) / 441.673
    similar = dist < max(0.005, float(tolerance))

    if not contiguous:
        return similar.astype(np.float32)

    # Flood fill through PIL rather than a Python loop over pixels. The image is
    # strictly 0 or 255, so filling with 128 marks the reached area unambiguously.
    if not similar[sy, sx]:
        return np.zeros((h, w), dtype=np.float32)
    # .copy() matters: Image.fromarray aliases the numpy buffer, and the fill
    # then writes somewhere the readback does not see
    binary = Image.fromarray((similar * 255).astype(np.uint8)).copy()
    ImageDraw.floodfill(binary, (sx, sy), 128, thresh=0)
    return (np.array(binary) == 128).astype(np.float32)


def to_png(mask, path, out_w, out_h, feather=0.01, smooth=1):
    """Clean the selection up and save it as a full-size brush PNG."""
    m = mask
    if smooth > 0:
        # close pinholes and drop speckle without pulling in scipy
        m = (imageops.box_blur(m, int(smooth) + 1, passes=1) > 0.45).astype(np.float32)
    im = Image.fromarray((np.clip(m, 0, 1) * 255).astype(np.uint8)).resize(
        (int(out_w), int(out_h)), Image.Resampling.BILINEAR
    )
    arr = np.asarray(im, dtype=np.float32)
    r = int(float(feather) * min(int(out_w), int(out_h)))
    if r >= 1:
        arr = imageops.box_blur(arr, r, passes=2)
    Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).save(str(path))
    return str(path)


def image_size(path):
    with Image.open(path) as im:
        return im.size
