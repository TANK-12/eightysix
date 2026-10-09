"""2.5D rig boxes and which way a character faces.

A rig gives the renderer the parts it animates: the head (turns), the eyes
(blinks), the mouth (lip-flap) and the neck and hip pivots (breathing, head
tilt). Everything is in panel coordinates and derived from the character box,
the face box and, when present, the cutout mask. Proportions follow standard
anime face construction: eyes on the line about 45% down the face, mouth at
about 78%, the neck just under the chin.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from . import geom

FRONT_BAND = 0.07  # face-centre offset (fraction of head width) still "front"


def head_extent(
    face: list[int], mask: np.ndarray | None, char_box: list[int]
) -> tuple[float, float]:
    """Left and right edge of the head at the face's rows, in panel x."""
    x, y, w, h = face
    if mask is not None and mask.size:
        cx0, cy0 = char_box[0], char_box[1]
        r0 = max(0, int(y - cy0))
        r1 = min(mask.shape[0], int(y + h - cy0))
        # Only look one face-width beyond the face, so shoulders don't count.
        c0 = max(0, int(x - cx0 - 1.2 * w))
        c1 = min(mask.shape[1], int(x + w - cx0 + 1.2 * w))
        band = mask[r0:r1, c0:c1] > 127 if r1 > r0 and c1 > c0 else None
        if band is not None and band.any():
            cols = np.where(band.mean(axis=0) > 0.35)[0]
            if cols.size:
                return cx0 + c0 + float(cols[0]), cx0 + c0 + float(cols[-1] + 1)
    return float(x - 0.12 * w), float(x + w + 0.12 * w)


def facing(
    face: list[int] | None,
    char_box: list[int],
    mask: np.ndarray | None = None,
) -> str | None:
    """'left', 'right' or 'front' (viewer's left/right), None without a face.

    When a head turns, the face slides toward the side it looks at and the
    back of the head (hair) fills the other side. So the face centre's offset
    from the head's centre gives the direction.
    """
    if not face:
        return None
    left, right = head_extent(face, mask, char_box)
    head_w = max(1.0, right - left)
    offset = (face[0] + face[2] / 2 - (left + right) / 2) / head_w
    band = FRONT_BAND if mask is not None else FRONT_BAND * 1.5
    if offset < -band:
        return "left"
    if offset > band:
        return "right"
    return "front"


def _int_box(b) -> list[int]:
    return [int(round(v)) for v in b]


def build(
    char_box: list[int],
    face: list[int] | None,
    facing_dir: str | None,
    panel_w: int,
    panel_h: int,
    mask: np.ndarray | None = None,
    eye_boxes: list[list[int]] | None = None,
) -> dict[str, Any]:
    """Rig boxes for one character. Missing parts are empty/None, never guessed
    outside the character box."""
    cx, cy, cw, ch = char_box
    if face:
        fx, fy, fw, fh = face
        left, right = head_extent(face, mask, char_box)
        top = fy - 0.35 * fh  # hair above the brow
        head = [min(left, fx), top, max(right, fx + fw) - min(left, fx), fh * 1.45]
    else:
        side = min(cw, ch * 0.3)
        fx, fy, fw, fh = cx + (cw - side) / 2, cy, side, side
        head = [fx, fy, fw, fh]
    head = geom.clip(head, panel_w, panel_h)
    head = geom.clip(
        [
            max(head[0], cx),
            max(head[1], cy),
            min(head[0] + head[2], cx + cw) - max(head[0], cx),
            min(head[1] + head[3], cy + ch) - max(head[1], cy),
        ],
        panel_w,
        panel_h,
    )

    eyes: list[list[int]] = []
    mouth = None
    if face:
        shift = {"left": -0.08, "right": 0.08}.get(facing_dir or "", 0.0)
        if eye_boxes:
            eyes = [geom.clip(e, panel_w, panel_h) for e in eye_boxes]
        else:
            ew, eh = fw * 0.22, fh * 0.14
            ey = fy + fh * 0.45 - eh / 2
            for ex in (0.31, 0.69):
                if facing_dir == "left" and ex > 0.5:
                    ex -= 0.04  # far eye foreshortened toward the face centre
                if facing_dir == "right" and ex < 0.5:
                    ex += 0.04
                eyes.append(
                    geom.clip(
                        [fx + fw * (ex + shift) - ew / 2, ey, ew, eh],
                        panel_w,
                        panel_h,
                    )
                )
        mw, mh = fw * 0.3, fh * 0.1
        mouth = geom.clip(
            [fx + fw * (0.5 + shift) - mw / 2, fy + fh * 0.78 - mh / 2, mw, mh],
            panel_w,
            panel_h,
        )
        eyes = [e for e in eyes if e[2] > 0 and e[3] > 0 and geom.inside(e, head, 1)]
        if mouth[2] <= 0 or mouth[3] <= 0 or not geom.inside(mouth, head, 1):
            mouth = None

    neck_y = min(cy + ch, fy + fh * 1.1)
    neck = [int(round(fx + fw / 2)), int(round(neck_y))]
    neck[0] = max(cx, min(cx + cw, neck[0]))
    hip = None
    # A hip only exists when the body is drawn well below the head.
    hip_y = fy + fh * 3.6
    if hip_y <= cy + ch and hip_y > neck_y + fh:
        hip = [int(round(cx + cw / 2)), int(round(hip_y))]
    return {
        "head": _int_box(head),
        "eyes": [_int_box(e) for e in eyes],
        "mouth": _int_box(mouth) if mouth else None,
        "pivot_neck": neck,
        "pivot_hip": hip,
    }


def find_eyes(bgr: np.ndarray, face: list[float]) -> list[list[float]]:
    """Eye boxes found in the drawing itself (image coords), or [].

    Anime eyes are the largest dark shapes in the upper half of the face
    box: the iris and pupil plus the upper lid line. Everything is measured
    against the face box, so it works at any scale. Two eyes must sit on
    about the same line; a profile gives one. Nothing is guessed: no dark
    shape of the right size and place means no eyes, and the puppet style
    then leaves the face still rather than blink in the wrong spot.
    """
    import cv2

    fx, fy, fw, fh = (float(v) for v in face)
    h, w = bgr.shape[:2]
    # the inner face only: hair and shadow come in from the box edges
    x0, x1 = int(max(0, fx + 0.1 * fw)), int(min(w, fx + 0.9 * fw))
    y0, y1 = int(max(0, fy + 0.22 * fh)), int(min(h, fy + 0.64 * fh))
    if x1 - x0 < 12 or y1 - y0 < 8:
        return []
    band = bgr[y0:y1, x0:x1, :3]
    gray = cv2.cvtColor(band, cv2.COLOR_BGR2GRAY)
    dark = (gray < 85).astype(np.uint8)
    dark = cv2.morphologyEx(
        dark, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    )
    n, _lab, stats, _ = cv2.connectedComponentsWithStats(dark, connectivity=8)
    face_area = fw * fh
    bh_, bw_ = gray.shape
    cands = []
    for i in range(1, n):
        bx, by, bw, bh, area = (float(v) for v in stats[i])
        if not (0.004 * face_area <= area <= 0.08 * face_area):
            continue
        if not (0.06 * fh <= bh <= 0.3 * fh and 0.06 * fw <= bw <= 0.45 * fw):
            continue
        if not (0.5 <= bw / max(1.0, bh) <= 3.5):
            continue
        if bx <= 0 or by <= 0 or bx + bw >= bw_ or by + bh >= bh_:
            continue  # touches the band edge: hair or shadow from outside
        # the white of the eye: bright pixels right next to the dark shape
        px, py = int(bw * 0.4) + 1, int(bh * 0.4) + 1
        ring = gray[
            int(max(0, by - py)) : int(min(bh_, by + bh + py)),
            int(max(0, bx - px)) : int(min(bw_, bx + bw + px)),
        ]
        if (ring > 165).mean() < 0.08:
            continue
        cands.append((area, [x0 + bx, y0 + by, bw, bh]))
    if not cands:
        return []
    cands.sort(key=lambda c: -c[0])
    first = cands[0][1]
    eyes = [first]
    fcx, fcy = first[0] + first[2] / 2, first[1] + first[3] / 2
    for _area, b in cands[1:]:
        cx, cy = b[0] + b[2] / 2, b[1] + b[3] / 2
        if abs(cy - fcy) <= 0.12 * fh and abs(cx - fcx) >= 0.2 * fw:
            eyes.append(b)
            break
    out = []
    for bx, by, bw, bh in eyes:
        px, py = bw * 0.2, bh * 0.25
        out.append([bx - px, by - py, bw + 2 * px, bh + 2 * py])
    return sorted(out, key=lambda b: b[0])


def mouth_from_eyes(eyes: list[list[float]], face: list[float]) -> list[float] | None:
    """The mouth box implied by where the eyes are: about 0.38 of the face
    height below the eye line, under the eyes' midpoint (one eye: shifted a
    little towards the face centre)."""
    if not eyes:
        return None
    fx, fy, fw, fh = (float(v) for v in face)
    cy = sum(e[1] + e[3] / 2 for e in eyes) / len(eyes)
    cx = sum(e[0] + e[2] / 2 for e in eyes) / len(eyes)
    if len(eyes) == 1:
        cx = cx * 0.6 + (fx + fw / 2) * 0.4
    mw, mh = fw * 0.28, fh * 0.1
    my = cy + 0.38 * fh
    if my + mh / 2 > fy + fh * 1.05:
        return None
    return [cx - mw / 2, my - mh / 2, mw, mh]
