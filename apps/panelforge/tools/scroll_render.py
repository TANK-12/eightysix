"""Render a chapter as a scroll-reader film without the server.

    .venv/bin/python tools/scroll_render.py <series> <chapter> <name> <seconds|0> <16:9|9:16>

0 seconds = the whole chapter. Writes chapters/<c>/renders/<name>.mp4.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from panelforge import paths
from panelforge.render.inputs import ChapterInputs
from panelforge.render import timeline as TL
from panelforge.render.renderer import render_timeline

if __name__ == "__main__":
    series, chapter, name, seconds, aspect = sys.argv[1:6]
    seconds = float(seconds)
    cdir = paths.chapter_dir(series, chapter)
    inp = ChapterInputs(cdir)
    tl = TL.build(
        inp,
        overrides={"mode": "scroll", "aspect": aspect, "height": 1080, "sound": "full"},
    )
    keep, acc = [], 0.0
    for s in tl["shots"]:
        if seconds and acc > seconds:
            break
        keep.append(s["id"])
        acc += s["dur"]
    sc = tl["shots"][0]["scroll"]
    print(
        len(keep),
        "shots,",
        round(acc),
        "s; window",
        sc["window_h"],
        "of strip",
        inp.strip["width"],
        "x",
        inp.strip["height"],
        "scale",
        sc["scale"],
        flush=True,
    )
    t = time.time()
    out = cdir / "renders" / f"{name}.mp4"
    res = render_timeline(cdir, tl, out, audio=True, inputs=inp, shot_ids=keep)
    print(f"{time.time()-t:.0f}s", res, out.stat().st_size // 1024, "KB")
