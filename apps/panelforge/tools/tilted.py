"""List the tilted lettering in a chapter, to find a page the reader misses.

    .venv/bin/python tools/tilted.py <series> <chapter> [min_degrees]

Finds the text blocks the reader finds, keeps those tilted at least
`min_degrees` (default 8), reads them the way the reader does (levelled crop,
OCR, the same text test so art is left out) and prints each: strip y, box,
angle (downhill to the right > 0), confidence, whether a balloon in
bubbles.json covers it, and the words -- so a slanted caption the chapter's
reading dropped shows up as "NOT READ" with its text. Emerson (2026-09-19):
"the detector works ok for text slanting upwards but not downwards".
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from panelforge import paths, store  # noqa: E402
from panelforge.detect import bubbles as Bu  # noqa: E402
from panelforge.detect import ocr  # noqa: E402
from panelforge.detect.strip import StripReader  # noqa: E402


def main() -> None:
    series, chapter = sys.argv[1], sys.argv[2]
    min_deg = float(sys.argv[3]) if len(sys.argv) > 3 else 8.0
    cdir = paths.chapter_dir(series, chapter)
    strip = store.read(cdir / "strip.json")
    bubbles = (store.read(cdir / "bubbles.json", {}) or {}).get("bubbles", [])
    reader = StripReader(cdir, strip)
    blocks = [
        b
        for b in Bu.find_candidates(reader)
        if len(b.lines) >= 2 and abs(b.angle) >= min_deg
    ]
    cands = Bu.attach_balloons(reader, blocks)
    Bu.ocr_candidates(reader, cands, ocr.engine())
    for c in cands:
        if not Bu.looks_like_text(c):
            continue  # art that looked like letters
        x0, top, w, h = c.box
        read = [
            bb["id"]
            for bb in bubbles
            if bb["box"][0] <= x0 + w / 2 <= bb["box"][0] + bb["box"][2]
            and bb["box"][1] <= top + h / 2 <= bb["box"][1] + bb["box"][3]
        ]
        print(
            f"y={top:>7} box=({x0},{top},{w},{h}) angle={c.angle:+.1f} "
            f"conf={c.conf:.2f} {'read as ' + ','.join(read) if read else 'NOT READ'}: "
            f"{c.raw[:60]!r}"
        )


if __name__ == "__main__":
    main()
