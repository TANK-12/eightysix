"""FastAPI backend for the local image/video generator.

Speed trick: every generation runs the diffusion model at a small native
resolution (fast) and then hands the result to a dedicated AI upscaler
(Real-ESRGAN, GPU-accelerated via Vulkan) to reach the final size. That is
what keeps this fast without sacrificing final image quality.

No content filter / safety-checker / prompt moderation is wired in anywhere
in this stack by design -- this is a local, offline tool.
"""

import base64
import binascii
import json
import logging
import os
import shutil
import threading
import time
from pathlib import Path
from typing import Annotated, List, Literal, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import AfterValidator, BaseModel, ConfigDict, Field

import config
import engine
import library
import model_manager
import longform
import motion
import video_models
from hybrid import Cancelled, HybridScheduler
from longform import LongformJob

app = FastAPI(title="AI Studio")


@app.exception_handler(engine.EngineError)
def _engine_error(_request: Request, exc: engine.EngineError):
    """The sd-server said no (or is down). Tell the page in words instead of
    a bare 500 with a traceback in the log."""
    return JSONResponse(status_code=502, content={"detail": str(exc)})


@app.exception_handler(Cancelled)
def _cancelled(_request: Request, _exc: Cancelled):
    """A job stopped by its Cancel button: a calm 409, not a 500."""
    return JSONResponse(status_code=409, content={"detail": "cancelled"})


@app.exception_handler(RequestValidationError)
def _bad_request(_request: Request, exc: RequestValidationError):
    """A 422 naming each field and what is wrong with it. FastAPI's own reply
    echoes the rejected value back, which could not be sent at all for a NaN
    (a 500 instead) and repeated a whole 4000-character prompt."""
    detail = [
        {
            "loc": list(e.get("loc", ())),
            "msg": str(e.get("msg", "")),
            "type": e.get("type"),
        }
        for e in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": detail})


library.init()


@app.on_event("startup")
def _startup():
    if model_manager.get_active_id():
        try:
            model_manager.servers.start()
        except RuntimeError as e:
            # e.g. the active model needs an engine build that is missing; the
            # page still opens and the Models panel says what is wrong.
            logging.getLogger("ai-studio").warning("sd-server not started: %s", e)
    # else: no model installed yet -- the UI's Models panel handles first-run download.


@app.on_event("shutdown")
def _shutdown():
    job = video_models.running_job()
    if job:
        job.cancel()
    try:
        import worlds  # pyright: ignore[reportMissingImports]

        for sid in worlds.manager().running():
            worlds.stop_session(sid)
    except Exception as e:  # never block shutdown on a world
        logging.getLogger("ai-studio").warning("world stop failed: %s", e)
    model_manager.servers.stop()


# ---- heavy-job guard (model_manager.busy): a model video or a 3D world holds
# most of the RAM, so the image servers stay down and other heavy jobs wait.


def _video_probe():
    job = video_models.running_job()
    if job is None:
        return None
    return {"kind": "video", "id": job.job_id, "detail": model_manager.VIDEO_BUSY}


def _world_probe():
    try:
        import worlds  # pyright: ignore[reportMissingImports]
    except ImportError:
        return None
    running = worlds.manager().running()
    if not running:
        return None
    return {"kind": "world", "id": running[0], "detail": model_manager.WORLD_BUSY}


model_manager.register_busy_probe(_video_probe)
model_manager.register_busy_probe(_world_probe)


@app.exception_handler(model_manager.Busy)
def _busy(_request: Request, exc: model_manager.Busy):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.get("/api/busy")
def busy_state():
    """The heavy job running now ({kind: video|world, id, detail}) or null;
    the page disables the other Go buttons while it is set."""
    return {"busy": model_manager.busy()}


def _require_active_model():
    if model_manager.get_active_id() is None:
        raise HTTPException(
            409, "no model installed -- download one from the Models panel first"
        )
    try:
        model_manager.ensure_running()
    except RuntimeError as e:  # Busy, or a model that cannot run
        raise HTTPException(409, str(e))


# Bounds on every number a page (or a stray script) can send, so a typo such
# as width 51200 or 9999 keyframes is a calm 422 instead of an hours-long job
# or a crashed sd-server. They sit well outside what the page itself offers.
PROMPT_MAX = 4000
Size = Field(default=None, ge=64, le=2048)
Steps = Field(default=None, ge=1, le=150)
Cfg = Field(default=None, ge=0, le=30)
Seed = Field(default=-1, ge=-1, le=2**32 - 1)


def _known_motion(name: str) -> str:
    if name not in motion.PRESETS:
        raise ValueError(f"unknown motion; one of {', '.join(motion.PRESETS)}")
    return name


Motion = Annotated[str, AfterValidator(_known_motion)]


class ImageRequest(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    prompt: str = Field(max_length=PROMPT_MAX)
    negative_prompt: str = Field(default="", max_length=PROMPT_MAX)
    # None = use the active model's default resolution
    width: Optional[int] = Size
    height: Optional[int] = Size
    steps: Optional[int] = Steps  # None = use the active model's recommended value
    cfg_scale: Optional[float] = Cfg
    seed: int = Seed
    upscale: bool = True
    upscale_scale: int = Field(default=4, ge=2, le=4)  # 2, 3, or 4x
    quality_upscale: bool = (
        False  # False = fast small model, True = sharper x4plus model
    )
    output_format: Literal["jpg", "png"] = (
        "jpg"  # "jpg" (compressed, default) or "png" (lossless, larger)
    )
    jpg_quality: int = Field(default=92, ge=1, le=100)
    # >1 fans out across the iGPU AND CPU servers concurrently.
    batch_count: int = Field(default=1, ge=1, le=8)
    # A single image is fastest GPU-only (diffusion is sequential,
    # so splitting one image's stages across devices can't overlap
    # and would only slow it down) -- the real "use both at once"
    # win is independent images in a batch running in parallel.


class Scene(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    prompt: str = Field(max_length=PROMPT_MAX)
    negative_prompt: str = Field(default="", max_length=PROMPT_MAX)
    frames: int = Field(default=6, ge=1, le=60)  # distinct AI keyframes in this scene
    motion: Motion = (
        "static"  # static, pan-left/right/up/down, zoom-in/out, orbit-cw/ccw
    )
    # img2img "healing" denoise strength after the motion warp
    strength: float = Field(default=0.35, ge=0, le=1)
    seed: int = Seed


class VideoRequest(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    # Simple mode: just fill these in (single implicit scene).
    prompt: str = Field(default="", max_length=PROMPT_MAX)
    negative_prompt: str = Field(default="", max_length=PROMPT_MAX)
    motion: Motion = "static"
    keyframes: int = Field(default=4, ge=1, le=60)
    motion_strength: float = Field(default=0.35, ge=0, le=1)
    seed: int = Seed

    # Longform mode: a storyboard of scenes overrides the simple fields above.
    scenes: List[Scene] = Field(default=[], max_length=20)

    width: int = Field(default=512, ge=64, le=2048)
    height: int = Field(default=512, ge=64, le=2048)
    steps: Optional[int] = Steps
    cfg_scale: Optional[float] = Cfg
    # interpolated output frames per keyframe gap
    hold_frames: int = Field(default=8, ge=1, le=60)
    fps: int = Field(default=12, ge=1, le=60)
    upscale: bool = True
    upscale_scale: int = Field(default=4, ge=2, le=4)
    quality_upscale: bool = False

    # False (the default): answer at once with the job id and run in the
    # background; poll GET /api/jobs/{id}/state. True: wait and answer with
    # the finished result, as before the rebuild.
    wait: bool = False

    # Longform quality/perf controls.
    use_cpu: bool = True  # run a second sd-server on CPU in parallel with the iGPU
    # every N frames, re-base the motion warp on the newest healed frame
    anchor_interval: int = Field(default=4, ge=1, le=100)
    # how strongly each frame's colours are pulled toward the scene's anchor (0-1)
    anchor_weight: float = Field(default=0.15, ge=0, le=1)
    # frames blended across each scene boundary
    crossfade_frames: int = Field(default=3, ge=0, le=30)


def _render_image(req, rs, width, height, seed, server_url):
    """Runs one full txt2img -> (optional) upscale -> save pipeline against
    whichever sd-server URL it's given, and returns (job_id, url, gen_time,
    upscale_time). Used both for the single-image fast path (GPU only) and,
    per-task, from a HybridScheduler batch (GPU AND CPU concurrently)."""
    job_id = engine.new_id()
    work_dir = config.OUTPUTS_DIR / job_id
    work_dir.mkdir(parents=True, exist_ok=True)

    ext = "jpg" if req.output_format == "jpg" else "png"
    raw_path = work_dir / "raw.png"
    upscaled_path = work_dir / "upscaled.png"
    final_path = work_dir / f"final.{ext}"

    t0 = time.time()
    engine.txt2img(
        prompt=req.prompt,
        negative_prompt=req.negative_prompt,
        width=width,
        height=height,
        steps=req.steps if req.steps is not None else rs["steps"],
        cfg_scale=req.cfg_scale if req.cfg_scale is not None else rs["cfg_scale"],
        seed=seed,
        out_path=str(raw_path),
        sampler=rs["sampler"],
        use_lcm=rs["use_lcm"],
        server_url=server_url,
    )
    gen_time = time.time() - t0

    upscale_time = 0.0
    if req.upscale:
        model = (
            config.UPSCALE_MODEL_QUALITY
            if req.quality_upscale
            else config.UPSCALE_MODEL_FAST
        )
        t1 = time.time()
        engine.upscale(
            str(raw_path), str(upscaled_path), model, scale=req.upscale_scale
        )
        upscale_time = time.time() - t1
        source_path = upscaled_path
    else:
        source_path = raw_path

    if ext == "jpg":
        Image.open(source_path).convert("RGB").save(final_path, quality=req.jpg_quality)
    else:
        shutil.copy(source_path, final_path)

    url = f"/outputs/{job_id}/final.{ext}"
    meta = {**req.model_dump(), "width": width, "height": height, "seed": seed}
    library.record(
        job_id,
        "image",
        req.prompt,
        req.negative_prompt,
        meta,
        url,
        round(gen_time + upscale_time, 2),
    )
    return job_id, url, gen_time, upscale_time


@app.post("/api/generate/image")
def generate_image(req: ImageRequest):
    _require_active_model()
    if not req.prompt.strip():
        raise HTTPException(400, "prompt is required")

    rs = model_manager.run_settings(model_manager.get_active_entry())
    width = req.width if req.width is not None else rs["default_width"]
    height = req.height if req.height is not None else rs["default_height"]

    if req.batch_count <= 1:
        job_id, url, gen_time, upscale_time = _render_image(
            req, rs, width, height, req.seed, config.SD_SERVER_URL
        )
        return {
            "id": job_id,
            "url": url,
            "gen_seconds": round(gen_time, 2),
            "upscale_seconds": round(upscale_time, 2),
            "total_seconds": round(gen_time + upscale_time, 2),
        }

    # Batch mode: N independent images have no sequential dependency on each
    # other, so unlike a single image they genuinely can run on the iGPU and
    # the CPU at the same time -- the scheduler hands each one to whichever
    # backend frees up soonest instead of a fixed split.
    count = req.batch_count
    seeds = [req.seed if req.seed == -1 else req.seed + i for i in range(count)]
    # The CPU sd-server only runs for the small models (see
    # engine_flags.wants_cpu_helper); otherwise the batch stays on the iGPU.
    scheduler = HybridScheduler(use_cpu=model_manager.servers.has_cpu)
    scheduler.start()
    try:
        tasks = [
            (
                lambda server_url, s=seed: _render_image(
                    req, rs, width, height, s, server_url
                )
            )
            for seed in seeds
        ]
        results: list = scheduler.run_all(tasks)
    finally:
        scheduler.shutdown()

    batch = [
        {
            "id": job_id,
            "url": url,
            "gen_seconds": round(gen_time, 2),
            "upscale_seconds": round(upscale_time, 2),
            "total_seconds": round(gen_time + upscale_time, 2),
            "worker": worker_name,
        }
        for (job_id, url, gen_time, upscale_time), worker_name, _elapsed in results
    ]
    return {
        "batch": batch,
        "id": batch[-1]["id"],
        "url": batch[-1]["url"],
        "total_seconds": round(sum(b["total_seconds"] for b in batch), 2),
        "wall_seconds": round(max(elapsed for _r, _w, elapsed in results), 2),
        "workers": scheduler.stats(),
    }


class EditRequest(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    prompt: str = Field(max_length=PROMPT_MAX)
    negative_prompt: str = Field(default="", max_length=PROMPT_MAX)
    # The picture to change: a data URL / base64 PNG or JPEG, or the URL of an
    # earlier result ("/outputs/<id>/final.jpg") -- same fields as model-video.
    start_image: Optional[str] = Field(default=None, max_length=30_000_000)
    start_image_url: Optional[str] = Field(default=None, max_length=300)
    strength: float = Field(default=0.6, ge=0.1, le=0.95)  # how much may change
    steps: Optional[int] = Steps
    cfg_scale: Optional[float] = Cfg
    seed: int = Seed
    upscale: bool = True
    upscale_scale: int = Field(default=4, ge=2, le=4)
    quality_upscale: bool = False
    output_format: Literal["jpg", "png"] = "jpg"
    jpg_quality: int = Field(default=92, ge=1, le=100)


def _edit_size(path, base):
    """The source picture's shape at the model's working size: the long side
    becomes `base`, both sides rounded to a multiple of 64."""
    with Image.open(path) as im:
        w, h = im.size
    scale = base / max(w, h)
    return (
        max(64, round(w * scale / 64) * 64),
        max(64, round(h * scale / 64) * 64),
    )


@app.post("/api/generate/edit")
def generate_edit(req: EditRequest):
    """Change a picture by prompt with the active image model (img2img)."""
    if not req.prompt.strip():
        raise HTTPException(400, "prompt is required")
    if not (req.start_image or req.start_image_url):
        raise HTTPException(400, "a picture to edit is required")
    _require_active_model()
    rs = model_manager.run_settings(model_manager.get_active_entry())
    job_id = engine.new_id()
    work_dir = config.OUTPUTS_DIR / job_id
    src = _save_start_image(req, work_dir)
    assert src is not None
    width, height = _edit_size(src, max(rs["default_width"], rs["default_height"]))

    ext = req.output_format
    raw_path = work_dir / "raw.png"
    t0 = time.time()
    engine.img2img(
        prompt=req.prompt,
        negative_prompt=req.negative_prompt,
        init_image=src,
        width=width,
        height=height,
        steps=req.steps if req.steps is not None else rs["steps"],
        cfg_scale=req.cfg_scale if req.cfg_scale is not None else rs["cfg_scale"],
        strength=req.strength,
        seed=req.seed,
        out_path=str(raw_path),
        sampler=rs["sampler"],
        use_lcm=rs["use_lcm"],
    )
    gen_time = time.time() - t0
    upscale_time = 0.0
    source = raw_path
    if req.upscale:
        t1 = time.time()
        source = work_dir / "upscaled.png"
        engine.upscale(
            str(raw_path),
            str(source),
            (
                config.UPSCALE_MODEL_QUALITY
                if req.quality_upscale
                else config.UPSCALE_MODEL_FAST
            ),
            scale=req.upscale_scale,
        )
        upscale_time = time.time() - t1
    final_path = work_dir / f"final.{ext}"
    if ext == "jpg":
        Image.open(source).convert("RGB").save(final_path, quality=req.jpg_quality)
    else:
        shutil.copy(source, final_path)
    url = f"/outputs/{job_id}/final.{ext}"
    total = round(gen_time + upscale_time, 2)
    meta = {
        **req.model_dump(exclude={"start_image"}),
        "width": width,
        "height": height,
        "edit": True,
    }
    library.record(job_id, "image", req.prompt, req.negative_prompt, meta, url, total)
    return {
        "id": job_id,
        "url": url,
        "gen_seconds": round(gen_time, 2),
        "upscale_seconds": round(upscale_time, 2),
        "total_seconds": total,
    }


@app.post("/api/generate/video")
def generate_video(req: VideoRequest):
    _require_active_model()
    scenes = req.scenes or [
        Scene(
            prompt=req.prompt,
            negative_prompt=req.negative_prompt,
            frames=req.keyframes,
            motion=req.motion,
            strength=req.motion_strength,
            seed=req.seed,
        )
    ]
    if not any(s.prompt.strip() for s in scenes):
        raise HTTPException(400, "at least one scene needs a prompt")

    rs = model_manager.run_settings(model_manager.get_active_entry())
    job_id = engine.new_id()
    work_dir = config.OUTPUTS_DIR / job_id

    job = LongformJob(
        job_id=job_id,
        work_dir=work_dir,
        scenes=[s.model_dump() for s in scenes],
        width=req.width,
        height=req.height,
        steps=req.steps if req.steps is not None else rs["steps"],
        cfg_scale=req.cfg_scale if req.cfg_scale is not None else rs["cfg_scale"],
        sampler=rs["sampler"],
        use_lcm=rs["use_lcm"],
        anchor_interval=req.anchor_interval,
        anchor_weight=req.anchor_weight,
        crossfade_frames=req.crossfade_frames,
        use_cpu=req.use_cpu and model_manager.servers.has_cpu,
        upscale=req.upscale,
        upscale_model=(
            config.UPSCALE_MODEL_QUALITY
            if req.quality_upscale
            else config.UPSCALE_MODEL_FAST
        ),
        upscale_scale=req.upscale_scale,
    )

    # The URL is known up front, so state.json has it the moment status
    # turns "done"; timings are added when the job finishes.
    job._set(url=f"/outputs/{job_id}/final.mp4")
    if req.wait:
        return _run_video_job(job, req, scenes)
    threading.Thread(
        target=_run_video_job_quietly, args=(job, req, scenes), daemon=True
    ).start()
    return {"id": job_id, "status": "running", "url": None}


def _run_video_job(job, req, scenes):
    """Keyframes -> upscale -> interpolate -> encode -> library. Progress and
    the outcome go to state.json (GET /api/jobs/{id}/state)."""
    t0 = time.time()
    frame_paths, backend_stats = job.run()
    gen_time = time.time() - t0

    source_dir, upscale_time = job.upscale_all(frame_paths)

    video_path = job.work_dir / "final.mp4"
    interp_time = job.interpolate_and_encode(
        source_dir, req.hold_frames, req.fps, video_path
    )

    total_seconds = round(gen_time + upscale_time + interp_time, 2)
    url = f"/outputs/{job.job_id}/final.mp4"
    combined_prompt = " | ".join(s.prompt for s in scenes)
    library.record(
        job.job_id,
        "video",
        combined_prompt,
        req.negative_prompt,
        req.model_dump(),
        url,
        total_seconds,
    )
    result = {
        "id": job.job_id,
        "url": url,
        "gen_seconds": round(gen_time, 2),
        "upscale_seconds": round(upscale_time, 2),
        "interpolate_seconds": round(interp_time, 2),
        "total_seconds": total_seconds,
        "backend_stats": backend_stats,
        "frame_count": len(frame_paths),
    }
    job._set(**{k: v for k, v in result.items() if k != "id"})
    return result


def _run_video_job_quietly(job, req, scenes):
    """Background version: failures and cancels are already in state.json
    (longform records them); anything else is recorded here."""
    try:
        _run_video_job(job, req, scenes)
    except Cancelled:
        pass
    except Exception as e:
        if job.state.get("status") == "running":
            job._set(status="failed", error=str(e)[:2000])
        logging.getLogger("ai-studio").warning("video job %s failed: %s", job.job_id, e)


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str):
    """Stop a running job: a warp video (longform) at its next frame, or a
    model video at once. Safe to call for a job that already finished."""
    if not job_id.isalnum():
        raise HTTPException(400, "invalid id")
    vjob = video_models.get_job(job_id)
    if vjob is not None:
        if vjob.state == "running":
            vjob.cancel()
        return {"id": job_id, "cancel_requested": True, "status": vjob.state}
    if not longform.request_cancel(config.OUTPUTS_DIR / job_id):
        raise HTTPException(404, "no such job")
    return {"id": job_id, "cancel_requested": True}


@app.get("/api/jobs/{job_id}/state")
def job_state(job_id: str):
    if not job_id.isalnum():
        raise HTTPException(400, "invalid id")
    path = config.OUTPUTS_DIR / job_id / "state.json"
    if not path.is_file():
        raise HTTPException(404, "no checkpoint state for this job")
    return json.loads(path.read_text())


@app.get("/api/models")
def list_models():
    """Every catalog model as a card, plus free disk space."""
    return model_manager.models_payload()


def _known(model_id):
    if model_id not in model_manager.CATALOG:
        raise HTTPException(404, "unknown model")
    return model_manager.CATALOG[model_id]


@app.get("/api/models/delete-all")
def delete_all_plan():
    """What "Delete all models" would remove, with sizes and default ticks."""
    return model_manager.delete_all_plan()


class DeleteAllRequest(BaseModel):
    ids: List[str] = Field(max_length=200)


@app.post("/api/models/delete-all")
def delete_all_models(body: DeleteAllRequest):
    return model_manager.delete_all(body.ids)


@app.get("/api/models/{model_id}/quote")
def quote_model(model_id: str):
    _known(model_id)
    return model_manager.quote(model_id)


@app.post("/api/models/{model_id}/download")
def download_model(model_id: str):
    _known(model_id)
    try:
        job = model_manager.start_download(model_id)
    except model_manager.DownloadError as e:
        raise HTTPException(e.status, e.message)
    if job is None:
        return {"status": "already installed", "download": None}
    return {"status": "started", "download": job}


@app.post("/api/models/{model_id}/cancel")
def cancel_download(model_id: str):
    _known(model_id)
    stopped = model_manager.cancel_download(model_id)
    return {"cancelled": stopped, "download": model_manager.download_state(model_id)}


@app.delete("/api/models/{model_id}")
def remove_model(model_id: str):
    _known(model_id)
    freed = model_manager.delete_model(model_id)
    return {"deleted": model_id, "freed_bytes": freed}


@app.post("/api/models/{model_id}/activate")
def activate_model(model_id: str):
    entry = _known(model_id)
    if not model_manager.is_installed(model_id):
        raise HTTPException(400, "not installed yet")
    can_run, note = model_manager.run_status(entry)
    if not can_run:
        raise HTTPException(409, note)
    kind = entry.get("kind", "image")
    if kind == "image":
        model_manager.servers.switch_to(model_id)
    elif kind == "video":
        model_manager.set_active_video_id(model_id)
    else:
        raise HTTPException(400, "3D worlds are started from their own panel")
    return {"active": model_id, "kind": kind}


class ModelVideoRequest(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    prompt: str = Field(max_length=PROMPT_MAX)
    negative_prompt: str = Field(default="", max_length=PROMPT_MAX)
    model_id: Optional[str] = None  # None = the active video model
    # Optional start picture: a data URL / base64 PNG or JPEG, or the URL of
    # an earlier result ("/outputs/<id>/final.jpg").
    start_image: Optional[str] = Field(default=None, max_length=30_000_000)
    start_image_url: Optional[str] = Field(default=None, max_length=300)
    frames: Optional[int] = Field(default=None, ge=1, le=257)
    width: Optional[int] = Field(default=None, ge=64, le=1920)
    height: Optional[int] = Field(default=None, ge=64, le=1920)
    steps: Optional[int] = Steps
    seed: int = Seed


def _output_file(url):
    """An earlier result's file from its /outputs/... URL, or None."""
    parts = url.strip("/").split("/")
    if len(parts) != 3 or parts[0] != "outputs":
        return None
    root = config.OUTPUTS_DIR.resolve()
    path = (config.OUTPUTS_DIR / parts[1] / parts[2]).resolve()
    return path if root in path.parents and path.is_file() else None


def _save_start_image(req, work_dir):
    if req.start_image_url:
        src = _output_file(req.start_image_url)
        if src is None:
            raise HTTPException(400, "start picture not found")
        data = src.read_bytes()
    elif req.start_image:
        raw = req.start_image.split(",", 1)[-1]
        try:
            data = base64.b64decode(raw, validate=True)
        except (binascii.Error, ValueError):
            raise HTTPException(400, "start picture is not a valid image")
    else:
        return None
    work_dir.mkdir(parents=True, exist_ok=True)
    path = work_dir / "start.png"
    try:
        import io

        Image.open(io.BytesIO(data)).convert("RGB").save(path)
    except Exception:
        raise HTTPException(400, "start picture is not a valid image")
    return path


def _record_model_video(req, job):
    library.record(
        job.job_id,
        "video",
        req.prompt,
        req.negative_prompt,
        {**req.model_dump(exclude={"start_image"}), "model_id": job.model_id},
        job.url,
        job.seconds or round(time.time() - job.started, 2),
    )


@app.post("/api/generate/model-video")
def generate_model_video(req: ModelVideoRequest):
    """Start a video from a real video model; answers at once with the job.
    Poll GET /api/generate/model-video/{id}; cancel with POST .../cancel."""
    if not req.prompt.strip():
        raise HTTPException(400, "prompt is required")
    model_id = req.model_id or model_manager.get_active_video_id()
    if model_id is None:
        raise HTTPException(
            409, "no video model installed -- download one from the Models panel first"
        )
    entry = _known(model_id)
    if entry.get("kind") != "video":
        raise HTTPException(400, "that model does not make videos")
    if not model_manager.is_installed(model_id):
        raise HTTPException(409, "that video model is not downloaded yet")
    can_run, note = model_manager.run_status(entry)
    if not can_run:
        raise HTTPException(409, note)
    try:
        model_manager.require_not_busy()  # a model video or a world running
    except model_manager.Busy as e:
        raise HTTPException(409, str(e))
    job_id = engine.new_id()
    start = _save_start_image(req, config.OUTPUTS_DIR / job_id)
    try:
        job = video_models.start(
            job_id,
            entry,
            model_manager.part_paths(entry),
            req.prompt,
            negative_prompt=req.negative_prompt,
            frames=req.frames,
            width=req.width,
            height=req.height,
            seed=req.seed,
            steps=req.steps,
            init_image=start,
            # The video model needs most of the RAM: stop the image servers;
            # they start again on the next image request.
            before_start=model_manager.servers.stop,
            on_done=lambda j: _record_model_video(req, j),
        )
    except video_models.VideoBusy as e:
        raise HTTPException(409, str(e))
    return job.snapshot()


@app.get("/api/generate/model-video/{job_id}")
def model_video_state(job_id: str):
    job = video_models.get_job(job_id) if job_id.isalnum() else None
    if job is None:
        raise HTTPException(404, "no such video job")
    return job.snapshot()


@app.post("/api/generate/model-video/{job_id}/cancel")
def cancel_model_video(job_id: str):
    job = video_models.get_job(job_id) if job_id.isalnum() else None
    if job is None:
        raise HTTPException(404, "no such video job")
    if job.state == "running":
        job.cancel()
    return job.snapshot()


# ---- 3D worlds (runners and sessions live in worlds/, docs/WORLDS.md) -------


def _worlds():
    try:
        import worlds  # pyright: ignore[reportMissingImports]
    except ImportError:
        raise HTTPException(503, model_manager.NOT_SET_UP)
    return worlds


def _world_call(fn, *args, **kwargs):
    """Run a worlds function, turning its WorldError into a plain HTTP error."""
    w = _worlds()
    try:
        return fn(*args, **kwargs)
    except w.WorldError as e:
        raise HTTPException(getattr(e, "status_code", 400), str(e))


class WorldSettings(BaseModel):
    """The only settings a request may change for a world; anything else
    (engine arguments above all) comes from the catalog entry alone."""

    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")

    seed: Optional[int] = Field(default=None, ge=-1, le=2**32 - 1)
    steps: Optional[int] = Field(default=None, ge=1, le=60)
    cfg_scale: Optional[float] = Field(default=None, ge=0, le=30)
    frames: Optional[int] = Field(default=None, ge=1, le=81)
    width: Optional[int] = Field(default=None, ge=64, le=1280)
    height: Optional[int] = Field(default=None, ge=64, le=1280)
    fps: Optional[int] = Field(default=None, ge=1, le=60)


class WorldStartRequest(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    prompt: str = Field(default="", max_length=PROMPT_MAX)
    start_image: Optional[str] = Field(default=None, max_length=30_000_000)
    start_image_url: Optional[str] = Field(default=None, max_length=300)
    actions: List[str] = Field(default=[], max_length=64)
    settings: Optional["WorldSettings"] = None


class WorldStepRequest(BaseModel):
    actions: List[str] = Field(max_length=64)


@app.get("/api/worlds")
def world_overview():
    """Running sessions and the move buttons (id -> label)."""
    w = _worlds()
    return {"sessions": w.list_sessions(), "actions": w.ACTION_LABELS}


@app.get("/api/worlds/runtime/{runner_id}")
def world_runtime(runner_id: str):
    plan = _worlds().runtime_plan(runner_id)
    if plan is None:
        raise HTTPException(404, "no runtime for that runner")
    return plan


@app.post("/api/worlds/{model_id}/start")
def world_start(model_id: str, req: WorldStartRequest):
    entry = _known(model_id)
    if entry.get("kind") != "world":
        raise HTTPException(400, "that model is not a 3D world")
    if not model_manager.is_installed(model_id):
        raise HTTPException(409, "that world model is not downloaded yet")
    w = _worlds()
    try:
        # a model video holds the memory; a second world is refused by worlds
        model_manager.require_not_busy(except_kind="world")
    except model_manager.Busy as e:
        raise HTTPException(409, str(e))
    image = _save_start_image(
        req, config.OUTPUTS_DIR / "world-uploads" / engine.new_id()
    )
    settings = req.settings.model_dump(exclude_none=True) if req.settings else {}
    # The world model needs the memory and the iGPU: stop the image servers
    # (they stay down while the world runs; see model_manager.busy).
    model_manager.servers.stop()
    return _world_call(
        w.start_session,
        entry,
        prompt=req.prompt,
        image=str(image) if image else None,
        actions=req.actions or None,
        settings=settings,
    )


@app.post("/api/worlds/sessions/{sid}/step")
def world_step(sid: str, req: WorldStepRequest):
    return _world_call(_worlds().step_session, sid, req.actions)


@app.get("/api/worlds/sessions/{sid}")
def world_poll(sid: str, since: int = 0):
    return _world_call(_worlds().poll_session, sid, since)


@app.post("/api/worlds/sessions/{sid}/stop")
def world_stop(sid: str):
    return _world_call(_worlds().stop_session, sid)


@app.get("/api/worlds/sessions/{sid}/frames/{name}")
def world_frame(sid: str, name: str):
    return FileResponse(_world_call(_worlds().frame_path, sid, name))


@app.post("/api/worlds/sessions/{sid}/clip")
def world_clip(sid: str):
    """Join the session's frames into one video; answers with its URL."""
    _world_call(_worlds().make_clip, sid)
    return {"url": f"/api/worlds/sessions/{sid}/clip"}


@app.get("/api/worlds/sessions/{sid}/clip")
def world_clip_file(sid: str):
    if not sid.replace("-", "").isalnum():
        raise HTTPException(400, "invalid id")
    path = Path(_worlds().manager().root) / sid / "walk.mp4"
    if not path.is_file():
        raise HTTPException(404, "no clip yet")
    return FileResponse(path)


@app.get("/api/library")
def search_library(q: str = "", kind: str = ""):
    return library.search(query=q, kind=kind or None)


@app.delete("/api/library/{job_id}")
def delete_generation(job_id: str):
    if not job_id.isalnum():
        raise HTTPException(400, "invalid id")
    found = library.delete(job_id)
    job_dir = config.OUTPUTS_DIR / job_id
    if job_dir.is_dir():
        shutil.rmtree(job_dir)
    elif not found:
        raise HTTPException(404, "not found")
    return {"deleted": job_id}


@app.get("/outputs/{job_id}/{filename}")
def get_output(job_id: str, filename: str):
    outputs_root = config.OUTPUTS_DIR.resolve()
    path = (config.OUTPUTS_DIR / job_id / filename).resolve()
    if outputs_root not in path.parents or not path.is_file():
        raise HTTPException(404, "not found")
    return FileResponse(path)


# The shared Forge frontend kit (forge.css / forge.js), two levels up from
# src/. Mounted before the catch-all "/" mount, which would otherwise swallow
# the path. Skipped when missing so AI Studio still runs outside Forge.
_SHARED = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "shared"
)
if os.path.isdir(_SHARED):
    app.mount("/shared", StaticFiles(directory=_SHARED), name="shared")

app.mount("/", StaticFiles(directory=str(config.STATIC_DIR), html=True), name="static")
