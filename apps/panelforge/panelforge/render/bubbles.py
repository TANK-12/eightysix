"""Bubbles: erase them from the art, and draw styled subtitles instead.

Erase finds the bubble's own bright interior (the connected light area in the
bubble box, text holes filled, outline included), then fills it from the
scene background when scene made one, otherwise by inpainting. Sound-effect
lettering is part of the drawing and is never erased.
"""

import re
from functools import lru_cache

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONT_DIR = "/usr/share/fonts/noto/"
FONTS = {
    "regular": "NotoSans-Bold.ttf",
    "italic": "NotoSans-BoldItalic.ttf",
    "shout": "NotoSans-Black.ttf",
    "caption": "NotoSans-Regular.ttf",
}


def bubble_mask(img_bgr: np.ndarray, box, kind: str) -> np.ndarray:
    h, w = img_bgr.shape[:2]
    x, y, bw, bh = [int(round(v)) for v in box]
    pad = max(4, int(0.06 * max(bw, bh)))
    x0, y0 = max(0, x - pad), max(0, y - pad)
    x1, y1 = min(w, x + bw + pad), min(h, y + bh + pad)
    mask = np.zeros((h, w), np.uint8)
    if x1 <= x0 or y1 <= y0:
        return mask
    roi = cv2.cvtColor(img_bgr[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
    light = (roi > 170).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(light, 4)
    inner = np.zeros_like(light)
    if n > 1:
        # the component covering most of the original box is the bubble body
        bx0, by0 = x - x0, y - y0
        best, best_area = 0, 0
        for i in range(1, n):
            cx0, cy0, cw, ch, area = stats[i]
            ox = max(0, min(cx0 + cw, bx0 + bw) - max(cx0, bx0))
            oy = max(0, min(cy0 + ch, by0 + bh) - max(cy0, by0))
            if ox * oy > best_area and area > 0.15 * bw * bh:
                best, best_area = i, ox * oy
        if best:
            inner = (lab == best).astype(np.uint8)
    if inner.sum() == 0 or kind == "caption":
        inner[max(0, y - y0) : y - y0 + bh, max(0, x - x0) : x - x0 + bw] = 1
    filled = inner.copy()
    cnts, _ = cv2.findContours(inner, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(filled, cnts, -1, 1, thickness=cv2.FILLED)
    ring = max(3, int(0.012 * max(bw, bh)) + 3)
    filled = cv2.dilate(
        filled,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ring * 2 + 1, ring * 2 + 1)),
    )
    mask[y0:y1, x0:x1] = filled * 255
    return mask


def erase(
    img_bgra: np.ndarray, boxes_kinds, background: np.ndarray | None = None
) -> np.ndarray:
    if not boxes_kinds:
        return img_bgra
    bgr = cv2.cvtColor(img_bgra, cv2.COLOR_BGRA2BGR)
    mask = np.zeros(bgr.shape[:2], np.uint8)
    for box, kind in boxes_kinds:
        if kind == "sfx":
            continue
        mask |= bubble_mask(bgr, box, kind)
    if not mask.any():
        return img_bgra
    if background is not None and background.shape[:2] == bgr.shape[:2]:
        filled = bgr.copy()
        filled[mask > 0] = background[..., :3][mask > 0]
    else:
        h, w = mask.shape
        s = min(1.0, 700 / max(h, w))
        small = cv2.resize(
            bgr, (max(1, int(w * s)), max(1, int(h * s))), interpolation=cv2.INTER_AREA
        )
        sm = cv2.resize(
            mask, (small.shape[1], small.shape[0]), interpolation=cv2.INTER_NEAREST
        )
        paint = cv2.inpaint(small, sm, 7, cv2.INPAINT_TELEA)
        paint = cv2.resize(paint, (w, h), interpolation=cv2.INTER_CUBIC)
        soft = cv2.GaussianBlur(mask, (0, 0), 1.5).astype(np.float32)[..., None] / 255
        filled = (bgr * (1 - soft) + paint * soft).astype(np.uint8)
    out = cv2.cvtColor(filled, cv2.COLOR_BGR2BGRA)
    out[..., 3] = img_bgra[..., 3]
    return out


def _scene_background(ctx, pid, shape):
    bg = ctx.inp.scene_panel(pid).get("background")
    if not bg:
        return None
    f = ctx.inp.dir / bg
    img = cv2.imread(str(f), cv2.IMREAD_COLOR) if f.exists() else None
    if img is None:
        return None
    if img.shape[:2] != shape[:2]:
        img = cv2.resize(img, (shape[1], shape[0]), interpolation=cv2.INTER_CUBIC)
    return img


TEXT_PANEL_COVER = 0.45  # lettering covering this much of a panel *is* the panel


def keeps_its_lettering(ctx, pid: str) -> bool:
    """A panel that is mostly lettering (a caption slab, a title, a warning
    card) keeps it even in erase mode: erasing left a blank white slab on
    screen for seconds (seen 2026-09-19), and the words are the art there."""
    panel = ctx.inp.by_id.get(pid) or {}
    if panel.get("kind") == "caption-only":
        return True
    w, h = float(panel.get("box", [0, 0, 1, 1])[2]), float(
        panel.get("box", [0, 0, 1, 1])[3]
    )
    area = 0.0
    for b in ctx.inp.panel_bubbles(pid):
        bx, by, bw, bh = ctx.inp.local_box(pid, b["box"])
        area += max(0.0, bw) * max(0.0, bh)
    return area >= TEXT_PANEL_COVER * max(1.0, w * h)


def erased_panel(ctx, pid: str, img: np.ndarray) -> np.ndarray:
    if keeps_its_lettering(ctx, pid):
        return img
    items = [
        (ctx.inp.local_box(pid, b["box"]), b.get("kind", "speech"))
        for b in ctx.inp.panel_bubbles(pid)
    ]
    cache = ctx.inp.dir / "work" / "render" / "erased" / f"{pid}-{ctx.inp.stamp()}.png"
    if cache.exists():
        got = cv2.imread(str(cache), cv2.IMREAD_UNCHANGED)
        if got is not None and got.shape == img.shape:
            return got
    out = erase(img, items, _scene_background(ctx, pid, img.shape))
    cache.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(cache), out)
    return out


def erase_in_region(ctx, pid: str, img: np.ndarray, region) -> np.ndarray:
    rx, ry = region[0], region[1]
    items = [
        (
            [b["box"][0] - rx, b["box"][1] - ry, b["box"][2], b["box"][3]],
            b.get("kind", "speech"),
        )
        for b in ctx.inp.panel_bubbles(pid)
    ]
    return erase(img, items)


# ---------------------------------------------------------------- subtitles


def tidy_text(text: str) -> str:
    """Manga lettering is all capitals; subtitles read better in sentence case."""
    t = re.sub(r"\s+", " ", text or "").strip()
    letters = [c for c in t if c.isalpha()]
    if letters and sum(c.isupper() for c in letters) / len(letters) > 0.8:
        t = t.lower()
        t = re.sub(
            r"(^|[.!?…]\s+|^\W+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), t
        )
        t = re.sub(r"\bi\b", "I", t)
        t = re.sub(r"\bi'", "I'", t)
    return t


@lru_cache(maxsize=16)
def _font(which: str, size: int):
    try:
        return ImageFont.truetype(FONT_DIR + FONTS[which], size)
    except OSError:
        return ImageFont.load_default()


def _wrap(draw, text, font, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if draw.textlength(trial, font=font) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


@lru_cache(maxsize=64)
def subtitle_sprite(
    text: str, kind: str, speaker_color: str | None, out_w: int, out_h: int
):
    """RGBA numpy sprite for one line, styled by kind."""
    short = min(out_w, out_h)
    base = int(short * 0.046)
    which, size, fill = "regular", base, (255, 255, 255, 255)
    if kind == "thought":
        which, fill = "italic", (214, 228, 255, 255)
    elif kind == "whisper":
        which, size, fill = "italic", int(base * 0.88), (225, 225, 225, 235)
    elif kind == "shout":
        which, size, fill = "shout", int(base * 1.15), (255, 236, 150, 255)
    elif kind == "caption":
        which, size, fill = "caption", int(base * 0.9), (245, 240, 228, 255)
    font = _font(which, size)
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    lines = _wrap(probe, tidy_text(text), font, out_w * 0.8)[:4]
    if not lines:
        return None
    lh = int(size * 1.22)
    tw = int(max(probe.textlength(ln, font=font) for ln in lines))
    stroke = max(2, size // 11)
    pad = size // 2
    w, h = tw + pad * 2, lh * len(lines) + pad * 2
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if kind == "caption":
        d.rounded_rectangle(
            [0, 0, w - 1, h - 1], radius=size // 3, fill=(20, 16, 12, 185)
        )
    if speaker_color and kind not in ("caption",):
        try:
            col = tuple(
                int(speaker_color.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4)
            )
            d.rounded_rectangle(
                [pad // 2, pad, pad // 2 + max(3, size // 9), h - pad],
                radius=2,
                fill=(*col, 230),
            )
        except ValueError:
            pass
    for i, ln in enumerate(lines):
        lw = probe.textlength(ln, font=font)
        x = (w - lw) / 2
        y = pad + i * lh
        sw = 0 if kind == "caption" else stroke
        d.text(
            (x, y),
            ln,
            font=font,
            fill=fill,
            stroke_width=sw,
            stroke_fill=(10, 10, 14, 255),
        )
    arr = np.array(img)
    return cv2.cvtColor(arr, cv2.COLOR_RGBA2BGRA)


def overlay(
    frame: np.ndarray, sprite: np.ndarray, x: int, y: int, alpha: float
) -> None:
    h, w = sprite.shape[:2]
    fh, fw = frame.shape[:2]
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(fw, x + w), min(fh, y + h)
    if x1 <= x0 or y1 <= y0 or alpha <= 0:
        return
    spr = sprite[y0 - y : y1 - y, x0 - x : x1 - x]
    a = spr[..., 3:4].astype(np.float32) * (alpha / 255.0)
    dst = frame[y0:y1, x0:x1, :3]
    dst[:] = (dst * (1 - a) + spr[..., :3] * a).astype(np.uint8)


def draw_subtitles(ctx, shot, t: float, frame: np.ndarray) -> None:
    mode = ctx.settings.get("subtitles", True)
    if not mode or (mode is True and ctx.settings.get("bubbles") != "erase"):
        return
    if shot.get("kind") != "reveal" and keeps_its_lettering(ctx, shot["panel_id"]):
        return  # the words are on screen already
    cast = {c["id"]: c for c in (ctx.inp.cast.get("cast") or [])}
    ow, oh = ctx.out
    for ln in shot.get("lines", []):
        at, dur = float(ln.get("at", 0)), float(ln.get("dur", 0) or 0)
        line = ctx.inp.lines.get(ln.get("line_id")) or {}
        bubble = next(
            (
                b
                for b in ctx.inp.panel_bubbles(shot["panel_id"])
                if b["id"] == ln.get("bubble_id")
            ),
            {},
        )
        text = line.get("text") or bubble.get("text") or ""
        if not dur:
            dur = max(1.1, len(text.split()) / 2.6 + 0.35)
        if not text or not (at <= t < at + dur + 0.15):
            continue
        kind = line.get("kind") or bubble.get("kind") or "speech"
        speaker = line.get("speaker") or bubble.get("speaker")
        color = (cast.get(speaker) or {}).get("color") if speaker else None
        spr = subtitle_sprite(text, kind, color, ow, oh)
        if spr is None:
            continue
        fade = min(1.0, (t - at) / 0.12, (at + dur + 0.15 - t) / 0.15)
        sh, sw = spr.shape[:2]
        if kind == "caption":
            y = int(oh * (0.06 if ow > oh else 0.1))
        else:
            y = int(oh * (0.93 if ow > oh else 0.8)) - sh
        overlay(frame, spr, (ow - sw) // 2, y, max(0.0, fade))
