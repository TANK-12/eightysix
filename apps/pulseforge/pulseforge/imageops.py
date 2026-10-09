"""
The pixel maths the living scene is built on.

Two primitives, both pure numpy (scipy is not installed and is not worth a
dependency for this):

* `displace()` -- bilinear resampling of a frame through a per-pixel offset
  field, confined to a bounding box and blended through a mask. Every
  geometric motion effect (water, sway, flow, breathe) is a different way of
  filling in that offset field; none of them touch pixels directly.
* `box_blur()` -- a separable moving average via `cumsum`. Two passes of it
  approximate a gaussian closely enough for feathered masks and bloom, at a
  cost that does not depend on the radius.

Work happens in float32: these run on every frame of every layer, and float64
doubles the memory traffic for no visible benefit.
"""

import math

import numpy as np


# --------------------------------------------------------------------------
# direction
# --------------------------------------------------------------------------
def direction_vector(degrees):
    """A compass angle as an (across, down) step in array coordinates.

    Angles read the way people expect them to -- 0 is right, 90 is up, 180 is
    left, 270 is down -- while array rows grow *downward*, so the vertical
    component is negated here rather than in each caller. Getting this wrong is
    not a subtle bug: it makes rain fall upward.
    """
    rad = math.radians(float(degrees))
    return math.cos(rad), -math.sin(rad)


# --------------------------------------------------------------------------
# blur
# --------------------------------------------------------------------------
def _blur1d(a, r, axis):
    n = a.shape[axis]
    if r < 1 or n < 2:
        return a
    r = int(min(r, max(1, n - 1)))
    pad = [(0, 0)] * a.ndim
    pad[axis] = (r, r)
    p = np.pad(a, pad, mode="edge")
    c = np.cumsum(p, axis=axis, dtype=np.float32)
    zshape = list(c.shape)
    zshape[axis] = 1
    c = np.concatenate([np.zeros(zshape, dtype=np.float32), c], axis=axis)
    hi = np.take(c, np.arange(2 * r + 1, 2 * r + 1 + n), axis=axis)
    lo = np.take(c, np.arange(0, n), axis=axis)
    return (hi - lo) / float(2 * r + 1)


def box_blur(a, radius, passes=2):
    """Blur a (H, W) or (H, W, C) array. Two passes ~= a gaussian."""
    r = int(radius)
    if r < 1:
        return a
    out = np.asarray(a, dtype=np.float32)
    for _ in range(max(1, int(passes))):
        out = _blur1d(out, r, 0)
        out = _blur1d(out, r, 1)
    return out


# --------------------------------------------------------------------------
# displacement
# --------------------------------------------------------------------------
def _sample_shift(src, dx, dy, box, fast=False):
    """A whole-region translation -- what a parallax nudge or a scroll is.

    No per-pixel index arrays: lift out just the rows and columns the four
    bilinear taps need (padding at the edges only when the shift runs off the
    picture), then combine four slice views with scalar weights. About five
    times quicker than gathering, and this runs on every layer of every frame.
    """
    h, w = src.shape[:2]
    y0, y1, x0, x1 = box
    bh, bw = y1 - y0, x1 - x0
    if fast:
        dx, dy = round(dx), round(dy)
    iy, ix = int(np.floor(dy)), int(np.floor(dx))
    wy = np.float32(dy - iy)
    wx = np.float32(dx - ix)

    ny0, ny1 = y0 + iy, y0 + iy + bh + 1
    nx0, nx1 = x0 + ix, x0 + ix + bw + 1
    cy0 = min(max(0, ny0), h - 1)
    cy1 = max(cy0 + 1, min(h, ny1))
    cx0 = min(max(0, nx0), w - 1)
    cx1 = max(cx0 + 1, min(w, nx1))
    sub = src[cy0:cy1, cx0:cx1]

    pt, pb = cy0 - ny0, ny1 - cy1
    pl, pr = cx0 - nx0, nx1 - cx1
    if pt or pb or pl or pr:
        sub = np.pad(
            sub,
            ((max(0, pt), max(0, pb)), (max(0, pl), max(0, pr)), (0, 0)),
            mode="edge",
        )
        sub = sub[: bh + 1, : bw + 1]

    a = sub[:bh, :bw]
    if wx == 0 and wy == 0:
        return a.astype(np.float32, copy=True)
    b = sub[:bh, 1 : 1 + bw]
    c = sub[1 : 1 + bh, :bw]
    d = sub[1 : 1 + bh, 1 : 1 + bw]
    return (
        a * ((1 - wx) * (1 - wy))
        + b * (wx * (1 - wy))
        + c * ((1 - wx) * wy)
        + d * (wx * wy)
    )


def sample(frame, dx, dy, box, fast=False):
    """Bilinearly read `frame` at (x+dx, y+dy) for every pixel in `box`.

    Returns a fresh (bh, bw, 3) block rather than writing anything, because
    several effects need two differently-offset samples to blend between (see
    `motion/flow.py`, which hides a scroll's reset that way). Reads come from
    the whole frame, so content slides in from outside the region instead of
    smearing at its edge.

    Two paths, because this is the hot loop of the whole renderer. A constant
    offset -- what a parallax nudge is -- only needs one index per row and one
    per column, so it goes through cheap outer indexing. A varying field falls
    back to flat linear indices, which numpy gathers faster than a pair of 2-D
    index arrays.
    """
    h, w = frame.shape[:2]
    y0, y1, x0, x1 = box
    bh, bw = y1 - y0, x1 - x0
    src = frame if frame.dtype == np.float32 else frame.astype(np.float32)

    if np.ndim(dx) == 0 and np.ndim(dy) == 0:
        return _sample_shift(src, float(dx), float(dy), box, fast)

    ys = np.arange(y0, y1, dtype=np.float32)[:, None]
    xs = np.arange(x0, x1, dtype=np.float32)[None, :]
    sx = np.clip(xs + dx, 0.0, w - 1.001)
    sy = np.clip(ys + dy, 0.0, h - 1.001)
    sx = np.ascontiguousarray(np.broadcast_to(sx, (bh, bw)), dtype=np.float32)
    sy = np.ascontiguousarray(np.broadcast_to(sy, (bh, bw)), dtype=np.float32)

    flat = src.reshape(-1, src.shape[2])
    if fast:
        lin = np.rint(sy).astype(np.intp) * w + np.rint(sx).astype(np.intp)
        return flat.take(lin, axis=0)

    ix0 = sx.astype(np.intp)
    iy0 = sy.astype(np.intp)
    fx = (sx - ix0)[..., None]
    fy = (sy - iy0)[..., None]
    row0 = iy0 * w
    row1 = np.minimum(iy0 + 1, h - 1) * w
    ix1 = np.minimum(ix0 + 1, w - 1)
    return (
        flat.take(row0 + ix0, axis=0) * ((1 - fx) * (1 - fy))
        + flat.take(row0 + ix1, axis=0) * (fx * (1 - fy))
        + flat.take(row1 + ix0, axis=0) * ((1 - fx) * fy)
        + flat.take(row1 + ix1, axis=0) * (fx * fy)
    )


def composite(frame, block, mask, box):
    """Blend a (bh, bw, 3) block back into `frame` through `mask`, in place."""
    y0, y1, x0, x1 = box
    region = frame[y0:y1, x0:x1]
    if mask is None:
        region[...] = block
    else:
        # region += (block - region) * m -- half the temporaries of the
        # equivalent region*(1-m) + block*m, and this runs per layer per frame
        block = np.subtract(block, region)
        block *= mask[y0:y1, x0:x1][..., None]
        region += block
    return frame


def displace(frame, dx, dy, mask=None, box=None, fast=False):
    """Resample `frame` inside `box` through an offset field and blend it back
    through `mask`. Modifies `frame` in place and returns it. This is the whole
    of what a geometric motion effect does -- each one just fills in dx/dy
    differently."""
    h, w = frame.shape[:2]
    box = box if box is not None else (0, h, 0, w)
    if box[1] <= box[0] or box[3] <= box[2]:
        return frame
    return composite(frame, sample(frame, dx, dy, box, fast=fast), mask, box)


def zoom_field(box, scale, cx=0.5, cy=0.5):
    """Offset field for scaling the box's content by `scale` about a point
    given in box-relative coordinates. `scale` > 1 magnifies."""
    y0, y1, x0, x1 = box
    bh, bw = y1 - y0, x1 - x0
    px = x0 + cx * bw
    py = y0 + cy * bh
    ys = np.arange(y0, y1, dtype=np.float32)[:, None]
    xs = np.arange(x0, x1, dtype=np.float32)[None, :]
    inv = 1.0 / max(1e-6, float(scale))
    dx = (xs - px) * (inv - 1.0)
    dy = (ys - py) * (inv - 1.0)
    return dx, dy


def grid(box):
    """Normalised (0..1) y and x ramps over a box, ready to broadcast."""
    y0, y1, x0, x1 = box
    gy = np.linspace(0.0, 1.0, max(1, y1 - y0), dtype=np.float32)[:, None]
    gx = np.linspace(0.0, 1.0, max(1, x1 - x0), dtype=np.float32)[None, :]
    return gy, gx


def value_noise(h, w, cells, seed=0, octaves=2):
    """Smooth low-frequency noise in [0, 1] -- upsampled random cells, a couple
    of octaves deep. Used for gusts, cloud fields and shimmer."""
    from PIL import Image

    rng = np.random.default_rng(seed)
    acc = np.zeros((h, w), dtype=np.float32)
    amp = 0.0
    for o in range(max(1, int(octaves))):
        n = max(2, int(cells * (2**o)))
        small = (rng.random((n, n)) * 255).astype(np.uint8)
        up = np.asarray(
            Image.fromarray(small).resize((w, h), Image.Resampling.BICUBIC),
            dtype=np.float32,
        )
        acc += up * (0.5**o)
        amp += 0.5**o
    acc /= max(1e-6, amp) * 255.0
    return np.clip(acc, 0.0, 1.0)


def _upsample_wrapping(g, h, w):
    """Smoothly blow up a small grid, reading neighbours modulo its size.

    The modulo is the whole point: sampling wraps around the grid, so the
    result is periodic by construction rather than by hoping the edges happen
    to line up. Resizing through an image library cannot do this -- its kernel
    clamps at the border, which leaves a faint seam exactly where a scrolling
    cloud layer would show it.
    """
    n = g.shape[0]
    ys = np.arange(h, dtype=np.float32) * n / h
    xs = np.arange(w, dtype=np.float32) * n / w
    y0 = np.floor(ys).astype(np.intp)
    x0 = np.floor(xs).astype(np.intp)
    fy = (ys - y0)[:, None]
    fx = (xs - x0)[None, :]
    # smoothstep the blend so the result has no visible grid creases
    fy = fy * fy * (3.0 - 2.0 * fy)
    fx = fx * fx * (3.0 - 2.0 * fx)
    y1 = (y0 + 1) % n
    x1 = (x0 + 1) % n
    y0 %= n
    x0 %= n
    return (
        g[np.ix_(y0, x0)] * ((1 - fx) * (1 - fy))
        + g[np.ix_(y0, x1)] * (fx * (1 - fy))
        + g[np.ix_(y1, x0)] * ((1 - fx) * fy)
        + g[np.ix_(y1, x1)] * (fx * fy)
    ).astype(np.float32)


def periodic_noise(h, w, cells=4, seed=0, octaves=3):
    """Smooth billowy noise that tiles *exactly* in both axes.

    A few octaves of random grids, each upsampled with wrap-around sampling.
    Rolling the result by any number of pixels leaves it meeting itself
    perfectly, which is what the cloud, shimmer and grain layers rely on: they
    are all scrolled, and all of them have to come back to the start when the
    loop closes.
    """
    rng = np.random.default_rng(seed)
    acc = np.zeros((h, w), dtype=np.float32)
    amp_total = 0.0
    for o in range(max(1, int(octaves))):
        amp = 0.5**o
        n = max(2, int(cells * (2**o)))
        acc += _upsample_wrapping(rng.random((n, n)).astype(np.float32), h, w) * amp
        amp_total += amp
    acc /= max(1e-6, amp_total)
    return np.clip(acc, 0.0, 1.0).astype(np.float32)
