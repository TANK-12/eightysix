"""Find lettering: letter-like strokes grouped into lines and blocks.

Classical and model-free. Works on a full-resolution BGR window of the strip.

1. Ink: pixels much darker than their locally estimated background (dark
   lettering on light balloons), and separately pixels much lighter than a
   dark background (white captions on black).
2. Letter candidates: connected components with letter-like size and fill.
3. Lines: letters of similar height on a shared baseline, close together.
4. Blocks: lines stacked with small leading and overlapping or centred spans.

A block is only a candidate; OCR confidence and the balloon test decide.
"""

import math
from dataclasses import dataclass, field

import cv2
import numpy as np

# Components shorter than this are punctuation or specks, never letters.
MIN_LETTER_H = 7
# Taller than this is a panel border or a drawing. Big webtoon lettering
# (shouts, captions, titles) runs to 120 px on an 800 px strip; with the old
# cap of 64 the finder picked up pieces of such words ("READERS" -> "Ad").
MAX_LETTER_H = 150


@dataclass
class Comp:
    x: int
    y: int
    w: int
    h: int

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2


@dataclass
class Line:
    comps: list[Comp]
    box: tuple[int, int, int, int]
    polarity: str  # "dark" letters on light, or "light" letters on dark

    @property
    def h(self) -> float:
        """Letter height: punctuation and shadow specks do not count."""
        big = [c.h for c in self.comps if c.h >= MIN_LETTER_H]
        return float(np.median(big if big else [c.h for c in self.comps]))

    @property
    def angle(self) -> float:
        """Skew of the baseline in degrees, positive when the line runs downhill
        to the right (image y grows downwards). Zero for a single letter."""
        big = [c for c in self.comps if c.h >= MIN_LETTER_H]
        if len(big) < 3:
            return 0.0
        xs = np.array([c.cx for c in big])
        ys = np.array([c.cy for c in big])
        if xs.max() - xs.min() < 2 * max(c.h for c in big):
            return 0.0
        slope = float(np.polyfit(xs, ys, 1)[0])
        return math.degrees(math.atan(slope))


@dataclass
class Block:
    lines: list[Line]
    box: tuple[int, int, int, int]
    polarity: str
    extra: dict = field(default_factory=dict)

    @property
    def angle(self) -> float:
        """Skew of the block: the median of its lines' angles, letters weighted."""
        pairs = [(l.angle, len(l.comps)) for l in self.lines if len(l.comps) >= 3]
        if not pairs:
            return 0.0
        pairs.sort()
        total = sum(n for _, n in pairs)
        acc = 0
        for a, n in pairs:
            acc += n
            if acc * 2 >= total:
                return a
        return pairs[-1][0]


def _union_box(boxes) -> tuple[int, int, int, int]:
    x0 = min(b[0] for b in boxes)
    y0 = min(b[1] for b in boxes)
    x1 = max(b[0] + b[2] for b in boxes)
    y1 = max(b[1] + b[3] for b in boxes)
    return int(x0), int(y0), int(x1 - x0), int(y1 - y0)


def ink_masks(img: np.ndarray, kernel: int = 21, contrast: int = 70):
    """(dark_ink, light_ink) boolean masks with the local background each sits on."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel, kernel))
    bg_light = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, k)  # strokes removed
    bg_dark = cv2.morphologyEx(gray, cv2.MORPH_OPEN, k)
    g = gray.astype(np.int16)
    dark = ((bg_light.astype(np.int16) - g) >= contrast) & (bg_light >= 170)
    light = ((g - bg_dark.astype(np.int16)) >= contrast) & (bg_dark <= 90)
    return dark, light


def letter_comps(
    mask: np.ndarray, min_h: int = MIN_LETTER_H, max_h: int = MAX_LETTER_H
) -> list[Comp]:
    n, _lab, stats, _ = cv2.connectedComponentsWithStats(
        mask.astype(np.uint8), connectivity=8
    )
    out = []
    for i in range(1, n):
        x, y, w, h, area = (int(v) for v in stats[i])
        if h < min_h or h > max_h:
            # punctuation dots and commas are small; keep them only as line members later
            if not (2 <= h < min_h and 2 <= w <= 8):
                continue
        if w > 14 * h:
            continue  # ruled lines, borders
        fill = area / (w * h)
        if h >= min_h and (fill < 0.08 or fill > 0.92):
            continue
        out.append(Comp(x, y, w, h))
    return out


class _DSU:
    def __init__(self, n: int):
        self.p = list(range(n))

    def find(self, i: int) -> int:
        while self.p[i] != i:
            self.p[i] = self.p[self.p[i]]
            i = self.p[i]
        return i

    def union(self, a: int, b: int) -> None:
        self.p[self.find(a)] = self.find(b)


LINE_TOL = 0.35  # letters on one line: centre heights within this many letter heights
LINE_GAP = 1.1  # ... and at most this many letter heights apart
SLANT_MAX = 0.9  # steepest baseline followed (about 42 degrees)


def _fragments(big: list[Comp]) -> list[list[Comp]]:
    """Runs of neighbouring letters at nearly the same height."""
    dsu = _DSU(len(big))
    for i, a in enumerate(big):
        for j in range(i + 1, len(big)):
            b = big[j]
            hmax = max(a.h, b.h)
            if b.x - (a.x + a.w) > LINE_GAP * hmax:
                # sorted by x: later comps only start further right
                if b.x - (a.x + a.w) > 3 * MAX_LETTER_H:
                    break
                continue
            if abs(a.cy - b.cy) > LINE_TOL * hmax:
                continue
            if max(a.h, b.h) > 2.2 * min(a.h, b.h):
                continue
            dsu.union(i, j)
    groups: dict[int, list[Comp]] = {}
    for i, c in enumerate(big):
        groups.setdefault(dsu.find(i), []).append(c)
    return [sorted(g, key=lambda c: c.x) for g in groups.values()]


def _slope(g: list[Comp]) -> float | None:
    """Rise per unit run of a fragment's letter centres, or None when the
    fragment is too short to say."""
    if len(g) < 3:
        return None
    xs = np.array([c.cx for c in g])
    ys = np.array([c.cy for c in g])
    if float(np.ptp(xs)) < 1:
        return None
    m = float(np.polyfit(xs, ys, 1)[0])
    return max(-SLANT_MAX, min(SLANT_MAX, m))


def _join_along_baseline(frags: list[list[Comp]]) -> list[list[Comp]]:
    """Join fragments that continue one another's baseline. Tilted lettering
    breaks into pieces in `_fragments` (each piece is nearly level); here a
    piece whose start sits where the previous piece's slanted baseline
    arrives is the same line. Following the slant is what keeps the line
    above or below apart: at a 20-degree downhill slant the last letters of
    one line and the first of the next are at the same height, which is
    how "THE IMPERIAL GUARD'S SOLE REASON ..." (chapter 1) became one
    six-line "line" and was never read."""
    frags = sorted(frags, key=lambda g: g[0].x)
    changed = True
    while changed:
        changed = False
        for i, a in enumerate(frags):
            if not a:
                continue
            a_end = a[-1]
            sa = _slope(a)
            for j in range(i + 1, len(frags)):
                b = frags[j]
                if not b:
                    continue
                b0 = b[0]
                h = max(a_end.h, b0.h)
                gap = b0.x - (a_end.x + a_end.w)
                if gap > LINE_GAP * h * 1.5:
                    if gap > 3 * MAX_LETTER_H:
                        break
                    continue
                if gap < -h:
                    continue  # b starts well inside a: another line over it
                if max(a_end.h, b0.h) > 2.2 * min(a_end.h, b0.h):
                    continue
                slope = sa if sa is not None else _slope(b)
                if slope is None:
                    slope = 0.0
                predicted = a_end.cy + slope * (b0.cx - a_end.cx)
                if abs(b0.cy - predicted) > LINE_TOL * h:
                    continue
                frags[i] = a = sorted(a + b, key=lambda c: c.x)
                frags[j] = []
                a_end = a[-1]
                sa = _slope(a)
                changed = True
    return [g for g in frags if g]


def group_lines(comps: list[Comp], polarity: str) -> list[Line]:
    """Letters on a shared baseline, at most about one letter height apart --
    level or slanted (see `_join_along_baseline`)."""
    big = [c for c in comps if c.h >= MIN_LETTER_H]
    small = [c for c in comps if c.h < MIN_LETTER_H]
    big.sort(key=lambda c: c.x)
    lines = []
    for g in _join_along_baseline(_fragments(big)):
        box = _union_box([(c.x, c.y, c.w, c.h) for c in g])
        wide = box[2] >= 1.6 * box[3]
        if len(g) < 2 and not wide:
            continue
        # punctuation that sits inside or just after the line
        for s in small:
            if (
                box[0] - 4 <= s.x <= box[0] + box[2] + box[3]
                and box[1] - 2 <= s.y <= box[1] + box[3] + 2
            ):
                g.append(s)
        box = _union_box([(c.x, c.y, c.w, c.h) for c in g])
        lines.append(Line(g, box, polarity))
    return lines


def group_blocks(lines: list[Line]) -> list[Block]:
    """Stack lines with small leading whose spans overlap (left, centre or right aligned)."""
    lines = sorted(lines, key=lambda l: l.box[1])
    dsu = _DSU(len(lines))
    for i, a in enumerate(lines):
        ax, ay, aw, ah = a.box
        for j in range(i + 1, len(lines)):
            b = lines[j]
            bx, by, bw, bh = b.box
            lh = max(a.h, b.h)
            if by - (ay + ah) > 1.3 * lh:
                if by > ay + ah + 200:
                    break
                continue
            if (
                by + bh < ay
            ):  # b above a is impossible after sorting, but overlap is fine
                continue
            if max(a.h, b.h) > 1.8 * min(a.h, b.h):
                continue
            overlap = min(ax + aw, bx + bw) - max(ax, bx)
            if overlap <= 0.3 * min(aw, bw):
                continue
            dsu.union(i, j)
    groups: dict[int, list[Line]] = {}
    for i, l in enumerate(lines):
        groups.setdefault(dsu.find(i), []).append(l)
    out = []
    for g in groups.values():
        box = _union_box([l.box for l in g])
        out.append(Block(sorted(g, key=lambda l: l.box[1]), box, g[0].polarity))
    return out


def _drop_containers(comps: list[Comp], others: list[Comp]) -> list[Comp]:
    """Drop tall components that have letters of the other polarity inside
    them: a white balloon on a dark page is one big light blob with dark
    lettering in it, and it is a balloon, not a 120 px letter."""
    out = []
    for c in comps:
        if c.h > 64:
            inside = sum(
                1
                for o in others
                if o.h >= MIN_LETTER_H
                and c.x <= o.cx <= c.x + c.w
                and c.y <= o.cy <= c.y + c.h
            )
            if inside >= 3:
                continue
        out.append(c)
    return out


def find_blocks(img: np.ndarray) -> list[Block]:
    """Candidate text blocks (dark-on-light and light-on-dark) in a BGR window."""
    dark, light = ink_masks(img)
    dark_comps, light_comps = letter_comps(dark), letter_comps(light)
    blocks = []
    for comps, others, pol in (
        (dark_comps, light_comps, "dark"),
        (light_comps, dark_comps, "light"),
    ):
        comps = _drop_containers(comps, others)
        blocks.extend(group_blocks(group_lines(comps, pol)))
    return blocks
