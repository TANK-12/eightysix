"""
Loading the user's own artwork.

Three ways people actually have animation lying around, all landing as the same
thing -- a list of (h, w, 4) uint8 RGBA frames:

* a **folder** of numbered PNGs,
* an animated **GIF** or WebP,
* a **sprite strip**: one image holding N frames side by side.

Also loads plain single images with their alpha intact, which is what the
stacked PNG layers in a shot are made of.

Everything is cached by path and mtime, so re-exporting a sprite from an editor
shows up on the next render without restarting anything.
"""

import os

import numpy as np
from PIL import Image, ImageSequence

_CACHE: dict = {}
_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")


def _stamp(path):
    try:
        st = os.stat(path)
        return (st.st_mtime, st.st_size)
    except OSError:
        return None


def _dir_stamp(path):
    try:
        names = sorted(n for n in os.listdir(path) if n.lower().endswith(_IMAGE_EXTS))
        return (len(names), names[0] if names else "", names[-1] if names else "")
    except OSError:
        return None


def _rgba(im):
    return np.asarray(im.convert("RGBA"), dtype=np.uint8)


def load_sequence(path, strip_columns=0):
    """Every frame at `path`, as a list of RGBA arrays. Empty list if missing."""
    path = str(path or "")
    if not path or not os.path.exists(path):
        return []

    is_dir = os.path.isdir(path)
    key = (os.path.abspath(path), int(strip_columns))
    stamp = _dir_stamp(path) if is_dir else _stamp(path)
    hit = _CACHE.get(key)
    if hit is not None and hit[0] == stamp:
        return hit[1]

    frames = []
    try:
        if is_dir:
            for name in sorted(os.listdir(path)):
                if name.lower().endswith(_IMAGE_EXTS):
                    with Image.open(os.path.join(path, name)) as im:
                        frames.append(_rgba(im))
        else:
            with Image.open(path) as im:
                n = getattr(im, "n_frames", 1)
                if n > 1:
                    frames = [_rgba(f) for f in ImageSequence.Iterator(im)]
                elif strip_columns > 1:
                    full = _rgba(im)
                    w = full.shape[1] // int(strip_columns)
                    frames = [
                        full[:, k * w : (k + 1) * w] for k in range(int(strip_columns))
                    ]
                else:
                    frames = [_rgba(im)]
    except Exception:
        frames = []

    if len(_CACHE) > 24:
        _CACHE.clear()
    _CACHE[key] = (stamp, frames)
    return frames


def load_image_rgba(path):
    """One RGBA image, alpha preserved -- the stacked-layer loader."""
    seq = load_sequence(path)
    return seq[0] if seq else None


def frame_index(tl, count, fps):
    """Which frame of a `count`-long clip to show now.

    The playback rate is nudged to the nearest one that fits a whole number of
    clip cycles into the loop, so a piece of hand-drawn animation ends where it
    began instead of jumping at the seam.
    """
    if count <= 0:
        return 0
    cycles = max(1, int(round(tl.loop_s * max(0.1, float(fps)) / count)))
    return int((tl.t / tl.loop_s) * cycles * count) % count


def fit_into(sprite, bh, bw, mode="contain", scale=1.0):
    """Resize an RGBA sprite for a box. Returns a new RGBA array."""
    sh, sw = sprite.shape[:2]
    if sh == 0 or sw == 0 or bh <= 0 or bw <= 0:
        return sprite
    if mode == "stretch":
        tw, th = bw, bh
    else:
        f = min(bw / sw, bh / sh) if mode == "contain" else max(bw / sw, bh / sh)
        tw, th = max(1, int(sw * f)), max(1, int(sh * f))
    tw = max(1, int(tw * float(scale)))
    th = max(1, int(th * float(scale)))
    if (th, tw) == (sh, sw):
        return sprite
    return np.asarray(
        Image.fromarray(sprite).resize((tw, th), Image.Resampling.BILINEAR),
        dtype=np.uint8,
    )


def blit(frame, sprite, x, y, opacity=1.0, mask=None, mode="over"):
    """Alpha-composite an RGBA sprite onto a float32 RGB frame, top-left at
    (x, y). `mask` further limits it to a region; `mode` picks over/screen/add."""
    fh, fw = frame.shape[:2]
    sh, sw = sprite.shape[:2]
    x, y = int(round(x)), int(round(y))
    sx0, sy0 = max(0, -x), max(0, -y)
    dx0, dy0 = max(0, x), max(0, y)
    dx1, dy1 = min(fw, x + sw), min(fh, y + sh)
    if dx1 <= dx0 or dy1 <= dy0:
        return frame
    src = sprite[sy0 : sy0 + (dy1 - dy0), sx0 : sx0 + (dx1 - dx0)]
    a = (src[..., 3:4].astype(np.float32) / 255.0) * float(opacity)
    if mask is not None:
        a = a * mask[dy0:dy1, dx0:dx1][..., None]
    rgb = src[..., :3].astype(np.float32)
    region = frame[dy0:dy1, dx0:dx1]
    if mode == "screen":
        region[...] = 255.0 - (255.0 - region) * (1.0 - a * (rgb / 255.0))
    elif mode == "add":
        region[...] = np.clip(region + rgb * a, 0.0, 255.0)
    else:
        region[...] = region * (1.0 - a) + rgb * a
    return frame
