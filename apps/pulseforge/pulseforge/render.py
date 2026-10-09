"""
The render pipeline.

Frame-generator scenes: their generator yields (H, W, 3) uint8 frames at an
internal size (<= 1080p tall); those are piped to ffmpeg as rawvideo, which
scales to the chosen format with lanczos, muxes the song, normalises loudness
to the YouTube target and encodes h264 + AAC + faststart.

Montage scenes: `scene.build_edl(ctx)` returns an edit decision list; that
becomes one ffmpeg filter_complex (trim -> scale/crop -> concat) muxed with
the song.

`loop_*` formats render a short seamless bed once and repeat it under the full
audio in a second pass.

The **living** pipeline (`scenes/living.py`) extends that last idea to a whole
project. A shot's motion is loop-exact by construction, so only one loop of it
is ever rendered in numpy -- a bed of a few hundred frames -- and ffmpeg
repeats that bed for as long as the shot holds. An hour-long mix over four
backgrounds costs four short renders instead of a hundred thousand frames.
Shots are then cross-faded into one timeline and the joined playlist is muxed
underneath. A shot set to "live" opts out and renders every frame, which is
what you want when the picture should react to that moment in the song.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

import numpy as np

from . import analyze, beatfx, editstyles, formats, overlays, sequence, tracklist
from . import particles
from .config import QUALITY_HEIGHTS, ffmpeg_caps
from .ffrunner import FFJob, probe_media, video_encode_args
from .scenes import get_scene
from .scenes.registry import SceneContext


def _internal_size(fmt):
    ih = min(fmt["h"], QUALITY_HEIGHTS.get(fmt.get("_quality", "standard"), 720))
    iw = int(round(ih * fmt["w"] / fmt["h"] / 2) * 2)
    return iw, ih


def _fade_filters(fade_in, fade_out, duration, audio=False):
    """`fade`/`afade` pairs for the start and end of the whole video."""
    verb = "afade" if audio else "fade"
    out = []
    if fade_in and fade_in > 0.05:
        out.append(f"{verb}=t=in:st=0:d={float(fade_in):.3f}")
    if fade_out and fade_out > 0.05 and duration > fade_out:
        out.append(
            f"{verb}=t=out:st={duration - float(fade_out):.3f}:d={float(fade_out):.3f}"
        )
    return out


def _audio_filter(settings, loop=False):
    lufs = settings.get("loudness_lufs", -14.0)
    # loudnorm works internally at 192 kHz and leaves the stream there, which
    # ffmpeg then hands to AAC as 96 kHz -- more bitrate than the content needs
    # and not what YouTube wants. Put it back to 48 kHz on the way out.
    return f"loudnorm=I={lufs}:TP=-1.5:LRA=11,aresample=48000"


def _esc_text(s):
    """Escape a string for ffmpeg drawtext's text= value."""
    return (
        str(s)
        .replace("\\", "\\\\")
        .replace(":", r"\:")
        .replace("'", r"’")
        .replace("%", r"\%")
    )


_TEXT_SIZE = {"s": 0.030, "m": 0.045, "l": 0.065}
_TEXT_POS = {
    "bottom-left": ("w*0.05", "h*0.86-line_h*L"),
    "bottom-center": ("(w-text_w)/2", "h*0.86-line_h*L"),
    "top-left": ("w*0.05", "h*0.08+line_h*L"),
    "center": ("(w-text_w)/2", "(h-text_h)/2+line_h*L"),
}


def text_overlay_filter(project, out_w, out_h):
    """Build a drawtext chain (or '') from the project's text-overlay fields.
    Two lines, a soft shadow, fading in over the first 1.5s."""
    title = (project.data.get("title_text") or "").strip()
    sub = (project.data.get("subtitle_text") or "").strip()
    if not title and not sub:
        return ""
    size_frac = _TEXT_SIZE.get(project.data.get("text_size", "m"), 0.045)
    px = _TEXT_POS.get(
        project.data.get("text_position", "bottom-left"), _TEXT_POS["bottom-left"]
    )
    fs = max(14, int(out_h * size_frac))
    parts = []
    for lineno, txt in enumerate((title, sub)):
        if not txt:
            continue
        this_fs = fs if lineno == 0 else int(fs * 0.6)
        x = px[0]
        y = px[1].replace("line_h", str(int(fs * 1.35))).replace("L", str(lineno))
        parts.append(
            f"drawtext=text='{_esc_text(txt)}':fontcolor=white:fontsize={this_fs}"
            f":x={x}:y={y}:shadowcolor=black@0.6:shadowx=2:shadowy=2"
            f":alpha='if(lt(t,1.5),t/1.5,1)'"
        )
    return ",".join(parts)


def _fit_expr(fmt, fit):
    w, h = fmt["w"], fmt["h"]
    if fit == "contain":
        return (
            f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1"
        )
    return (
        f"scale={w}:{h}:force_original_aspect_ratio=increase," f"crop={w}:{h},setsar=1"
    )


# --------------------------------------------------------------------------
# public entry
# --------------------------------------------------------------------------
def render(
    project,
    scene_id,
    params,
    fmt_id,
    out_path,
    settings,
    feat=None,
    art_pack=None,
    log=None,
    progress=None,
    should_stop=None,
    preview=False,
):
    log = log or (lambda s: None)
    progress = progress or (lambda f: None)
    should_stop = should_stop or (lambda: False)
    ff = ffmpeg_caps()
    if not ff["ffmpeg"]:
        raise RuntimeError("ffmpeg not found on PATH")

    meta, frame_fn = get_scene(scene_id)
    pipeline = str(meta.get("pipeline") or "")
    fmt = dict(formats.get(fmt_id))
    fps = fmt["fps"]
    fmt["_quality"] = "draft" if preview else settings.get("render_quality", "standard")

    # fill any param the user never set from the scene's own schema default
    merged = {p["key"]: p["default"] for p in meta.get("params", [])}
    merged.update({k: v for k, v in (params or {}).items() if v is not None})
    params = merged

    # scenes read attached images / clip folders from ctx.assets, carried in
    # params["_assets"]; source it from the project unless the caller set it
    if not params.get("_assets"):
        try:
            params["_assets"] = project.resolved_assets()
        except Exception:
            params["_assets"] = []

    tmp_audio_dir = tempfile.mkdtemp(prefix="pulseforge-audio-")
    spans = []
    if pipeline == "living":
        songs = project.playlist_paths()
        if not songs:
            raise RuntimeError("this project has no songs yet")
        gap = project.data.get("song_gap", 0.0)
        xfade = project.data.get("song_crossfade", 0.0)
        audio_path, spans, duration = sequence.build_audio(
            songs,
            os.path.join(tmp_audio_dir, "playlist.flac"),
            gap=gap,
            crossfade=xfade,
            log=log,
            gains=project.data.get("song_gain"),
        )
        if not preview:
            one_pass = duration
            _paths, passes = sequence.expand_for_target(
                songs,
                sequence.song_durations(songs),
                gap,
                xfade,
                project.data.get("target_seconds"),
            )
            audio_path, duration = sequence.repeat_audio(
                audio_path,
                os.path.join(tmp_audio_dir, "repeated.flac"),
                passes,
                one_pass,
                log=log,
            )
            spans = sequence.repeat_spans(spans, passes, one_pass)
            amb = project.data.get("ambience") or {}
            if amb.get("bed"):
                audio_path = sequence.mix_ambience(
                    audio_path,
                    os.path.join(tmp_audio_dir, "mixed.flac"),
                    amb.get("bed"),
                    amb.get("level", 0.25),
                    log=log,
                )
    else:
        audio_path = project.audio_path()
        if not audio_path or not os.path.exists(audio_path):
            raise RuntimeError("this project has no audio yet")
        duration = probe_media(audio_path)["duration"]
    if preview:
        duration = min(duration, float(settings.get("preview_seconds", 8)))
        fmt["h"] = int(settings.get("preview_height", 480))
        fmt["w"] = int(
            round(fmt["h"] * formats.get(fmt_id)["w"] / formats.get(fmt_id)["h"] / 2)
            * 2
        )
        fmt.pop("loop", None)
    if duration <= 0:
        raise RuntimeError("could not read the audio duration")

    text_vf = text_overlay_filter(project, fmt["w"], fmt["h"])
    if pipeline == "living" and not preview:
        cards = project.data.get("cards") or []
        if any((c or {}).get("title") or (c or {}).get("subtitle") for c in cards):
            # per-song captions replace the single project-wide title
            text_vf = sequence.text_filter(
                cards,
                spans,
                fmt["w"],
                fmt["h"],
                project.data.get("text_position", "bottom-left"),
                project.data.get("text_size", "m"),
            )
        overlay_vf = overlays.build(
            project.data.get("overlay"),
            spans,
            cards,
            [os.path.basename(x) for x in project.playlist_paths()],
            duration,
            fmt["h"],
        )
        if overlay_vf:
            text_vf = f"{text_vf},{overlay_vf}" if text_vf else overlay_vf
    tmpdir = tempfile.mkdtemp(prefix="pulseforge-")
    try:
        if feat is None:
            log("analysing audio…")
            feat = analyze.analyze(
                audio_path,
                fps,
                duration=duration,
                progress=lambda f: progress(f * 0.15),
            )
        n_frames = int(round(duration * fps))

        common = dict(
            fmt=fmt,
            audio_path=audio_path,
            duration=duration,
            feat=feat,
            art_pack=art_pack,
            out_path=out_path,
            settings=settings,
            tmpdir=tmpdir,
            text_vf=text_vf,
            log=log,
            progress=progress,
            should_stop=should_stop,
        )
        if meta.get("family") == "amv":
            _render_amv(scene_id=scene_id, params=params, **common)
        elif meta.get("family") == "montage":
            _render_montage(scene_id=scene_id, params=params, **common)
        elif pipeline == "living":
            _render_living(
                frame_fn=frame_fn,
                scene_id=scene_id,
                params=params,
                project=project,
                spans=spans,
                preview=preview,
                **common,
            )
        elif fmt.get("loop"):
            _render_loop(frame_fn=frame_fn, params=params, n_frames=n_frames, **common)
        else:
            _render_frames(
                frame_fn=frame_fn, params=params, n_frames=n_frames, **common
            )
        return {
            "out": out_path,
            "duration": duration,
            "size_bytes": os.path.getsize(out_path) if os.path.exists(out_path) else 0,
        }
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
        shutil.rmtree(tmp_audio_dir, ignore_errors=True)


# --------------------------------------------------------------------------
# frame-generator path
# --------------------------------------------------------------------------
def _feed(frame_fn, ctx, should_stop):
    expected = ctx.w * ctx.h * 3
    for idx, fr in enumerate(particles.wrap(frame_fn)(ctx)):
        if should_stop():
            break
        a = np.ascontiguousarray(fr, dtype=np.uint8)
        if a.shape != (ctx.h, ctx.w, 3):
            a = np.zeros((ctx.h, ctx.w, 3), dtype=np.uint8)
        b = a.tobytes()
        if len(b) != expected:
            b = b[:expected].ljust(expected, b"\x00")
        yield b
        if idx + 1 >= ctx.n_frames:
            break


def _encode_from_pipe(
    frames_iter,
    iw,
    ih,
    fmt,
    audio_path,
    duration,
    out_path,
    settings,
    text_vf,
    log,
    progress,
    video_only=False,
    prog_lo=0.15,
    prog_hi=0.95,
):
    ff = ffmpeg_caps()["ffmpeg"]
    pre, vc = video_encode_args(settings)
    vf = f"scale={fmt['w']}:{fmt['h']}:flags=lanczos"
    if text_vf and not video_only:
        vf += "," + text_vf
    if settings.get("encoder") == "vaapi":
        vf += ",format=nv12,hwupload"
    else:
        vf += ",format=yuv420p"
    cmd = [
        ff,
        "-y",
        *pre,
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{iw}x{ih}",
        "-r",
        str(fmt["fps"]),
        "-i",
        "pipe:0",
    ]
    if not video_only:
        cmd += ["-i", str(audio_path)]
    cmd += ["-map", "0:v:0"]
    if not video_only:
        cmd += [
            "-map",
            "1:a:0",
            "-af",
            _audio_filter(settings),
            "-c:a",
            "aac",
            "-b:a",
            settings.get("audio_bitrate", "256k"),
        ]
    cmd += [
        "-vf",
        vf,
        *vc,
        "-r",
        str(fmt["fps"]),
        "-t",
        f"{duration:.3f}",
        "-movflags",
        "+faststart",
        str(out_path),
    ]
    job = FFJob(
        cmd,
        duration=duration,
        on_line=log,
        on_progress=lambda f: progress(prog_lo + (prog_hi - prog_lo) * f),
    )
    rc = job.run(stdin_bytes_iter=frames_iter)
    if rc != 0:
        raise RuntimeError(f"ffmpeg exited {rc}")


def _make_ctx(fmt, n_frames, duration, feat, params, art_pack, tmpdir):
    iw, ih = _internal_size(fmt)
    fast = fmt.get("_quality", "standard") != "high"
    ctx = SceneContext(
        iw,
        ih,
        fmt["fps"],
        n_frames,
        duration,
        feat,
        params,
        params.get("_assets", []),
        art_pack,
        tmpdir,
        fast=fast,
    )
    return ctx, iw, ih


def _render_frames(
    frame_fn,
    params,
    fmt,
    audio_path,
    duration,
    feat,
    art_pack,
    n_frames,
    out_path,
    settings,
    tmpdir,
    text_vf,
    log,
    progress,
    should_stop,
):
    ctx, iw, ih = _make_ctx(fmt, n_frames, duration, feat, params, art_pack, tmpdir)
    log(
        f"rendering {n_frames} frames at {iw}x{ih} -> {fmt['w']}x{fmt['h']}"
        f" ({fmt.get('_quality')})…"
    )
    it = _feed(frame_fn, ctx, should_stop)
    _encode_from_pipe(
        it,
        iw,
        ih,
        fmt,
        audio_path,
        duration,
        out_path,
        settings,
        text_vf,
        log,
        progress,
    )
    if should_stop():
        raise RuntimeError("render stopped")


def _render_loop(
    frame_fn,
    params,
    fmt,
    audio_path,
    duration,
    feat,
    art_pack,
    n_frames,
    out_path,
    settings,
    tmpdir,
    text_vf,
    log,
    progress,
    should_stop,
):
    loop_secs = min(fmt.get("loop_seconds", 40), duration)
    loop_frames = int(round(loop_secs * fmt["fps"]))
    ctx, iw, ih = _make_ctx(fmt, loop_frames, loop_secs, feat, params, art_pack, tmpdir)
    bed = os.path.join(tmpdir, "bed.mp4")
    log(f"rendering a {loop_secs:.0f}s seamless bed…")
    it = _feed(frame_fn, ctx, should_stop)
    _encode_from_pipe(
        it,
        iw,
        ih,
        fmt,
        audio_path,
        loop_secs,
        bed,
        settings,
        text_vf,
        log,
        progress,
        video_only=True,
        prog_lo=0.15,
        prog_hi=0.55,
    )
    if should_stop():
        raise RuntimeError("render stopped")
    ff = ffmpeg_caps()["ffmpeg"]
    pre, vc = video_encode_args(settings)
    vf = text_vf + ",format=yuv420p" if text_vf else "format=yuv420p"
    cmd = [
        ff,
        "-y",
        *pre,
        "-stream_loop",
        "-1",
        "-i",
        bed,
        "-i",
        str(audio_path),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-shortest",
        "-af",
        _audio_filter(settings),
        "-c:a",
        "aac",
        "-b:a",
        settings.get("audio_bitrate", "256k"),
        "-vf",
        vf,
        *vc,
        "-t",
        f"{duration:.3f}",
        "-movflags",
        "+faststart",
        str(out_path),
    ]
    job = FFJob(
        cmd,
        duration=duration,
        on_line=log,
        on_progress=lambda f: progress(0.55 + 0.4 * f),
    )
    if job.run() != 0:
        raise RuntimeError("ffmpeg loop pass failed")


# --------------------------------------------------------------------------
# montage path
# --------------------------------------------------------------------------
_XFADE = {"crossfade": "dissolve", "dip_black": "fadeblack", "dip_white": "fadewhite"}


# --------------------------------------------------------------------------
# living path -- shot beds repeated and cross-faded along the playlist
# --------------------------------------------------------------------------
def _shot_key(shot):
    """Identity of a shot's *look*, ignoring where it sits on the timeline.

    Shots cycle when there are fewer backgrounds than songs, so the same
    picture usually comes round several times. Hashing what it looks like means
    its bed gets rendered once and reused."""
    import json

    ignore = {"index", "start", "duration", "hold", "transition", "transition_s"}
    return json.dumps(
        {k: v for k, v in shot.items() if k not in ignore}, sort_keys=True, default=str
    )


def _slice_features(feat, start_frame, n):
    """The stretch of the analysis a live shot sits over."""
    out = {}
    for k, arr in (feat or {}).items():
        try:
            seg = arr[start_frame : start_frame + n]
            out[k] = seg if len(seg) else arr[-1:]
        except Exception:
            out[k] = arr
    return out


def _render_bed(
    frame_fn,
    shot,
    params,
    fmt,
    feat,
    art_pack,
    settings,
    tmpdir,
    base_dir,
    mask_dir,
    path,
    log,
    progress,
    should_stop,
):
    live = str(shot.get("mode", "loop")) == "live"
    span = float(shot["duration"]) if live else float(shot["loop_seconds"])
    span = max(0.5, span)
    n = max(1, int(round(span * fmt["fps"])))

    p = dict(params)
    p["_shot"] = shot
    p["_base_dir"] = str(base_dir)
    p["_mask_dir"] = str(mask_dir)
    use_feat = feat
    if live:
        use_feat = _slice_features(feat, int(shot["start"] * fmt["fps"]), n)
    ctx, iw, ih = _make_ctx(fmt, n, span, use_feat, p, art_pack, tmpdir)

    kind = "segment" if live else "loop bed"
    log(f"  {kind}: {n} frames at {iw}x{ih} ({span:.1f}s)…")
    bed_settings = dict(settings)
    # the bed is re-encoded during assembly, so keep it well above final quality
    bed_settings["crf"] = max(12, int(settings.get("crf", 18)) - 4)
    _encode_from_pipe(
        _feed(frame_fn, ctx, should_stop),
        iw,
        ih,
        fmt,
        None,
        span,
        path,
        bed_settings,
        "",
        log,
        progress,
        video_only=True,
        prog_lo=0.0,
        prog_hi=1.0,
    )
    return path


def _render_beds_in_parallel(jobs, workers, tmpdir, log, progress, should_stop):
    """Render several beds at once, each in its own process.

    Returns True if it saw the job through, False if it could not -- and the
    caller then falls back to the sequential path, so this can only make a
    render faster or leave it unchanged. See `bedworker.py` for why these are
    subprocesses rather than a multiprocessing pool.
    """
    procs = []
    try:
        for n, job in enumerate(jobs):
            spec = os.path.join(tmpdir, f"job{n}.json")
            with open(spec, "w", encoding="utf-8") as f:
                json.dump(job, f)
            procs.append((job, spec))
    except (TypeError, ValueError) as e:
        log(f"  could not hand these beds to workers ({e}); doing them in order")
        return False

    running = []
    queued = list(procs)
    done = 0
    total = len(procs)
    try:
        while queued or running:
            while queued and len(running) < workers:
                _job, spec = queued.pop(0)
                running.append(
                    subprocess.Popen(
                        [sys.executable, "-m", "pulseforge.bedworker", spec],
                        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.PIPE,
                    )
                )
            still = []
            for proc in running:
                rc = proc.poll()
                if rc is None:
                    still.append(proc)
                    continue
                if rc != 0:
                    err = (
                        (proc.stderr.read() or b"").decode()[-400:]
                        if proc.stderr
                        else ""
                    )
                    raise RuntimeError(f"a bed worker failed: {err}")
                done += 1
                log(f"  bed {done} of {total} done")
                progress(done / total)
            running = still
            if should_stop():
                for proc in running:
                    proc.kill()
                raise RuntimeError("render stopped")
            if running:
                time.sleep(0.2)
    except RuntimeError:
        for proc in running:
            proc.kill()
        raise
    except Exception as e:
        for proc in running:
            proc.kill()
        log(f"  parallel rendering unavailable ({e}); doing them in order")
        return False

    missing = [j["path"] for j, _ in procs if not os.path.exists(j["path"])]
    if missing:
        log("  a worker produced nothing; doing them in order")
        return False
    return True


def _card_text(plan, out_h):
    """Big centred titles for any shot marked as a card, over its own window."""
    parts = []
    for shot in plan:
        if str(shot.get("kind", "")) != "card":
            continue
        title = overlays.escape(shot.get("card_title", ""))
        sub = overlays.escape(shot.get("card_subtitle", ""))
        if not title and not sub:
            continue
        t0 = float(shot["start"])
        t1 = t0 + float(shot["duration"])
        fade = min(1.2, max(0.3, (t1 - t0) * 0.2))
        alpha = (
            f"if(lt(t-{t0:.2f},{fade:.2f}),(t-{t0:.2f})/{fade:.2f},"
            f"if(gt(t-{t0:.2f},{t1 - t0 - fade:.2f}),"
            f"({t1 - t0:.2f}-(t-{t0:.2f}))/{fade:.2f},1))"
        )
        win = f"between(t,{t0:.2f},{t1:.2f})"
        big = max(20, int(out_h * 0.075))
        small = max(14, int(big * 0.45))
        if title:
            parts.append(
                f"drawtext=text='{title}':fontcolor=white:fontsize={big}"
                f":x=(w-tw)/2:y=(h-th)/2-{small if sub else 0}:enable='{win}'"
                f":alpha='{alpha}':shadowcolor=black@0.5:shadowx=2:shadowy=3"
            )
        if sub:
            parts.append(
                f"drawtext=text='{sub}':fontcolor=white@0.8:fontsize={small}"
                f":x=(w-tw)/2:y=(h-th)/2+{big - small}:enable='{win}'"
                f":alpha='{alpha}':shadowcolor=black@0.5:shadowx=2:shadowy=2"
            )
    return ",".join(parts)


def _render_living(
    frame_fn,
    scene_id,
    params,
    project,
    spans,
    preview,
    fmt,
    audio_path,
    duration,
    feat,
    art_pack,
    out_path,
    settings,
    tmpdir,
    text_vf,
    log,
    progress,
    should_stop,
):
    default_loop = float(settings.get("shot_loop_seconds", 12.0))
    plan = sequence.plan_shots(
        project.data.get("shots"), spans, duration, default_loop=default_loop
    )
    if preview:
        plan = plan[:1]
        plan[0]["duration"] = duration
        plan[0]["loop_seconds"] = min(plan[0]["loop_seconds"], duration)
    if not plan:
        raise RuntimeError("nothing to render -- add a background in the Scenery tab")

    base_dir = project.assets_dir()
    mask_dir = project.masks_dir()
    log(f"{len(plan)} shot(s) over {duration / 60:.1f} minutes")

    # Title cards are drawn in the assembly pass, not baked into their bed: the
    # bed is a few seconds repeated, so anything tied to a moment in the video
    # has to be a filter with an `enable` window instead.
    card_vf = _card_text(plan, fmt["h"])
    if card_vf and not preview:
        text_vf = f"{text_vf},{card_vf}" if text_vf else card_vf

    # one bed per distinct look, however many times it comes round
    beds = {}
    todo = []
    for k, shot in enumerate(plan):
        live = str(shot.get("mode", "loop")) == "live"
        key = _shot_key(shot) if not live else f"live-{k}"
        shot["_live"] = live
        if key in beds:
            shot["_bed"] = beds[key]
            continue
        path = os.path.join(tmpdir, f"bed{len(beds)}.mp4")
        beds[key] = path
        shot["_bed"] = path
        todo.append({"shot": dict(shot), "path": path, "live": live})

    parallelisable = [j for j in todo if not j["live"]]
    workers = max(1, int(settings.get("render_workers", 3) or 1))
    workers = min(workers, len(parallelisable))
    log(
        f"{len(todo)} bed(s) to render"
        + (f", {workers} at a time" if workers > 1 else "")
    )

    ran_parallel = False
    if workers > 1:
        # each bed gets a share of the cores rather than all of them
        share = dict(settings)
        share["threads"] = max(1, (os.cpu_count() or 4) // workers)
        jobs = [
            {
                **j,
                "scene_id": scene_id,
                "params": params,
                "fmt": fmt,
                # no `feat`: a loop bed never reads the analysis, and megabytes
                # of numpy would not survive the trip to a worker anyway
                "art_pack": art_pack,
                "settings": share,
                "tmpdir": tmpdir,
                "base_dir": str(base_dir),
                "mask_dir": str(mask_dir),
            }
            for j in parallelisable
        ]
        for job in jobs:
            job.pop("live", None)
        ran_parallel = _render_beds_in_parallel(
            jobs,
            workers,
            tmpdir,
            log,
            lambda f: progress(0.15 + 0.60 * f),
            should_stop,
        )

    remaining = todo if not ran_parallel else [j for j in todo if j["live"]]
    if remaining:
        for n, j in enumerate(remaining):
            if should_stop():
                raise RuntimeError("render stopped")
            lo = 0.15 + 0.60 * (n / max(1, len(remaining)))
            hi = 0.15 + 0.60 * ((n + 1) / max(1, len(remaining)))
            _render_bed(
                frame_fn,
                j["shot"],
                params,
                fmt,
                feat,
                art_pack,
                settings,
                tmpdir,
                base_dir,
                mask_dir,
                j["path"],
                log,
                lambda f, lo=lo, hi=hi: progress(lo + (hi - lo) * f),
                should_stop,
            )

    if should_stop():
        raise RuntimeError("render stopped")

    # the tracklist: chapter marks inside the file, and the description to paste
    meta_path = None
    if not preview and spans:
        built = tracklist.build(
            spans,
            project.data.get("cards") or [],
            [os.path.basename(s) for s in project.playlist_paths()],
            duration,
        )
        meta_path = os.path.join(tmpdir, "chapters.txt")
        with open(meta_path, "w", encoding="utf-8") as f:
            f.write(built["ffmetadata"])
        try:
            desc = os.path.splitext(str(out_path))[0] + ".txt"
            with open(desc, "w", encoding="utf-8") as f:
                f.write(built["description"])
            log(f"tracklist written to {os.path.basename(desc)}")
        except OSError:
            pass
        for w in built["warnings"]:
            log(f"note: {w}")

    log("assembling the timeline…")
    progress(0.76)
    _assemble_living(
        plan,
        fmt,
        audio_path,
        duration,
        out_path,
        settings,
        text_vf,
        log,
        progress,
        meta_path,
        progress_bar=overlays.wants_progress(project.data.get("overlay")),
        bar_opacity=(project.data.get("overlay") or {}).get("opacity", 0.8),
        fade_in=project.data.get("fade_in", 0.0),
        fade_out=project.data.get("fade_out", 0.0),
    )


def _assemble_living(
    plan,
    fmt,
    audio_path,
    duration,
    out_path,
    settings,
    text_vf,
    log,
    progress,
    meta_path=None,
    progress_bar=False,
    bar_opacity=0.8,
    fade_in=0.0,
    fade_out=0.0,
):
    """Repeat each bed for as long as its shot holds, cross-fade between them,
    caption it and mux the playlist underneath -- one ffmpeg pass."""
    ff = ffmpeg_caps()["ffmpeg"]
    inputs = []
    parts = []
    for k, shot in enumerate(plan):
        nxt = plan[k + 1] if k + 1 < len(plan) else None
        pad = 0.0
        if nxt is not None and sequence.TRANSITIONS.get(nxt.get("transition")):
            pad = float(nxt.get("transition_s", 0.0) or 0.0)
        if shot.get("_live"):
            inputs += ["-i", shot["_bed"]]
        else:
            inputs += ["-stream_loop", "-1", "-i", shot["_bed"]]
        parts.append(
            f"[{k}:v]trim=0:{shot['duration'] + pad:.3f},setpts=PTS-STARTPTS,"
            f"fps={fmt['fps']},format=yuv420p[v{k}]"
        )

    chain = list(parts)
    if len(plan) > 1:
        prev = "v0"
        for k in range(1, len(plan)):
            xf = sequence.TRANSITIONS.get(plan[k].get("transition")) or "fade"
            td = max(0.05, float(plan[k].get("transition_s", 1.5) or 0.05))
            # Each transition sits at the shot's own place on the timeline.
            # Accumulating `previous duration - transition` instead makes the
            # shots overlap, so the video comes out shorter than the audio by
            # the total of every transition -- the picture froze on the last
            # shot while the music kept going, and anything timed off the end
            # (a fade-out) never fired.
            offset = max(0.0, float(plan[k]["start"]))
            label = "vcat" if k == len(plan) - 1 else f"x{k}"
            chain.append(
                f"[{prev}][v{k}]xfade=transition={xf}:duration={td:.3f}"
                f":offset={offset:.3f}[{label}]"
            )
            prev = label
        last = "vcat"
    else:
        chain.append("[v0]null[vcat]")
        last = "vcat"

    video_fades = _fade_filters(fade_in, fade_out, duration)
    tail = ",".join([f for f in [text_vf] if f] + video_fades)
    if tail:
        chain.append(f"[{last}]{tail}[vout]")
        last = "vout"

    pre, vc = video_encode_args(settings)
    cmd = [ff, "-y", *pre, *inputs, "-i", str(audio_path)]
    audio_index = len(plan)
    meta_index = audio_index
    next_index = audio_index + 1
    if meta_path:
        cmd += ["-i", str(meta_path)]
        meta_index = next_index
        next_index += 1
    if progress_bar:
        cmd += overlays.progress_input(fmt["w"], fmt["h"])
        chain.append(
            overlays.progress_overlay(
                duration, fmt["w"], last, next_index, "vbar", bar_opacity
            )
        )
        last = "vbar"
        next_index += 1
    cmd += [
        "-filter_complex",
        ";".join(chain),
        "-map",
        f"[{last}]",
        "-map",
        f"{audio_index}:a:0",
    ]
    audio_chain = ",".join(
        [_audio_filter(settings)]
        + _fade_filters(fade_in, fade_out, duration, audio=True)
    )
    if meta_path:
        # the chapter marks come from the metadata input, not the beds
        cmd += ["-map_metadata", str(meta_index)]
    cmd += [
        "-af",
        audio_chain,
        "-c:a",
        "aac",
        "-b:a",
        settings.get("audio_bitrate", "256k"),
        *vc,
        "-r",
        str(fmt["fps"]),
        "-t",
        f"{duration:.3f}",
        "-movflags",
        "+faststart",
        str(out_path),
    ]
    job = FFJob(
        cmd,
        duration=duration,
        on_line=log,
        on_progress=lambda f: progress(0.76 + 0.22 * f),
    )
    if job.run() != 0:
        raise RuntimeError("ffmpeg could not assemble the timeline")


def _render_montage(
    scene_id,
    params,
    fmt,
    audio_path,
    duration,
    feat,
    art_pack,
    out_path,
    settings,
    tmpdir,
    text_vf,
    log,
    progress,
    should_stop,
):
    mod = __import__("pulseforge.scenes." + scene_id, fromlist=["build_edl"])
    ctx = SceneContext(
        fmt["w"],
        fmt["h"],
        fmt["fps"],
        int(duration * fmt["fps"]),
        duration,
        feat,
        params,
        params.get("_assets", []),
        art_pack,
        tmpdir,
    )
    log("planning cuts…")
    edl = mod.build_edl(ctx)
    if not edl:
        raise RuntimeError("no clips found — attach a folder of video files first")
    log(f"{len(edl)} shots; assembling…")
    progress(0.2)

    ff = ffmpeg_caps()["ffmpeg"]
    transition = params.get("transition", "cut")
    xf = _XFADE.get(transition)
    tdur = max(0.05, float(params.get("transition_ms", 250)) / 1000.0)

    inputs, parts = [], []
    for k, shot in enumerate(edl):
        pad = tdur if xf else 0.0
        inputs += [
            "-ss",
            f"{shot['start']:.3f}",
            "-t",
            f"{shot['dur'] + pad:.3f}",
            "-i",
            shot["path"],
        ]
        parts.append(
            f"[{k}:v]{_fit_expr(fmt, shot.get('fit', 'cover'))},"
            f"fps={fmt['fps']},format=yuv420p,setpts=PTS-STARTPTS[v{k}]"
        )

    if xf and len(edl) > 1:
        chain = parts[:]
        prev = "v0"
        offset = 0.0
        for k in range(1, len(edl)):
            offset += edl[k - 1]["dur"] - tdur
            out_lbl = f"x{k}" if k < len(edl) - 1 else "vcat"
            chain.append(
                f"[{prev}][v{k}]xfade=transition={xf}:duration={tdur:.3f}"
                f":offset={max(0.0, offset):.3f}[{out_lbl}]"
            )
            prev = out_lbl
        body = ";".join(chain)
        last = "vcat"
    else:
        body = ";".join(parts) + ";" + "".join(f"[v{k}]" for k in range(len(edl)))
        body += f"concat=n={len(edl)}:v=1:a=0[vcat]"
        last = "vcat"

    if text_vf:
        body += f";[{last}]{text_vf}[vout]"
        last = "vout"
    fc = body

    pre, vc = video_encode_args(settings)
    cmd = [
        ff,
        "-y",
        *pre,
        *inputs,
        "-i",
        str(audio_path),
        "-filter_complex",
        fc,
        "-map",
        f"[{last}]",
        "-map",
        f"{len(edl)}:a:0",
        "-af",
        _audio_filter(settings),
        "-c:a",
        "aac",
        "-b:a",
        settings.get("audio_bitrate", "256k"),
        *vc,
        "-t",
        f"{duration:.3f}",
        "-movflags",
        "+faststart",
        str(out_path),
    ]
    job = FFJob(
        cmd,
        duration=duration,
        on_line=log,
        on_progress=lambda f: progress(0.2 + 0.75 * f),
    )
    if job.run() != 0:
        raise RuntimeError("ffmpeg montage assembly failed")


# --------------------------------------------------------------------------
# AMV path -- a planned edit, per-shot effects, per-cut transitions
# --------------------------------------------------------------------------
AMV_CHUNK = 40  # shots per ffmpeg pass; each shot is one open input


def _letterbox_crop(lb):
    """A crop filter for the black bars a clip carries, or "" for none."""
    if not lb:
        return ""
    t, b = float(lb.get("top", 0)), float(lb.get("bottom", 0))
    l, r = float(lb.get("left", 0)), float(lb.get("right", 0))
    if max(t, b, l, r) < 0.005:
        return ""
    return (
        f"crop=w='iw*{max(0.05, 1 - l - r):.4f}':h='ih*{max(0.05, 1 - t - b):.4f}'"
        f":x='iw*{l:.4f}':y='ih*{t:.4f}'"
    )


def _amv_shot_chain(idx, shot, fmt, label):
    """The filter chain for one shot: crop the bars off, set the speed, fit it
    to the format, then run its beat effects."""
    parts = []
    crop = _letterbox_crop(shot.get("letterbox"))
    if crop:
        parts.append(crop)
    parts.append("setpts=PTS-STARTPTS")
    speed = float(shot.get("speed", 1.0) or 1.0)
    if abs(speed - 1.0) > 0.01 and speed > 0.05:
        # `speed` is how much source is consumed per second of output, so 0.55
        # means slow motion. Timestamps are stretched by its reciprocal and the
        # frame rate is regenerated afterwards.
        parts.append(f"setpts=PTS*{1.0 / speed:.5f}")
    parts.append(_fit_expr(fmt, shot.get("fit", "cover")))
    parts.append(f"fps={fmt['fps']}")
    # Guarantee the stream is at least as long as the timeline expects. An
    # `xfade` whose offset falls past the end of its left input silently stops
    # the whole chain there, so a single shot longer than the footage behind it
    # truncates the entire video -- which is how a 28-shot edit came out six
    # seconds long. Holding the last frame is a visible flaw; ending the video
    # is not even that.
    parts.append(
        f"tpad=stop_mode=clone:stop_duration={max(0.5, float(shot['dur'])):.3f}"
    )
    chain = beatfx.build_chain(
        shot.get("fx"),
        {"w": fmt["w"], "h": fmt["h"], "fps": fmt["fps"], "dur": float(shot["dur"])},
    )
    if chain:
        parts.append(chain)
    parts.append("format=yuv420p")
    parts.append("setsar=1")
    return f"[{idx}:v]" + ",".join(parts) + f"[{label}]"


def _amv_chunks(shots, size=AMV_CHUNK):
    """Split the edit into runs small enough for one ffmpeg pass.

    A chunk boundary is only ever placed at a hard cut, so no transition is
    ever split across two passes -- the joins that need both shots present
    always have them."""
    out, cur = [], []
    for sh in shots:
        if cur and len(cur) >= size and int(sh.get("transition_ms", 0)) <= 0:
            out.append(cur)
            cur = []
        cur.append(sh)
    if cur:
        out.append(cur)
    # A chunk that grew past the limit because nothing was a cut is still
    # correct, just slower; splitting it would break a transition.
    return out


def _amv_chunk_graph(chunk, fmt):
    """(inputs, filter_complex body, final label, chunk duration).

    Every join is an `xfade`, including the hard cuts, which use a single
    frame. Mixing `concat` for the cuts with `xfade` for the rest means two
    incompatible ways of counting time in one graph, and that is precisely
    where the transition-offset bug of v6 came from. One rule, applied
    everywhere, with **absolute** offsets read off each shot's own place on the
    timeline rather than accumulated -- an accumulated offset is wrong by the
    total of every transition before it."""
    fps = float(fmt["fps"])
    frame = 1.0 / fps
    n = len(chunk)
    base = float(chunk[0]["at"])
    durs = [float(sh["dur"]) for sh in chunk]
    # transition INTO shot k; the first shot of a chunk is always a hard cut
    tds = [0.0] + [
        max(frame, float(chunk[k].get("transition_ms", 0)) / 1000.0)
        for k in range(1, n)
    ]

    inputs, parts = [], []
    for k, sh in enumerate(chunk):
        # enough source for this shot plus whatever the next transition eats
        nxt = tds[k + 1] if k + 1 < n else 0.0
        src = durs[k] * float(sh.get("speed", 1.0) or 1.0) + nxt + frame
        inputs += [
            "-ss",
            f"{float(sh['start']):.3f}",
            "-t",
            f"{src:.3f}",
            "-i",
            sh["path"],
        ]
        parts.append(_amv_shot_chain(k, sh, fmt, f"v{k}"))

    if n == 1:
        return inputs, ";".join(parts), "v0", durs[0]

    prev = "v0"
    for k in range(1, n):
        d = tds[k]
        xf = editstyles.TRANSITIONS.get(chunk[k].get("transition", "cut"), {}).get(
            "xfade"
        )
        name = xf or "fade"
        offset = max(0.0, float(chunk[k]["at"]) - base)
        out_lbl = f"x{k}" if k < n - 1 else "amvcat"
        parts.append(
            f"[{prev}][v{k}]xfade=transition={name}:duration={d:.4f}"
            f":offset={offset:.4f}[{out_lbl}]"
        )
        prev = out_lbl
    total = float(chunk[-1]["at"]) - base + durs[-1]
    return inputs, ";".join(parts), prev, total


def _render_amv(
    scene_id,
    params,
    fmt,
    audio_path,
    duration,
    feat,
    art_pack,
    out_path,
    settings,
    tmpdir,
    text_vf,
    log,
    progress,
    should_stop,
):
    mod = __import__("pulseforge.scenes." + scene_id, fromlist=["build_edl"])
    ctx = SceneContext(
        fmt["w"],
        fmt["h"],
        fmt["fps"],
        int(duration * fmt["fps"]),
        duration,
        feat,
        params,
        params.get("_assets", []),
        art_pack,
        tmpdir,
    )
    ctx.progress = lambda f: progress(0.05 + 0.20 * float(f))  # clip analysis
    log("looking at the clips…")
    edl = mod.build_edl(ctx)
    if not edl:
        raise RuntimeError(
            "no usable clips — attach a folder of video files in Compose first"
        )
    fx_count = sum(len(sh.get("fx") or []) for sh in edl)
    log(f"{len(edl)} shots, {fx_count} effects; assembling…")
    progress(0.28)

    ff = ffmpeg_caps()["ffmpeg"]
    pre, vc = video_encode_args(settings)
    chunks = _amv_chunks(edl)
    log(f"{len(chunks)} pass{'es' if len(chunks) != 1 else ''}")

    if len(chunks) == 1:
        inputs, body, last, _total = _amv_chunk_graph(chunks[0], fmt)
        n_in = len(chunks[0])
        if text_vf:
            body += f";[{last}]{text_vf}[vout]"
            last = "vout"
        cmd = [
            ff,
            "-y",
            *pre,
            *inputs,
            "-i",
            str(audio_path),
            "-filter_complex",
            body,
            "-map",
            f"[{last}]",
            "-map",
            f"{n_in}:a:0",
            "-af",
            _audio_filter(settings),
            "-c:a",
            "aac",
            "-b:a",
            settings.get("audio_bitrate", "256k"),
            *vc,
            "-t",
            f"{duration:.3f}",
            "-movflags",
            "+faststart",
            str(out_path),
        ]
        job = FFJob(
            cmd,
            duration=duration,
            on_line=log,
            on_progress=lambda f: progress(0.28 + 0.68 * f),
        )
        if job.run() != 0:
            raise RuntimeError("ffmpeg AMV assembly failed")
        return

    # More shots than one pass can hold: render each run to its own file and
    # join them. Chunk boundaries are hard cuts, so a plain concat is exact.
    seg_paths = []
    for ci, chunk in enumerate(chunks):
        if should_stop and should_stop():
            raise RuntimeError("stopped")
        inputs, body, last, total = _amv_chunk_graph(chunk, fmt)
        seg = os.path.join(tmpdir, f"amv_{ci:04d}.mp4")
        cmd = [
            ff,
            "-y",
            *pre,
            *inputs,
            "-filter_complex",
            body,
            "-map",
            f"[{last}]",
            "-an",
            *vc,
            "-t",
            f"{total:.3f}",
            str(seg),
        ]
        lo = 0.28 + 0.60 * (ci / len(chunks))
        hi = 0.28 + 0.60 * ((ci + 1) / len(chunks))
        job = FFJob(
            cmd,
            duration=total,
            on_line=log,
            on_progress=lambda f, lo=lo, hi=hi: progress(lo + (hi - lo) * f),
        )
        if job.run() != 0:
            raise RuntimeError(f"ffmpeg AMV pass {ci + 1} failed")
        seg_paths.append(seg)
        log(f"pass {ci + 1}/{len(chunks)} done")

    listing = os.path.join(tmpdir, "amv_segments.txt")
    with open(listing, "w", encoding="utf-8") as fh:
        for sp in seg_paths:
            fh.write(f"file '{sp}'\n")
    cmd = [ff, "-y", "-f", "concat", "-safe", "0", "-i", listing, "-i", str(audio_path)]
    if text_vf:
        cmd += ["-filter_complex", f"[0:v]{text_vf}[vout]", "-map", "[vout]"]
    else:
        cmd += ["-map", "0:v:0"]
    cmd += [
        "-map",
        "1:a:0",
        "-af",
        _audio_filter(settings),
        "-c:a",
        "aac",
        "-b:a",
        settings.get("audio_bitrate", "256k"),
    ]
    # Re-encoding here would be a second generation for no gain when there is
    # no text to draw; with text the picture has to be touched anyway.
    cmd += vc if text_vf else ["-c:v", "copy"]
    cmd += ["-t", f"{duration:.3f}", "-movflags", "+faststart", str(out_path)]
    job = FFJob(
        cmd,
        duration=duration,
        on_line=log,
        on_progress=lambda f: progress(0.88 + 0.11 * f),
    )
    if job.run() != 0:
        raise RuntimeError("ffmpeg AMV join failed")


# --------------------------------------------------------------------------
# thumbnail
# --------------------------------------------------------------------------
def grab_thumbnail(
    src_mp4,
    dst_png,
    t_seconds=1.0,
    width=1280,
    height=720,
    title="",
    subtitle="",
    scrim=0.0,
    position="bottom-left",
    pop=0.0,
):
    """A frame from the render, optionally with the title on it.

    The last thing between a finished video and an upload. `scrim` darkens the
    frame behind the text, which is what makes a title readable over a bright
    background instead of sitting in a drop shadow and hoping.
    """
    ff = ffmpeg_caps()["ffmpeg"]
    if not ff:
        raise RuntimeError("ffmpeg not found")
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height}"
    )
    if pop > 0.001:  # thumbnails compete in a grid; a little extra colour helps
        vf += f",eq=saturation={1 + pop:.2f}:contrast={1 + pop * 0.25:.3f}"
    if scrim > 0.001:
        vf += f",drawbox=x=0:y=0:w=iw:h=ih:color=black@{min(0.85, scrim):.2f}:t=fill"
    if title or subtitle:
        pad = int(height * 0.07)
        big = max(28, int(min(height, width) * 0.115))
        small = max(18, int(big * 0.42))
        ax, ay = overlays.POSITIONS.get(
            str(position), overlays.POSITIONS["bottom-left"]
        )
        ax, ay = ax.format(pad=pad), ay.format(pad=pad)
        if title:
            vf += (
                f",drawtext=text='{overlays.escape(title)}':fontcolor=white"
                f":fontsize={big}:x={ax}:y={ay}-{small + 10 if subtitle else 0}"
                f":shadowcolor=black@0.75:shadowx=3:shadowy=3"
            )
        if subtitle:
            vf += (
                f",drawtext=text='{overlays.escape(subtitle)}':fontcolor=white@0.85"
                f":fontsize={small}:x={ax}:y={ay}"
                f":shadowcolor=black@0.75:shadowx=2:shadowy=2"
            )
    cmd = [
        ff,
        "-y",
        "-ss",
        f"{max(0.0, t_seconds):.2f}",
        "-i",
        str(src_mp4),
        "-frames:v",
        "1",
        "-vf",
        vf,
        str(dst_png),
    ]
    import subprocess

    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if r.returncode != 0 or not os.path.exists(dst_png):
        raise RuntimeError("could not extract a frame at that time")
    return dst_png
