"""2.5D puppets: the 3D layered style plus life in each character cutout.

Everything here is animation of the manga's own drawing, by rules and maths,
never generated footage. Per character layer, from the rig the analysis
found (head, eyes, mouth, neck and hip pivots in ``scene.json``):

- breathing: a slow vertical rise and fall about the hip (or the bottom of
  the cutout), a fraction of a percent, period about four seconds;
- sway: while the character speaks, a small rotation about the neck;
- blinks: every few seconds the eye boxes close for a fifth of a second, by
  pulling the skin above and below each eye towards its centre line;
- lip-flap: while the character's line plays, the mouth box opens and
  closes at speech rate, by stretching the mouth region downwards.

Blinks are on a deterministic schedule per character and shot, so a re-render
gives the same film. Characters without a rig only breathe.
"""

from __future__ import annotations

import hashlib
import math

import cv2
import numpy as np

from .depth3d import Depth3D, _num

BLINK_CLOSE = 0.07  # seconds to close
BLINK_HOLD = 0.04
BLINK_OPEN = 0.08
BLINK_EVERY = 3.6  # mean seconds between blinks
BREATH_PERIOD = 3.9
LIP_RATE = 6.5  # openings per second while speaking


def _seed(*parts) -> float:
    h = hashlib.sha1("|".join(str(p) for p in parts).encode()).digest()
    return int.from_bytes(h[:4], "big") / 2**32


def blink_amount(t: float, seed: float, rate: float = 1.0) -> float:
    """0 = eyes open, 1 = closed, at time t of a shot."""
    if rate <= 0:
        return 0.0
    gap = BLINK_EVERY / rate
    # first blink a little way in, then roughly every `gap` seconds with a
    # per-character offset so two people never blink in step
    start = 0.9 + seed * gap
    if t < start:
        return 0.0
    k = int((t - start) // gap)
    at = start + k * gap + (0.5 - _seed(seed, k)) * 0.6 * gap
    d = t - at
    if d < 0:
        # the previous blink may still be in progress
        at = start + (k - 1) * gap + (0.5 - _seed(seed, k - 1)) * 0.6 * gap
        d = t - at
    if d < 0:
        return 0.0
    if d < BLINK_CLOSE:
        return d / BLINK_CLOSE
    if d < BLINK_CLOSE + BLINK_HOLD:
        return 1.0
    if d < BLINK_CLOSE + BLINK_HOLD + BLINK_OPEN:
        return 1.0 - (d - BLINK_CLOSE - BLINK_HOLD) / BLINK_OPEN
    return 0.0


def mouth_amount(t: float, speaking: list[tuple[float, float]], seed: float) -> float:
    """0 = closed, 1 = fully open, while one of the speaking intervals is on."""
    for at, end in speaking:
        if at <= t <= end:
            env = min(1.0, (t - at) / 0.12, (end - t) / 0.15)
            wobble = 0.75 + 0.25 * math.sin(2 * math.pi * t * 1.7 + seed * 6.28)
            return max(
                0.0, env * wobble * abs(math.sin(math.pi * LIP_RATE * t + seed * 3.0))
            )
    return 0.0


def speaking_intervals(ctx, shot) -> dict[str, list[tuple[float, float]]]:
    """cast id -> [(at, end)] of that character's lines in this shot."""
    out: dict[str, list[tuple[float, float]]] = {}
    pid = shot["panel_id"]
    bubbles = {b["id"]: b for b in ctx.inp.panel_bubbles(pid)}
    for ln in shot.get("lines", []):
        line = ctx.inp.lines.get(ln.get("line_id")) or {}
        bubble = bubbles.get(ln.get("bubble_id") or line.get("bubble_id")) or {}
        speaker = line.get("speaker") or bubble.get("speaker")
        if not speaker:
            continue
        at = float(ln.get("at", 0.0))
        dur = float(ln.get("dur") or line.get("dur") or 0) or max(
            1.1,
            len((line.get("text") or bubble.get("text") or "").split()) / 2.6 + 0.35,
        )
        out.setdefault(speaker, []).append((at, at + dur))
    return out


def _local_box(box, layer_box, flip: bool, f: float):
    """A rig box in panel coords -> the layer image's coords."""
    x, y, w, h = (float(v) for v in box)
    lx, ly, lw, lh = layer_box
    if flip:
        x = lx + lw - (x - lx) - w
    return (x - lx) * f, (y - ly) * f, w * f, h * f


def squash_rows(img: np.ndarray, box, amount: float, mode: str) -> None:
    """Warp the rows of `box` in place. mode "close": pull the rows above and
    below the centre line inwards (a blink). mode "open": push the lower
    half downwards (a mouth opening). `amount` 0..1."""
    if amount <= 0.01:
        return
    h, w = img.shape[:2]
    x, y, bw, bh = box
    pad = bh * (0.9 if mode == "close" else 1.2)
    y0, y1 = int(max(0, y - pad)), int(min(h, y + bh + pad))
    x0, x1 = int(max(0, x - bw * 0.25)), int(min(w, x + bw * 1.25))
    if y1 - y0 < 4 or x1 - x0 < 4:
        return
    cy = y + bh / 2
    rows = np.arange(y0, y1, dtype=np.float32)
    rel = rows - cy
    if mode == "close":
        k = 1.0 + 6.0 * amount  # sample further out: the eye shrinks to a line
        inner = np.abs(rel) < bh / 2 + pad
        src = np.where(inner, cy + rel * k, rows)
        # keep the edges of the window where they are
        edge = np.clip((np.abs(rel) - bh / 2) / max(1.0, pad), 0, 1)
        src = src * (1 - edge) + rows * edge
    else:
        below = rel > 0
        k = 1.0 / (1.0 + 0.7 * amount)  # the lower lip and chin move down
        src = np.where(below, cy + rel * k, rows)
        edge = np.clip((rel - bh) / max(1.0, pad), 0, 1)
        src = src * (1 - edge) + rows * edge
    src = np.clip(src, 0, h - 1).astype(np.float32)
    map_y = np.repeat(src[:, None], x1 - x0, axis=1)
    map_x = np.repeat(np.arange(x0, x1, dtype=np.float32)[None, :], y1 - y0, axis=0)
    warped = cv2.remap(img, map_x, map_y, cv2.INTER_LINEAR)
    # feather the sides so a box that is a little off never shows an edge
    xs = np.linspace(-1.0, 1.0, x1 - x0, dtype=np.float32)
    win = np.clip((1.0 - np.abs(xs)) / 0.35, 0, 1)[None, :, None]
    patch = img[y0:y1, x0:x1].astype(np.float32)
    img[y0:y1, x0:x1] = np.rint(warped * win + patch * (1 - win)).astype(np.uint8)


class Puppet25D(Depth3D):
    name = "puppet25d"
    label = "2.5D puppets"
    description = (
        "The 3D layered style with living characters: breathing, blinks, a "
        "sway while talking and a moving mouth on the character's own drawing."
    )
    version = 1
    enabled = True
    settings = {
        **Depth3D.settings,
        "breathing": _num(0.0, 2.0, 0.05, 1.0, "Breathing"),
        "blinks": _num(0.0, 2.0, 0.05, 1.0, "Blink rate"),
        "lipflap": _num(0.0, 2.0, 0.05, 1.0, "Mouth movement"),
        "talk_sway": _num(0.0, 2.0, 0.05, 1.0, "Sway while talking"),
    }

    def scene(self, ctx, shot):
        key = ("puppet", shot.get("id"), shot["panel_id"])
        if key in ctx.cache:
            return ctx.cache[key]
        sc = dict(super().scene(ctx, shot))
        panel = (
            ctx.inp.scene_panel(shot["panel_id"])
            if shot.get("kind") != "reveal"
            else {}
        )
        rigs = {r.get("char_index"): r for r in panel.get("rigs", [])}
        speaking = speaking_intervals(ctx, shot)
        chars = []
        for ch in sc["chars"]:
            rig = rigs.get(ch.get("char_index"))
            f, flip, lbox = ch["scale"], ch["flip"], ch["box"]
            info = dict(ch)
            info["eyes"] = [
                _local_box(e, lbox, flip, f) for e in (rig or {}).get("eyes") or []
            ]
            info["mouth"] = (
                _local_box(rig["mouth"], lbox, flip, f)
                if rig and rig.get("mouth")
                else None
            )
            neck = (rig or {}).get("pivot_neck")
            info["neck"] = (
                _local_box([neck[0], neck[1], 0, 0], lbox, flip, f)[:2]
                if neck
                else None
            )
            hip = (rig or {}).get("pivot_hip")
            info["hip"] = (
                _local_box([hip[0], hip[1], 0, 0], lbox, flip, f)[:2] if hip else None
            )
            info["speaking"] = speaking.get(ch.get("cast_id") or "", [])
            info["seed"] = _seed(
                shot.get("id"), ch.get("cast_id"), ch.get("char_index")
            )
            chars.append(info)
        sc["chars"] = chars
        ctx.cache[key] = sc
        return sc

    def layer_image(self, ctx, shot, sc, ch, t) -> np.ndarray:
        breathing = float(self.option(ctx, shot, "breathing"))
        blinks = float(self.option(ctx, shot, "blinks"))
        lipflap = float(self.option(ctx, shot, "lipflap"))
        sway = float(self.option(ctx, shot, "talk_sway"))
        img = ch["img"]
        h, w = img.shape[:2]
        talking = any(at <= t <= end for at, end in ch.get("speaking", []))
        # face work first, on a copy, then the whole-body transform
        blink = blink_amount(t, ch["seed"], blinks)
        mouth = (
            mouth_amount(t, ch.get("speaking", []), ch["seed"]) * lipflap
            if ch.get("mouth")
            else 0.0
        )
        out = img
        if (blink > 0.01 and ch.get("eyes")) or mouth > 0.01:
            out = img.copy()
            for eye in ch.get("eyes", []):
                squash_rows(out, eye, blink, "close")
            if mouth > 0.01 and ch.get("mouth"):
                squash_rows(out, ch["mouth"], min(1.0, mouth), "open")
        # breathing scale about the hip (or the bottom) and a talking sway
        # about the neck, as one affine warp
        amp = 0.006 * breathing
        sy = 1.0 + amp * math.sin(2 * math.pi * t / BREATH_PERIOD + ch["seed"] * 6.28)
        sx = 1.0 - amp * 0.4 * math.sin(
            2 * math.pi * t / BREATH_PERIOD + ch["seed"] * 6.28
        )
        px, py = ch.get("hip") or (w / 2, h)
        angle = 0.0
        if talking and sway > 0:
            angle = 1.1 * sway * math.sin(2 * math.pi * t / 1.9 + ch["seed"] * 3.0)
        if abs(sy - 1) < 1e-4 and abs(angle) < 1e-3:
            return out
        m = np.array([[sx, 0.0, px * (1 - sx)], [0.0, sy, py * (1 - sy)]], np.float64)
        if abs(angle) >= 1e-3 and ch.get("neck"):
            nx, ny = ch["neck"]
            r = cv2.getRotationMatrix2D((float(nx), float(ny)), angle, 1.0)
            r3 = np.vstack([r, [0, 0, 1]])
            m3 = np.vstack([m, [0, 0, 1]])
            m = (r3 @ m3)[:2]
        return cv2.warpAffine(
            out,
            m,
            (w, h),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(0, 0, 0, 0),
        )


STYLE = Puppet25D()
