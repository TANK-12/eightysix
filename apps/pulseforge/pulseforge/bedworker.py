"""
Render one shot bed, as a standalone process.

Beds are completely independent -- a different background, its own ffmpeg, no
shared state -- so several can render at once and a mix over four backgrounds
finishes in roughly the time of one.

This is a subprocess rather than `multiprocessing` on purpose. The pool
approaches all have a catch here: `fork` from the web app's render thread is
the deadlock-prone one Python now warns about, and `spawn`/`forkserver` both
re-import `__main__`, which fails outright depending on how the parent was
started. A plain subprocess taking a JSON job file has none of those problems,
is trivially cancellable (kill it), and works identically from the app, a test
or a shell.

    python -m pulseforge.bedworker job.json

Only **loop** beds come through here. A live shot needs the audio analysis --
megabytes of numpy that would have to be serialised for no gain, since a live
shot is the length of the whole song and there is rarely more than one.
"""

import json
import sys

from .render import _render_bed
from .scenes import get_scene


def run_job(job):
    _meta, frame_fn = get_scene(job["scene_id"])
    _render_bed(
        frame_fn,
        job["shot"],
        job["params"],
        job["fmt"],
        {},  # loop beds never read the analysis
        job.get("art_pack"),
        job["settings"],
        job["tmpdir"],
        job["base_dir"],
        job["mask_dir"],
        job["path"],
        lambda _s: None,
        lambda _f: None,
        lambda: False,
    )
    return job["path"]


def main(argv):
    if len(argv) != 2:
        print("usage: python -m pulseforge.bedworker <job.json>", file=sys.stderr)
        return 2
    with open(argv[1], "r", encoding="utf-8") as f:
        run_job(json.load(f))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
