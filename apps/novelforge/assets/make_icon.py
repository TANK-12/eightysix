#!/usr/bin/env python3
"""Generate a simple NovelForge app icon (PNG). Uses Pillow if present."""
import sys

OUT = sys.argv[1] if len(sys.argv) > 1 else "novelforge.png"

try:
    from PIL import Image, ImageDraw
except Exception:
    sys.exit(0)

S = 256
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# rounded-square background gradient-ish (two stacked rects)
d.rounded_rectangle([8, 8, S - 8, S - 8], radius=52, fill=(13, 17, 23, 255))
d.rounded_rectangle([8, 8, S - 8, S - 8], radius=52, outline=(31, 111, 235, 255), width=6)

# an open book / anvil abstraction: two page blocks + a spark
d.polygon([(48, 172), (124, 150), (124, 96), (48, 118)], fill=(230, 237, 243, 255))
d.polygon([(208, 172), (132, 150), (132, 96), (208, 118)], fill=(139, 148, 158, 255))
d.line([(128, 96), (128, 156)], fill=(31, 111, 235, 255), width=6)

# spark
cx, cy = 128, 74
for dx, dy, r in [(0, 0, 16), (0, -34, 6), (30, 6, 5), (-30, 6, 5)]:
    d.ellipse([cx + dx - r, cy + dy - r, cx + dx + r, cy + dy + r], fill=(56, 139, 253, 255))

img.save(OUT)
print(f"wrote {OUT}")
