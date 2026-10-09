"""Speech bubbles, captions and sound words for a whole strip.

1. Text blocks are found window by window down the strip (text.find_blocks),
   so the full strip is never held in memory.
2. Each block gets its enclosing balloon (balloons.find_balloon). Blocks that
   share one balloon become one bubble.
3. All bubble crops are read in batches by the OCR engine. Art outside a
   closed balloon is blanked first so it cannot leak into the text.
4. A candidate survives when its text looks like language (confidence and
   dictionary words), with looser rules inside a real balloon.
5. Kind, tail tip, panel, reading order and balloon groups are filled in.
"""

import math
import re
from dataclasses import dataclass, field

import cv2
import numpy as np

from . import balloons as B
from . import normalize as N
from . import ocr as O
from . import style as S
from . import text as T
from .panels import order_boxes
from .strip import StripReader

WINDOW = 2400
STRIDE = 1600
# Lettering skewed by more than this is turned level before it is read;
# the OCR engine reads tilted lines as junk.
LEVEL_ANGLE = 2.5


@dataclass
class Cand:
    blocks: list[T.Block]
    box: tuple[int, int, int, int]  # strip coords of the text
    polarity: str
    line_h: float
    balloon: B.Balloon | None = None
    balloon_box: tuple[int, int, int, int] | None = None  # strip coords
    oy: int = 0  # strip y of the balloon window origin
    kind: str = "speech"
    feats: dict = field(default_factory=dict)
    tail: list[int] | None = None
    polygon: list[list[int]] | None = None
    raw: str = ""
    conf: float = 0.0
    words: list[dict] = field(default_factory=list)
    colour: str = "#000000"
    angle: float = 0.0  # baseline skew in degrees, see text.Line.angle


def _iou(a, b) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0, min(ay + ah, by + bh) - max(ay, by))
    inter = ix * iy
    return inter / max(1, aw * ah + bw * bh - inter)


def _inside(inner, outer, slack: int = 4) -> bool:
    ix, iy, iw, ih = inner
    ox, oy, ow, oh = outer
    return (
        ix >= ox - slack
        and iy >= oy - slack
        and ix + iw <= ox + ow + slack
        and iy + ih <= oy + oh + slack
    )


def find_candidates(reader: StripReader, progress=None) -> list[T.Block]:
    """Text blocks of the whole strip, in strip coordinates, without duplicates."""
    out: list[T.Block] = []
    H = reader.height
    starts = list(range(0, max(1, H - WINDOW + STRIDE), STRIDE))
    for k, ws in enumerate(starts):
        img = reader.rows(ws, ws + WINDOW)
        lo = ws + (WINDOW - STRIDE) // 2 if ws > 0 else 0
        hi = ws + (WINDOW + STRIDE) // 2 if ws + WINDOW < H else H
        for b in T.find_blocks(img):
            x, y, w, h = b.box
            cy = ws + y + h / 2
            if lo <= cy < hi:
                b.box = (x, y + ws, w, h)
                for line in b.lines:
                    lx, ly, lw, lh = line.box
                    line.box = (lx, ly + ws, lw, lh)
                out.append(b)
        if progress:
            progress((k + 1) / len(starts))
    return out


def attach_balloons(reader: StripReader, blocks: list[T.Block]) -> list[Cand]:
    """One candidate per balloon (or per open text block)."""
    cands: list[Cand] = []
    for b in sorted(blocks, key=lambda b: (b.box[1], b.box[0])):
        x, y, w, h = b.box
        pad = int(max(w, h) * 0.9) + 60
        y0 = max(0, y - pad)
        area = reader.rows(y0, y + h + pad)
        bal = B.find_balloon(area, (x, y - y0, w, h), b.polarity)
        line_h = float(np.median([l.h for l in b.lines]))
        bb = (
            (bal.box[0], bal.box[1] + y0, bal.box[2], bal.box[3])
            if bal.closed
            else None
        )
        # a balloon hugely bigger than its text is a panel region, not a balloon
        if bb and (
            bb[2] * bb[3] > 60 * max(1, w * h)
            or bb[2] >= 0.97 * reader.width
            and bb[3] > 400
        ):
            bb = None
        merged = False
        if bb:
            for c in cands:
                if c.balloon_box and _iou(c.balloon_box, bb) > 0.6:
                    c.blocks.append(b)
                    c.box = T._union_box([c.box, b.box])
                    merged = True
                    break
        if merged:
            continue
        cands.append(
            Cand(
                [b],
                b.box,
                b.polarity,
                line_h,
                bal if bb else None,
                bb,
                oy=y0,
                angle=b.angle,
            )
        )
    return cands


def _letter_corners(c: Cand) -> np.ndarray:
    """Corners of every letter box of the candidate, in strip coordinates.

    Letter components are stored in window coordinates; each line's box was
    moved to strip coordinates, so the difference is the window offset.
    """
    pts = []
    for b in c.blocks:
        for line in b.lines:
            dy = line.box[1] - min(k.y for k in line.comps)
            dx = line.box[0] - min(k.x for k in line.comps)
            for k in line.comps:
                x0, y0, x1, y1 = k.x + dx, k.y + dy, k.x + k.w + dx, k.y + k.h + dy
                pts.extend([(x0, y0), (x1, y0), (x0, y1), (x1, y1)])
    return np.array(pts, np.float64)


def levelled_crop(reader: StripReader, c: Cand, pad: int) -> np.ndarray:
    """The candidate's lettering turned level, trimmed to the letters plus pad.

    The strip is rotated about the text box centre by the fitted skew, and the
    letter boxes are carried through the same rotation to find how much of the
    turned picture is the text. Neighbouring art is filled with the page
    colour the lettering sits on, so it cannot bleed in as extra words.
    """
    x, y, w, h = c.box
    cx, cy = x + w / 2, y + h / 2
    r = int(math.hypot(w, h) / 2) + pad + 2
    x0, y0 = max(0, int(cx) - r), max(0, int(cy) - r)
    big = reader.crop([x0, y0, 2 * r, 2 * r])
    fill = (255, 255, 255) if c.polarity == "dark" else (0, 0, 0)
    m = cv2.getRotationMatrix2D((cx - x0, cy - y0), c.angle, 1.0)
    turned = cv2.warpAffine(
        big,
        m,
        (big.shape[1], big.shape[0]),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=fill,
    )
    pts = _letter_corners(c) - (x0, y0)
    pts = pts @ m[:, :2].T + m[:, 2]
    lx0 = max(0, int(pts[:, 0].min()) - pad)
    ly0 = max(0, int(pts[:, 1].min()) - pad)
    lx1 = min(turned.shape[1], int(pts[:, 0].max()) + pad + 1)
    ly1 = min(turned.shape[0], int(pts[:, 1].max()) + pad + 1)
    return turned[ly0:ly1, lx0:lx1].copy()


_ALPHA = re.compile(r"[A-Za-z]+")


def reads_well(c: Cand) -> bool:
    """Two or more real words at good confidence: a reading, not a fragment."""
    words = [w for w in _ALPHA.findall(c.raw) if len(w) >= 2]
    if len(words) < 2 or c.conf < 0.7:
        return False
    known = sum(
        1 for w in words if N.known(w) or all(N.known(p) for p in N.split_glued(w))
    )
    return known >= 0.6 * len(words)


def _area(b) -> float:
    return float(max(0, b[2]) * max(0, b[3]))


def dedupe(cands: list[Cand]) -> list[Cand]:
    """Drop candidates that overlap a kept one (light and dark passes see the
    same text), and any candidate that sits inside a bigger one: a piece of
    big lettering ("Ad" inside "READERS") is never the better reading."""
    cands = sorted(cands, key=lambda c: (c.balloon_box is None, -c.conf))
    # Between a candidate inside another: keep the one that reads better.
    # A piece of big lettering ("Ad" inside "READERS") reads worse than the
    # whole and goes; a real balloon inside a junk block made of the
    # balloon's own white pieces reads better than the junk, so the junk goes.
    # A container holding two or more well-read candidates is a region (two
    # balloons taken as one) and goes whatever it read.
    drop: set[int] = set()
    for k in cands:
        inner = [
            c
            for c in cands
            if c is not k
            and _inside(c.box, k.box)
            and _area(c.box) < 0.5 * _area(k.box)
        ]
        if sum(1 for c in inner if reads_well(c)) >= 2:
            drop.add(id(k))
            continue
        for c in inner:
            if reads_well(c) and c.conf > k.conf:
                drop.add(id(k))
            else:
                drop.add(id(c))
    fragments = drop
    kept: list[Cand] = []
    for c in cands:
        if id(c) in fragments:
            continue
        if any(
            _iou(c.box, k.box) > 0.3 or _inside(c.box, k.balloon_box or k.box)
            # a slanted block's stray piece ("Who eaten" beside the whole
            # levelled caption) lies mostly over the kept one
            or _covered(c.box, k.balloon_box or k.box) >= 0.6
            for k in kept
        ):
            continue
        kept.append(c)
    return kept


def _covered(a, b) -> float:
    """Share of box a's area that box b covers."""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    iw = min(ax + aw, bx + bw) - max(ax, bx)
    ih = min(ay + ah, by + bh) - max(ay, by)
    if iw <= 0 or ih <= 0 or aw <= 0 or ah <= 0:
        return 0.0
    return iw * ih / float(aw * ah)


def ocr_candidates(reader: StripReader, cands: list[Cand], eng) -> None:
    items = []
    for c in cands:
        x, y, w, h = c.box
        p = max(6, int(0.4 * c.line_h))
        if c.balloon is None and abs(c.angle) >= LEVEL_ANGLE:
            crop = levelled_crop(reader, c, p)
        else:
            crop = reader.crop(
                [max(0, x - p), max(0, y - p), w + 2 * p, h + 2 * p]
            ).copy()
        if c.balloon is not None:
            bal = c.balloon
            cy0, cx0 = max(0, y - p), max(0, x - p)
            my0, mx0 = cy0 - (c.oy + bal.oy), cx0 - bal.ox
            m = np.zeros(crop.shape[:2], bool)
            sub = bal.mask[
                max(0, my0) : my0 + crop.shape[0], max(0, mx0) : mx0 + crop.shape[1]
            ]
            m[
                max(0, -my0) : max(0, -my0) + sub.shape[0],
                max(0, -mx0) : max(0, -mx0) + sub.shape[1],
            ] = sub
            fill = 255 if c.polarity == "dark" else 0
            crop[~m] = fill
        items.append((crop, c.polarity, c.line_h))
        c.colour = S.ink_colour(crop, c.polarity)
    if eng is None:
        return
    for c, r in zip(cands, eng.recognize(items)):
        c.raw = N.clean_raw(r.text)
        c.conf = r.conf
        c.words = r.words


SHORT_OK = {
    "no",
    "yes",
    "ok",
    "oh",
    "ah",
    "hm",
    "hmm",
    "huh",
    "uh",
    "ugh",
    "eh",
    "hey",
    "hi",
    "wow",
    "ow",
    "yo",
    "so",
    "go",
    "run",
    "why",
    "who",
    "how",
    "now",
    "me",
    "you",
    "him",
    "her",
    "not",
    "yet",
    "sir",
    "mom",
    "dad",
    "god",
    "die",
}


GLUE_MIN_CONF = 0.6  # a forced split of a doubtful read is two guesses stacked


def _word_known(w: str, allow_glue: bool = True) -> bool:
    """A two-letter read only counts as a word when it is a real function
    word: the tesseract list vouches for "gl", "ry" and "tI" otherwise.
    Splitting a glued read into known pieces ("WASIN" -> WAS IN) is only
    trusted on a confident read: at 0.5 the pieces are as doubtful as the
    whole ("_WASIN HE WORKGS." was spoken aloud on chapter 1)."""
    if len(w) == 2:
        return w.lower() in N.TWO_LETTER
    return N.known(w) or (allow_glue and _glued_words(w))


def _glued_words(w: str) -> bool:
    """True when `w` splits into known words of two or more letters (or a
    lone a/I): "tI" -> "t", "I" does not count as two words."""
    pieces = N.split_glued(w)
    if len(pieces) < 2:
        return False
    return all(N.known(p) and (len(p) >= 2 or p.lower() in ("a", "i")) for p in pieces)


def looks_like_text(c: Cand) -> bool:
    words = _ALPHA.findall(c.raw)
    letters = sum(len(w) for w in words)
    if letters < 2:
        return (
            c.balloon is not None and bool(re.search(r"[?!]", c.raw)) and c.conf >= 0.7
        )
    if len(words) == 1 and letters <= 3 and not re.search(r"[?!]", c.raw):
        # a lone two- or three-letter "word" is nearly always a piece of big
        # lettering ("Al" from "ALL", "An" from "AN EXHAUSTION"); only a
        # known short word read with real confidence, or a listed
        # interjection, passes
        w = words[0].lower()
        if w not in SHORT_OK and not (c.conf >= 0.9 and N.known(w)):
            return False
    junk = sum(1 for ch in c.raw if not (ch.isalnum() or ch in " .,!?'\"-~…:;()"))
    if junk > 0.15 * len(c.raw):
        # balloon edges read as strokes: "tI' \i' \\ gl..- RY" (chapter 5)
        return False
    long_words = [w for w in words if len(w) >= 2]
    glue_ok = c.conf >= GLUE_MIN_CONF
    dict_share = (
        sum(_word_known(w, glue_ok) for w in long_words) / len(long_words)
        if long_words
        else 0.0
    )
    if c.balloon is not None:
        # a short read ("N 9 AN", "Rt - I") needs real confidence: the
        # dictionary cannot vouch for one or two letters
        one_word = len(words) == 1 and letters >= 3 and N.known(words[0])
        # "But I-": speech cut off mid-word, every word known, ends in a dash
        cut_off = dict_share >= 1.0 and bool(re.search(r"[A-Za-z]-\s*$", c.raw))
        return (
            c.conf >= 0.45
            and dict_share >= 0.5
            and (
                letters > 4
                or c.conf >= 0.7
                or one_word
                and c.conf >= 0.55
                or cut_off
                and c.conf >= 0.6
            )
        )
    # open text: needs to read cleanly
    if c.conf >= 0.7 and dict_share >= 0.6 and letters >= 4:
        return True
    return False


def ring_flatness(reader: StripReader, box, pad: int = 12) -> float:
    """How uniform the background around an open text block is (share of ring pixels near the median)."""
    x, y, w, h = box
    X0, Y0 = max(0, x - pad), max(0, y - pad)
    area = reader.crop([X0, Y0, w + 2 * pad, h + 2 * pad]).astype(np.int16)
    ring = np.ones(area.shape[:2], bool)
    ring[y - Y0 : y - Y0 + h, x - X0 : x - X0 + w] = False
    px = area[ring]
    if len(px) == 0:
        return 0.0
    med = np.median(px, axis=0)
    return float((np.abs(px - med).max(axis=1) <= 24).mean())


SCREEN_RECT_FILL = 0.6


def is_screen_text(c: Cand) -> bool:
    """Light lettering inside a dark box: screen or sign text. The box is
    rectangular-ish, or holds a single word (a readout like ERROR); a dark
    rounded balloon with a sentence in it stays speech."""
    if c.polarity != "light" or c.balloon is None:
        return False
    words = len(_ALPHA.findall(c.raw))
    if words > SCREEN_MAX_WORDS:
        # a sentence: the white-on-black captions of a prologue (chapter 1)
        return False
    boxy = float((c.feats or {}).get("rect_fill", 0.0)) >= SCREEN_RECT_FILL
    return boxy or words <= 1


SFX_LINE_SCALE = (
    1.7  # open lettering this much taller than the chapter's usual is a sound word
)
SCREEN_MAX_WORDS = 3  # a sentence in a dark box is a caption, not a readout


def classify(reader: StripReader, c: Cand, med_line_h: float = 0.0) -> None:
    if c.balloon is not None and c.balloon_box is not None:
        bal = c.balloon
        ys, xs = np.nonzero(bal.mask)
        bx0, by0 = xs.min(), ys.min()
        m = bal.mask[by0 : ys.max() + 1, bx0 : xs.max() + 1]
        pad = 40
        sx, sy = bal.ox + int(bx0) - pad, c.oy + bal.oy + int(by0) - pad
        region = reader.crop(
            [max(0, sx), max(0, sy), m.shape[1] + 2 * pad, m.shape[0] + 2 * pad]
        )
        gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
        mm = np.zeros(gray.shape, bool)
        offx, offy = sx - max(0, sx), sy - max(0, sy)
        hh = min(m.shape[0], gray.shape[0] - pad - offy)
        ww = min(m.shape[1], gray.shape[1] - pad - offx)
        mm[pad + offy : pad + offy + hh, pad + offx : pad + offx + ww] = m[:hh, :ww]
        kind, feats = B.classify_shape(mm, gray)
        c.kind, c.feats = kind, feats
        tip = B.find_tail(mm)
        if tip is not None:
            c.tail = [max(0, sx) + tip[0], max(0, sy) + tip[1]]
        cnts, _ = cv2.findContours(
            mm.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        if cnts:
            cnt = max(cnts, key=cv2.contourArea)
            approx = cv2.approxPolyDP(cnt, 2.0, True)
            c.polygon = [
                [max(0, sx) + int(p[0][0]), max(0, sy) + int(p[0][1])] for p in approx
            ]
        return
    flat = ring_flatness(reader, c.box)
    c.feats = {"ring_flat": round(flat, 3)}
    # big open lettering is a drawn sound word; "big" is relative to the
    # chapter's usual letter height (a fixed 28 px made every ordinary
    # caption of a high-resolution webtoon a sound word)
    big = c.line_h >= max(28.0, SFX_LINE_SCALE * med_line_h)
    # a sound word is a word or two with no sentence punctuation; big
    # lettering that reads "..And earth was destroyed." is a caption
    sentence = len(_ALPHA.findall(c.raw)) >= 3 and bool(re.search(r"[.,!?;:]", c.raw))
    if flat >= 0.85:
        c.kind = "caption"
    elif big and not sentence:
        c.kind = "sfx"
    else:
        c.kind = "caption"


def assign_panels(bubbles: list[dict], panels: list[dict]) -> None:
    for b in bubbles:
        x, y, w, h = b["box"]
        cx, cy = x + w / 2, y + h / 2
        best, best_d = None, float("inf")
        for p in panels:
            for key, bonus in (("art_box", 0.0), ("box", 1.0)):
                px, py, pw, ph = p.get(key) or p["box"]
                dx = max(px - cx, 0, cx - (px + pw))
                dy = max(py - cy, 0, cy - (py + ph))
                d = float(np.hypot(dx, dy)) + bonus
                if d < best_d:
                    best, best_d = p, d
        b["panel_id"] = best["id"] if best else None


def order_bubbles(
    bubbles: list[dict], panels: list[dict], reading: str = "ttb"
) -> list[dict]:
    rank = {p["id"]: p["order"] for p in panels}
    by_panel: dict = {}
    for b in bubbles:
        by_panel.setdefault(b["panel_id"], []).append(b)
    out = []
    for pid in sorted(by_panel, key=lambda k: rank.get(k, 10**9)):
        group = by_panel[pid]
        idx = order_boxes([g["box"] for g in group], reading)
        out.extend(group[i] for i in idx)
    return out


def link_groups(bubbles: list[dict], gap: int = 8) -> None:
    """Balloons that touch or overlap form a group read in order (contract addition: group)."""
    n = len(bubbles)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(n):
        for j in range(i + 1, n):
            a, b = bubbles[i], bubbles[j]
            if a["kind"] in ("sfx", "caption") or b["kind"] in ("sfx", "caption"):
                continue
            if a["panel_id"] != b["panel_id"]:
                continue
            ax, ay, aw, ah = a.get("balloon_box") or a["box"]
            bx, by, bw, bh = b.get("balloon_box") or b["box"]
            if (
                ax - gap <= bx + bw
                and bx - gap <= ax + aw
                and ay - gap <= by + bh
                and by - gap <= ay + ah
            ):
                parent[find(i)] = find(j)
    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    k = 0
    for members in groups.values():
        if len(members) < 2:
            continue
        k += 1
        for i in members:
            bubbles[i]["group"] = f"g{k:04d}"


def detect_bubbles(
    reader: StripReader,
    panels: list[dict],
    reading: str = "ttb",
    progress=None,
    log=None,
) -> list[dict]:
    def prog(a, b):
        return (lambda f: progress(a + (b - a) * f)) if progress else None

    blocks = find_candidates(reader, prog(0.0, 0.25))
    if log:
        log(f"{len(blocks)} text candidates")
    cands = attach_balloons(reader, blocks)
    if progress:
        progress(0.35)
    eng = O.engine()
    if eng is None and log:
        log("no OCR engine found: bubbles keep their boxes but no text")
    ocr_candidates(reader, cands, eng)
    if progress:
        progress(0.8)
    kept = [
        c for c in cands if eng is None and c.balloon is not None or looks_like_text(c)
    ]
    kept = dedupe(kept)
    if log:
        log(f"{len(kept)} bubbles kept after reading")
    lines_h = [c.line_h for c in kept]
    strokes = [
        float(np.median([w["stroke"] for w in c.words if w.get("ink", 0) >= 8]))
        for c in kept
        if any(w.get("ink", 0) >= 8 for w in c.words)
    ]
    roughs = [w["rough"] for c in kept for w in c.words if w.get("ink", 0) >= 8]
    med_line_h = float(np.median(lines_h)) if lines_h else 0.0
    med_stroke = float(np.median(strokes)) if strokes else 0.0
    med_rough = float(np.median(roughs)) if roughs else 1.0
    out = []
    for c in kept:
        classify(reader, c, med_line_h)
        if is_screen_text(c):
            # a HUD box, a sign, a screen readout: light lettering in a
            # dark rectangle. Shown in the picture, never read aloud, so
            # the narrator does not say "ERROR" ten times (chapter 4)
            c.kind = "sfx"
        style = S.bubble_style(
            c.kind,
            c.feats,
            c.balloon is not None,
            c.words,
            c.line_h,
            S.line_waviness([l for b in c.blocks for l in b.lines]),
            c.colour,
            med_line_h,
            med_stroke,
            med_rough,
        )
        box = c.balloon_box or c.box
        out.append(
            {
                "id": "",
                "panel_id": None,
                "order": 0,
                "box": [int(v) for v in box],
                "kind": c.kind,
                "text": N.normalize(c.raw),
                "text_raw": c.raw,
                "ocr_conf": round(float(c.conf), 3),
                "tail": c.tail,
                "speaker": None,
                "speaker_conf": 0.0,
                "edited": False,
                "text_box": [int(v) for v in c.box],
                "polygon": c.polygon,
                "shape_features": c.feats,
                "style": style,
                "polarity": c.polarity,  # dark letters on light, or light on dark
                "angle": round(
                    float(c.angle), 1
                ),  # baseline tilt, downhill-to-the-right > 0
            }
        )
    assign_panels(out, panels)
    out = order_bubbles(out, panels, reading)
    for n, b in enumerate(out, 1):
        b["id"] = f"b{n:04d}"
        b["order"] = n
    link_groups(out)
    if progress:
        progress(1.0)
    return out
