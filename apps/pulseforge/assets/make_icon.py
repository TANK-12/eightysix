#!/usr/bin/env python3
"""Generate a simple PulseForge icon (a waveform pulse) -> PNG at the given path."""

import sys

from PIL import Image, ImageDraw


def make(path, size=256):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([8, 8, size - 8, size - 8], radius=44, fill=(18, 7, 30, 255))
    cx, cy = size / 2, size / 2
    bars = [0.2, 0.5, 0.85, 1.0, 0.6, 0.9, 0.35, 0.15]
    n = len(bars)
    bw = (size - 80) / (n * 1.6)
    for i, v in enumerate(bars):
        x = 40 + i * bw * 1.6
        bh = v * (size - 90)
        t = i / (n - 1)
        col = (int(209 - t * 100), int(107 + t * 100), 255, 255)
        d.rounded_rectangle(
            [x, cy - bh / 2, x + bw, cy + bh / 2], radius=int(bw / 2), fill=col
        )
    img.save(path)


if __name__ == "__main__":
    make(sys.argv[1] if len(sys.argv) > 1 else "pulseforge.png")
