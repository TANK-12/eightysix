"""Renderer: timeline -> per-shot cached clips -> concatenated mp4 (+ mixed audio).

Every shot is rendered to its own clip in work/render/shots/<key>.mp4. The key
hashes everything that changes the pixels (the shot, the previous shot when a
transition blends into it, settings, style version, input files, output size,
encoder). A resumed or re-run render only renders shots whose key changed,
and a single-shot re-render from the editor fills the same cache.

Frames of a shot: style.render -> effects -> transition blend from the previous
shot (which keeps playing past its end) -> subtitles.
"""

import hashlib
import json
import multiprocessing
import os
import time
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from pathlib import Path

import numpy as np

from .. import styles, transitions
from . import bubbles, effects, encode
from .context import RenderContext
from .inputs import ChapterInputs
from .timeline import retime

RENDER_VERSION = 3


class Renderer:
    def __init__(self, ctx: RenderContext, tl: dict):
        self.ctx = ctx
        self.tl = retime(tl, ctx.fps)
        self.shots = self.tl["shots"]

    def body(self, i: int, t: float) -> np.ndarray:
        shot = self.shots[i]
        frame = styles.render_shot(self.ctx, shot, t)
        return effects.apply(self.ctx, shot, t, frame)

    def frame(self, i: int, t: float) -> np.ndarray:
        shot = self.shots[i]
        tr = shot.get("transition_in") or {}
        kind, tdur = tr.get("kind", "cut"), float(tr.get("dur", 0.0))
        frame = self.body(i, t)
        if kind != "cut" and tdur > 0 and t < tdur:
            if i > 0:
                prev = self.shots[i - 1]
                a = self.body(i - 1, float(prev["dur"]) + t)
            else:
                a = np.zeros_like(frame)
                a[..., 3] = 255
            info = transitions.TransitionInfo(
                direction=transitions.reading_direction(self.ctx.inp.reading),
                fps=self.ctx.fps,
            )
            frame = transitions.blend(kind, a, frame, t / tdur, info)
        if not frame.flags.writeable or not frame.flags.c_contiguous:
            frame = np.ascontiguousarray(frame)
        bubbles.draw_subtitles(self.ctx, shot, t, frame)
        return frame

    def n_frames(self, i: int) -> int:
        return max(1, int(round(float(self.shots[i]["dur"]) * self.ctx.fps)))

    def key(self, i: int, preview: bool) -> str:
        shot = self.shots[i]
        tr = shot.get("transition_in") or {}
        prev = self.shots[i - 1] if i > 0 and tr.get("kind", "cut") != "cut" else None
        st = styles.style_for(self.ctx, shot)
        prev_st = styles.style_for(self.ctx, prev) if prev else None
        audio_stamps = []
        for ln in shot.get("lines", []):
            line = self.ctx.inp.lines.get(ln.get("line_id")) or {}
            if line.get("audio"):
                f = self.ctx.chapter_dir / line["audio"]
                audio_stamps.append(f.stat().st_mtime_ns if f.exists() else 0)
        doc = {
            "v": RENDER_VERSION,
            "shot": _strip(shot),
            "prev": _strip(prev) if prev else None,
            "settings": {
                k: v
                for k, v in self.ctx.settings.items()
                if k not in ("transition", "mode")
            },
            "style": [
                st.name,
                st.version,
                prev_st.name if prev_st else None,
                prev_st.version if prev_st else None,
            ],
            "out": self.ctx.out,
            "fps": self.ctx.fps,
            "frames": self.n_frames(i),
            "enc": [encode.encoder_name(), preview],
            "inputs": self.ctx.inp.stamp(),
            "audio": audio_stamps,
            "panel": self.ctx.inp.by_id.get(shot["panel_id"], {}).get("box"),
        }
        return hashlib.sha1(
            json.dumps(doc, sort_keys=True, default=str).encode()
        ).hexdigest()[:20]

    def clip(self, i: int, preview=False, job=None, progress=None) -> tuple[Path, bool]:
        """Render shot i to its cached clip. Returns (path, was_cached)."""
        path = (
            self.ctx.chapter_dir
            / "work"
            / "render"
            / "shots"
            / f"{self.key(i, preview)}.mp4"
        )
        if path.exists():
            return path, True
        w = encode.FrameWriter(path, self.ctx.out, self.ctx.fps, preview=preview)
        n = self.n_frames(i)
        try:
            for fi in range(n):
                if job is not None and fi % 10 == 0:
                    job.check()
                w.write(self.frame(i, fi / self.ctx.fps))
                if progress and fi % 10 == 0:
                    progress(fi / n)
        except BaseException:
            w.abort()
            raise
        w.close()
        return path, False


def _strip(shot):
    if shot is None:
        return None
    return {k: v for k, v in shot.items() if k not in ("start", "edited", "notes")}


def mix_audio(chapter_dir: Path, tl: dict, out_wav: Path, log=None) -> Path | None:
    """Voices, SFX and music through the audio mixer, or None (silent video)."""
    try:
        from ..audio import mix  # type: ignore[attr-defined]
    except ImportError:
        if log:
            log("audio mixer not available yet: rendering silent video")
        return None
    try:
        out_wav.parent.mkdir(parents=True, exist_ok=True)
        got = mix.mix_timeline(chapter_dir, tl, out_wav)
        return Path(got) if got and Path(got).exists() else None
    except Exception as e:  # a failed mix must not lose the render
        if log:
            log(f"audio mix failed ({type(e).__name__}: {e}): rendering silent video")
        return None


def _die_with_parent() -> None:
    """Pool worker start-up: a watchdog thread ends the worker once its
    parent is gone. Six workers (2.8 GB) from a server killed at 02:50 were
    still alive at 16:50. (PR_SET_PDEATHSIG was tried first and is the
    wrong tool: it fires when the creating *thread* exits, and the pool
    spawns from a helper thread, so every worker died at once.)"""
    import threading

    parent = os.getppid()

    def watch():
        while True:
            time.sleep(2.0)
            if os.getppid() != parent:
                os._exit(0)

    threading.Thread(target=watch, daemon=True, name="parent-watch").start()


def render_workers(n_shots: int) -> int:
    """How many shot clips to draw at once.

    Drawing a frame is CPU work (warps and blends in OpenCV and numpy) and
    shots are independent clips, so they are spread over the cores; the GPU
    already does the encoding (h264_vaapi). Half the logical cores by default,
    because OpenCV threads inside each worker use the rest;
    `PANELFORGE_RENDER_WORKERS` overrides (1 = the old one-at-a-time path).
    """
    env = os.environ.get("PANELFORGE_RENDER_WORKERS")
    if env:
        return max(1, min(int(env), n_shots))
    return max(1, min(n_shots, (os.cpu_count() or 2) // 2))


_WORKER: dict = {}


def _worker_clip(chapter_dir: str, tl: dict, i: int, preview: bool, scale: float):
    """Render one shot in a worker process; the renderer is built once per
    process and kept (a job renders one chapter, so one key is enough)."""
    import cv2

    cv2.setNumThreads(2)
    key = (chapter_dir, id(tl), preview, scale)
    if _WORKER.get("key") != key:
        inp = ChapterInputs(Path(chapter_dir))
        ctx = RenderContext(inp, tl.get("settings") or {}, scale=scale)
        _WORKER["key"], _WORKER["r"] = key, Renderer(ctx, tl)
    path, cached = _WORKER["r"].clip(i, preview=preview)
    return i, str(path), cached


def _clips(chapter_dir, tl, idx, preview, scale, workers, r, job):
    """Yield (shot index, clip path, was_cached) in timeline order."""
    if workers <= 1:
        for n, i in enumerate(idx):

            def prog(frac, n=n):
                if job is not None:
                    job.progress((n + frac) / len(idx) * 0.95)

            path, cached = r.clip(i, preview=preview, job=job, progress=prog)
            yield i, path, cached
        return
    results: dict[int, tuple] = {}
    # spawned workers are direct children of this process (the default fork
    # server on Python 3.14 is a middleman that outlives a killed server),
    # so the death signal set in the initializer reaches them
    with ProcessPoolExecutor(
        max_workers=workers,
        mp_context=multiprocessing.get_context("spawn"),
        initializer=_die_with_parent,
    ) as pool:
        pending = {
            pool.submit(_worker_clip, str(chapter_dir), tl, i, preview, scale): i
            for i in idx
        }
        next_pos = 0
        try:
            while pending:
                done, _ = wait(pending, timeout=1.0, return_when=FIRST_COMPLETED)
                if job is not None:
                    job.check()  # a cancelled job stops handing out work
                for fut in done:
                    pending.pop(fut)
                    i, path, cached = fut.result()
                    results[i] = (Path(path), cached)
                while next_pos < len(idx) and idx[next_pos] in results:
                    i = idx[next_pos]
                    yield i, results[i][0], results[i][1]
                    next_pos += 1
        except BaseException:
            for fut in pending:
                fut.cancel()
            raise
        while next_pos < len(idx):
            i = idx[next_pos]
            yield i, results[i][0], results[i][1]
            next_pos += 1


def render_timeline(
    chapter_dir: Path,
    tl: dict,
    out: Path,
    *,
    scale: float = 1.0,
    preview: bool = False,
    audio: bool = True,
    job=None,
    shot_ids: list[str] | None = None,
    inputs: ChapterInputs | None = None,
) -> dict:
    """Render all (or some) shots and write out. Returns stats for the job result."""
    inp = inputs or ChapterInputs(chapter_dir)
    ctx = RenderContext(inp, tl.get("settings") or {}, scale=scale)
    r = Renderer(ctx, tl)
    idx = [i for i, s in enumerate(r.shots) if not shot_ids or s["id"] in shot_ids]
    if not idx:
        raise ValueError("no shots to render")
    t0 = time.time()
    clips, rendered, total_frames = [], 0, 0
    workers = render_workers(len(idx))
    if workers > 1 and job is not None:
        job.log(f"rendering on {workers} cores")
    for n, (i, path, cached) in enumerate(
        _clips(chapter_dir, tl, idx, preview, scale, workers, r, job)
    ):
        clips.append(path)
        if not cached:
            rendered += 1
            total_frames += r.n_frames(i)
        if job is not None:
            job.progress((n + 1) / len(idx) * 0.95)
            job.log(
                f"shot {r.shots[i]['id']} {'reused' if cached else 'rendered'} ({n + 1}/{len(idx)})"
            )
    render_s = time.time() - t0
    out = Path(out)
    video = out.with_name(out.stem + ".video.mp4")
    encode.concat(clips, video)
    wav = None
    if audio and (tl.get("settings") or {}).get("sound", "full") != "silent":
        sub = dict(r.tl)
        if shot_ids:
            sub = retime({**r.tl, "shots": [dict(r.shots[i]) for i in idx]}, ctx.fps)
        wav = mix_audio(
            chapter_dir,
            sub,
            chapter_dir / "work" / "render" / f"{out.stem}.wav",
            job.log if job else None,
        )
    if wav:
        encode.mux_audio(video, wav, out)
        video.unlink()
    else:
        video.replace(out)
    info = encode.probe(out)
    out_seconds = total_frames / ctx.fps
    return {
        "file": str(out),
        "shots": len(idx),
        "rendered": rendered,
        "reused": len(idx) - rendered,
        "render_seconds": round(render_s, 2),
        "seconds_per_output_second": (
            round(render_s / out_seconds, 3) if out_seconds else None
        ),
        "audio": bool(wav),
        "probe": info,
        "encoder": encode.encoder_name(),
    }
