#!/usr/bin/env python3
"""Generate a MediaForge icon (PNG)."""
import sys
OUT = sys.argv[1] if len(sys.argv) > 1 else "mediaforge.png"
try:
    from PIL import Image, ImageDraw
except Exception:
    sys.exit(0)

S = 256
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle([8, 8, S - 8, S - 8], radius=52, fill=(14, 17, 22, 255))
d.rounded_rectangle([8, 8, S - 8, S - 8], radius=52, outline=(34, 184, 207, 255), width=6)
# anvil / play triangle hybrid
d.polygon([(96, 78), (96, 178), (182, 128)], fill=(230, 237, 243, 255))
d.rectangle([60, 186, 196, 202], fill=(34, 184, 207, 255))
# sparks
for cx, cy, r in [(196, 70, 10), (176, 48, 6), (210, 96, 5)]:
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(59, 201, 219, 255))
img.save(OUT)
print("wrote", OUT)
