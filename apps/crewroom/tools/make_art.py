"""Generate the Crew Room's default pixel art into seed/.

The output is ordinary Forge art data (palette-indexed rows), so everything
here can be repainted by hand in PixelForge afterwards; this script only makes
the first draft. Rooms are not generated -- they are hand-written JSON in
seed/packs/crewroom/rooms/.

Run:  .venv/bin/python tools/make_art.py
It rewrites seed/palettes/crewroom.json and seed/packs/crewroom-*.json only.
"""

from __future__ import annotations

import json
import os

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEED = os.path.join(APP, "seed")

# fmt: off
PALETTE = {
    "o": "#1e1a2e", "w": "#fbf7ff", "k": "#3b3552", "q": "#6b6485", "Q": "#a9a3c2",
    "s": "#ffdcc2", "S": "#eab196", "r": "#ff9fae", "m": "#b8475e",
    "e": "#2a2140", "i": "#4fa3ff", "I": "#e05a9a", "u": "#3fbf8f", "U": "#c4832b",
    "a": "#f79ac0", "A": "#cc6593", "b": "#7ec3ff", "B": "#4a84cc",
    "c": "#e8ebf7", "C": "#aeb4cf", "d": "#5a5078", "D": "#342d4d",
    "f": "#ffb35c", "F": "#d07a2e", "g": "#8fe0ae", "G": "#55a877",
    "j": "#5566c8", "J": "#3a4690", "h": "#e0566b", "H": "#a53449",
    "l": "#efe6d8", "L": "#c7b9a4",
    "n": "#69e0c8", "N": "#3aa58f", "p": "#ffbe55", "P": "#d08a26",
    "v": "#a57bff", "V": "#6f4ccc",
    "y": "#7ff7ff", "Y": "#37a9c9", "z": "#d8fffb",
    "t": "#c58a55", "T": "#8e5a33", "E": "#5e3b22",
    "x": "#9aa5bd", "X": "#5c667e", "R": "#2b3148", "Z": "#1d3b5a",
    "W": "#5cbf6a", "K": "#2f8a47",
    "1": "#f3d9a0", "2": "#d9b877", "3": "#4fc4e8", "4": "#2b8fc4",
    "5": "#ffc7a8", "6": "#ff8fa3", "7": "#4a4668", "8": "#3d3a58",
    "9": "#d86a8c", "0": "#b24e70", "M": "#ff5a5a", "O": "#ffe066",
}
ROLES = {
    "outline": "o", "skin": "s", "glow": "y", "screen": "Z", "wood": "t",
    "metal": "X", "sand": "1", "water": "3", "night": "R", "lamp": "O",
    "alert": "M", "light": "l", "carpet": "7",
}
# fmt: on


# --- a tiny drawing surface --------------------------------------------------


class Grid:
    def __init__(self, w: int, h: int, fill: str = "."):
        self.w, self.h = w, h
        self.g = [[fill] * w for _ in range(h)]

    def px(self, x: int, y: int, c: str) -> None:
        if 0 <= x < self.w and 0 <= y < self.h:
            self.g[y][x] = c

    def rect(self, x: int, y: int, w: int, h: int, c: str) -> None:
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self.px(xx, yy, c)

    def box(self, x: int, y: int, w: int, h: int, fill: str, edge: str = "o") -> None:
        self.rect(x, y, w, h, edge)
        self.rect(x + 1, y + 1, w - 2, h - 2, fill)

    def hline(self, x: int, y: int, w: int, c: str) -> None:
        self.rect(x, y, w, 1, c)

    def vline(self, x: int, y: int, h: int, c: str) -> None:
        self.rect(x, y, 1, h, c)

    def disc(self, cx: float, cy: float, r: float, c: str) -> None:
        for y in range(self.h):
            for x in range(self.w):
                if (x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2 <= r * r:
                    self.g[y][x] = c

    def paste(self, rows: list[str], x: int = 0, y: int = 0) -> None:
        for dy, row in enumerate(rows):
            for dx, ch in enumerate(row):
                if ch != ".":
                    self.px(x + dx, y + dy, ch)

    def get(self, x: int, y: int) -> str:
        return self.g[y][x] if 0 <= x < self.w and 0 <= y < self.h else "."

    def outline(self, edge: str = "o") -> None:
        """Ring every opaque region with an outline pixel."""
        marks = []
        for y in range(self.h):
            for x in range(self.w):
                if self.g[y][x] != ".":
                    continue
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    if self.get(x + dx, y + dy) not in (".", edge):
                        marks.append((x, y))
                        break
        for x, y in marks:
            self.g[y][x] = edge

    def rows(self) -> list[str]:
        return ["".join(r) for r in self.g]


def noise(x: int, y: int, seed: int = 0) -> float:
    n = (x * 374761393 + y * 668265263 + seed * 982451653) & 0xFFFFFFFF
    n = ((n ^ (n >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((n ^ (n >> 16)) & 0xFFFF) / 0xFFFF


def mirror(rows: list[str]) -> list[str]:
    return [r[::-1] for r in rows]


def recolor(rows: list[str], mapping: dict[str, str]) -> list[str]:
    return ["".join(mapping.get(ch, ch) for ch in row) for row in rows]


def sprite(frames, tags, ms=None):
    frames = [f if isinstance(f, list) else f.rows() for f in frames]
    ms = ms or [0] * len(frames)
    h, w = len(frames[0]), len(frames[0][0])
    for f in frames:
        assert len(f) == h and all(len(r) == w for r in f), (tags, [len(r) for r in f])
    return {
        "w": w,
        "h": h,
        "tags": tags,
        "frames": [{"ms": m, "rows": f} for m, f in zip(ms, frames)],
    }


# --- characters ----------------------------------------------------------------
# Template symbols: H/h hair, C/c outfit, i iris. Everything else is a palette
# key already. recolor() swaps the symbols for a variant's keys.

HEAD_TOP = [
    "....oooooooo....",
    "..ooHHHHHHHHoo..",
    ".oHHHHHHHHHHHHo.",
    "oHHHHHHHHHHHHHHo",
    "oHHhHHHHHHHHhHHo",
    "oHhshHHhhHHhshHo",
    "oHssssssssssssHo",
]
EYES_FRONT = {
    "open": ["oHseesssssseesHo", "oHsiwsssssswisHo", "oHriissssssiirHo"],
    "closed": ["oHssssssssssssHo", "oHseesssssseesHo", "oHrssssssssssrHo"],
    "happy": ["oHsessssssssesHo", "oHesesssssseseHo", "oHrssssssssssrHo"],
}
MOUTH_FRONT = {
    "closed": [".oHssssmmssssHo.", "..oSssssssssSo.."],
    "open": [".oHssssmmssssHo.", "..oSsssmmsssSo.."],
}
NECK = ["...oooSSSSooo..."]

HEAD_BACK = [
    "....oooooooo....",
    "..ooHHHHHHHHoo..",
    ".oHHHHHHHHHHHHo.",
    "oHHHHHHHHHHHHHHo",
    "oHHHHHHHHHHHHHHo",
    "oHHhHHHHHHHHhHHo",
    "oHHHHHHHHHHHHHHo",
    "oHHhHHHHHHHHhHHo",
    "oHHHhHHHHHHhHHHo",
    "oHHHHHHHHHHHHHHo",
    ".oHHHHHHHHHHHHo.",
    "..ohHHHHHHHHho..",
    "...oooSSSSooo...",
]
HEAD_SIDE = [
    "....oooooooo....",
    "..ooHHHHHHHHoo..",
    ".oHHHHHHHHHHHHo.",
    "oHHHHHHHHHHHHHHo",
    "oHHHHHHHHHhHHHHo",
    "oHHHHHHhHhshHhHo",
    "oHHHHHhsssssssso",
    "oHHHHHsssssseeso",
    "oHHHHhssssssiwso",
    "oHHHHhsssssriiso",
    ".oHHHhsssssssmso",
    "..oHHhSssssssso.",
    "...oooSSSSooo...",
]

BODY_FRONT = [
    "...oCCwwwwCCo...",
    "..oCCCCwwCCCCo..",
    ".oCcCCCCCCCCcCo.",
    ".oCcCCCCCCCCcCo.",
    ".osoCCCCCCCCoso.",
    "..ooCCCCCCCCoo..",
]
BODY_BACK = [
    "...oCCCCCCCCo...",
    "..oCCCCCCCCCCo..",
    ".oCcCCCCCCCCcCo.",
    ".oCcCCCCCCCCcCo.",
    ".osoCCCCCCCCoso.",
    "..ooCCCCCCCCoo..",
]
HANDS_TYPE = ["..oCCsoCCosCCo..", "..oCsoCCCCosCo.."]
LEGS_STAND = [
    "...okkkkkkkko...",
    "...okkkookkko...",
    "...okko..okko...",
    "..okkko..okkko..",
    "..ooooo..ooooo..",
]
LEGS_WALK = [
    "...okkkkkkkko...",
    "...okkkookkko...",
    "...okko..okko...",
    "..okkko..oko....",
    "..ooooo..ooo....",
]
BODY_SIDE = [
    "....oCCCCCCo....",
    "....oCCCCCCCo...",
    "....oCCcCCCCo...",
    "....oCCcCCCCo...",
    "....oCCsoCCCo...",
    "....oCCCCCCo....",
    ".....okkkkko....",
    ".....okkkkko....",
]
LEGS_SIDE = [
    [".....okkkko.....", ".....okkkkko....", ".....ooooooo...."],
    ["....okko.okko...", "...okko...okko..", "...ooo.....ooo.."],
]
SIT_LEGS = ["..okkkkkkkkkko..", "..oooooooooooo.."]
MUG_HANDS = "...oCCsMMsCCo..."


def front_head(eyes="open", mouth="closed"):
    return HEAD_TOP + EYES_FRONT[eyes] + MOUTH_FRONT[mouth] + NECK


def side_head(eyes="open"):
    rows = list(HEAD_SIDE)
    if eyes == "closed":
        rows[7], rows[8], rows[9] = (
            "oHHHHHssssssssso",
            "oHHHHhsssssseeso",
            "oHHHHhsssssrssso",
        )
    return rows


def style_hair(rows: list[str], style: str, view: str) -> list[str]:
    g = [list(r) for r in rows]
    top = 0
    while top < len(g) and "o" not in "".join(g[top]):
        top += 1
    if style == "spiky":
        g[top] = list("..o.o.oooo.o.o..")
        g[top + 1] = list(".oHoHoHHHHoHoHo.")
        g[top + 2] = list("oHHHHHHHHHHHHHHo")
    elif style == "long":
        start, end = top + 10, min(len(g), top + 18)
        for y in range(start, end):
            last = y == end - 1
            if view in ("front", "back"):
                for x0, x1 in ((0, 1), (15, 14)):
                    g[y][x0] = "o"
                    g[y][x1] = "o" if last else "h"
            if view == "back":
                for x in range(2, 14):
                    g[y][x] = "o" if last else ("h" if x in (2, 13) else "H")
            if view == "side":
                g[y][2] = "o"
                g[y][3] = "o" if last else "h"
                g[y][4] = "o" if last or y < start + 2 else g[y][4]
    elif style == "bun":
        g[top][6:10] = list("oHHo")
    return ["".join(r) for r in g]


def compose(parts: list[tuple[list[str], int]], w=16, h=24) -> list[str]:
    grid = Grid(w, h)
    for rows, y in parts:
        grid.paste(rows, 0, y)
    return grid.rows()


def person_frames(style: str):
    """name -> (frames, ms), in template symbols."""

    def front(head, legs=LEGS_STAND, hands=None):
        rows = compose([(BODY_FRONT, 13), (legs, 19)])
        if hands:
            rows[17] = hands
        g = Grid(16, 24)
        g.paste(rows)
        g.paste([r for r in head[:13]])
        return g.rows()

    def restyle(rows, view):
        return style_hair(rows, style, view)

    head_open = front_head()
    head_blink = front_head(eyes="closed")
    head_talk = front_head(mouth="open")
    head_happy = front_head(eyes="happy")

    idle = [restyle(front(head_open), "front"), restyle(front(head_blink), "front")]
    talk = [restyle(front(head_talk), "front"), restyle(front(head_open), "front")]
    typ = [
        restyle(front(head_open, hands=HANDS_TYPE[0]), "front"),
        restyle(front(head_open, hands=HANDS_TYPE[1]), "front"),
    ]
    walk_down = [
        restyle(front(head_open, legs=LEGS_WALK), "front"),
        restyle(front(head_open, legs=[r[::-1] for r in LEGS_WALK]), "front"),
    ]

    def back(legs):
        g = Grid(16, 24)
        g.paste(compose([(BODY_BACK, 13), (legs, 19)]))
        g.paste(HEAD_BACK)
        return restyle(g.rows(), "back")

    walk_up = [back(LEGS_WALK), back([r[::-1] for r in LEGS_WALK])]
    idle_up = [back(LEGS_STAND)]

    def side(legs, eyes="open"):
        g = Grid(16, 24)
        g.paste(BODY_SIDE, 0, 13)
        g.paste(legs, 0, 21)
        g.paste(side_head(eyes))
        return restyle(g.rows(), "side")

    walk_right = [side(LEGS_SIDE[1]), side(LEGS_SIDE[0])]
    walk_left = [mirror(f) for f in walk_right]

    def sit(head, mug=False):
        g = Grid(16, 24)
        body = list(BODY_FRONT)
        if mug:
            body[4] = MUG_HANDS
        g.paste(body, 0, 16)
        g.paste(SIT_LEGS, 0, 22)
        g.paste(head[:13], 0, 3)
        return restyle(g.rows(), "front")

    relax = [
        sit(head_happy, mug=True),
        sit(head_open, mug=True),
        sit(head_blink, mug=True),
    ]
    return {
        "idle": (idle, [2600, 140]),
        "talk": (talk, [200, 240]),
        "type": (typ, [150, 150]),
        "walk_down": (walk_down, [170, 170]),
        "walk_up": (walk_up, [170, 170]),
        "walk_right": (walk_right, [170, 170]),
        "walk_left": (walk_left, [170, 170]),
        "back": (idle_up, [0]),
        "relax": (relax, [2200, 1400, 140]),
    }


MINI_HEAD = {
    "open": [
        "...oooooo...",
        "..oHHHHHHo..",
        ".oHHHHHHHHo.",
        ".oHhHHHHhHo.",
        ".oHssssssHo.",
        ".oseesseeso.",
        ".oriwsswiro.",
        "..osssssso..",
    ],
}
MINI_HEAD["blink"] = MINI_HEAD["open"][:5] + [
    ".osssssssso.",
    ".oreesseero.",
    "..osssssso..",
]
MINI_HEAD["talk"] = MINI_HEAD["open"][:7] + ["..ossmmsso.."]
MINI_BACK = [
    "...oooooo...",
    "..oHHHHHHo..",
    ".oHHHHHHHHo.",
    ".oHhHHHHhHo.",
    ".oHHHHHHHHo.",
    ".oHhHHHHhHo.",
    "..oHHHHHHo..",
    "...oSSSSo...",
]
MINI_BODY = ["...oCwwCo...", "..oCCCCCCo..", ".osCCCCCCso.", "..oCcCCcCo.."]
MINI_TYPE = [".oCsCCCCsCo.", ".oCCsCCsCCo."]
MINI_LEGS = {
    "stand": ["...okkkko...", "...ok..ko...", "...oo..oo...", "............"],
    "a": ["...okkkko...", "..oko..oko..", "..oo....oo..", "............"],
    "b": ["...okkkko...", "....okko....", "....oooo....", "............"],
}


def mini_frames():
    def make(head, legs="stand", hands=None, back=False):
        body = list(MINI_BODY)
        if back:
            body[0] = "...oCCCCo..."
        if hands:
            body[2] = hands
        return compose([(head, 0), (body, 8), (MINI_LEGS[legs], 12)], w=12, h=16)

    o, b, t = MINI_HEAD["open"], MINI_HEAD["blink"], MINI_HEAD["talk"]
    return {
        "idle": ([make(o), make(b)], [2200, 140]),
        "talk": ([make(t), make(o)], [200, 240]),
        "type": (
            [make(o, hands=MINI_TYPE[0]), make(o, hands=MINI_TYPE[1])],
            [140, 140],
        ),
        "walk": ([make(o, "a"), make(o, "b")], [160, 160]),
        "walk_up": (
            [make(MINI_BACK, "a", back=True), make(MINI_BACK, "b", back=True)],
            [160, 160],
        ),
    }


SESSION_LOOKS = [
    {"hair": "aA", "iris": "i", "outfit": "jJ", "style": "long"},
    {"hair": "bB", "iris": "U", "outfit": "lL", "style": "bob"},
    {"hair": "cC", "iris": "I", "outfit": "hH", "style": "spiky"},
    {"hair": "dD", "iris": "u", "outfit": "jJ", "style": "bun"},
    {"hair": "fF", "iris": "u", "outfit": "hH", "style": "bob"},
    {"hair": "gG", "iris": "i", "outfit": "lL", "style": "spiky"},
    {"hair": "DD", "iris": "I", "outfit": "lL", "style": "long"},
    {"hair": "cC", "iris": "U", "outfit": "jJ", "style": "bob"},
]
HELPER_TYPES = {"light": "nN", "worker": "pP", "deep": "vV", "other": "QX"}
HELPER_HAIR = {"a": "aA", "b": "bB", "c": "fF"}


def characters_pack():
    sprites = {}
    frames_by_style = {}
    for index, look in enumerate(SESSION_LOOKS, start=1):
        style = look["style"]
        if style not in frames_by_style:
            frames_by_style[style] = person_frames(style)
        mapping = {
            "H": look["hair"][0],
            "h": look["hair"][1],
            "i": look["iris"],
            "C": look["outfit"][0],
            "c": look["outfit"][1],
        }
        for pose, (frames, ms) in frames_by_style[style].items():
            sprites[f"person{index}_{pose}"] = sprite(
                [recolor(f, mapping) for f in frames], ["actor", "session", pose], ms
            )
    minis = mini_frames()
    for kind, outfit in HELPER_TYPES.items():
        for hair_id, hair in HELPER_HAIR.items():
            mapping = {
                "H": hair[0],
                "h": hair[1],
                "i": "i",
                "C": outfit[0],
                "c": outfit[1],
            }
            for pose, (frames, ms) in minis.items():
                sprites[f"helper_{kind}_{hair_id}_{pose}"] = sprite(
                    [recolor(f, mapping) for f in frames],
                    ["actor", "helper", kind, pose],
                    ms,
                )
    sprites.update(jan_sprites())
    return {
        "id": "crewroom-characters",
        "label": "Crew Room — characters",
        "tile": 16,
        "default_palette": "crewroom",
        "sprites": sprites,
    }


def jan_sprites():
    base = [
        ".......o........",
        "......oyo.......",
        ".......o........",
        "....oooooooo....",
        "...oYYYYYYYYo...",
        "..oYzzzzzzzzYo..",
        "..oYzRRRRRRzYo..",
        "..oYzRyRRyRzYo..",
        "..oYzRRRRRRzYo..",
        "..oYzzzzzzzzYo..",
        "...oYYYYYYYYo...",
        "....oooooooo....",
        ".....oYYYYo.....",
        "......oyyo......",
        ".......oo.......",
        "................",
    ]
    blink = list(base)
    blink[7] = "..oYzRRRRRRzYo.."
    blink[8] = "..oYzRyyyyRzYo.."
    glow = list(base)
    glow[1] = "......ozo......."
    glow[13] = "......ozzo......"
    busy = list(base)
    busy[7] = "..oYzRRyyRRzYo.."
    think = list(base)
    think[7] = "..oYzyRRRRyzYo.."
    variants = {
        "jan_a": {},
        "jan_b": {"Y": "V", "y": "a", "z": "w"},
        "jan_c": {"Y": "N", "y": "g", "z": "w"},
    }
    out = {}
    for name, mapping in variants.items():
        out[name + "_idle"] = sprite(
            [recolor(f, mapping) for f in (base, blink, glow)],
            ["actor", "jan"],
            [1400, 130, 700],
        )
        out[name + "_busy"] = sprite(
            [recolor(f, mapping) for f in (busy, think, glow)],
            ["actor", "jan", "busy"],
            [160, 160, 120],
        )
    return out


# --- tiles ---------------------------------------------------------------------


def tile_wood():
    g = Grid(16, 16, "t")
    for plank in range(4):
        y0 = plank * 4
        g.hline(0, y0 + 3, 16, "T")
        g.vline((5 + plank * 7) % 16, y0, 3, "T")
        for x in range(16):
            if noise(x, y0, 3) > 0.86:
                g.px(x, y0 + 1, "T")
    return g


def tile_carpet():
    g = Grid(16, 16, "7")
    for y in range(16):
        for x in range(16):
            if (x + y) % 4 == 0 and noise(x, y, 5) > 0.3:
                g.px(x, y, "8")
    return g


def tile_metal():
    g = Grid(16, 16, "X")
    g.hline(0, 0, 16, "R")
    g.vline(0, 0, 16, "R")
    g.hline(1, 1, 15, "x")
    for x, y in ((3, 3), (12, 3), (3, 12), (12, 12)):
        g.px(x, y, "q")
    g.hline(5, 8, 6, "q")
    return g


def tile_metal_stripe():
    g = tile_metal()
    for x in range(16):
        if (x // 4) % 2 == 0:
            g.px(x, 14, "O")
            g.px(x, 15, "O")
        else:
            g.px(x, 14, "k")
            g.px(x, 15, "k")
    return g


def tile_tatami():
    g = Grid(16, 16, "1")
    for y in range(16):
        for x in range(0, 16, 2):
            g.px(x, y, "2" if y % 3 else "1")
    g.hline(0, 15, 16, "W")
    g.vline(15, 0, 16, "K")
    return g


def tile_rug():
    g = Grid(16, 16, "9")
    for y in range(16):
        for x in range(16):
            if (x + y) % 8 == 0 or (x - y) % 8 == 0:
                g.px(x, y, "0")
    g.px(8, 8, "O")
    g.px(0, 0, "O")
    return g


def tile_sand(wet=False):
    base, speck = ("2", "1") if wet else ("1", "2")
    g = Grid(16, 16, base)
    for y in range(16):
        for x in range(16):
            n = noise(x, y, 11 if wet else 7)
            if n > 0.82:
                g.px(x, y, speck)
            elif n > 0.985 and not wet:
                g.px(x, y, "w")
    return g


def tile_water(frame):
    g = Grid(16, 16, "3")
    for y in range(2, 16, 5):
        for x in range(16):
            if ((x + frame * 3 + y) % 8) < 3:
                g.px(x, y, "4")
    g.px((5 + frame * 5) % 16, 4, "w")
    g.px((12 + frame * 3) % 16, 11, "w")
    return g


def tile_foam(frame):
    g = Grid(16, 16, "2")
    g.rect(0, 0, 16, 7, "3")
    for x in range(16):
        edge = 6 + (1 if (x + frame * 2) % 6 < 3 else 0)
        g.px(x, edge, "w")
        g.px(x, edge + 1, "w" if (x + frame) % 3 == 0 else "2")
    return g


def tile_sky():
    g = Grid(16, 16, "5")
    for y in range(16):
        for x in range(16):
            if y < 6 or (y < 11 and (x + y) % 2 == 0) or (y < 14 and (x + y) % 4 == 0):
                g.px(x, y, "6")
    return g


def tile_wall(kind):
    if kind == "office":
        g = Grid(16, 16, "l")
        for y in range(0, 12, 4):
            for x in range(16):
                if (x + y) % 8 == 3:
                    g.px(x, y + 1, "L")
        g.hline(0, 12, 16, "L")
        g.rect(0, 13, 16, 3, "T")
        g.hline(0, 13, 16, "t")
        g.hline(0, 0, 16, "L")
    elif kind == "metal":
        g = Grid(16, 16, "X")
        g.hline(0, 0, 16, "R")
        g.hline(0, 7, 16, "R")
        g.vline(0, 0, 16, "R")
        g.hline(1, 1, 15, "x")
        g.rect(0, 11, 16, 2, "Y")
        for x in range(2, 16, 4):
            g.px(x, 11, "y")
        g.hline(0, 15, 16, "R")
    else:
        g = Grid(16, 16, "8")
        for x in range(0, 16, 4):
            g.vline(x, 0, 10, "7")
        g.hline(0, 10, 16, "T")
        g.rect(0, 11, 16, 5, "E")
        g.vline(7, 11, 5, "T")
        g.vline(15, 11, 5, "T")
    return g


def tiles_pack():
    s = {
        "floor_wood": sprite([tile_wood()], ["tile", "floor"]),
        "floor_carpet": sprite([tile_carpet()], ["tile", "floor"]),
        "floor_metal": sprite([tile_metal()], ["tile", "floor"]),
        "floor_metal_stripe": sprite([tile_metal_stripe()], ["tile", "floor"]),
        "floor_tatami": sprite([tile_tatami()], ["tile", "floor"]),
        "rug": sprite([tile_rug()], ["tile", "floor"]),
        "sand": sprite([tile_sand()], ["tile", "floor"]),
        "sand_wet": sprite([tile_sand(wet=True)], ["tile", "floor"]),
        "water": sprite(
            [tile_water(f) for f in range(3)], ["tile", "water"], [420] * 3
        ),
        "foam": sprite([tile_foam(f) for f in range(3)], ["tile", "water"], [420] * 3),
        "sky": sprite([tile_sky()], ["tile", "sky"]),
        "wall_office": sprite([tile_wall("office")], ["tile", "wall"]),
        "wall_metal": sprite([tile_wall("metal")], ["tile", "wall"]),
        "wall_lounge": sprite([tile_wall("lounge")], ["tile", "wall"]),
    }
    return {
        "id": "crewroom-tiles",
        "label": "Crew Room — floors and walls",
        "tile": 16,
        "default_palette": "crewroom",
        "sprites": s,
    }


# --- props ---------------------------------------------------------------------


def laptop_back(g: Grid, x: int, y: int, logo="y"):
    g.box(x, y, 12, 7, "X")
    g.rect(x + 2, y + 1, 8, 5, "x")
    g.px(x + 5, y + 3, logo)
    g.px(x + 6, y + 3, logo)


def desk():
    g = Grid(32, 20)
    g.box(0, 5, 32, 6, "t")
    g.hline(1, 9, 30, "T")
    g.box(0, 10, 32, 4, "T")
    for x in (0, 29):
        g.box(x, 13, 3, 7, "E")
    laptop_back(g, 10, 0)
    g.box(22, 4, 5, 4, "w")  # mug
    g.px(24, 5, "M")
    return g


def console():
    g = Grid(32, 20)
    g.box(4, 0, 24, 8, "R")
    g.hline(5, 1, 22, "X")
    for x in range(7, 26, 3):
        g.px(x, 4, "y" if x % 2 else "Y")
    g.box(0, 7, 32, 5, "x")
    g.box(1, 11, 30, 9, "X")
    for x in range(4, 28, 4):
        g.px(x, 14, "y")
        g.px(x + 1, 16, "M" if x % 8 == 0 else "O")
    return g


def beach_table():
    g = Grid(32, 20)
    g.box(2, 6, 28, 14, "t")
    for y in (9, 13, 17):
        g.hline(3, y, 26, "T")
    g.vline(15, 7, 12, "T")
    laptop_back(g, 10, 0, logo="O")
    g.box(24, 2, 4, 5, "3")  # drink
    g.px(26, 1, "W")
    g.px(27, 0, "W")
    return g


def kotatsu():
    g = Grid(32, 20)
    g.box(1, 9, 30, 11, "9")
    for x in range(3, 30, 4):
        g.vline(x, 11, 8, "0")
    g.box(0, 5, 32, 5, "T")
    g.hline(1, 6, 30, "t")
    laptop_back(g, 10, 0, logo="a")
    g.box(24, 3, 5, 3, "O")  # orange
    return g


def board_frame(w, h, inner, edge, trim):
    g = Grid(w, h)
    g.box(0, 0, w, h, edge)
    g.rect(2, 2, w - 4, h - 4, inner)
    g.rect(2, 2, w - 4, 1, trim)
    return g


def whiteboard():
    g = board_frame(64, 36, "w", "x", "Q")
    g.box(20, 32, 24, 4, "X")
    g.px(24, 32, "M")
    g.px(27, 32, "i")
    return g


def bridge_display():
    g = board_frame(64, 36, "Z", "X", "y")
    for x in range(6, 60, 8):
        g.vline(x, 3, 31, "R")
    for y in range(8, 34, 8):
        g.hline(2, y, 60, "R")
    return g


def beach_sign():
    g = Grid(64, 44)
    g.box(0, 0, 64, 34, "t")
    for y in (8, 16, 24):
        g.hline(1, y, 62, "T")
    g.box(10, 33, 4, 11, "E")
    g.box(50, 33, 4, 11, "E")
    g.px(5, 4, "E")
    g.px(58, 4, "E")
    return g


def corkboard():
    g = board_frame(64, 36, "2", "E", "T")
    for y in range(3, 33):
        for x in range(3, 61):
            if noise(x, y, 21) > 0.8:
                g.px(x, y, "1")
    for x, c in ((6, "M"), (57, "b"), (6, "g"), (57, "O")):
        g.px(x, 5 if c in ("M", "b") else 30, c)
    return g


def window_city():
    g = Grid(48, 32)
    g.box(0, 0, 48, 32, "L")
    for y in range(2, 30):
        c = "6" if y < 12 else "5"
        g.hline(2, y, 44, c)
    g.disc(35, 14, 5, "O")
    heights = [10, 14, 8, 16, 11, 13, 7, 15, 9]
    x = 2
    for i, hgt in enumerate(heights):
        wid = 4 + (i % 3)
        g.rect(x, 30 - hgt, wid, hgt, "k" if i % 2 else "q")
        for yy in range(30 - hgt + 2, 29, 3):
            if noise(x, yy, 9) > 0.45:
                g.px(x + 1, yy, "O")
        x += wid
    g.vline(23, 1, 30, "L")
    g.hline(1, 15, 46, "L")
    g.hline(0, 31, 48, "T")
    return g


def window_night():
    g = Grid(48, 32)
    g.box(0, 0, 48, 32, "T")
    g.rect(2, 2, 44, 28, "R")
    for y in range(2, 30):
        for x in range(2, 46):
            if noise(x, y, 31) > 0.975:
                g.px(x, y, "w")
    g.disc(34, 11, 5, "c")
    g.disc(32, 10, 4, "R")
    g.vline(23, 1, 30, "T")
    g.hline(1, 15, 46, "T")
    return g


def star_window():
    # The glass is left transparent: the room's "stars" ambient paints the
    # moving sky underneath, and this frame is drawn over it.
    g = Grid(224, 40)
    g.box(0, 0, 224, 40, "X")
    g.rect(2, 2, 220, 34, ".")
    for x in range(0, 224, 56):
        g.rect(x, 0, 3, 40, "X")
        g.vline(x + 1, 0, 40, "x")
    g.rect(0, 36, 224, 4, "X")
    g.hline(0, 37, 224, "x")
    return g


def plant():
    g = Grid(16, 24)
    for cx, cy, r in ((8, 7, 5), (4, 10, 3.5), (12, 10, 3.5), (8, 3, 3)):
        g.disc(cx, cy, r, "W")
    for x, y in ((6, 6), (10, 8), (4, 11), (12, 11), (8, 4), (7, 10)):
        g.px(x, y, "K")
    g.outline()
    g.box(3, 14, 10, 10, "T")
    g.hline(4, 15, 8, "t")
    return g


def bookshelf():
    g = Grid(32, 36)
    g.box(0, 0, 32, 36, "E")
    books = "abgfhvjnpiM"
    for shelf, y in enumerate((2, 13, 24)):
        g.rect(2, y, 28, 10, "k")
        x = 3
        i = shelf * 3
        while x < 29:
            wid = 2 + (i % 2)
            hgt = 7 + (i % 3)
            g.rect(x, y + 10 - hgt, wid, hgt, books[i % len(books)])
            x += wid + (1 if i % 4 == 0 else 0)
            i += 1
        g.hline(1, y + 10, 30, "T")
    return g


def coffee_machine():
    g = Grid(16, 24)
    g.box(1, 0, 14, 20, "k")
    g.rect(3, 2, 10, 4, "R")
    g.px(5, 3, "y")
    g.px(10, 3, "M")
    g.rect(4, 9, 8, 7, "o")
    g.box(6, 12, 5, 4, "w")
    g.box(0, 19, 16, 5, "x")
    return g


def couch():
    g = Grid(48, 24)
    g.box(0, 0, 48, 14, "0")
    g.box(3, 9, 42, 11, "9")
    for x in (3, 17, 31):
        g.box(x, 10, 14, 8, "9")
        g.hline(x + 1, 11, 12, "a")
    g.box(0, 7, 5, 15, "0")
    g.box(43, 7, 5, 15, "0")
    g.rect(4, 20, 3, 4, "E")
    g.rect(41, 20, 3, 4, "E")
    return g


def beanbag(color="v", shade="V"):
    g = Grid(20, 14)
    g.disc(10, 8.5, 6.5, shade)
    g.disc(10, 7.5, 5.5, color)
    g.px(7, 5, "w")
    g.outline()
    return g


def lamp():
    g = Grid(14, 34)
    g.box(1, 0, 12, 8, "O")
    g.hline(2, 6, 10, "f")
    g.box(6, 7, 3, 24, "E")
    g.box(3, 30, 8, 4, "E")
    return g


def server_rack(frame):
    g = Grid(16, 32)
    g.box(0, 0, 16, 32, "R")
    for y in range(3, 29, 5):
        g.box(2, y, 12, 4, "k")
        on = (y + frame) % 3
        g.px(4, y + 1, "y" if on == 0 else "Y")
        g.px(6, y + 1, "M" if on == 1 else "k")
        g.px(8, y + 1, "O" if on == 2 else "q")
    return g


def reactor(frame):
    g = Grid(32, 44)
    g.box(4, 0, 24, 6, "X")
    g.box(6, 5, 20, 30, "Y")
    g.rect(8, 6, 16, 28, "3")
    glow = ("y", "z", "y")[frame]
    g.rect(13, 6, 6, 28, glow)
    g.rect(15, 6, 2, 28, "z" if frame == 1 else "y")
    for y in range(8 + frame * 3, 34, 9):
        g.hline(8, y, 16, "Y")
    g.box(0, 34, 32, 10, "X")
    g.hline(1, 36, 30, "x")
    for x in range(4, 28, 6):
        g.px(x, 40, "M" if frame == x % 3 else "O")
    return g


def palm():
    g = Grid(40, 56)
    for i in range(34):
        y = 55 - i
        x = 18 + int(3 * (i / 34) ** 2 * 3) - 4
        g.rect(x, y, 5, 1, "t" if i % 4 else "T")
        g.px(x, y, "o")
        g.px(x + 4, y, "o")
    leaves = [(-1, -0.2), (1, -0.25), (-1, 0.35), (1, 0.4), (0.2, -1)]
    cx, cy = 19, 20
    for dx, slope in leaves:
        for step in range(17):
            x = int(cx + dx * step if dx else cx + step * 0.2)
            y = int(cy + slope * step + (step * step) * 0.035 * (1 if dx else -1))
            if dx == 0.2:
                x, y = cx + step // 4, cy - step // 2 - 1
            thick = 2 if step < 12 else 1
            g.rect(x, y, 2, thick + 1, "W" if step % 3 else "K")
    g.disc(cx + 1, cy + 3, 3, "T")
    g.px(cx, cy + 2, "E")
    g.outline()
    return g


def umbrella():
    g = Grid(40, 44)
    for y in range(12):
        half = 4 + int(y * 1.4)
        for x in range(20 - half, 20 + half):
            band = ((x - 20) // 5) % 2
            g.px(x, y + 2, "M" if band else "w")
    g.outline()
    g.vline(19, 13, 31, "Q")
    g.vline(20, 13, 31, "q")
    return g


def towel(a, b):
    g = Grid(32, 16)
    g.box(0, 0, 32, 16, a)
    for x in range(3, 30, 6):
        g.rect(x, 1, 3, 14, b)
    return g


def sun():
    g = Grid(28, 28)
    g.disc(14, 14, 12, "O")
    g.disc(12, 12, 5, "w")
    return g


def tiki(frame):
    g = Grid(10, 34)
    g.box(3, 8, 4, 26, "T")
    g.box(1, 6, 8, 4, "E")
    flame = [["..O.", ".OMO", "OMMO", ".MM."], [".O..", "OMO.", "OMMO", ".MM."]][frame]
    g.paste(flame, 3, 2)
    return g


def aquarium(frame):
    g = Grid(36, 32)
    g.box(0, 0, 36, 22, "Y")
    g.rect(2, 3, 32, 18, "3")
    g.hline(2, 3, 32, "y")
    for x in range(2, 34):
        if noise(x, 1, 41) > 0.5:
            g.px(x, 19, "2")
        g.px(x, 20, "2")
    fx = 8 + frame * 3
    g.paste([".ff.", "fwfF", ".ff."], fx, 8)
    g.paste([".aa", "awA", ".aa"], 26 - frame * 4, 13)
    g.px(5, 10 - frame, "w")
    g.px(30, 7 + frame, "w")
    g.vline(8, 14, 6, "W")
    g.vline(28, 12, 8, "K")
    g.box(2, 21, 32, 11, "E")
    g.hline(3, 23, 30, "T")
    return g


def cat(frame):
    g = Grid(18, 12)
    g.disc(9, 7.5 - (0.5 if frame else 0), 5.5, "f")
    g.paste(["o.o", "fof"], 3, 1)
    g.disc(5, 6, 3.2, "f")
    g.px(4, 6, "o")
    g.px(6, 6, "o")
    g.rect(10, 9, 7, 2, "F")
    g.outline()
    return g


def crab(frame):
    g = Grid(14, 10)
    g.disc(7, 6, 4, "M")
    g.px(5, 4, "w")
    g.px(9, 4, "w")
    g.px(5, 3, "o")
    g.px(9, 3, "o")
    claw_y = 3 if frame else 4
    g.rect(1, claw_y, 2, 2, "M")
    g.rect(11, claw_y, 2, 2, "M")
    g.outline()
    return g


def bench():
    g = Grid(48, 16)
    g.box(0, 0, 48, 8, "X")
    g.hline(1, 2, 46, "x")
    g.box(0, 7, 48, 5, "R")
    g.rect(3, 12, 3, 4, "X")
    g.rect(42, 12, 3, 4, "X")
    return g


def counter():
    g = Grid(48, 28)
    g.box(0, 0, 48, 6, "l")
    g.box(0, 5, 48, 23, "T")
    for x in (15, 31):
        g.vline(x, 6, 21, "E")
    for x in (7, 23, 39):
        g.px(x, 12, "O")
    return g


def item_file():
    g = Grid(8, 9)
    g.box(0, 0, 8, 9, "w")
    g.px(6, 1, "Q")
    g.px(6, 0, "o")
    g.px(7, 1, "o")
    for y in (3, 5, 7):
        g.hline(2, y, 4, "q")
    return g


def props_pack():
    s = {
        "desk": sprite([desk()], ["prop", "station"]),
        "console": sprite([console()], ["prop", "station"]),
        "beach_table": sprite([beach_table()], ["prop", "station"]),
        "kotatsu": sprite([kotatsu()], ["prop", "station"]),
        "whiteboard": sprite([whiteboard()], ["prop", "board"]),
        "bridge_display": sprite([bridge_display()], ["prop", "board"]),
        "beach_sign": sprite([beach_sign()], ["prop", "board"]),
        "corkboard": sprite([corkboard()], ["prop", "board"]),
        "window_city": sprite([window_city()], ["prop", "wall"]),
        "window_night": sprite([window_night()], ["prop", "wall"]),
        "star_window": sprite([star_window()], ["prop", "wall"]),
        "plant": sprite([plant()], ["prop"]),
        "bookshelf": sprite([bookshelf()], ["prop"]),
        "coffee_machine": sprite([coffee_machine()], ["prop"]),
        "couch": sprite([couch()], ["prop", "seat"]),
        "beanbag": sprite([beanbag()], ["prop", "seat"]),
        "beanbag_green": sprite([beanbag("g", "G")], ["prop", "seat"]),
        "lamp": sprite([lamp()], ["prop"]),
        "server_rack": sprite(
            [server_rack(f) for f in range(3)], ["prop", "jan"], [500] * 3
        ),
        "reactor": sprite([reactor(f) for f in range(3)], ["prop", "jan"], [260] * 3),
        "palm": sprite([palm()], ["prop"]),
        "umbrella": sprite([umbrella()], ["prop"]),
        "towel_pink": sprite([towel("a", "w")], ["prop", "seat"]),
        "towel_blue": sprite([towel("b", "w")], ["prop", "seat"]),
        "sun": sprite([sun()], ["prop", "sky"]),
        "tiki": sprite([tiki(f) for f in range(2)], ["prop", "jan"], [300, 300]),
        "aquarium": sprite([aquarium(f) for f in range(3)], ["prop", "jan"], [600] * 3),
        "cat": sprite([cat(f) for f in range(2)], ["prop", "pet"], [1300, 1300]),
        "crab": sprite([crab(f) for f in range(2)], ["prop", "pet"], [260, 260]),
        "bench": sprite([bench()], ["prop", "seat"]),
        "counter": sprite([counter()], ["prop"]),
        "item_file": sprite([item_file()], ["item"]),
    }
    return {
        "id": "crewroom-props",
        "label": "Crew Room — furniture and props",
        "tile": 16,
        "default_palette": "crewroom",
        "sprites": s,
    }


def write(relative: str, data: dict) -> None:
    path = os.path.join(SEED, relative)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, ensure_ascii=False)
        fh.write("\n")


def main() -> None:
    write(
        "palettes/crewroom.json",
        {"id": "crewroom", "label": "Crew Room", "colors": PALETTE, "roles": ROLES},
    )
    for pack in (characters_pack(), tiles_pack(), props_pack()):
        write(f"packs/{pack['id']}.json", pack)
        print(pack["id"], len(pack["sprites"]), "sprites")


if __name__ == "__main__":
    main()
