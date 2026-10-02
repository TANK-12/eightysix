#!/usr/bin/env python3
"""Contact sheet of a bot run's screenshots, or a before/after pair side by side (lane LOOK).

tools/contact_sheet.py images/390-look_small out.png [--cols 4] [--width 640]
tools/contact_sheet.py images/390-look_small images/395-look_small out.png   (matching names, before | after)
"""

import argparse
import os
import re
import sys

from PIL import Image, ImageDraw


def shots(folder: str) -> dict[str, str]:
    out = {}
    for f in sorted(os.listdir(folder)):
        m = re.match(r"\d+-(.+)\.png$", f)
        if m:
            out[m.group(1)] = os.path.join(folder, f)
    return out


def thumb(path: str, width: int, label: str) -> Image.Image:
    im = Image.open(path).convert("RGB")
    im = im.resize((width, int(im.height * width / im.width)), Image.Resampling.LANCZOS)
    ImageDraw.Draw(im).text((6, 4), label, fill=(255, 255, 0))
    return im


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--cols", type=int, default=3)
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--only", default="", help="comma-separated shot names")
    a = ap.parse_args()
    out = a.paths[-1]
    folders = a.paths[:-1]
    sets = [shots(f) for f in folders]
    names = [n for n in sets[0] if all(n in s for s in sets)]
    if a.only:
        names = [n for n in a.only.split(",") if n in names]
    ncols = len(sets) if len(sets) > 1 else a.cols
    tiles = []
    for n in names:
        for s in sets:
            tiles.append(thumb(s[n], a.width, n))
    if not tiles:
        print("no matching shots", file=sys.stderr)
        return 1
    h = tiles[0].height
    rows = (len(tiles) + ncols - 1) // ncols
    sheet = Image.new("RGB", (ncols * a.width, rows * h), (16, 16, 16))
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % ncols) * a.width, (i // ncols) * h))
    sheet.save(out)
    print(out, sheet.size)
    return 0


if __name__ == "__main__":
    sys.exit(main())
