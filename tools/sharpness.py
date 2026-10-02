#!/usr/bin/env python3
"""Fine-detail measure of screenshots (lane LOOK): the mean absolute Laplacian of the luminance over the lower
three quarters of the frame (sky and the compass left out). Higher is sharper; compare the same view only.

  tools/sharpness.py images/401-look_aa/*.png
"""

import sys

import numpy as np
from PIL import Image


def sharpness(path: str) -> float:
    im = np.asarray(Image.open(path).convert("L"), dtype=np.float32)
    im = im[im.shape[0] // 4 :, :]
    lap = (
        -4 * im[1:-1, 1:-1]
        + im[:-2, 1:-1]
        + im[2:, 1:-1]
        + im[1:-1, :-2]
        + im[1:-1, 2:]
    )
    return float(np.abs(lap).mean())


if __name__ == "__main__":
    for p in sys.argv[1:]:
        print(f"{sharpness(p):7.2f}  {p}")
