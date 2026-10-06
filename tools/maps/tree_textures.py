"""Textures for the forest's fir trees (scripts/world/big/big_forest.gd), written to assets/trees/fir/:
  bark.jpg, bark_nrm.jpg  a strip of Poly Haven's fir_tree_01 trunk bark (CC0), mirrored so it tiles
  branch.png              one drooping fir bough on a transparent card (drawn here: stem, twigs, needles)
  far.png                 the whole tree's silhouette for the far billboard, lit from the upper left
Usage: python3 tools/maps/tree_textures.py <fir_tree_01_trunk_a_diff_1k.jpg> <..._trunk_a_nor_gl_1k.jpg>
(from https://polyhaven.com/a/fir_tree_01, 1k JPG). Deterministic: the same files every run.
"""

import math
import random
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

OUT = Path(__file__).resolve().parents[2] / "assets" / "trees" / "fir"
# needle colours (linear-ish sRGB 0-255): shade, mid, sunlit tip
NEEDLE = [(28, 46, 26), (44, 70, 36), (70, 98, 48)]
STEM = (72, 52, 36)


def bark(diff: Path, nrm: Path) -> None:
    """The bark strip at the lower left of trunk_a, mirrored both ways so it tiles."""
    box = (8, 600, 328, 1000)
    for src, name, q in ((diff, "bark.jpg", 88), (nrm, "bark_nrm.jpg", 92)):
        a = Image.open(src).convert("RGB").crop(box)
        w, h = a.size
        tile = Image.new("RGB", (w * 2, h * 2))
        tile.paste(a, (0, 0))
        tile.paste(a.transpose(Image.Transpose.FLIP_LEFT_RIGHT), (w, 0))
        tile.paste(a.transpose(Image.Transpose.FLIP_TOP_BOTTOM), (0, h))
        tile.paste(a.transpose(Image.Transpose.ROTATE_180), (w, h))
        if name == "bark_nrm.jpg":
            # the mirrored halves flip the normal's x (and y) components back so light stays consistent
            t = np.asarray(tile).astype(np.int16)
            t[:, w:, 0] = 255 - t[:, w:, 0]
            t[h:, :, 1] = 255 - t[h:, :, 1]
            tile = Image.fromarray(t.astype(np.uint8))
        tile.resize((512, 512), Image.Resampling.LANCZOS).save(OUT / name, quality=q)


def _mix(a: tuple, b: tuple, t: float) -> tuple:
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _needles(
    d: ImageDraw.ImageDraw,
    x0: float,
    y0: float,
    ang: float,
    length: float,
    rng: random.Random,
    tip_light: float,
    scale: float,
) -> None:
    """One twig with needles either side, from (x0, y0) along ang for length px."""
    steps = max(int(length / (2.2 * scale)), 2)
    for i in range(steps):
        t = i / steps
        x = x0 + math.cos(ang) * length * t
        y = y0 + math.sin(ang) * length * t
        nl = (9.0 - 4.0 * t) * scale
        for side in (-1, 1):
            a = ang + side * rng.uniform(0.75, 1.15)
            c = _mix(NEEDLE[0], NEEDLE[1], rng.random())
            c = _mix(c, NEEDLE[2], tip_light * t * rng.uniform(0.4, 1.0))
            d.line(
                [(x, y), (x + math.cos(a) * nl, y + math.sin(a) * nl)],
                fill=c + (255,),
                width=max(int(1.6 * scale), 1),
            )
    d.line(
        [(x0, y0), (x0 + math.cos(ang) * length, y0 + math.sin(ang) * length)],
        fill=STEM + (255,),
        width=max(int(1.4 * scale), 1),
    )


def _bleed(img: Image.Image) -> Image.Image:
    """Fill see-through pixels with the needle colour so mipmaps do not go dark at the edges."""
    a = np.asarray(img).astype(np.float32)
    alpha = a[..., 3:4] / 255.0
    mean = (a[..., :3] * alpha).sum(axis=(0, 1)) / max(alpha.sum(), 1.0)
    a[..., :3] = a[..., :3] * alpha + mean * (1.0 - alpha)
    return Image.fromarray(a.astype(np.uint8), "RGBA")


def branch() -> None:
    """A bough from the trunk (left edge) to its tip (right edge), drooping a little, seen from above."""
    rng = random.Random(86)
    w, h = 512, 256
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    mid = h * 0.5
    for i in range(46):
        t = 0.04 + 0.94 * i / 46
        x = t * (w - 16)
        y = mid + math.sin(t * 3.0) * 6.0
        reach = (1.0 - t * 0.75) * h * 0.48
        for side in (-1, 1):
            ang = side * rng.uniform(0.55, 0.85)
            _needles(d, x, y, ang, reach * rng.uniform(0.7, 1.0), rng, 0.9, 1.0)
    _needles(d, 0, mid, 0.0, w - 8, rng, 0.5, 1.2)
    img = img.filter(ImageFilter.SMOOTH)
    _bleed(img).save(OUT / "branch.png")


def far() -> None:
    """The tree seen from the side at a distance: a narrow spire of drooping tiers over a short trunk."""
    rng = random.Random(1986)
    w, h = 256, 512
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = w * 0.5
    trunk_top = h * 0.82
    d.rectangle([cx - 4, trunk_top, cx + 4, h - 1], fill=STEM + (255,))
    tiers = 34
    for i in range(tiers):
        t = i / (tiers - 1)  # 0 at the bottom tier, 1 at the top
        y = trunk_top - t * (trunk_top - 6) + rng.uniform(-4, 4)
        half_w = (1.0 - t) ** 0.85 * w * 0.45 + 4
        for side in (-1, 1):
            # a drooping bough as a ragged filled wedge, then needle strokes over it
            length = half_w * rng.uniform(0.8, 1.05)
            droop = length * rng.uniform(0.25, 0.45)
            ex, ey = cx + side * length, y + droop
            thick = 7 + 12 * (1.0 - t)
            pts = [(cx, y - 2), (ex, ey)]
            for k in range(8, -1, -1):
                u = k / 8
                pts.append(
                    (
                        cx + side * length * u,
                        y + droop * u + thick * (1.0 - u * 0.6) + rng.uniform(-3, 3),
                    )
                )
            light = (0.55 if side < 0 else 0.2) * (0.5 + 0.5 * t)
            base = _mix(NEEDLE[0], NEEDLE[1], 0.5)
            d.polygon(pts, fill=_mix(base, NEEDLE[2], light * 0.6) + (255,))
            for j in range(int(length * 1.2)):
                u = rng.random()
                px = cx + side * length * u
                py = y + droop * u + rng.uniform(0, thick * (1.0 - u * 0.6))
                c = _mix(NEEDLE[0], NEEDLE[2], light * rng.uniform(0.3, 1.2))
                d.line(
                    [(px, py), (px + side * rng.uniform(1, 4), py + rng.uniform(2, 6))],
                    fill=c + (255,),
                    width=2,
                )
    img = img.filter(ImageFilter.SMOOTH)
    _bleed(img).save(OUT / "far.png")


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    OUT.mkdir(parents=True, exist_ok=True)
    bark(Path(sys.argv[1]), Path(sys.argv[2]))
    branch()
    far()
    print("wrote", ", ".join(sorted(p.name for p in OUT.iterdir())))


if __name__ == "__main__":
    main()
