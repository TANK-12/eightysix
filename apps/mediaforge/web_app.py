"""FastAPI backend for MediaForge, replacing the customtkinter GUI.

Reuses the business logic modules unchanged (config.py, index.py, ffrunner.py,
translate.py, manifest.py, metadata.py, audiohash.py, janclient.py) -- none of
it ever depended on customtkinter, it was already cleanly separated behind
plain callback hooks (on_status/on_line/on_progress/should_stop). What's new
is only the delivery mechanism: a Job runs each long task on a background
thread and an SSE endpoint streams its events, batched, to the browser --
this also fixes, by construction, the known bugs where the desktop GUI
blocked its single UI thread on things like the anime-library export or the
first ffmpeg-capability probe at startup: there is no shared UI thread here
for a slow call to block.

All 9 modules are wired: Storage Tools, Anime Library, Subtitle Studio, Video
Enhancer, Duplicate Slayer, Library Organiser, Japanese Tutor, AI Image Studio,
and Manga Downloader.
"""

import asyncio
import hashlib
import json
import math
import os
import queue
import re
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from mediaforge import config, metadata
from mediaforge.ffrunner import (
    build_encode_args,
    escape_for_filter,
    FFJob,
    probe_streams,
    track_label,
)
from mediaforge.index import FileIndex
from mediaforge.janclient import JanClient
from mediaforge.manifest import Manifest, apply_op, list_manifests, quick_hash, revert
from mediaforge.modules.anime_library import library_report
from mediaforge.modules.organizer import build_target, parse_name
from mediaforge.translate import translate_subtitle_file

app = FastAPI(title="MediaForge")


@app.exception_handler(RequestValidationError)
async def _readable_validation_error(request: Request, exc: RequestValidationError):
    """A 422 whose detail is one line ("min_mb: Input should be a valid
    number"), so the page's toast can show it as is."""
    parts = []
    for e in exc.errors():
        where = [str(x) for x in e.get("loc", ()) if x not in ("body", "query", "path")]
        parts.append((where[-1] + ": " if where else "") + str(e.get("msg", "")))
    return JSONResponse(status_code=422, content={"detail": "; ".join(parts)})


# --------------------------------------------------------------------------
# App-wide state
# --------------------------------------------------------------------------
class AppState:
    def __init__(self):
        self.settings = config.load_settings()
        self.index = FileIndex()
        self.jan = JanClient(self.settings.get("jan_base", "http://localhost:1337/v1"))
        self.jobs: dict[str, "Job"] = {}

    def save_settings(self):
        config.save_settings(self.settings)


state = AppState()


class Job:
    def __init__(self, kind):
        self.id = uuid.uuid4().hex[:12]
        self.kind = kind
        self.status = "running"
        self.error = None
        self.stop_requested = threading.Event()
        self.current_ffjob = None
        self.events = queue.Queue()
        self.thread = None
        self.result: Any = None  # what the job hands back

    def log(self, msg):
        self.events.put({"type": "log", "text": msg})

    def progress(self, frac):
        self.events.put({"type": "progress", "frac": frac})

    def should_stop(self):
        return self.stop_requested.is_set()

    def finish(self, status, error=None):
        self.status = status
        self.error = error
        self.events.put({"type": status, "error": error})

    def kill_now(self):
        self.stop_requested.set()
        if self.current_ffjob:
            self.current_ffjob.kill()


def _run_job(job: Job, target_fn):
    try:
        target_fn()
        job.finish("done")
    except Exception as e:
        job.finish("error", str(e))


def _prune_jobs(keep=20):
    """Finished jobs are kept so a client can still ask how one ended, but not
    forever -- this backend can stay up for days across many runs."""
    finished = [j for j in state.jobs.values() if j.status != "running"]
    for j in finished[:-keep] if len(finished) > keep else []:
        state.jobs.pop(j.id, None)


def start_job(kind, target_fn):
    job = Job(kind)
    _prune_jobs()
    state.jobs[job.id] = job
    job.thread = threading.Thread(target=_run_job, args=(job, target_fn), daemon=True)
    job.thread.start()
    return job


@app.post("/api/jobs/{job_id}/stop")
def stop_job(job_id: str):
    job = state.jobs.get(job_id)
    if not job:
        raise HTTPException(404, "no such job")
    job.kill_now()
    return {"ok": True}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = state.jobs.get(job_id)
    if not job:
        raise HTTPException(404, "no such job")
    return {
        "id": job.id,
        "kind": job.kind,
        "status": job.status,
        "error": job.error,
        "result": getattr(job, "result", None),
    }


@app.get("/api/jobs/{job_id}/events")
async def job_events(job_id: str):
    job = state.jobs.get(job_id)
    if not job:
        raise HTTPException(404, "no such job")

    async def gen():
        while True:
            batch = []
            try:
                batch.append(await asyncio.to_thread(job.events.get, True, 5.0))
            except Exception:
                if job.status != "running":
                    # The job ended without this connection seeing its terminal
                    # event -- either it finished before anyone listened, or an
                    # earlier connection consumed it (the queue is
                    # single-consumer). Ending the stream silently would leave
                    # the client reconnecting forever with its buttons stuck,
                    # so synthesize the terminal event from the job's status.
                    yield f"data: {json.dumps({'type': job.status, 'error': job.error})}\n\n"
                    return
                yield ": keep-alive\n\n"
                continue
            deadline = time.time() + 0.12
            while time.time() < deadline:
                try:
                    batch.append(job.events.get_nowait())
                except Exception:
                    break
            # Coalesce a burst of progress ticks into just the latest one -- a
            # batch ffmpeg job can emit dozens of these in 120ms. The kept tick
            # is flushed as soon as a non-progress event needs to go out, so
            # progress never overtakes the log line it belongs to and the final
            # tick is not dropped when "done" lands in the same batch.
            last_progress = None
            for e in batch:
                if e["type"] == "progress":
                    last_progress = e
                    continue
                if last_progress:
                    yield f"data: {json.dumps(last_progress)}\n\n"
                    last_progress = None
                yield f"data: {json.dumps(e)}\n\n"
                if e["type"] in ("done", "error"):
                    return
            if last_progress:
                yield f"data: {json.dumps(last_progress)}\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# --------------------------------------------------------------------------
# Thumbnails
# --------------------------------------------------------------------------
THUMB_CACHE = config.DATA_ROOT / "thumbnails"
THUMB_CACHE.mkdir(parents=True, exist_ok=True)
_thumb_lock = threading.Lock()


def _thumb_for(path: str, width: int) -> Path:
    """Render (and cache) a small thumbnail for one image or video file.

    Video frames cost an ffmpeg spawn each, and the organiser preview can list
    hundreds of files, so results are cached on disk keyed by path + size +
    mtime. The frontend loads these lazily, so only what scrolls into view is
    ever rendered.
    """
    st = os.stat(path)
    key = hashlib.sha1(
        f"{os.path.abspath(path)}|{width}|{int(st.st_mtime)}|{st.st_size}".encode()
    ).hexdigest()
    out = THUMB_CACHE / f"{key}.jpg"
    if out.exists():
        return out

    ext = Path(path).suffix.lower()
    with _thumb_lock:
        if out.exists():
            return out
        tmp = out.with_suffix(".tmp.jpg")
        if ext in config.VIDEO_EXTS:
            # -ss before -i seeks without decoding everything up to that point.
            # Twenty seconds in clears the black frames and studio logos most
            # files open with. A clip shorter than that yields nothing, so the
            # retry below grabs the first frame instead.
            subprocess.run(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-y",
                    "-ss",
                    "20",
                    "-i",
                    path,
                    "-frames:v",
                    "1",
                    "-vf",
                    f"scale={width}:-1",
                    str(tmp),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=25,
            )
            if not tmp.exists() or tmp.stat().st_size == 0:
                subprocess.run(
                    [
                        "ffmpeg",
                        "-v",
                        "error",
                        "-y",
                        "-i",
                        path,
                        "-frames:v",
                        "1",
                        "-vf",
                        f"scale={width}:-1",
                        str(tmp),
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=25,
                )
        else:
            from PIL import Image

            with Image.open(path) as im:
                im = im.convert("RGB")
                im.thumbnail((width, width * 4))
                im.save(tmp, "JPEG", quality=80)
        if not tmp.exists() or tmp.stat().st_size == 0:
            tmp.unlink(missing_ok=True)
            raise RuntimeError("could not render a thumbnail")
        tmp.replace(out)
    return out


@app.get("/api/thumbnail")
def thumbnail(path: str, w: int = 96):
    """Thumbnail for any indexed image or video file, for the preview lists."""
    w = max(32, min(int(w), 480))
    if not os.path.isfile(path):
        raise HTTPException(404, "no such file")
    try:
        return FileResponse(
            _thumb_for(path, w),
            media_type="image/jpeg",
            headers={"Cache-Control": "max-age=86400"},
        )
    except Exception as e:
        raise HTTPException(415, f"no thumbnail for this file: {e}")


# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------
class SettingsPatch(BaseModel):
    values: dict


@app.get("/api/settings")
def get_settings():
    return state.settings


def _settings_problem(values: dict) -> str | None:
    """Why a settings patch is refused, or None (advanced_mode "x" or
    jan_base 5 used to be saved and broke the page and the next start)."""
    if len(values) > 200:
        return "too many settings in one save"
    for k, v in values.items():
        problem = config.value_problem(k, v)
        if problem:
            return problem
    return None


@app.post("/api/settings")
def update_settings(patch: SettingsPatch):
    problem = _settings_problem(patch.values)
    if problem:
        raise HTTPException(422, problem)
    state.settings.update(patch.values)
    state.save_settings()
    return state.settings


@app.get("/api/encoders")
def get_encoders():
    from mediaforge.config import available_hw_encoders

    return {"encoders": available_hw_encoders()}


# --------------------------------------------------------------------------
# Storage Tools
# --------------------------------------------------------------------------
class ScanRequest(BaseModel):
    root: str
    min_bytes: int = 0


@app.get("/api/storage/count")
def storage_count():
    return {"count": state.index.count()}


@app.post("/api/storage/scan")
def storage_scan(req: ScanRequest):
    job = Job("storage-scan")
    state.jobs[job.id] = job

    def work():
        state.index.scan(
            req.root,
            min_bytes=req.min_bytes,
            on_status=job.log,
            should_stop=job.should_stop,
        )

    job.thread = threading.Thread(target=_run_job, args=(job, work), daemon=True)
    job.thread.start()
    return {"job_id": job.id}


@app.get("/api/storage/search")
def storage_search(
    term: str = "",
    min_mb: float = 0,
    ext: str = "",
    order: str = "size",
    limit: int = 800,
):
    if not math.isfinite(min_mb):
        raise HTTPException(422, "min_mb must be a finite number")
    limit = max(1, min(limit, 5000))
    rows = state.index.search(
        term=term, min_mb=min_mb, ext=ext, limit=limit, order=order
    )
    return [{"name": n, "ext": e, "size": s, "path": p} for (n, e, s, p) in rows]


@app.post("/api/storage/duplicates")
def storage_duplicates(min_bytes: int = 1_000_000):
    def work(job):
        return lambda: setattr(
            job,
            "result",
            state.index.find_duplicates(
                min_bytes=min_bytes, on_status=job.log, should_stop=job.should_stop
            ),
        )

    job = Job("storage-duplicates")
    job.result = []
    state.jobs[job.id] = job
    job.thread = threading.Thread(target=_run_job, args=(job, work(job)), daemon=True)
    job.thread.start()
    return {"job_id": job.id}


@app.get("/api/storage/duplicates/{job_id}/result")
def storage_duplicates_result(job_id: str):
    job = state.jobs.get(job_id)
    if not job:
        raise HTTPException(404, "no such job")
    return {"groups": getattr(job, "result", [])}


@app.post("/api/storage/clean-dead")
def storage_clean_dead():
    return {"removed": state.index.clean_dead()}


@app.post("/api/storage/clear")
def storage_clear():
    state.index.clear()
    return {"ok": True}


# --------------------------------------------------------------------------
# Anime Library
# --------------------------------------------------------------------------
@app.get("/api/anime-library/report")
def anime_library_report(root: str):
    text, lib = library_report(root)
    return {"text": text, "series_count": len(lib)}


@app.post("/api/anime-library/export")
def anime_library_export(root: str):
    def work():
        text, _ = library_report(root)
        out = Path(root) / "_library_report.txt"
        out.write_text(text, "utf-8")

    job = start_job("anime-export", work)
    return {"job_id": job.id}


@app.get("/api/anime-library/namecheck")
def anime_library_namecheck(root: str):
    import re

    try:
        import anitopy
    except ImportError:
        raise HTTPException(409, "anitopy not installed")
    from mediaforge.modules.anime_library import EP_RE, YEAR_RE, EXTS

    def work(job):
        def run():
            lines, n = [], 0
            for d in sorted(p for p in Path(root).iterdir() if p.is_dir()):
                folder_key = re.sub(r"[^a-z0-9]+", "", YEAR_RE.sub("", d.name).lower())
                for f in d.rglob("*"):
                    if f.suffix.lower() not in EXTS:
                        continue
                    if not EP_RE.search(f.stem) and "-" not in f.stem:
                        lines.append(f"no SxxExx : {f.relative_to(root)}")
                        n += 1
                        continue
                    p = anitopy.parse(f.name) or {}
                    t = re.sub(r"[^a-z0-9]+", "", (p.get("anime_title") or "").lower())
                    if t and folder_key and t not in folder_key and folder_key not in t:
                        lines.append(f"{p.get('anime_title', '?')}  in  {d.name}")
                        n += 1
            job.result = {"flagged": n, "lines": lines}

        return run

    job = Job("anime-namecheck")
    job.result = {}
    state.jobs[job.id] = job
    job.thread = threading.Thread(target=_run_job, args=(job, work(job)), daemon=True)
    job.thread.start()
    return {"job_id": job.id}


@app.get("/api/anime-library/namecheck/{job_id}/result")
def anime_library_namecheck_result(job_id: str):
    job = state.jobs.get(job_id)
    if not job:
        raise HTTPException(404, "no such job")
    return getattr(job, "result", {})


# --------------------------------------------------------------------------
# Subtitle Studio
# --------------------------------------------------------------------------
@app.get("/api/subtitles/scan-folder")
def subtitles_scan_folder(folder: str):
    p = Path(folder)
    if not p.is_dir():
        raise HTTPException(400, "not a folder")
    files = sorted(
        str(f)
        for f in p.iterdir()
        if f.is_file() and f.suffix.lower() in config.VIDEO_EXTS
    )
    return {"files": files}


@app.get("/api/subtitles/probe")
def subtitles_probe(path: str):
    if not os.path.isfile(path):
        raise HTTPException(
            404, "That file is not there any more: scan the folder again"
        )
    info = probe_streams(path)
    if not (info["video"] or info["audio"] or info["subtitle"]):
        raise HTTPException(400, "That is not a video or audio file ffmpeg can read")
    return {
        "duration": info["duration"],
        "audio": [{"index": t["index"], "label": track_label(t)} for t in info["audio"]]
        or [{"index": 0, "label": "0 -- (none)"}],
        "subtitle": [
            {"index": t["index"], "label": track_label(t)} for t in info["subtitle"]
        ]
        or [{"index": 0, "label": "0 -- (none)"}],
    }


class SubtitleStartRequest(BaseModel):
    files: list[str]
    out_dir: str
    mode: str = "hardbake_embedded"
    audio_idx: int = 0
    sub_idx: int = 0
    ext_sub_path: str | None = None
    keep_size: bool = False
    width: int = 1280
    height: int = 720
    encoder_family: str | None = None
    hw_encoder: str | None = None
    crf: int | None = None
    preset: str | None = None
    tune: str | None = None
    translate_backend: str | None = None
    target_language: str | None = None
    whisper_model: str | None = None


def _process_one_subtitle(job, src, out_dir, req, settings):
    src = str(src)
    info = probe_streams(src)
    dur = info.get("duration", 0)
    out = str(Path(out_dir) / (Path(src).stem + ".mp4"))
    import tempfile

    tmp = tempfile.mkdtemp(prefix="mf_")
    sub_path, burn_si = None, None

    if req.mode == "hardbake_embedded":
        burn_si = req.sub_idx
    elif req.mode == "hardbake_file":
        if not req.ext_sub_path:
            raise RuntimeError("no external subtitle file given")
        sub_path = req.ext_sub_path
    elif req.mode == "translate_hardbake":
        raw = req.ext_sub_path
        if not raw:
            raw = os.path.join(tmp, "extracted.srt")
            job.log("extracting embedded subtitle...")
            import subprocess

            r = subprocess.run(
                [
                    config.ffmpeg_caps()["ffmpeg"],
                    "-y",
                    "-i",
                    src,
                    "-map",
                    f"0:s:{req.sub_idx}",
                    raw,
                ],
                capture_output=True,
                text=True,
            )
            if r.returncode != 0 or not os.path.exists(raw):
                raise RuntimeError("could not extract an embedded subtitle track")
        sub_path = os.path.join(tmp, "translated" + os.path.splitext(raw)[1])
        job.log(
            f"translating -> {settings.get('target_language')} via {settings.get('translate_backend')}"
        )
        translate_subtitle_file(
            raw, sub_path, settings, state.jan, log=job.log, kill=job.should_stop
        )
    elif req.mode == "transcribe_hardbake":
        srt = os.path.join(tmp, "whisper.srt")
        _whisper(job, src, srt, tmp, settings)
        sub_path = srt
        if settings.get("target_language", "English").lower() not in (
            "",
            "english",
            "auto",
        ):
            tr = os.path.join(tmp, "whisper_translated.srt")
            translate_subtitle_file(
                srt, tr, settings, state.jan, log=job.log, kill=job.should_stop
            )
            sub_path = tr

    ff = config.ffmpeg_caps()["ffmpeg"]
    pre, vc = build_encode_args(settings)
    w = req.width if not req.keep_size else 0
    h = req.height if not req.keep_size else 0
    scale = (
        f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2"
        if w and h
        else ""
    )

    vf = []
    if burn_si is not None:
        vf.append(f"subtitles='{escape_for_filter(src)}':si={burn_si}")
    elif sub_path:
        vf.append(f"subtitles='{escape_for_filter(sub_path)}'")
    if scale:
        vf.append(scale)

    cmd = (
        [ff, "-y"] + pre + ["-i", src, "-map", "0:v:0", "-map", f"0:a:{req.audio_idx}?"]
    )
    if vf:
        cmd += [
            "-vf",
            ",".join(vf)
            + (
                ",format=nv12,hwupload" if settings.get("hw_encoder") == "vaapi" else ""
            ),
        ]
    elif settings.get("hw_encoder") == "vaapi":
        cmd += ["-vf", "format=nv12,hwupload"]
    cmd += vc
    cmd += [
        "-c:a",
        settings.get("audio_codec", "aac"),
        "-b:a",
        settings.get("audio_bitrate", "192k"),
        "-movflags",
        "+faststart",
        out,
    ]

    job.current_ffjob = FFJob(
        cmd,
        duration=dur,
        on_line=lambda s: job.log(s) if not s.startswith("$") else None,
        on_progress=job.progress,
    )
    rc = job.current_ffjob.run()
    if rc == 0:
        job.log(f"done: {out}")
    elif job.current_ffjob._killed:
        job.log("killed.")
        raise RuntimeError("killed")
    else:
        job.log(f"ffmpeg exited {rc}")


def _whisper(job, src, out_srt, tmp, settings):
    job.log("transcribing with Whisper (first run downloads the model)...")
    import subprocess

    wav = os.path.join(tmp, "a.wav")
    subprocess.run(
        [
            config.ffmpeg_caps()["ffmpeg"],
            "-y",
            "-i",
            src,
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            wav,
        ],
        capture_output=True,
    )
    from faster_whisper import WhisperModel

    model = WhisperModel(
        settings.get("whisper_model", "base"), device="cpu", compute_type="int8"
    )
    segs, _ = model.transcribe(wav)
    with open(out_srt, "w", encoding="utf-8") as f:
        for i, s in enumerate(segs, 1):
            f.write(f"{i}\n{_ts(s.start)} --> {_ts(s.end)}\n{s.text.strip()}\n\n")


def _ts(t):
    h, m, s = int(t // 3600), int(t % 3600 // 60), t % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")


@app.post("/api/subtitles/start")
def subtitles_start(req: SubtitleStartRequest):
    if not config.ffmpeg_caps()["ffmpeg"]:
        raise HTTPException(409, "ffmpeg not found on PATH")
    settings = dict(state.settings)
    for key in (
        "encoder_family",
        "hw_encoder",
        "crf",
        "preset",
        "tune",
        "translate_backend",
        "target_language",
        "whisper_model",
    ):
        val = getattr(req, key)
        if val is not None:
            settings[key] = val
    state.settings.update({k: v for k, v in settings.items() if k in state.settings})
    state.save_settings()
    out_dir = Path(req.out_dir)

    def make_work(job):
        def work():
            out_dir.mkdir(parents=True, exist_ok=True)
            for i, src in enumerate(req.files, 1):
                job.log(f"\n=== [{i}/{len(req.files)}] {os.path.basename(src)} ===")
                if job.should_stop():
                    job.log("stopped.")
                    break
                try:
                    _process_one_subtitle(job, src, out_dir, req, settings)
                except Exception as e:
                    job.log(f"FAILED: {e}")
            job.log("\nBatch complete.")

        return work

    job = Job("subtitles")
    state.jobs[job.id] = job
    job.thread = threading.Thread(
        target=_run_job, args=(job, make_work(job)), daemon=True
    )
    job.thread.start()
    return {"job_id": job.id}


# --------------------------------------------------------------------------
# Video Enhancer
# --------------------------------------------------------------------------
ENHANCE_RES = {
    "original": None,
    "720p": (1280, 720),
    "1080p": (1920, 1080),
    "1440p": (2560, 1440),
    "4k": (3840, 2160),
}


class EnhanceRequest(BaseModel):
    files: list[str]
    out_dir: str
    resolution: str = "original"  # original | 720p | 1080p | 1440p | 4k
    scaler: str = "lanczos"
    interpolate: bool = False
    fps: int = 60
    encoder_family: str = "x264"
    hw_encoder: str = "cpu"
    crf: int = 20
    gop: int = 250
    scene_threshold: int = 40
    copy_audio: bool = True


@app.post("/api/enhance/start")
def enhance_start(req: EnhanceRequest):
    if not config.ffmpeg_caps()["ffmpeg"]:
        raise HTTPException(409, "ffmpeg not found on PATH")
    settings = dict(state.settings)
    settings["encoder_family"] = req.encoder_family
    settings["hw_encoder"] = req.hw_encoder
    settings["crf"] = req.crf
    res = ENHANCE_RES.get(req.resolution)

    def make_work(job):
        def work():
            out_dir = Path(req.out_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            ff = config.ffmpeg_caps()["ffmpeg"]
            for i, src in enumerate(req.files, 1):
                if job.should_stop():
                    job.log("stopped.")
                    break
                dur = probe_streams(src).get("duration", 0)
                out = str(out_dir / (Path(src).stem + "_enhanced.mp4"))
                vf = []
                if res:
                    vf.append(f"scale={res[0]}:{res[1]}:flags={req.scaler}")
                if req.interpolate:
                    vf.append(
                        f"minterpolate=fps={req.fps}:mi_mode=mci:mc_mode=aobmc:vsbmc=1"
                    )
                pre, vc = build_encode_args(settings)
                cmd = [ff, "-y"] + pre + ["-i", src, "-map", "0:v:0", "-map", "0:a?"]
                if req.hw_encoder == "vaapi":
                    cmd += [
                        "-vf",
                        (",".join(vf) + "," if vf else "") + "format=nv12,hwupload",
                    ]
                elif vf:
                    cmd += ["-vf", ",".join(vf)]
                cmd += vc + [
                    "-g",
                    str(req.gop),
                    "-sc_threshold",
                    str(req.scene_threshold),
                ]
                cmd += (
                    ["-c:a", "copy"]
                    if req.copy_audio
                    else ["-c:a", "aac", "-b:a", "192k"]
                )
                cmd += ["-movflags", "+faststart", out]
                job.log(f"\n[{i}/{len(req.files)}] {os.path.basename(src)}")
                job.current_ffjob = FFJob(
                    cmd,
                    dur,
                    on_line=lambda s: job.log(s) if not s.startswith("$") else None,
                    on_progress=job.progress,
                )
                rc = job.current_ffjob.run()
                job.log("done." if rc == 0 else f"exit {rc}")
            job.log("\nDone.")

        return work

    job = Job("enhance")
    state.jobs[job.id] = job
    job.thread = threading.Thread(
        target=_run_job, args=(job, make_work(job)), daemon=True
    )
    job.thread.start()
    return {"job_id": job.id}


# --------------------------------------------------------------------------
# Duplicate Slayer
# --------------------------------------------------------------------------
class DedupeScanRequest(BaseModel):
    target: str
    target_type: str  # "pdf" | "dir"
    threshold: str = "near"  # exact | near | loose
    auto: bool = False
    compress: bool = True
    out_format: str = "pdf"  # pdf | cbz


_THRESH = {"exact": 0, "near": 6, "loose": 12}


def _pdf_page_images(pdf_path, tmp):
    try:
        import pymupdf as fitz
    except ImportError:
        import fitz
    doc = fitz.open(pdf_path)
    out = []
    for pn in range(len(doc)):
        for k, img in enumerate(doc.load_page(pn).get_images(full=True)):
            try:
                b = doc.extract_image(img[0])
                fp = os.path.join(tmp, f"p{pn:04d}_{k}.{b['ext']}")
                open(fp, "wb").write(b["image"])
                out.append(fp)
            except Exception:
                pass
    doc.close()
    return out


def _compile_dedupe(images, target, compress, fmt, tmp, log):
    from PIL import Image

    if not images:
        log("Nothing to write.")
        return None
    base = os.path.splitext(os.path.basename(target))[0] + "_optimised"
    out_dir = os.path.dirname(target) if os.path.isfile(target) else target
    pil = []
    for k, im in enumerate(sorted(images)):
        try:
            img = Image.open(im).convert("RGB")
            if compress and img.height > 3000:
                r = 3000 / img.height
                img = img.resize((int(img.width * r), 3000), Image.LANCZOS)
            if compress:
                jp = os.path.join(tmp, f"c{k}.jpg")
                img.save(jp, "JPEG", quality=80, optimize=True)
                img = Image.open(jp)
            pil.append(img)
        except Exception as e:
            log(f"skip {im}: {e}")
    if not pil:
        log("Nothing to write.")
        return None
    if fmt == "cbz":
        import zipfile

        out_path = os.path.join(out_dir, base + ".cbz")
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
            for k, img in enumerate(pil):
                fp = os.path.join(tmp, f"z{k:04d}.jpg")
                img.save(fp, "JPEG", quality=88)
                z.write(fp, f"{k:04d}.jpg")
    else:
        out_path = os.path.join(out_dir, base + ".pdf")
        pil[0].save(out_path, save_all=True, append_images=pil[1:])
    log(f"wrote {out_path}")
    return out_path


@app.post("/api/dedupe/scan")
def dedupe_scan(req: DedupeScanRequest):
    try:
        import imagehash
        from PIL import Image
    except ImportError:
        raise HTTPException(
            409, "needs Pillow + imagehash: pip install pillow imagehash"
        )

    def make_work(job):
        def work():
            import tempfile

            tmp = tempfile.mkdtemp(prefix="mf_dedupe_")
            if req.target_type == "pdf":
                job.log("Extracting page images from PDF...")
                imgs = _pdf_page_images(req.target, tmp)
            else:
                imgs = sorted(
                    str(p)
                    for p in Path(req.target).iterdir()
                    if p.suffix.lower() in config.IMAGE_EXTS
                )
            if not imgs:
                job.log("No images found.")
                job.result = {"needs_review": False, "groups": [], "output": None}
                return
            job.log(f"Hashing {len(imgs)} images...")
            hashes = []
            for i, im in enumerate(imgs):
                try:
                    hashes.append((im, imagehash.dhash(Image.open(im))))
                except Exception:
                    hashes.append((im, None))
                if i % 20 == 0:
                    job.log(f"hashed {i}/{len(imgs)}")
            maxd = _THRESH.get(req.threshold, 6)
            used, groups = set(), []
            for i, (pa, ha) in enumerate(hashes):
                if i in used or ha is None:
                    continue
                grp = [pa]
                used.add(i)
                for j in range(i + 1, len(hashes)):
                    pb, hb = hashes[j]
                    if j in used or hb is None:
                        continue
                    if (ha - hb) <= maxd:
                        grp.append(pb)
                        used.add(j)
                if len(grp) > 1:
                    groups.append(grp)
            dupes = sum(len(g) - 1 for g in groups)
            job.log(f"{dupes} duplicate pages in {len(groups)} groups.")
            keep = [im for im, _h in hashes if not any(im in g for g in groups)]
            if req.auto or not groups:
                for g in groups:
                    keep.append(g[0])
                out = _compile_dedupe(
                    keep, req.target, req.compress, req.out_format, tmp, job.log
                )
                job.result = {"needs_review": False, "groups": [], "output": out}
            else:
                job.result = {
                    "needs_review": True,
                    "groups": groups,
                    "keep": keep,
                    "tmp": tmp,
                    "compress": req.compress,
                    "out_format": req.out_format,
                    "target": req.target,
                }

        return work

    job = Job("dedupe-scan")
    job.result = {}
    state.jobs[job.id] = job
    job.thread = threading.Thread(
        target=_run_job, args=(job, make_work(job)), daemon=True
    )
    job.thread.start()
    return {"job_id": job.id}


@app.get("/api/dedupe/{job_id}/result")
def dedupe_result(job_id: str):
    job = state.jobs.get(job_id)
    if not job:
        raise HTTPException(404, "no such job")
    r = getattr(job, "result", {})
    return {k: v for k, v in r.items() if k != "tmp"}


@app.get("/api/dedupe/thumbnail")
def dedupe_thumbnail(path: str):
    """A page of a pending Duplicate Slayer review. Only paths a review lists
    are served: this used to hand back any file on disk (/etc/passwd too)."""
    listed = any(
        path in grp
        for job in list(state.jobs.values())
        if isinstance(job.result, dict) and job.result.get("needs_review")
        for grp in job.result.get("groups", [])
    )
    if not listed or not os.path.isfile(path):
        raise HTTPException(404, "no such file")
    return FileResponse(path)


class DedupeReviewChoice(BaseModel):
    keep_from_groups: list[str]  # one chosen path per group, in group order


@app.post("/api/dedupe/{job_id}/finish")
def dedupe_finish(job_id: str, choice: DedupeReviewChoice):
    job = state.jobs.get(job_id)
    if not job or not (isinstance(job.result, dict) and job.result.get("needs_review")):
        raise HTTPException(404, "no pending review for this job")
    r = job.result
    keep = list(r["keep"]) + choice.keep_from_groups
    out = _compile_dedupe(
        keep, r["target"], r["compress"], r["out_format"], r["tmp"], job.log
    )
    job.result = {"needs_review": False, "groups": [], "output": out}
    return {"output": out}


# --------------------------------------------------------------------------
# Library Organiser
# --------------------------------------------------------------------------
class OrganizePreviewRequest(BaseModel):
    src_dir: str
    library_root: str
    naming_pattern: str
    metadata_provider: str = "anilist"  # anilist | jikan | tmdb | none
    tmdb_key: str = ""


@app.post("/api/organizer/preview")
def organizer_preview(req: OrganizePreviewRequest):
    def make_work(job):
        def work():
            vids = [
                str(p)
                for p in Path(req.src_dir).rglob("*")
                if p.suffix.lower() in config.VIDEO_EXTS and p.is_file()
            ]
            job.log(f"Found {len(vids)} video files. Parsing + looking up metadata...")
            rows = []
            meta_cache = {}
            for i, src in enumerate(vids, 1):
                if job.should_stop():
                    job.log("stopped.")
                    break
                p = parse_name(src)
                mt = p["raw_title"]
                if req.metadata_provider != "none":
                    ck = (mt.lower(), p["is_movie"])
                    if ck not in meta_cache:
                        meta_cache[ck] = metadata.lookup(
                            mt, req.metadata_provider, req.tmdb_key, p["is_movie"]
                        )
                    m = meta_cache[ck]
                else:
                    m = None
                title = m["title"] if m else mt
                year = m["year"] if m and m["year"] else p["year"]
                rel = build_target(
                    title,
                    year,
                    p["season"],
                    p["episode"],
                    p["resolution"],
                    p["is_movie"],
                    req.naming_pattern,
                    req.library_root,
                )
                target = str(Path(req.library_root) / (rel + Path(src).suffix))
                note = (
                    "already in place"
                    if os.path.abspath(src) == os.path.abspath(target)
                    else (m["source"] if m else "no metadata")
                )
                rows.append(
                    {
                        "src": src,
                        "target": target,
                        "on": note != "already in place",
                        "note": note,
                    }
                )
                if i % 15 == 0:
                    job.log(f"parsed {i}/{len(vids)}")
            job.result = {"rows": rows}
            job.log("Preview ready.")

        return work

    job = Job("organizer-preview")
    job.result = {"rows": []}
    state.jobs[job.id] = job
    job.thread = threading.Thread(
        target=_run_job, args=(job, make_work(job)), daemon=True
    )
    job.thread.start()
    return {"job_id": job.id}


@app.get("/api/organizer/preview/{job_id}/result")
def organizer_preview_result(job_id: str):
    job = state.jobs.get(job_id)
    if not job:
        raise HTTPException(404, "no such job")
    return getattr(job, "result", {"rows": []})


class OrganizeRow(BaseModel):
    src: str
    target: str
    on: bool = True


class OrganizeApplyRequest(BaseModel):
    rows: list[OrganizeRow]
    src_dir: str
    library_root: str
    action: str = "move"  # move | copy | hardlink
    on_conflict: str = "skip"  # skip | number | conflicts_folder | duplicates_folder
    hash_check: bool = True


@app.post("/api/organizer/apply")
def organizer_apply(req: OrganizeApplyRequest):
    picked = [r for r in req.rows if r.on]
    if not picked:
        raise HTTPException(400, "nothing selected")

    def dup_target(src, root, src_root):
        try:
            rel = os.path.relpath(src, src_root)
        except ValueError:
            rel = os.path.basename(src)
        return Path(root) / "_DUPLICATES" / rel

    def make_work(job):
        def work():
            man = Manifest("organise")
            done = skip = parked = 0
            for r in picked:
                if job.should_stop():
                    job.log("stopped.")
                    break
                src, tgt = r.src, Path(r.target)
                if not os.path.exists(src):
                    skip += 1
                    continue
                if tgt.exists():
                    identical = req.hash_check and quick_hash(src) == quick_hash(
                        str(tgt)
                    )
                    if req.on_conflict == "duplicates_folder":
                        dst = dup_target(src, req.library_root, req.src_dir)
                        k = 2
                        while dst.exists():
                            dst = dst.with_stem(f"{dst.stem} ({k})")
                            k += 1
                        try:
                            sz = os.path.getsize(src)
                            apply_op("move", src, dst)
                            man.record(
                                "move",
                                src,
                                dst,
                                sz,
                                quick_hash(str(dst)) if req.hash_check else None,
                            )
                            parked += 1
                            job.log(
                                f"-> _DUPLICATES ({'identical' if identical else 'competing encode'}): {os.path.basename(src)}"
                            )
                        except Exception as e:
                            job.log(f"FAIL park {os.path.basename(src)}: {e}")
                            skip += 1
                        continue
                    if identical:
                        job.log(f"skip (identical exists): {tgt.name}")
                        skip += 1
                        continue
                    if req.on_conflict == "skip":
                        job.log(f"skip (name clash): {tgt.name}")
                        skip += 1
                        continue
                    elif req.on_conflict == "number":
                        k = 2
                        while tgt.with_stem(f"{tgt.stem} ({k})").exists():
                            k += 1
                        tgt = tgt.with_stem(f"{tgt.stem} ({k})")
                    else:
                        tgt = tgt.parent / "_conflicts" / tgt.name
                try:
                    sz = os.path.getsize(src)
                    h = quick_hash(src) if req.hash_check else None
                    apply_op(req.action, src, str(tgt))
                    man.record(req.action, src, str(tgt), sz, h)
                    done += 1
                except Exception as e:
                    job.log(f"FAIL {os.path.basename(src)}: {e}")
                    skip += 1
            path = man.save()
            extra = f", parked {parked} in _DUPLICATES" if parked else ""
            job.log(f"\n{req.action}d {done} files, skipped {skip}{extra}.")
            job.log(f"Manifest: {path}")
            job.result = {
                "done": done,
                "skipped": skip,
                "parked": parked,
                "manifest": str(path),
            }

        return work

    job = Job("organizer-apply")
    job.result = {}
    state.jobs[job.id] = job
    job.thread = threading.Thread(
        target=_run_job, args=(job, make_work(job)), daemon=True
    )
    job.thread.start()
    return {"job_id": job.id}


@app.get("/api/organizer/history")
def organizer_history():
    return list_manifests()


class RevertRequest(BaseModel):
    manifest_path: str


@app.post("/api/organizer/revert")
def organizer_revert(req: RevertRequest):
    def make_work(job):
        def work():
            u, s, rp = revert(req.manifest_path, log=job.log)
            job.log(f"\nReverted {u}, skipped {s}. New manifest: {rp}")
            job.result = {"reverted": u, "skipped": s, "new_manifest": str(rp)}

        return work

    job = Job("organizer-revert")
    job.result = {}
    state.jobs[job.id] = job
    job.thread = threading.Thread(
        target=_run_job, args=(job, make_work(job)), daemon=True
    )
    job.thread.start()
    return {"job_id": job.id}


# --------------------------------------------------------------------------
# Japanese Tutor
# --------------------------------------------------------------------------
@app.get("/api/jptutor/status")
def jptutor_status():
    up = state.jan.up()
    return {"jan_up": up, "models": state.jan.models() if up else []}


class JpTutorMessage(BaseModel):
    message: str
    model: str
    register: str = "Polite (desu/masu)"
    persona: str = "Balanced tutor"
    romaji: bool = True


@app.post("/api/jptutor/send")
def jptutor_send(req: JpTutorMessage):
    if not state.jan.up():
        raise HTTPException(
            409, "Jan is offline -- open Jan and start its local API server"
        )
    system = (
        f"You are a Japanese language {req.persona.lower()}. Reply in natural Japanese in a "
        f"{req.register} register. "
        + (
            "Then give a line of romaji and a short English gloss."
            if req.romaji
            else "Japanese only."
        )
    )
    try:
        out = state.jan.chat(
            req.model, system, req.message, max_tokens=400, temperature=0.5
        )
    except Exception as e:
        raise HTTPException(502, str(e))
    return {"reply": out}


# --------------------------------------------------------------------------
# AI Image Studio (fal.ai generate + local Pillow upscale)
# --------------------------------------------------------------------------
FAL_MODELS = {
    "FLUX.1 [schnell] (fast)": "fal-ai/flux/schnell",
    "FLUX.1 [dev]": "fal-ai/flux/dev",
    "SDXL": "fal-ai/fast-sdxl",
}


class FalGenerateRequest(BaseModel):
    fal_key: str
    model: str = "FLUX.1 [schnell] (fast)"
    prompt: str
    size: str = "landscape_16_9"
    steps: int = 4
    img2img_path: str | None = None
    strength: float = 0.75
    out_dir: str


@app.get("/api/imagestudio/models")
def imagestudio_models():
    return list(FAL_MODELS.keys())


@app.post("/api/imagestudio/generate")
def imagestudio_generate(req: FalGenerateRequest):
    if not req.fal_key.strip():
        raise HTTPException(400, "a fal.ai API key is required")
    state.settings["fal_key"] = req.fal_key
    state.save_settings()
    model_id = FAL_MODELS.get(req.model, req.model)
    out_dir = Path(req.out_dir)

    def make_work(job):
        def work():
            import base64
            import requests

            out_dir.mkdir(parents=True, exist_ok=True)
            url = f"https://fal.run/{model_id}"
            data = {
                "prompt": req.prompt,
                "image_size": req.size,
                "num_inference_steps": req.steps,
                "num_images": 1,
            }
            if req.img2img_path and os.path.isfile(req.img2img_path):
                b = base64.b64encode(open(req.img2img_path, "rb").read()).decode()
                data["image_url"] = f"data:image/png;base64,{b}"
                data["strength"] = req.strength
                url = f"https://fal.run/{model_id}/image-to-image"
            job.log("Requesting fal.ai...")
            r = requests.post(
                url,
                headers={"Authorization": f"Key {req.fal_key}"},
                json=data,
                timeout=180,
            )
            if r.status_code >= 400:
                raise RuntimeError(f"fal.ai {r.status_code}: {r.text[:300]}")
            paths = []
            for i, im in enumerate((r.json().get("images") or [])):
                iu = im.get("url")
                if not iu:
                    continue
                content = requests.get(iu, timeout=120).content
                fp = out_dir / f"fal_{int(time.time())}_{i}.png"
                fp.write_bytes(content)
                job.log(f"wrote {fp}")
                paths.append(str(fp))
            job.result = {"files": paths}

        return work

    job = Job("imagestudio-generate")
    job.result = {"files": []}
    state.jobs[job.id] = job
    job.thread = threading.Thread(
        target=_run_job, args=(job, make_work(job)), daemon=True
    )
    job.thread.start()
    return {"job_id": job.id}


class UpscaleRequest(BaseModel):
    input_path: str
    scale: float = 2.0
    method: str = "lanczos"  # lanczos | bicubic | hamming
    sharpen: bool = True
    out_dir: str


@app.post("/api/imagestudio/upscale")
def imagestudio_upscale(req: UpscaleRequest):
    if not os.path.exists(req.input_path):
        raise HTTPException(400, "no such input file/folder")
    from PIL import Image, ImageFilter

    resample = {
        "lanczos": Image.LANCZOS,
        "bicubic": Image.BICUBIC,
        "hamming": Image.HAMMING,
    }[req.method]
    out_dir = Path(req.out_dir)
    files = (
        [req.input_path]
        if os.path.isfile(req.input_path)
        else [
            str(p)
            for p in Path(req.input_path).iterdir()
            if p.suffix.lower() in config.IMAGE_EXTS
        ]
    )

    def make_work(job):
        def work():
            out_dir.mkdir(parents=True, exist_ok=True)
            for p in files:
                try:
                    im = Image.open(p)
                    im = im.resize(
                        (int(im.width * req.scale), int(im.height * req.scale)),
                        resample,
                    )
                    if req.sharpen:
                        im = im.filter(
                            ImageFilter.UnsharpMask(radius=2, percent=110, threshold=3)
                        )
                    fp = out_dir / (Path(p).stem + f"_x{req.scale:g}.png")
                    im.save(fp)
                    job.log(f"wrote {fp.name}")
                except Exception as e:
                    job.log(f"skip {os.path.basename(p)}: {e}")

        return work

    job = Job("imagestudio-upscale")
    state.jobs[job.id] = job
    job.thread = threading.Thread(
        target=_run_job, args=(job, make_work(job)), daemon=True
    )
    job.thread.start()
    return {"job_id": job.id}


# --------------------------------------------------------------------------
# Manga Downloader. Two engines:
#   - comix.to (CDP_SITES in mediaforge/modules/manga_fetch.py): the reader
#     draws pages on a canvas, so the chapter list and every page are fetched
#     by PanelForge's headless-Chrome fetcher (apps/panelforge/tools/
#     fetch_cli.py). Verified 2026-09-20 from this backend.
#   - every other site: the Selenium scrape below, an unmodified port of the
#     desktop module's methods into per-job closures. Selenium needs a Chrome
#     or Chromium on PATH, which this machine does not have, so this path is
#     unverified here.
# --------------------------------------------------------------------------
from mediaforge.modules import manga_fetch

try:
    from selenium import webdriver as _webdriver
    from selenium.webdriver.common.by import By as _By
    from selenium.webdriver.chrome.options import Options as _ChromeOptions

    HAVE_SELENIUM = True
except ImportError:
    HAVE_SELENIUM = False

_MANGA_IMG_BLACKLIST = (
    "avatar",
    "comment",
    "/user",
    "profile",
    "logo",
    "icon",
    "banner",
    "ads",
    "sprite",
    "placeholder",
    "loading",
)


def _manga_driver(headless):
    opts = _ChromeOptions()
    for a in (
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--window-size=1400,2000",
    ):
        opts.add_argument(a)
    if headless:
        opts.add_argument("--headless=new")
    return _webdriver.Chrome(options=opts)


class MangaFetchRequest(BaseModel):
    url1: str
    url2: str = ""
    headless: bool = False


def _cdp_fetch_list(url, job):
    """Whole series through the headless-Chrome fetcher: every chapter the
    site lists on every page of its own pager, one row per chapter and scan
    group, plus the group names, so the page can show who scanned what."""
    job.log("comix.to: reading the title page in headless Chrome...")
    r = manga_fetch.panelforge_fetch(["list", url, "--all"], job.log, job.should_stop)
    chapters = [
        {
            "num": c["number"],
            "title": c["title"],
            "url": c["url"],
            "group": c.get("group") or "",
        }
        for c in r.get("chapters", [])
    ]
    return {
        "title": r.get("title") or "Manga",
        "chapters": chapters,
        "groups": r.get("groups", []),
    }


@app.post("/api/manga/fetch")
def manga_fetch_route(req: MangaFetchRequest):
    cdp = manga_fetch.uses_panelforge_fetcher(req.url1)
    if not cdp and not HAVE_SELENIUM:
        raise HTTPException(
            409,
            "selenium not installed: pip install selenium, and install a Chromium/Chrome browser",
        )

    def make_work(job):
        def work():
            if cdp:
                job.result = _cdp_fetch_list(req.url1, job)
                job.log(
                    f"'{job.result['title']}' -- {len(job.result['chapters'])} chapter rows, "
                    f"{len(job.result['groups'])} scan group(s)."
                )
                return
            job.log("Launching browser...")
            d = _manga_driver(req.headless)
            found, title = {}, "Manga"
            try:
                template = None
                if req.url2 and "2" in req.url2:
                    i = req.url2.rfind("2")
                    template = req.url2[:i] + "{page}" + req.url2[i + 1 :]
                    job.log(f"pattern mode: {template}")
                page, empty = 1, 0
                while not job.should_stop() and empty < 2:
                    url = (
                        req.url1
                        if page == 1
                        else (template.format(page=page) if template else None)
                    )
                    if url is None:
                        break
                    d.get(url)
                    time.sleep(3)
                    if page == 1:
                        title = (
                            re.sub(
                                r'[\\/*?:"<>|]',
                                "",
                                d.title.split("-")[0].split("|")[0].strip(),
                            )
                            or "Manga"
                        )
                    new = 0
                    for a in d.find_elements(_By.TAG_NAME, "a"):
                        try:
                            href = a.get_attribute("href") or ""
                            txt = (a.text or "").strip()
                            m = re.search(
                                r"(?:ch\.?|chapter|episode)\s*[-_ ]?(\d+(?:\.\d+)?)",
                                txt + " " + href,
                                re.I,
                            )
                            if m:
                                num = float(m.group(1))
                                if num not in found and href:
                                    found[num] = (txt or f"Chapter {num}", href)
                                    new += 1
                        except Exception:
                            continue
                    job.log(f"page {page}: +{new} chapters ({len(found)} total)")
                    empty = empty + 1 if new == 0 else 0
                    if not template:
                        if not _manga_click_next(d):
                            break
                    page += 1
            finally:
                d.quit()
            chapters = [
                {"num": k, "title": found[k][0], "url": found[k][1], "group": ""}
                for k in sorted(found)
            ]
            job.log(f"'{title}' -- {len(chapters)} chapters.")
            job.result = {"title": title, "chapters": chapters, "groups": []}

        return work

    job = Job("manga-fetch")
    job.result = {"title": "", "chapters": [], "groups": []}
    state.jobs[job.id] = job
    job.thread = threading.Thread(
        target=_run_job, args=(job, make_work(job)), daemon=True
    )
    job.thread.start()
    return {"job_id": job.id}


def _manga_click_next(d):
    for xp in (
        "//a[normalize-space(text())='>']",
        "//button[normalize-space(text())='>']",
        "//a[contains(@class,'next')]",
        "//button[contains(@class,'next')]",
        "//a[contains(text(),'Next')]",
    ):
        try:
            for el in d.find_elements(_By.XPATH, xp):
                if el.is_displayed() and "disabled" not in (
                    el.get_attribute("class") or ""
                ):
                    d.execute_script(
                        "arguments[0].scrollIntoView({block:'center'});", el
                    )
                    time.sleep(0.4)
                    d.execute_script("arguments[0].click();", el)
                    time.sleep(2)
                    return True
        except Exception:
            continue
    return False


def _manga_img_urls(d):
    urls = []
    for img in d.find_elements(_By.TAG_NAME, "img"):
        try:
            src = (
                img.get_attribute("src")
                or img.get_attribute("data-src")
                or img.get_attribute("data-lazy-src")
                or ""
            )
            if not src.startswith("http") or any(
                b in src.lower() for b in _MANGA_IMG_BLACKLIST
            ):
                continue
            w = int(
                img.get_attribute("naturalWidth") or img.get_attribute("width") or 0
            )
            if w and w < 250:
                continue
            urls.append(src)
        except Exception:
            continue
    return urls


def _manga_save(session, url, folder, name, num):
    try:
        r = session.get(url, timeout=15)
        r.raise_for_status()
        ext = url.split("?")[0].rsplit(".", 1)[-1].lower()
        if ext not in ("jpg", "jpeg", "png", "webp"):
            ext = "jpg"
        (folder / f"{name}_{num:03d}.{ext}").write_bytes(r.content)
        return True
    except Exception:
        return False


def _manga_collect_scroll(d, session, folder, name, cfg, job, log):
    seen, n, empty = set(), 0, 0
    while not job.should_stop() and empty < cfg["patience"]:
        for src in _manga_img_urls(d):
            if src in seen:
                continue
            seen.add(src)
            n += 1
            if _manga_save(session, src, folder, name, n):
                empty = 0
            else:
                n -= 1
        h = d.execute_script("return document.body.scrollHeight")
        d.execute_script("window.scrollBy(0, Math.round(window.innerHeight*0.85));")
        time.sleep(cfg["delay"])
        new_h = d.execute_script("return document.body.scrollHeight")
        at_bottom = d.execute_script(
            "return (window.innerHeight + window.scrollY) >= document.body.scrollHeight - 5;"
        )
        if not _manga_img_urls(d) or (at_bottom and new_h == h):
            empty += 1
    log(f"[{name}] scroll finished -- {n} pages")


def _manga_collect_keys(d, session, folder, name, cfg, job, log):
    from selenium.webdriver.common.keys import Keys

    keymap = {
        "arrowright": Keys.ARROW_RIGHT,
        "arrowleft": Keys.ARROW_LEFT,
        "arrowdown": Keys.ARROW_DOWN,
        "space": Keys.SPACE,
        "d": "d",
        "a": "a",
    }
    key = keymap.get(cfg["key"].lower(), cfg["key"])
    seen, n, empty = set(), 0, 0
    for _ in range(400):
        if job.should_stop() or empty >= cfg["patience"]:
            break
        got = False
        for src in _manga_img_urls(d):
            if src in seen:
                continue
            seen.add(src)
            n += 1
            if _manga_save(session, src, folder, name, n):
                got = True
            else:
                n -= 1
        empty = 0 if got else empty + 1
        try:
            d.find_element(_By.TAG_NAME, "body").send_keys(key)
        except Exception:
            pass
        time.sleep(cfg["delay"])
    log(f"[{name}] key-nav finished -- {n} pages")


def _manga_compile(folder, name, out_root, cfg, log):
    import glob as _glob

    imgs = sorted(_glob.glob(str(folder / f"{name}_*")))
    if not imgs:
        return
    from PIL import Image

    pil, bad = [], []
    for p in imgs:
        try:
            pil.append(Image.open(p).convert("RGB"))
        except Exception:
            bad.append(os.path.basename(p))
    if bad:
        log(
            f"[{name}] {len(bad)} page(s) would not open and were left out: {', '.join(bad[:5])}"
        )
    if not pil:
        log(f"[{name}] compile skipped: no readable pages")
        return
    if cfg["pdf"]:
        pp = out_root / f"{name}.pdf"
        pil[0].save(pp, save_all=True, append_images=pil[1:])
        log(f"[{name}] -> {pp.name}")
    if cfg["cbz"]:
        import zipfile

        zp = out_root / f"{name}.cbz"
        with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
            for p in imgs:
                z.write(p, os.path.basename(p))
        log(f"[{name}] -> {zp.name}")


def _manga_chapter(name, url, out_root, cfg, job):
    folder = out_root / name
    folder.mkdir(parents=True, exist_ok=True)
    if manga_fetch.uses_panelforge_fetcher(url):
        job.log(f"[{name}] capturing pages in headless Chrome...")
        r = manga_fetch.panelforge_fetch(
            ["get", url, str(folder), name],
            lambda m: job.log(f"[{name}] {m}"),
            job.should_stop,
        )
        if not r.get("pages"):
            raise RuntimeError("no pages captured")
    else:
        d = _manga_driver(cfg["headless"])
        session = manga_fetch.robust_session()
        try:
            d.get(url)
            time.sleep(4)
            if cfg["nav"].startswith("Vertical"):
                _manga_collect_scroll(d, session, folder, name, cfg, job, job.log)
            else:
                _manga_collect_keys(d, session, folder, name, cfg, job, job.log)
        finally:
            d.quit()
    files = sorted(folder.glob(f"{name}_*"))
    job.log(f"[{name}] {len(files)} pages saved")
    if cfg["pdf"] or cfg["cbz"]:
        _manga_compile(folder, name, out_root, cfg, job.log)
    if cfg["del_raw"]:
        for p in folder.glob(f"{name}_*"):
            p.unlink()
        try:
            folder.rmdir()
        except OSError:
            pass


_MANGA_DEFAULT_DIR = os.path.expanduser("~/Downloads/MediaForge/Manga")


class MangaDownloadRequest(BaseModel):
    chapters: list[tuple[str, str]] = Field(max_length=10000)  # [[name, url], ...]
    out_dir: str
    title: str = "Manga"
    nav: str = "Vertical scroll (long strip)"
    key: str = "ArrowRight"
    delay: float = 1.5
    patience: int = 10
    headless: bool = False
    threads: int = 3
    pdf: bool = True
    cbz: bool = False
    del_raw: bool = False


@app.post("/api/manga/download")
def manga_download(req: MangaDownloadRequest):
    if not req.chapters:
        raise HTTPException(400, "no chapters selected")
    cdp = all(manga_fetch.uses_panelforge_fetcher(url) for _name, url in req.chapters)
    if not cdp and not HAVE_SELENIUM:
        raise HTTPException(
            409,
            "selenium not installed: pip install selenium, and install a Chromium/Chrome browser",
        )
    out_dir = (
        os.path.expanduser(req.out_dir.strip())
        if req.out_dir.strip()
        else _MANGA_DEFAULT_DIR
    )
    out_root = Path(out_dir) / (
        re.sub(r'[\\/*?:"<>|]', "", req.title).strip() or "Manga"
    )
    cfg = {
        "nav": req.nav,
        "key": req.key,
        "delay": req.delay,
        "patience": req.patience,
        "headless": req.headless,
        "pdf": req.pdf,
        "cbz": req.cbz,
        "del_raw": req.del_raw,
    }
    # one headless Chrome per chapter on the comix.to path; two is what the
    # laptop takes comfortably (a third makes every capture slower)
    threads = min(req.threads, 2) if cdp else req.threads

    def make_work(job):
        def work():
            from concurrent.futures import ThreadPoolExecutor, as_completed

            out_root.mkdir(parents=True, exist_ok=True)
            job.log(
                f"-> {out_root}  ({len(req.chapters)} chapters, {threads} at a time)"
            )
            done = failed = 0
            with ThreadPoolExecutor(max_workers=threads) as ex:
                futs = {
                    ex.submit(_manga_chapter, name, url, out_root, cfg, job): name
                    for name, url in req.chapters
                }
                for fut in as_completed(futs):
                    try:
                        fut.result()
                        done += 1
                    except Exception as e:
                        failed += 1
                        job.log(f"[{futs[fut]}] failed: {e}")
                    job.progress((done + failed) / len(futs))
            job.log(f"\nAll chapters done: {done} saved, {failed} failed -> {out_root}")
            job.result = {"out_root": str(out_root), "done": done, "failed": failed}

        return work

    job = Job("manga-download")
    state.jobs[job.id] = job
    job.thread = threading.Thread(
        target=_run_job, args=(job, make_work(job)), daemon=True
    )
    job.thread.start()
    return {"job_id": job.id}


# The shared Forge frontend kit (forge.css / forge.js) lives one level above
# apps/ so all three tools share one copy. Mounted before the catch-all "/"
# mount below, which would otherwise swallow the path. Skipped when missing so
# the app still runs standalone outside a Forge checkout.
_SHARED = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "shared")
if os.path.isdir(_SHARED):
    app.mount("/shared", StaticFiles(directory=_SHARED), name="shared")

app.mount("/", StaticFiles(directory="static", html=True), name="static")
