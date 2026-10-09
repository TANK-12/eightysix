"""Scroll reader: the whole strip, read top to bottom, nothing cut.

The timeline's "scroll" mode gives every shot a `scroll` plan (strip window
positions in strip pixels, see `render/timeline.plan_scroll`); this style
draws the strip band at that position, whole width, over a dark backdrop.
No panel crops, no camera moves inside the art, no cut-outs: the picture is
the comic as drawn, moving down at reading pace and pausing on each panel
while its lines are spoken. Emerson asked for this after the fancy styles
kept cutting panels and objects apart (2026-09-19).
"""

from __future__ import annotations

import cv2
import numpy as np

from .base import Style

GLOW_PAD = 10  # strip pixels of room between the balloon and its ring
GLOW_FADE = 0.25  # seconds the ring takes to appear and to go
GLOW_COLOUR = (60, 200, 255)  # BGR: a warm amber
GLOW_ALPHA = 0.85


def ease(u: float) -> float:
    u = min(1.0, max(0.0, u))
    return u * u * (3.0 - 2.0 * u)


def _keyed_y(keys, t: float) -> float:
    """Window top from (time, y) keys: eased moves between them, so the
    window rests on a balloon while its line plays (timeline._scroll_keys)."""
    if t <= keys[0][0]:
        return float(keys[0][1])
    for (t0, y0), (t1, y1) in zip(keys, keys[1:]):
        if t <= t1:
            span = max(1e-6, t1 - t0)
            return float(y0) + (float(y1) - float(y0)) * ease((t - t0) / span)
    return float(keys[-1][1])


def scroll_y(plan: dict, t: float) -> float:
    """Strip y of the window's top at shot time t: move from y0 to y_a in
    `move` seconds, then drift from y_a to y_b over the rest of the shot."""
    keys = plan.get("keys")
    if keys:
        return _keyed_y(keys, t)
    y0, ya, yb = float(plan["y0"]), float(plan["y_a"]), float(plan["y_b"])
    move, dur = float(plan.get("move", 0.0)), max(0.05, float(plan.get("dur", 1.0)))
    if move > 0 and t < move:
        return y0 + (ya - y0) * ease(t / move)
    if yb != ya and dur > move:
        return ya + (yb - ya) * min(1.0, (t - move) / (dur - move))
    return ya


class Scroll(Style):
    name = "scroll"
    label = "Scroll reader"
    description = (
        "Reads down the strip as drawn, whole width, pausing on each panel; "
        "nothing is cut out or cropped. Use with the Scroll mode."
    )
    preferred_transition = "cut"
    # 2: the ring round the spoken balloon went off by default (21:47);
    # cached clips drawn with it would otherwise be reused as they are
    version = 2
    settings = {
        "width": {
            "type": "number",
            "label": "Strip width (share of a wide frame)",
            "min": 0.3,
            "max": 1.0,
            "step": 0.05,
            "default": 0.55,
        },
        "highlight": {
            "type": "bool",
            "label": "Ring round the balloon being spoken",
            "default": False,  # Emerson (21:47): "yellow boxes around the text"
        },
    }

    def render(self, ctx, shot, t):
        plan = shot.get("scroll")
        if not plan:
            # chosen from the style list without the scroll mode: show the
            # panel whole and still
            return self.draw_camera(ctx, shot, t)
        ow, oh = ctx.out
        W = int(plan["strip_w"])
        H = int(plan["window_h"])
        y = int(round(scroll_y(plan, t)))
        band = self._band(ctx, shot, plan)
        by0 = int(plan["band_y0"])
        win = band[max(0, y - by0) : max(0, y - by0) + H]
        if win.shape[0] < H:
            win = cv2.copyMakeBorder(
                win,
                0,
                H - win.shape[0],
                0,
                0,
                cv2.BORDER_CONSTANT,
                value=(255, 255, 255),
            )
        s = float(plan["scale"])
        dw = max(2, int(round(W * s)))
        dst = cv2.resize(
            win, (dw, oh), interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC
        )
        frame = self._backdrop(ctx, shot, dst)
        x0 = (ow - dw) // 2
        if dw >= ow:
            frame[:, :, :3] = dst[:, (dw - ow) // 2 : (dw - ow) // 2 + ow]
            x0 = -((dw - ow) // 2)
        else:
            frame[:, x0 : x0 + dw, :3] = dst
        if self.option(ctx, shot, "highlight"):
            self._glow(ctx, shot, t, frame, x0, y, s)
        return frame

    def _glow(self, ctx, shot, t, frame, x0, y, s) -> None:
        """A soft ring round the balloon whose line is playing at `t`, so the
        eye finds the words being spoken while the strip scrolls."""
        for ln in shot.get("lines", []):
            at, dur = float(ln.get("at", 0.0)), float(ln.get("dur", 0.0))
            if not (at <= t < at + dur) or not ln.get("bubble_id"):
                continue
            b = self._bubble(ctx, shot, ln["bubble_id"])
            if b is None:
                continue
            bx, by, bw, bh = b["box"]
            pad = GLOW_PAD
            p0 = (int(x0 + (bx - pad) * s), int((by - y - pad) * s))
            p1 = (int(x0 + (bx + bw + pad) * s), int((by - y + bh + pad) * s))
            # the ring fades in and out over the first and last GLOW_FADE seconds
            u = min(1.0, (t - at) / GLOW_FADE, (at + dur - t) / GLOW_FADE)
            self._ring(frame, p0, p1, max(0.0, u))

    @staticmethod
    def _bubble(ctx, shot, bid):
        for b in ctx.inp.panel_bubbles(shot.get("panel_id")):
            if b.get("id") == bid:
                return b
        return None

    @staticmethod
    def _ring(frame, p0, p1, strength: float) -> None:
        if strength <= 0:
            return
        h, w = frame.shape[:2]
        x0, y0 = max(0, p0[0]), max(0, p0[1])
        x1, y1 = min(w - 1, p1[0]), min(h - 1, p1[1])
        if x1 - x0 < 4 or y1 - y0 < 4:
            return
        overlay = frame[:, :, :3].copy()
        thick = max(2, int(round(min(w, h) * 0.004)))
        cv2.rectangle(overlay, (x0, y0), (x1, y1), GLOW_COLOUR, thick, cv2.LINE_AA)
        overlay = cv2.GaussianBlur(overlay, (0, 0), thick)
        cv2.rectangle(overlay, (x0, y0), (x1, y1), GLOW_COLOUR, thick, cv2.LINE_AA)
        a = GLOW_ALPHA * strength
        mixed = cv2.addWeighted(
            overlay, a, np.ascontiguousarray(frame[:, :, :3]), 1 - a, 0
        )
        frame[:, :, :3] = mixed

    def _band(self, ctx, shot, plan) -> np.ndarray:
        """The strip rows this shot can show, read once per shot."""
        ck = ("scroll-band", shot.get("id"), int(plan["band_y0"]), int(plan["band_h"]))
        if ck in ctx.cache:
            return ctx.cache[ck]
        band = ctx.inp.crop_strip([0, plan["band_y0"], plan["strip_w"], plan["band_h"]])
        ctx._evict("scroll-band", keep=3)
        ctx.cache[ck] = band
        return band

    def _backdrop(self, ctx, shot, dst) -> np.ndarray:
        """Dark blurred copy of the strip window behind it, or black."""
        ow, oh = ctx.out
        frame = np.zeros((oh, ow, 4), np.uint8)
        frame[..., 3] = 255
        if ctx.settings.get("backdrop") == "black" or dst.shape[1] >= ow:
            return frame
        small = cv2.resize(
            dst, (max(1, ow // 16), max(1, oh // 16)), interpolation=cv2.INTER_AREA
        )
        small = cv2.GaussianBlur(small, (0, 0), 2.0)
        big = cv2.resize(small, (ow, oh), interpolation=cv2.INTER_LINEAR)
        frame[..., :3] = (big.astype(np.float32) * 0.35).astype(np.uint8)
        return frame


STYLE = Scroll()
