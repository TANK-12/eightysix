"""
What a shot is made of: a background, then transparent images stacked on it.

The background can be blurred and left as a soft bed; each image on top is a
PNG with real alpha, placed and scaled where you want it, carrying its own
depth. Depth is the whole point of stacking them -- a cut-out layer moves
further than the background as the camera drifts, and because it has genuine
transparency there is nothing showing through behind it. Painting a region on a
flat photo can only fake that; cut-outs do it properly.

An image layer can also carry a motion effect of its own, and then its own
alpha *is* the mask. Drop in a `hair.png` with `sway` on it and there is nothing
to paint.

Everything a shot needs is loaded once in `Backdrop` and reused for every frame
of the loop; per frame only the compositing runs.
"""

import math
import os

import numpy as np

from . import artsource, imageops, masks, overlay, videosource
from .motion import registry as motion_registry


class Camera:
    """The slow drift over a shot.

    In loop mode the move has to come back to where it started, so it is a
    swell and a sway rather than a straight push -- a sine on the zoom and a
    slow figure-eight on the pan, all wrapping exactly with the loop. In live
    mode a plain linear push is available, because nothing has to repeat.
    """

    def __init__(self, spec=None, live=False):
        spec = spec or {}

        def num(key, fallback):
            v = spec.get(key)
            return fallback if v is None else float(v)

        self.push = num("push", 0.06)
        self.drift = num("drift", 0.35)
        self.parallax = num("parallax", 0.5)
        self.live = bool(live)

    def at(self, tl, h, w):
        """Returns (zoom, pan_x_px, pan_y_px) for this instant."""
        if self.live:
            t = min(1.0, tl.t / max(1e-6, tl.loop_s))
            zoom = 1.0 + self.push * t
            sx = (t - 0.5) * 2.0
            sy = math.sin(2 * math.pi * t * 0.5) * 0.4
        else:
            zoom = 1.0 + self.push * 0.5 * (1.0 - tl.cowave(tl.loop_s))
            sx = tl.wave(tl.loop_s)
            sy = tl.wave(tl.loop_s / 2.0, offset=0.25) * 0.5
        span = self.drift * 0.04
        return zoom, sx * span * w, sy * span * h

    def depth_offset(self, ox, oy, depth):
        """How far a layer at `depth` (0 far, 1 near) moves against the camera."""
        f = self.parallax * (0.35 + 0.65 * float(depth))
        return ox * f, oy * f


def blur_bucket(radius):
    """Quantise a blur radius so a whole render reuses a handful of variants.

    Depth of field wants a slightly different radius on every frame as the focus
    drifts. Blurring a full-frame layer that often would cost more than
    everything else in the scene put together, so the radius is rounded to a
    step and the blurred copy is cached against it. The step is small enough
    that the focus still reads as continuous.
    """
    r = int(radius)
    if r < 1:
        return 0
    return min(48, int(round(r / 3.0) * 3))


class ImageLayer:
    """One transparent PNG placed over the background."""

    def __init__(self, spec, h, w, base_dir):
        self.spec = spec or {}
        self.h, self.w = h, w
        self.depth = float(self.spec.get("depth", 0.6))
        self.opacity = float(self.spec.get("opacity", 1.0))
        self.blend = str(self.spec.get("blend", "over"))
        self.effect = self.spec.get("effect") or ""
        self.params = self.spec.get("params") or {}
        self.sprite = None
        self.x0 = 0
        self.y0 = 0
        self._mask = None

        src = self.spec.get("src") or ""
        path = src if os.path.isabs(src) else os.path.join(str(base_dir or ""), src)
        img = artsource.load_image_rgba(path)
        if img is None:
            return

        fit = str(self.spec.get("fit", "contain"))
        scale = float(self.spec.get("scale", 1.0))
        if fit == "none":
            sp = img
            if scale != 1.0:
                sp = artsource.fit_into(
                    img,
                    max(2, int(img.shape[0] * scale)),
                    max(2, int(img.shape[1] * scale)),
                    "stretch",
                )
        else:
            sp = artsource.fit_into(img, h, w, fit, scale)
        self.sprite = sp

        blur = float(self.spec.get("blur", 0.0))
        if blur > 0.001 and sp is not None:
            r = max(1, int(blur * 0.06 * min(h, w)))
            soft = imageops.box_blur(sp.astype(np.float32), r, passes=2)
            self.sprite = np.clip(soft, 0, 255).astype(np.uint8)

        sh, sw = self.sprite.shape[:2]
        self.x0 = int(round(float(self.spec.get("x", 0.5)) * w - sw / 2))
        self.y0 = int(round(float(self.spec.get("y", 0.5)) * h - sh / 2))
        self._defocused: dict = {}

    def defocused(self, radius):
        """This layer blurred for depth of field, cached per bucket."""
        r = blur_bucket(radius)
        if r <= 0 or self.sprite is None:
            return self.sprite
        hit = self._defocused.get(r)
        if hit is None:
            soft = imageops.box_blur(self.sprite.astype(np.float32), r, passes=2)
            hit = np.clip(soft, 0, 255).astype(np.uint8)
            if len(self._defocused) > 6:
                self._defocused.clear()
            self._defocused[r] = hit
        return hit

    def ok(self):
        return self.sprite is not None

    def alpha_mask(self, ox=0, oy=0):
        """The layer's own alpha as a full-frame mask -- what its effect uses."""
        m = np.zeros((self.h, self.w), dtype=np.float32)
        if self.sprite is None:
            return m
        sh, sw = self.sprite.shape[:2]
        x, y = self.x0 + int(ox), self.y0 + int(oy)
        sx0, sy0 = max(0, -x), max(0, -y)
        dx0, dy0 = max(0, x), max(0, y)
        dx1, dy1 = min(self.w, x + sw), min(self.h, y + sh)
        if dx1 <= dx0 or dy1 <= dy0:
            return m
        m[dy0:dy1, dx0:dx1] = (
            self.sprite[sy0 : sy0 + (dy1 - dy0), sx0 : sx0 + (dx1 - dx0), 3].astype(
                np.float32
            )
            / 255.0
        )
        return m

    def draw(self, frame, tl, ox, oy, ctx, defocus=0.0, haze=None):
        if self.sprite is None:
            return frame
        sprite = self.defocused(defocus) if defocus >= 1 else self.sprite
        if haze is not None and haze[0] > 0.001:
            sprite = _hazed(sprite, haze[0], haze[1])
        artsource.blit(
            frame,
            sprite,
            self.x0 + ox,
            self.y0 + oy,
            opacity=self.opacity,
            mode=self.blend,
        )
        if self.effect:
            m = self.alpha_mask(ox, oy)
            box = masks.bbox(m, pad=8)
            if not masks.is_empty(box):
                motion_registry.apply_effect(
                    self.effect, frame, m, box, tl, self.params, ctx
                )
        return frame


_HAZE_CACHE: dict = {}


def _hazed(sprite, amount, color):
    """Fade a sprite toward a haze colour -- distance, cheaply."""
    key = (id(sprite), round(float(amount), 2), tuple(color))
    hit = _HAZE_CACHE.get(key)
    if hit is None:
        rgb = sprite[..., :3].astype(np.float32)
        tint = np.array(color, dtype=np.float32)
        out = sprite.copy()
        out[..., :3] = np.clip(rgb * (1 - amount) + tint * amount, 0, 255).astype(
            np.uint8
        )
        if len(_HAZE_CACHE) > 12:
            _HAZE_CACHE.clear()
        _HAZE_CACHE[key] = out
        hit = out
    return hit


class Backdrop:
    """A shot's background plus its stacked images, loaded once per render."""

    OVERSAMPLE = 1.14  # headroom so a drifting camera never runs off the edge

    def __init__(self, shot, h, w, base_dir, fps=30, n_frames=1):
        self.shot = shot or {}
        self.h, self.w = h, w
        self.base_dir = base_dir
        self.bg = None
        self.grad = None
        self.video = None
        self._video_frames = None
        self._last_video = None
        self.fps = float(fps)
        self.n_frames = int(n_frames)

        src = self.shot.get("image") or ""
        path = src if os.path.isabs(src) else os.path.join(str(base_dir or ""), src)

        if src and os.path.exists(path) and videosource.is_video(path):
            # a clip instead of a still -- decoded a frame at a time, at the same
            # oversampled size a still gets so the camera still has headroom
            self.video = videosource.VideoSource(
                path,
                int(w * self.OVERSAMPLE),
                int(h * self.OVERSAMPLE),
                self.fps,
                self.n_frames,
                start=float(self.shot.get("video_start", 0.0) or 0.0),
                blend=float(self.shot.get("video_blend", 0.5) or 0.0),
            )
        elif src and os.path.exists(path):
            bh = int(h * self.OVERSAMPLE)
            bw = int(w * self.OVERSAMPLE)
            img = overlay.load_image_cover(path, bh, bw).astype(np.float32)
            blur = float(self.shot.get("blur", 0.0))
            if blur > 0.001:
                img = imageops.box_blur(img, max(1, int(blur * 0.08 * min(h, w))), 2)
            self.bg = img
        else:
            look = self.shot.get("look") or {}
            self.grad = overlay.vertical_gradient(
                h,
                w,
                overlay.hex_rgb(str(look.get("grade_top", "#243056"))),
                overlay.hex_rgb(str(look.get("grade_bottom", "#0a0d18"))),
            ).astype(np.float32)

        self._defocused: dict = {}
        self.video_blur = float(self.shot.get("blur", 0.0) or 0.0)
        self.images = [
            ImageLayer(spec, h, w, base_dir) for spec in (self.shot.get("images") or [])
        ]
        self.images = [im for im in self.images if im.ok()]
        self.images.sort(key=lambda im: im.depth)

    def _source(self, bg, defocus):
        """The background, blurred for depth of field. Blurring the *source*
        rather than each cropped frame means it happens once per bucket instead
        of once per frame."""
        r = blur_bucket(defocus)
        if r <= 0:
            return bg
        hit = self._defocused.get(r)
        if hit is None:
            hit = imageops.box_blur(bg, r, passes=2)
            if len(self._defocused) > 6:
                self._defocused.clear()
            self._defocused[r] = hit
        return hit

    def _next_video_frame(self):
        """The clip's frame for this output frame. Pulled once per frame, in
        order, which is what streaming from one pipe requires."""
        video = self.video
        if video is None:  # pragma: no cover - callers check first
            return np.zeros((self.h, self.w, 3), dtype=np.float32)
        if self._video_frames is None:
            self._video_frames = video.frames()
        try:
            self._last_video = next(self._video_frames)
        except StopIteration:  # pragma: no cover - the source pads to length
            pass
        if self._last_video is None:
            self._last_video = np.zeros((video.h, video.w, 3), dtype=np.float32)
        frame = self._last_video
        if self.video_blur > 0.001:
            frame = imageops.box_blur(
                frame, max(1, int(self.video_blur * 0.08 * min(self.h, self.w))), 2
            )
        return frame

    def draw_base(self, tl, camera, defocus=0.0):
        """The background, cropped for the camera's zoom and drift."""
        bg = self._next_video_frame() if self.video is not None else self.bg
        if bg is None:
            return (
                self.grad.copy()
                if self.grad is not None
                else np.zeros((self.h, self.w, 3), dtype=np.float32)
            )
        zoom, ox, oy = camera.at(tl, self.h, self.w)
        bx, by = camera.depth_offset(ox, oy, 0.0)
        # a still's blurred variants are cached; a clip is a new picture every
        # frame, so its defocus has to be done as it goes
        src = (
            imageops.box_blur(bg, blur_bucket(defocus), passes=2)
            if (self.video is not None and blur_bucket(defocus) > 0)
            else (bg if self.video is not None else self._source(bg, defocus))
        )
        ih, iw = src.shape[:2]
        ch, cw = self.h / zoom, self.w / zoom
        x = (iw - cw) / 2 + bx
        y = (ih - ch) / 2 + by
        x = float(np.clip(x, 0, max(0, iw - cw)))
        y = float(np.clip(y, 0, max(0, ih - ch)))
        crop = src[int(y) : int(y + ch) + 1, int(x) : int(x + cw) + 1]
        from PIL import Image

        mode = Image.Resampling.BILINEAR
        pil = Image.fromarray(np.clip(crop, 0, 255).astype(np.uint8)).resize(
            (self.w, self.h), mode
        )
        return np.asarray(pil, dtype=np.float32)
