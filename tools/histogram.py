#!/usr/bin/env python3
"""Tone measure of screenshots (lane LOOK2, "washed out"): per image, the mean luminance, the black and white
points (1st and 99th percentile of luminance), the spread between them, the luminance standard deviation and the
mean saturation and the share of clipped pixels (any channel at 250+), all on the 0-255 sRGB values the player sees, over the world part of the frame (HUD corners
left out). A washed-out frame has a high black point, a
narrow spread and low saturation. Compare the same view only.

  tools/histogram.py images/530-look2_before_small/*.png
  tools/histogram.py --json out.json images/a/*.png images/b/*.png
"""

import argparse
import json
import pathlib

import numpy as np
from PIL import Image

# Rec. 709 luma weights on the encoded values (what the eye reads as brightness on screen)
LUMA = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


# the world part of the frame: the HUD sits in the corners and along the top, and its dark panels would set the
# black point (x from 12 % to 85 %, y from 6 % to 78 %)
CROP = (0.12, 0.06, 0.85, 0.78)


def measure(path: str) -> dict:
    rgb = np.asarray(Image.open(path).convert("RGB"), dtype=np.float32)
    h, w = rgb.shape[:2]
    rgb = rgb[int(h * CROP[1]) : int(h * CROP[3]), int(w * CROP[0]) : int(w * CROP[2])]
    y = rgb @ LUMA
    hi = rgb.max(axis=2)
    lo = rgb.min(axis=2)
    sat = np.where(hi > 0, (hi - lo) / np.maximum(hi, 1e-6), 0.0)
    black, white = np.percentile(y, [1, 99])
    return {
        "mean": round(float(y.mean()), 1),
        "black": round(float(black), 1),
        "white": round(float(white), 1),
        "spread": round(float(white - black), 1),
        "std": round(float(y.std()), 1),
        "sat": round(float(sat.mean()), 3),
        "clip": round(float((hi >= 250).mean() * 100), 2),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Tone measure of screenshots.")
    ap.add_argument("images", nargs="+")
    ap.add_argument("--json", help="also write the numbers to this file")
    a = ap.parse_args()
    rows = {}
    print(
        f"{'image':42} {'mean':>6} {'black':>6} {'white':>6} {'spread':>6} {'std':>6} {'sat':>6} {'clip%':>6}"
    )
    for p in a.images:
        m = measure(p)
        name = "/".join(pathlib.Path(p).parts[-2:])
        rows[name] = m
        print(
            f"{name[-42:]:42} {m['mean']:6.1f} {m['black']:6.1f} {m['white']:6.1f} {m['spread']:6.1f}"
            f" {m['std']:6.1f} {m['sat']:6.3f} {m['clip']:6.2f}"
        )
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
