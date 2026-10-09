"""RenderContext: what a style needs to draw one frame of a shot.

- `ctx.source(shot)`: the shot's picture (panel, or strip region for a page
  reveal) as BGRA, bubbles erased and mirrored when asked, and pre-scaled
  once so the per-frame warp never magnifies line art much (cubic upscale
  plus a light unsharp mask looks far better than a big bilinear stretch).
- `ctx.matrix(shot, t)`: camera (with shake) as a 2x3 affine onto the output.
- `ctx.backdrop(shot)`: blurred, darkened fill behind letterboxed panels.
"""

import math
from pathlib import Path

import cv2
import numpy as np

from ..camera import keys as K
from .inputs import ChapterInputs
from .timeline import DEFAULT_SETTINGS, out_size

MAX_SOURCE_PIXELS = 36_000_000


AUTO_STRETCH_BELOW = 0.7  # panel aspect against frame aspect


def backdrop_mode(mode: str, src: tuple[int, int], out: tuple[int, int]) -> str:
    """Resolve `auto` to a real backdrop mode for this panel and frame.

    A panel much narrower than the frame (a webtoon strip panel in 16:9) is
    filled by carrying its own edges outwards; anything else gets the blurred
    copy, which suits a panel that nearly fills the frame already.
    """
    if mode != "auto":
        return mode
    frame_ar = out[0] / max(1, out[1])
    return (
        "stretch"
        if (src[0] / max(1, src[1])) < frame_ar * AUTO_STRETCH_BELOW
        else "blur"
    )


class RenderContext:
    def __init__(self, inp: ChapterInputs, settings: dict, scale: float = 1.0):
        self.inp = inp
        self.settings = {**DEFAULT_SETTINGS, **(settings or {})}
        w, h = out_size(self.settings)
        self.scale = scale
        self.out = (int(round(w * scale / 2)) * 2, int(round(h * scale / 2)) * 2)
        self.fps = int(self.settings.get("fps", 30))
        self.cache: dict = {}

    @property
    def chapter_dir(self) -> Path:
        return self.inp.dir

    # ------------------------------------------------------------ source

    def source_size(self, shot) -> tuple[int, int]:
        if shot.get("kind") == "reveal":
            r = shot["region"]
            return int(r[2]), int(r[3])
        b = self.inp.by_id[shot["panel_id"]]["box"]
        return int(b[2]), int(b[3])

    def base_image(self, shot) -> np.ndarray:
        """Unscaled BGRA picture for the shot, bubbles erased if asked, mirrored if flipped."""
        ck = self._base_key(shot)
        erase, flip = ck[4], ck[5]
        if ck in self.cache:
            return self.cache[ck]
        from . import bubbles

        if shot.get("kind") == "reveal":
            r = shot["region"]
            img = cv2.cvtColor(self.inp.crop_strip(r), cv2.COLOR_BGR2BGRA)
            if erase:
                for pid in shot.get("panels", []):
                    img = bubbles.erase_in_region(self, pid, img, r)
        else:
            img = self.inp.panel_image(shot["panel_id"])
            sw, sh = self.source_size(shot)
            if img.shape[1] != sw or img.shape[0] != sh:
                img = cv2.resize(img, (sw, sh), interpolation=cv2.INTER_AREA)
            if erase:
                img = bubbles.erased_panel(self, shot["panel_id"], img)
        if flip:
            img = cv2.flip(img, 1)
        self._evict("base", keep=8)
        self.cache[ck] = img
        return img

    def _base_key(self, shot) -> tuple:
        erase = self.settings.get("bubbles") == "erase"
        flip = bool((shot.get("camera") or {}).get("flip"))
        region = tuple(shot.get("region") or ())
        return ("base", shot.get("kind"), shot["panel_id"], region, erase, flip)

    def source_factor(self, shot) -> float:
        """How much the source is pre-scaled before the per-frame warp."""
        src = self.source_size(shot)
        keys = (shot.get("camera") or {}).get("keys") or [{"zoom": 1.0}]
        zmax = max(float(k.get("zoom", 1.0)) for k in keys)
        need = K.contain_scale(src, self.out) * zmax * 1.08
        if 0.8 <= need <= 1.25:
            return 1.0
        cap = math.sqrt(MAX_SOURCE_PIXELS / max(1, src[0] * src[1]))
        return max(0.05, min(need, 3.0, cap))

    def source(self, shot) -> np.ndarray:
        f = self.source_factor(shot)
        ck = ("src", self._base_key(shot), round(f, 3))
        if ck in self.cache:
            return self.cache[ck]
        base = self.base_image(shot)
        if f == 1.0:
            img = base
        else:
            size = (
                max(1, int(round(base.shape[1] * f))),
                max(1, int(round(base.shape[0] * f))),
            )
            if f < 1.0:
                img = cv2.resize(base, size, interpolation=cv2.INTER_AREA)
            else:
                up = cv2.resize(base, size, interpolation=cv2.INTER_CUBIC)
                soft = cv2.GaussianBlur(up, (0, 0), 0.6 + 0.35 * f)
                img = cv2.addWeighted(up, 1.45, soft, -0.45, 0)
        self._evict("src")
        self.cache[ck] = img
        return img

    def _evict(self, tag: str, keep=6) -> None:
        ks = [k for k in self.cache if isinstance(k, tuple) and k and k[0] == tag]
        for k in ks[: max(0, len(ks) - keep)]:
            del self.cache[k]

    # ------------------------------------------------------------ camera

    def max_zoom(self, shot) -> float:
        keys = (shot.get("camera") or {}).get("keys") or []
        return max([12.0] + [float(k.get("zoom", 1.0)) for k in keys])

    def camera_at(self, shot, t: float) -> dict:
        cam = shot.get("camera") or {}
        return K.sample(
            cam.get("keys") or [],
            t,
            self.source_size(shot),
            self.out,
            self.max_zoom(shot),
        )

    def shake(self, shot, t: float) -> tuple[float, float]:
        cam = shot.get("camera") or {}
        amount = float(cam.get("shake", 0.0)) * float(self.settings.get("effects", 1.0))
        impacts = [float(x) for x in cam.get("impacts", [])]
        if amount <= 0 and not impacts:
            return 0.0, 0.0
        return K.shake_offset(t, amount, impacts, self.out[1])

    def matrix(
        self, shot, t: float, key: dict | None = None, extra_zoom: float = 1.0
    ) -> np.ndarray:
        k = key if key is not None else self.camera_at(shot, t)
        k = {"cx": 0.5, "cy": 0.5, "zoom": 1.0, "rot": 0.0, **k}
        cam = shot.get("camera") or {}
        dx, dy = self.shake(shot, t)
        if cam.get("shake") or cam.get("impacts"):
            extra_zoom *= 1.0 + 0.06 * min(1.0, float(cam.get("shake", 0.0)) + 0.3)
        m = np.array(
            K.affine(k, self.source_size(shot), self.out, (dx, dy), extra_zoom)
        )
        m[:, :2] /= self.source_factor(shot)
        return m

    # ------------------------------------------------------------ backdrop

    def backdrop(self, shot) -> np.ndarray:
        """The fill behind a panel that does not cover the whole frame.

        `black`, `blur` (a darkened, blurred copy of the panel) or `stretch`
        (the panel's own edges carried outwards and blurred, so a tall webtoon
        panel in a wide frame looks like it continues instead of sitting in
        dead space). `auto`, the default, picks `stretch` when the panel is
        much taller than the frame and `blur` otherwise.
        """
        mode = backdrop_mode(
            self.settings.get("backdrop", "auto"), self.source_size(shot), self.out
        )
        ck = ("backdrop", shot.get("id"), shot["panel_id"], mode, self.out)
        if ck in self.cache:
            return self.cache[ck]
        w, h = self.out
        if mode == "black":
            bd = np.zeros((h, w, 4), np.uint8)
            bd[..., 3] = 255
        elif mode == "stretch":
            base = cv2.cvtColor(self.base_image(shot), cv2.COLOR_BGRA2BGR)
            bh, bw = base.shape[:2]
            s = h / max(1, bh)
            fit = cv2.resize(
                base, (max(1, int(bw * s)), h), interpolation=cv2.INTER_AREA
            )
            if fit.shape[1] < w:
                pad = (w - fit.shape[1] + 1) // 2
                fit = cv2.copyMakeBorder(fit, 0, 0, pad, pad, cv2.BORDER_REPLICATE)
            x0 = max(0, (fit.shape[1] - w) // 2)
            fit = fit[:, x0 : x0 + w]
            small = cv2.resize(
                fit, (max(1, w // 10), max(1, h // 10)), interpolation=cv2.INTER_AREA
            )
            small = cv2.GaussianBlur(small, (0, 0), max(2.0, w / 260))
            big = cv2.resize(small, (w, h), interpolation=cv2.INTER_CUBIC).astype(
                np.float32
            )
            yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
            vig = 1.0 - 0.22 * (((xx / w - 0.5) ** 2 + (yy / h - 0.5) ** 2) * 2.5)
            big *= (0.6 * vig)[..., None]
            bd = cv2.cvtColor(np.clip(big, 0, 255).astype(np.uint8), cv2.COLOR_BGR2BGRA)
        else:
            base = cv2.cvtColor(self.base_image(shot), cv2.COLOR_BGRA2BGR)
            sw, sh = w // 8 or 1, h // 8 or 1
            bh, bw = base.shape[:2]
            s = max(sw / bw, sh / bh)
            small = cv2.resize(
                base,
                (max(1, int(bw * s)), max(1, int(bh * s))),
                interpolation=cv2.INTER_AREA,
            )
            y0 = (small.shape[0] - sh) // 2
            x0 = (small.shape[1] - sw) // 2
            small = small[y0 : y0 + sh, x0 : x0 + sw]
            # strong enough that big lettering dissolves into a colour wash
            # instead of showing through as ghost words
            small = cv2.GaussianBlur(small, (0, 0), max(2.0, sw / 12))
            big = cv2.resize(small, (w, h), interpolation=cv2.INTER_CUBIC).astype(
                np.float32
            )
            yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
            vig = 1.0 - 0.35 * (((xx / w - 0.5) ** 2 + (yy / h - 0.5) ** 2) * 2.5)
            big *= (0.42 * vig)[..., None]
            bd = cv2.cvtColor(np.clip(big, 0, 255).astype(np.uint8), cv2.COLOR_BGR2BGRA)
        self._evict("backdrop", keep=4)
        self.cache[ck] = bd
        return bd
