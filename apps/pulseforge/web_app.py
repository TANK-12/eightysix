"""FastAPI backend for PulseForge -- a music-video / visualizer studio.

Feed it a song plus (optionally) a background image, pixel-sprite pack or a
folder of video clips; pick a scene and an output format; get a YouTube-ready
MP4. Long renders run on a background thread and an SSE endpoint streams
batched progress -- the same Job pattern MediaForge and NovelForge use.

The audio analysis (analyze.py), the scene registry (scenes/) and the render
pipeline (render.py) carry all the logic; this file is the delivery layer.
"""

import asyncio
import json
import os
import queue
import shutil
import sys
import tempfile
import threading
import time
import uuid

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(ROOT, "static")
SHARED_DIR = os.environ.get("FORGE_SHARED_DIR") or os.path.join(
    ROOT, "..", "..", "shared"
)
sys.path.insert(0, os.path.abspath(SHARED_DIR))

try:
    import forge_art  # noqa: E402
except Exception:  # pragma: no cover - standalone without the shared kit
    forge_art = None

from pulseforge import analyze, autoregions, config, formats  # noqa: E402
from pulseforge import autopilot as autopilotmod  # noqa: E402
from pulseforge import recipes as recipesmod  # noqa: E402
from pulseforge import ambience as ambiencemod  # noqa: E402
from pulseforge import amvplan as amvplanmod  # noqa: E402
from pulseforge import beatfx as beatfxmod  # noqa: E402
from pulseforge import editstyles as editstylesmod  # noqa: E402
from pulseforge import musicmap as musicmapmod  # noqa: E402
from pulseforge import palette as palettemod  # noqa: E402
from pulseforge import shotdna as shotdnamod  # noqa: E402
from pulseforge import grades as gradesmod  # noqa: E402
from pulseforge import jan as janmod  # noqa: E402
from pulseforge import preflight as preflightmod  # noqa: E402
from pulseforge import projectfile as projectfilemod  # noqa: E402
from pulseforge import snapshots as snapshotsmod  # noqa: E402
from pulseforge import masks as masksmod  # noqa: E402
from pulseforge import presets as presetsmod  # noqa: E402
from pulseforge import project as projmod  # noqa: E402
from pulseforge import render as rendermod  # noqa: E402
from pulseforge import sequence as seqmod  # noqa: E402
from pulseforge import modulation as modmod  # noqa: E402
from pulseforge import strictjson  # noqa: E402
from pulseforge import tracklist as tracklistmod  # noqa: E402
from pulseforge import wand as wandmod  # noqa: E402
from pulseforge.emitters import emitters_as_list  # noqa: E402
from pulseforge.motion import effects_as_list  # noqa: E402
from pulseforge.scenes import scenes_as_list  # noqa: E402

app = FastAPI(title="PulseForge")


class RequestGuard:
    """Refuse two kinds of request before any route sees them.

    A "." or ".." path segment (sent as %2E%2E) made a project slug point at
    the data folder itself: DELETE /api/projects/%2E%2E removed all of
    ~/PulseForgeData. And NaN or Infinity in a JSON body either broke the 422
    answer or was saved into project.json, after which the project could not be
    opened. Both are a calm 400 now."""

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith("/api/"):
            return await self.inner(scope, receive, send)
        if any(seg in (".", "..") for seg in scope["path"].split("/")):
            return await _refuse(send, "bad path")
        ctype = dict(scope.get("headers") or []).get(b"content-type", b"").lower()
        if b"json" not in ctype:
            return await self.inner(scope, receive, send)
        chunks, more = [], True
        while more:
            msg = await receive()
            if msg["type"] != "http.request":
                return
            chunks.append(msg.get("body", b""))
            more = msg.get("more_body", False)
        body = b"".join(chunks)
        try:
            strictjson.loads(body or b"null")
        except ValueError as e:
            word = str(e) if str(e) in strictjson.NOT_FINITE else ""
            if word:
                return await _refuse(send, f"{word} is not a number this app takes")
        sent = False

        async def replay():
            nonlocal sent
            if sent:
                return await receive()
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}

        return await self.inner(scope, replay, send)


async def _refuse(send, detail):
    data = json.dumps({"detail": detail}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 400,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(data)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": data})


app.add_middleware(RequestGuard)


# --------------------------------------------------------------------------
# Jobs -- a single FIFO worker so several renders queue instead of colliding.
# --------------------------------------------------------------------------
class Job:
    def __init__(self, kind, project_slug, make_target):
        self.id = uuid.uuid4().hex[:12]
        self.kind = kind
        self.project = project_slug
        self.make_target = make_target
        self.status = "queued"  # queued | running | done | error | canceled
        self.error = None
        self.result = None
        self.created = time.time()
        self.stop_requested = threading.Event()
        self.events: queue.Queue = queue.Queue()

    def log(self, msg):
        self.events.put({"type": "log", "text": str(msg)})

    def progress(self, frac):
        self.events.put({"type": "progress", "frac": float(frac)})

    def should_stop(self):
        return self.stop_requested.is_set()

    def finish(self, status, error=None):
        self.status = status
        self.error = error
        self.events.put({"type": status, "error": error})

    def brief(self):
        return {
            "id": self.id,
            "kind": self.kind,
            "project": self.project,
            "status": self.status,
            "error": self.error,
        }


class AppState:
    def __init__(self):
        self.settings = config.load_settings()
        self.jobs: dict[str, Job] = {}
        self.q: queue.Queue = queue.Queue()
        self.running_job_id: str | None = None
        self.worker = threading.Thread(target=self._worker, daemon=True)
        self.worker.start()

    def save_settings(self):
        config.save_settings(self.settings)

    def _worker(self):
        while True:
            jid = self.q.get()
            job = self.jobs.get(jid)
            if not job or job.stop_requested.is_set():
                if job:
                    job.finish("canceled")
                continue
            job.status = "running"
            self.running_job_id = jid
            try:
                target = job.make_target(job)
                job.result = target()
                job.finish("done")
            except Exception as e:  # noqa: BLE001 - surface any failure to the client
                job.finish("error", str(e))
            finally:
                self.running_job_id = None
                self._prune()

    def _prune(self, keep=30):
        done = sorted(
            (
                j
                for j in self.jobs.values()
                if j.status in ("done", "error", "canceled")
            ),
            key=lambda j: j.created,
        )
        for j in done[:-keep] if len(done) > keep else []:
            self.jobs.pop(j.id, None)

    def enqueue(self, kind, project_slug, make_target):
        job = Job(kind, project_slug, make_target)
        self.jobs[job.id] = job
        self.q.put(job.id)
        return job

    def queue_view(self):
        pending = [
            self.jobs[jid].brief()
            for jid in list(self.q.queue)
            if jid in self.jobs and not self.jobs[jid].stop_requested.is_set()
        ]
        running = (
            self.jobs[self.running_job_id].brief()
            if self.running_job_id and self.running_job_id in self.jobs
            else None
        )
        return {"running": running, "queued": pending}


state = AppState()


def start_job(kind, project_slug, make_target):
    """Enqueue a job. make_target(job) -> callable is built by the worker just
    before the job runs, so it closes over live log/progress callbacks."""
    return state.enqueue(kind, project_slug, make_target)


@app.post("/api/jobs/{job_id}/stop")
def stop_job(job_id: str):
    job = state.jobs.get(job_id)
    if not job:
        raise HTTPException(404, "no such job")
    job.stop_requested.set()
    if job.status == "queued":
        job.finish("canceled")  # the worker also skips it when it reaches the id
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
        "result": job.result,
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
                if job.status in ("done", "error", "canceled"):
                    yield f"data: {json.dumps({'type': job.status, 'error': job.error})}\n\n"
                    return
                # still queued or running -- keep the connection open
                yield f"data: {json.dumps({'type': 'waiting', 'status': job.status})}\n\n"
                continue
            deadline = time.time() + 0.12
            while time.time() < deadline:
                try:
                    batch.append(job.events.get_nowait())
                except Exception:
                    break
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
# state / registries
# --------------------------------------------------------------------------
@app.get("/api/state")
def get_state():
    caps = config.ffmpeg_caps()
    return {
        "settings": state.settings,
        "ffmpeg": bool(caps["ffmpeg"]),
        "encoders": config.available_encoders(),
        "queue": state.queue_view(),
    }


@app.get("/api/scenes")
def get_scenes():
    return scenes_as_list()


@app.get("/api/formats")
def get_formats():
    return formats.as_list()


@app.get("/api/art-packs")
def get_art_packs():
    if not forge_art:
        return {"packs": [], "note": "shared forge_art not available"}
    lib = forge_art.library()
    return {
        "packs": [
            {"id": k, "label": v.get("label", k), "sprites": len(v.get("sprites", {}))}
            for k, v in lib.get("packs", {}).items()
        ],
        "palettes": list(lib.get("palettes", {}).keys()),
    }


class SettingsPatch(BaseModel):
    values: dict


@app.post("/api/settings")
def update_settings(patch: SettingsPatch):
    state.settings.update(patch.values)
    state.save_settings()
    return state.settings


# --------------------------------------------------------------------------
# projects
# --------------------------------------------------------------------------
class CreateProject(BaseModel):
    name: str = Field(max_length=300)


@app.get("/api/projects")
def list_projects():
    return [
        projmod.Project(s).summary()
        for s in projmod.list_projects()
        if s != PREVIEW_SLUG
    ]


@app.post("/api/projects")
def create_project(req: CreateProject):
    if not req.name.strip():
        raise HTTPException(400, "name is required")
    return projmod.create(req.name).summary()


@app.get("/api/projects/{slug}")
def get_project(slug: str):
    p = projmod.Project(slug)
    if not p.path().exists():
        raise HTTPException(404, "no such project")
    return {**p.summary(), "data": p.data}


@app.delete("/api/projects/{slug}")
def delete_project(slug: str):
    projmod.delete(slug)
    return {"ok": True}


class ProjectPatch(BaseModel):
    name: str | None = Field(None, max_length=300)
    scene: str | None = None
    params: dict | None = None
    format: str | None = None
    title_text: str | None = None
    subtitle_text: str | None = None
    text_position: str | None = None
    text_size: str | None = None
    # v3 -- the playlist and the shot list
    shots: list | None = None
    cards: list | None = None
    song_gap: float | None = None
    song_crossfade: float | None = None
    target_seconds: float | None = None
    ambience: dict | None = None
    overlay: dict | None = None
    song_gain: list | None = None
    fade_in: float | None = None
    fade_out: float | None = None


@app.put("/api/projects/{slug}")
def update_project(slug: str, patch: ProjectPatch):
    p = projmod.Project(slug)
    if not p.path().exists():
        raise HTTPException(404, "no such project")
    for k, v in patch.model_dump(exclude_none=True).items():
        p.data[k] = v
    p.save()
    return {**p.summary(), "data": p.data}


def _save_upload(upload: UploadFile) -> str:
    fd, tmp = tempfile.mkstemp(prefix="pf-up-")
    with os.fdopen(fd, "wb") as f:
        shutil.copyfileobj(upload.file, f)
    return tmp


@app.post("/api/projects/{slug}/audio")
def upload_audio(slug: str, file: UploadFile):
    p = projmod.Project(slug)
    if not p.path().exists():
        raise HTTPException(404, "no such project")
    if os.path.splitext(file.filename or "")[1].lower() not in config.AUDIO_EXTS:
        raise HTTPException(400, "not an audio file")
    tmp = _save_upload(file)
    try:
        p.set_audio(tmp, file.filename or "audio.mp3")
    finally:
        os.unlink(tmp)
    return p.summary()


@app.post("/api/projects/{slug}/asset")
def upload_asset(slug: str, file: UploadFile):
    p = projmod.Project(slug)
    if not p.path().exists():
        raise HTTPException(404, "no such project")
    tmp = _save_upload(file)
    try:
        name = p.add_asset(tmp, file.filename or "image.png")
    finally:
        os.unlink(tmp)
    return {**p.summary(), "added": name}


class ClipsFolder(BaseModel):
    path: str


@app.post("/api/projects/{slug}/clips-folder")
def set_clips_folder(slug: str, req: ClipsFolder):
    p = projmod.Project(slug)
    if not p.path().exists():
        raise HTTPException(404, "no such project")
    if not os.path.isdir(os.path.expanduser(req.path)):
        raise HTTPException(400, "not a folder")
    p.link_clips_folder(req.path)
    return p.summary()


class RemoveAsset(BaseModel):
    name: str


@app.post("/api/projects/{slug}/asset/remove")
def remove_asset(slug: str, req: RemoveAsset):
    p = projmod.Project(slug)
    p.remove_asset(req.name)
    return p.summary()


# --------------------------------------------------------------------------
# AI backdrop
# --------------------------------------------------------------------------
def _load_art_pack(p: "projmod.Project"):
    """If the chosen scene is the sprite swarm, resolve the pack + its palette."""
    if p.data.get("scene") != "swarm" or not forge_art:
        return None
    pack_id = (p.data.get("params") or {}).get("art_pack")
    lib = forge_art.library()
    packs = lib.get("packs", {})
    if not packs:
        return None
    pack = packs.get(pack_id) or next(iter(packs.values()))
    pal_id = pack.get("default_palette")
    palettes = lib.get("palettes", {})
    pal = palettes.get(pal_id) or (next(iter(palettes.values())) if palettes else {})
    pack = dict(pack)
    pack["_palette_colors"] = (pal or {}).get("colors", {})
    return pack


@app.post("/api/projects/{slug}/analyze")
def analyze_project(slug: str):
    p = projmod.Project(slug)
    ap = p.audio_path()
    if not ap:
        raise HTTPException(409, "attach a song first")
    fmt = formats.get(p.data.get("format"))

    def make_target(job):
        def work():
            feats = analyze.analyze(ap, fmt["fps"], progress=job.progress)
            analyze.save_features(str(p.features_path(fmt["fps"])), feats)
            return {
                "n_frames": int(feats["n_frames"]),
                "duration": feats["duration"],
                "beats": int(feats["beat"].sum()),
            }

        return work

    job = start_job("analyze", slug, make_target)
    return {"job_id": job.id}


class RenderReq(BaseModel):
    preview: bool = False


def _render_make_target(p: "projmod.Project", preview: bool):
    fmt_id = p.data.get("format", formats.DEFAULT_FORMAT)
    fmt = formats.get(fmt_id)
    scene_id = p.data.get("scene", "bars")
    params = dict(p.data.get("params") or {})
    params["_assets"] = p.resolved_assets()
    art_pack = _load_art_pack(p)

    feat = None
    fpath = p.features_path(fmt["fps"])
    if fpath.exists() and not preview:
        try:
            feat = analyze.load_features(str(fpath))
        except Exception:
            feat = None

    ts = time.strftime("%Y%m%d-%H%M%S")
    tag = "preview" if preview else fmt_id
    out = p.renders_dir() / f"{p.slug}_{tag}_{ts}.mp4"

    def make_target(job):
        def target():
            res = rendermod.render(
                p,
                scene_id,
                params,
                fmt_id,
                str(out),
                state.settings,
                feat=feat,
                art_pack=art_pack,
                log=job.log,
                progress=job.progress,
                should_stop=job.should_stop,
                preview=preview,
            )
            return {**res, "file": out.name}

        return target

    return make_target


@app.post("/api/projects/{slug}/preview")
def preview_render(slug: str):
    p = projmod.Project(slug)
    if not p.audio_path():
        raise HTTPException(409, "attach a song first")
    job = start_job("preview", slug, _render_make_target(p, preview=True))
    return {"job_id": job.id}


@app.post("/api/projects/{slug}/render")
def full_render(slug: str):
    p = projmod.Project(slug)
    if not p.audio_path():
        raise HTTPException(409, "attach a song first")
    job = start_job("render", slug, _render_make_target(p, preview=False))
    return {"job_id": job.id}


@app.get("/api/projects/{slug}/render-file")
def render_file(slug: str, name: str):
    p = projmod.Project(slug)
    f = p.renders_dir() / os.path.basename(name)
    if not f.exists():
        raise HTTPException(404, "no such render")
    return FileResponse(str(f), media_type="video/mp4", filename=f.name)


@app.post("/api/projects/{slug}/render-file/delete")
def delete_render(slug: str, req: RemoveAsset):
    p = projmod.Project(slug)
    f = p.renders_dir() / os.path.basename(req.name)
    if f.exists():
        f.unlink()
    return p.summary()


@app.post("/api/projects/{slug}/reveal")
def reveal_renders(slug: str):
    p = projmod.Project(slug)
    d = p.renders_dir()
    try:
        import subprocess

        subprocess.Popen(["xdg-open", str(d)])
    except Exception:
        pass
    return {"path": str(d)}


# --------------------------------------------------------------------------
# thumbnails
# --------------------------------------------------------------------------
class ThumbReq(BaseModel):
    render: str | None = None  # a render filename; default = newest
    t_seconds: float = 1.0
    title: str = ""
    subtitle: str = ""
    scrim: float = 0.0
    position: str = "bottom-left"


@app.post("/api/projects/{slug}/thumbnail")
def make_thumbnail(slug: str, req: ThumbReq):
    p = projmod.Project(slug)
    if not p.path().exists():
        raise HTTPException(404, "no such project")
    renders = sorted(p.renders_dir().glob("*.mp4"))
    if not renders:
        raise HTTPException(409, "render something first")
    src = (
        (p.renders_dir() / os.path.basename(req.render)) if req.render else renders[-1]
    )
    if not src.exists():
        raise HTTPException(404, "no such render")
    dst = p.thumbs_dir() / (src.stem + f"_{int(req.t_seconds)}s.png")
    try:
        rendermod.grab_thumbnail(
            str(src),
            str(dst),
            t_seconds=req.t_seconds,
            title=req.title,
            subtitle=req.subtitle,
            scrim=req.scrim,
            position=req.position,
        )
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    return {"thumbnail": dst.name}


@app.get("/api/projects/{slug}/thumbnail-file")
def thumbnail_file(slug: str, name: str):
    p = projmod.Project(slug)
    f = p.thumbs_dir() / os.path.basename(name)
    if not f.exists():
        raise HTTPException(404, "no such thumbnail")
    return FileResponse(str(f), media_type="image/png", filename=f.name)


# --------------------------------------------------------------------------
# album batch
# --------------------------------------------------------------------------
class BatchReq(BaseModel):
    folder: str
    scene: str = "bars"
    format: str = "long_1080p"
    params: dict = {}


@app.post("/api/batch")
def album_batch(req: BatchReq):
    folder = os.path.expanduser(req.folder)
    if not os.path.isdir(folder):
        raise HTTPException(400, "not a folder")
    tracks = sorted(
        os.path.join(folder, f)
        for f in os.listdir(folder)
        if os.path.splitext(f)[1].lower() in config.AUDIO_EXTS
    )
    if not tracks:
        raise HTTPException(409, "no audio files in that folder")
    album = os.path.basename(folder.rstrip("/")) or "album"
    made = []
    for track in tracks:
        title = os.path.splitext(os.path.basename(track))[0]
        p = autopilotmod.new_project(
            f"{album} - {title}", track, req.scene, req.format, req.params
        )
        job = start_job("render", p.slug, _render_make_target(p, preview=False))
        made.append({"slug": p.slug, "job_id": job.id, "title": title})
    return {"album": album, "count": len(made), "items": made}


# --------------------------------------------------------------------------
# Autopilot: a folder of songs in, upload-ready packages out
# --------------------------------------------------------------------------
class AutopilotRunReq(BaseModel):
    inbox: str
    recipe: str
    art: str | None = None


class LedgerReq(BaseModel):
    slug: str
    action: str  # "uploaded" | "figures"
    url: str | None = None
    month: str | None = None
    views: int = 0
    revenue: float = 0.0


def _autopilot_render(p, scene, params, fmt, out, log, progress, should_stop):
    return rendermod.render(
        p,
        scene,
        params,
        fmt,
        out,
        state.settings,
        feat=None,
        art_pack=_load_art_pack(p),
        log=log,
        progress=progress,
        should_stop=should_stop,
        preview=False,
    )


def _autopilot_prepare(p, recipe):
    """Living-still recipes need shots, a look and a length before they render.

    Built from the same route functions the Simple editor calls, so an
    Autopilot mix is exactly what you would get by hand in Simple mode and
    opens there for fine-tuning.
    """
    if recipe["scene"] != "living":
        return p
    look = recipe.get("look") or {}
    # one shot per song, cycling the pictures, so every pass is the same
    names = [os.path.basename(a) for a in p.data.get("assets") or []]
    n_songs = max(1, len(p.playlist_paths()))
    shots = [names[i % len(names)] for i in range(max(n_songs, len(names)))]
    shots_from_images(p.slug, BulkShotsReq(images=shots, replace=True))
    if look.get("preset") or look.get("grade"):
        apply_look_to_all(
            p.slug,
            ApplyAllReq(
                preset=look.get("preset", ""),
                grade=look.get("grade", ""),
                grade_amount=float(look.get("grade_amount", 0.7)),
            ),
        )
    p = projmod.Project(p.slug)
    for shot in p.data.get("shots") or []:
        shot["hold"] = "song"  # a picture per song, cycling through the mix
    # no target length here: Autopilot renders one pass and repeats the file
    if recipe.get("ambience"):
        p.data["ambience"] = dict(recipe["ambience"])
    p.save()
    return p


def _autopilot_chapters(p):
    try:
        return get_tracklist(p.slug).get("description", "")
    except Exception:  # noqa: BLE001 - chapters are a nicety, never a failure
        return ""


@app.get("/api/autopilot/recipes")
def autopilot_recipes():
    return {
        "recipes": [
            {
                **{k: r.get(k) for k in ("id", "label", "description", "format")},
                "format_label": formats.get(r["format"]).get("label", r["format"]),
                "per": r.get("per", "song"),
            }
            for r in recipesmod.recipes_as_list()
        ]
    }


@app.post("/api/autopilot/run")
def autopilot_run(req: AutopilotRunReq):
    try:
        todo, skipped = autopilotmod.plan_run(req.inbox, req.recipe, req.art)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except LookupError as e:
        raise HTTPException(409, str(e))
    if not todo:
        return {"job_id": None, "queued": [], "skipped": skipped}
    autopilotmod.queue_songs(todo, req.recipe)

    def make_target(job):
        def target():
            done = autopilotmod.run(
                todo,
                req.recipe,
                _autopilot_render,
                log=job.log,
                progress=job.progress,
                should_stop=job.should_stop,
                prepare_fn=_autopilot_prepare,
                chapters_fn=_autopilot_chapters,
            )
            return {"finished": done}

        return target

    job = start_job("autopilot", None, make_target)
    return {
        "job_id": job.id,
        "queued": [{"song": autopilotmod._label(t), "slug": t["slug"]} for t in todo],
        "skipped": skipped,
    }


@app.get("/api/autopilot/browse")
def autopilot_browse(path: str = ""):
    try:
        return autopilotmod.browse(path or None)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/autopilot/scan")
def autopilot_scan(inbox: str = "", art: str = "", recipe: str = "lofi_radio"):
    return autopilotmod.scan(inbox, art, recipe)


PREVIEW_SLUG = "autopilot-preview"  # hidden from the project list


def _living_preview(recipe, image, width):
    """One frame of a living-still recipe, built exactly like a real mix:
    the picture as a shot, the recipe's look applied, one still rendered."""
    from pulseforge.scenes import living

    projmod.delete(PREVIEW_SLUG)
    p = projmod.create(PREVIEW_SLUG)
    p.data["scene"], p.data["format"] = recipe["scene"], recipe["format"]
    p.save()
    p.add_asset(image, os.path.basename(image))
    p = _autopilot_prepare(p, recipe)
    shot = (p.data.get("shots") or [{}])[0]
    ctx = _living_ctx(p, shot, width, 12.0)
    return living.still(ctx, 3.0)


@app.get("/api/autopilot/preview")
def autopilot_preview(recipe: str, image: str = "", w: int = 480):
    """A real frame of `recipe` over `image` (a PNG), cached on disk."""
    from PIL import Image

    try:
        r = recipesmod.get_recipe(recipe)
    except KeyError:
        raise HTTPException(404, "no such recipe")
    image = os.path.expanduser(image) if image else ""
    if image and not os.path.isfile(image):
        raise HTTPException(404, "no such picture")
    if r["scene"] == "living" and not image:
        raise HTTPException(409, "add pictures to see this look")
    w = max(160, min(960, int(w)))
    out = autopilotmod.preview_path(r["id"], image, w)
    if not out.exists():
        try:
            if r["scene"] == "living":
                arr = _living_preview(r, image, w)
            else:
                arr = autopilotmod.preview_frame(r, image or None, w)
        except Exception as e:  # noqa: BLE001 - a preview never breaks the page
            raise HTTPException(400, f"could not draw a preview: {e}")
        out.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(arr).save(out)
    return FileResponse(str(out), media_type="image/png")


@app.get("/api/autopilot/package/{slug}/text")
def autopilot_package_text(slug: str):
    try:
        return autopilotmod.upload_text_of(slug)
    except KeyError:
        raise HTTPException(404, "no such package")


@app.get("/api/autopilot/packages")
def autopilot_packages():
    return {"packages": autopilotmod.package_list()}


@app.get("/api/autopilot/thumb/{slug}")
def autopilot_thumb(slug: str):
    f = autopilotmod.package_dir(os.path.basename(slug)) / "thumb.jpg"
    if not f.exists():
        raise HTTPException(404, "no thumbnail yet")
    return FileResponse(str(f), media_type="image/jpeg")


@app.post("/api/autopilot/reveal/{slug}")
def autopilot_reveal(slug: str):
    d = autopilotmod.package_dir(os.path.basename(slug))
    if not d.exists():
        raise HTTPException(404, "that package is not ready yet")
    try:
        import subprocess

        subprocess.Popen(["xdg-open", str(d)])
    except Exception:
        pass
    return {"path": str(d)}


@app.get("/api/autopilot/ledger")
def autopilot_ledger():
    return autopilotmod.ledger()


@app.post("/api/autopilot/ledger")
def autopilot_ledger_post(req: LedgerReq):
    try:
        if req.action == "uploaded":
            autopilotmod.mark_uploaded(req.slug, req.url)
        elif req.action == "figures":
            autopilotmod.record_figures(req.slug, req.month, req.views, req.revenue)
        else:
            raise HTTPException(400, "action must be uploaded or figures")
    except KeyError:
        raise HTTPException(404, "no such package")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return autopilotmod.ledger()


# --------------------------------------------------------------------------
# v3: the living-still studio
#
# Everything below serves the Scenery tab. The three registry endpoints are
# what make the editor generate itself -- it never hardcodes an effect name,
# an emitter or a transition, so adding one to `pulseforge/motion/` or
# `pulseforge/emitters/` puts it in the UI with its own controls.
# --------------------------------------------------------------------------
@app.get("/api/motion-effects")
def get_motion_effects():
    return effects_as_list()


@app.get("/api/emitters")
def get_emitters():
    return emitters_as_list()


@app.get("/api/transitions")
def get_transitions():
    return seqmod.transitions_as_list()


@app.get("/api/presets")
def get_presets():
    return presetsmod.presets_as_list()


@app.get("/api/modulation-sources")
def get_modulation_sources():
    """What a parameter can be tied to. The editor builds its picker from this."""
    return {"sources": modmod.SOURCES, "shapes": list(modmod.SHAPES)}


def _project_or_404(slug):
    p = projmod.Project(slug)
    if not p.path().exists():
        raise HTTPException(404, "no such project")
    return p


# ---- playlist ------------------------------------------------------------
@app.post("/api/projects/{slug}/songs")
def add_song(slug: str, file: UploadFile):
    p = _project_or_404(slug)
    tmp = _save_upload(file)
    try:
        name = p.add_song(tmp, file.filename or "song.mp3")
    finally:
        os.unlink(tmp)
    return {"name": name, "playlist": p.data["playlist"], "cards": p.data["cards"]}


class SongRef(BaseModel):
    name: str


@app.post("/api/projects/{slug}/songs/remove")
def remove_song(slug: str, req: SongRef):
    p = _project_or_404(slug)
    p.remove_song(os.path.basename(req.name))
    return {"playlist": p.data["playlist"], "cards": p.data["cards"]}


class Order(BaseModel):
    order: list[str]


@app.post("/api/projects/{slug}/songs/order")
def reorder_songs(slug: str, req: Order):
    p = _project_or_404(slug)
    p.reorder_playlist([os.path.basename(n) for n in req.order])
    return {"playlist": p.data["playlist"], "cards": p.data["cards"]}


@app.get("/api/projects/{slug}/timeline")
def get_timeline(slug: str):
    """What the finished video will look like on paper, before rendering it."""
    p = _project_or_404(slug)
    songs = p.playlist_paths()
    if not songs:
        return {"songs": [], "shots": [], "duration": 0.0}
    durations = seqmod.song_durations(songs)
    gap = p.data.get("song_gap", 0.0)
    xfade = p.data.get("song_crossfade", 0.0)
    spans, one_pass = seqmod.audio_spans(durations, gap, xfade)
    # match what a render will actually do, repeats included -- a summary that
    # disagrees with the finished video is worse than no summary
    _paths, passes = seqmod.expand_for_target(
        songs, durations, gap, xfade, p.data.get("target_seconds")
    )
    spans = seqmod.repeat_spans(spans, passes, one_pass)
    total = one_pass * passes
    plan = seqmod.plan_shots(
        p.data.get("shots"),
        spans,
        total,
        default_loop=state.settings.get("shot_loop_seconds", 12.0),
    )
    cards = p.data.get("cards") or []
    return {
        "songs": [
            {
                "name": os.path.basename(songs[i % len(songs)]),
                "start": round(sp["start"], 2),
                "duration": round(sp["duration"], 2),
                "card": cards[i % len(cards)] if cards else {},
            }
            for i, sp in enumerate(spans)
        ],
        "passes": passes,
        "shots": [
            {
                "index": s["index"],
                "image": s.get("image", ""),
                "start": round(s["start"], 2),
                "duration": round(s["duration"], 2),
                "transition": s.get("transition"),
                "loop_seconds": s.get("loop_seconds"),
                "mode": s.get("mode", "loop"),
            }
            for s in plan
        ],
        "duration": round(total, 2),
        "beds": len({rendermod._shot_key(s) for s in plan}),
    }


# ---- files the canvas editor needs to draw -------------------------------
@app.get("/api/projects/{slug}/asset-file")
def asset_file(slug: str, name: str):
    p = _project_or_404(slug)
    f = p.assets_dir() / os.path.basename(name)
    if not f.exists():
        raise HTTPException(404, "no such asset")
    return FileResponse(str(f))


@app.get("/api/projects/{slug}/mask-file")
def mask_file(slug: str, name: str):
    p = _project_or_404(slug)
    f = p.masks_dir() / os.path.basename(name)
    if not f.exists():
        raise HTTPException(404, "no such mask")
    return FileResponse(str(f), media_type="image/png")


@app.post("/api/projects/{slug}/mask")
def upload_mask(slug: str, file: UploadFile, name: str = ""):
    """A brush region, painted on the canvas and posted back as a PNG."""
    p = _project_or_404(slug)
    safe = os.path.basename(name or file.filename or "")
    if not safe.lower().endswith(".png"):
        safe = f"mask-{uuid.uuid4().hex[:8]}.png"
    dst = p.masks_dir() / safe
    tmp = _save_upload(file)
    try:
        shutil.move(tmp, dst)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return {"name": dst.name}


# ---- the two speeds of feedback ------------------------------------------
def _living_ctx(p, shot, width, seconds):
    """A scene context for one shot, at editor size."""
    from pulseforge.scenes.registry import SCENES, SceneContext

    fmt = formats.get(p.data.get("format", formats.DEFAULT_FORMAT))
    w = max(160, min(1920, int(width)))
    w = int(round(w / 2) * 2)
    h = int(round(w * fmt["h"] / fmt["w"] / 2) * 2)
    meta = SCENES["living"]
    params = {sp["key"]: sp.get("default") for sp in meta.get("params", [])}
    params.update(
        {k: v for k, v in (p.data.get("params") or {}).items() if v is not None}
    )
    params["_shot"] = shot
    params["_base_dir"] = str(p.assets_dir())
    params["_mask_dir"] = str(p.masks_dir())
    n = max(1, int(round(seconds * fmt["fps"])))
    return SceneContext(
        w, h, fmt["fps"], n, seconds, {}, params, [], _load_art_pack(p), None, fast=True
    )


class StillReq(BaseModel):
    shot: dict = {}
    t: float = 0.0
    width: int = 720


@app.post("/api/projects/{slug}/still")
def render_still(slug: str, req: StillReq):
    """One real frame, right now.

    This is the fast half of the editor's feedback: dragging a slider re-renders
    a single frame through the actual renderer, so what you are tuning against
    is never an approximation of the effect.
    """
    import io as _io

    from PIL import Image

    from pulseforge.scenes import living

    p = _project_or_404(slug)
    shot = req.shot or {}
    loop_s = float(
        shot.get("loop_seconds") or state.settings.get("shot_loop_seconds", 12.0)
    )
    ctx = _living_ctx(p, shot, req.width, loop_s)
    try:
        arr = living.still(ctx, float(req.t))
    except Exception as e:
        raise HTTPException(400, f"could not render that shot: {e}")
    buf = _io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG", compress_level=1)
    from fastapi.responses import Response

    return Response(content=buf.getvalue(), media_type="image/png")


class ShotPreviewReq(BaseModel):
    shot: dict = {}
    seconds: float | None = None
    width: int = 854


@app.post("/api/projects/{slug}/shot-preview")
def shot_preview(slug: str, req: ShotPreviewReq):
    """The slow half: one whole loop, rendered and played back looping, so the
    seam can actually be judged. Silent -- this is about the picture."""
    from pulseforge.scenes import living

    p = _project_or_404(slug)
    shot = dict(req.shot or {})
    seconds = float(
        req.seconds
        or shot.get("loop_seconds")
        or state.settings.get("shot_preview_seconds", 10)
    )
    shot["loop_seconds"] = seconds
    out = p.renders_dir() / "shot-preview.mp4"

    def make_target(job):
        def target():
            ctx = _living_ctx(p, shot, req.width, seconds)
            n = ctx.n_frames
            job.log(f"rendering a {seconds:.0f}s loop at {ctx.w}x{ctx.h}…")

            def frames():
                for i, fr in enumerate(living.frames(ctx)):
                    if job.should_stop():
                        break
                    job.progress(i / max(1, n))
                    yield fr.tobytes()

            rendermod._encode_from_pipe(
                frames(),
                ctx.w,
                ctx.h,
                {"w": ctx.w, "h": ctx.h, "fps": ctx.fps, "_quality": "draft"},
                None,
                seconds,
                str(out),
                state.settings,
                "",
                job.log,
                job.progress,
                video_only=True,
            )
            return {"file": out.name, "duration": seconds}

        return target

    job = start_job("shot-preview", slug, make_target)
    return {"job_id": job.id}


# ---- the intelligent bits ------------------------------------------------
class AutoReq(BaseModel):
    image: str


@app.post("/api/projects/{slug}/auto-regions")
def auto_regions(slug: str, req: AutoReq):
    """Look at a background and propose the parts of it that should move."""
    p = _project_or_404(slug)
    img = p.assets_dir() / os.path.basename(req.image)
    if not img.exists():
        raise HTTPException(404, "no such image")
    from PIL import Image

    with Image.open(img) as im:
        iw, ih = im.size
    scale = min(1.0, 1600 / max(1, iw))
    out = []
    for found in autoregions.suggest(str(img)):
        name = f"auto-{os.path.splitext(img.name)[0]}-{found['name']}.png"[-90:]
        autoregions.mask_to_png(
            found["mask"], p.masks_dir() / name, int(iw * scale), int(ih * scale)
        )
        out.append(
            {
                "name": found["name"],
                "effect": found["effect"],
                "params": found["params"],
                "coverage": found["coverage"],
                "region": {"kind": "brush", "brush": name, "feather": 0.0},
            }
        )
    return {"regions": out}


class PresetReq(BaseModel):
    preset: str
    shot_index: int = 0
    auto: bool = True


@app.post("/api/projects/{slug}/apply-preset")
def apply_preset(slug: str, req: PresetReq):
    """Drop a whole look onto a shot, optionally finding its regions first."""
    p = _project_or_404(slug)
    shots = list(p.data.get("shots") or [])
    if not shots:
        raise HTTPException(409, "add a background first")
    i = max(0, min(req.shot_index, len(shots) - 1))
    suggestions = []
    if req.auto and shots[i].get("image"):
        try:
            suggestions = auto_regions(slug, AutoReq(image=shots[i]["image"]))[
                "regions"
            ]
        except HTTPException:
            suggestions = []
    try:
        shots[i] = presetsmod.apply_to(
            req.preset, shots[i], suggestions, mask_dir=str(p.masks_dir())
        )
    except KeyError as e:
        raise HTTPException(404, str(e))
    p.data["shots"] = shots
    p.save()
    return {"shot": shots[i], "regions_found": [s["name"] for s in suggestions]}


# ---- magic wand ----------------------------------------------------------
class WandReq(BaseModel):
    image: str
    x: float
    y: float
    tolerance: float = 0.12
    contiguous: bool = True
    feather: float = 0.01


@app.post("/api/projects/{slug}/wand")
def wand_select(slug: str, req: WandReq):
    """Grow a region from one clicked pixel and save it as a brush mask."""
    p = _project_or_404(slug)
    img = p.assets_dir() / os.path.basename(req.image)
    if not img.exists():
        raise HTTPException(404, "no such image")
    mask = wandmod.select(
        str(img),
        req.x,
        req.y,
        tolerance=req.tolerance,
        contiguous=req.contiguous,
    )
    coverage = float(mask.mean())
    if coverage <= 0.0005:
        raise HTTPException(422, "nothing similar enough there -- try more tolerance")
    iw, ih = wandmod.image_size(str(img))
    scale = min(1.0, 1600 / max(1, iw))
    name = f"wand-{uuid.uuid4().hex[:8]}.png"
    wandmod.to_png(
        mask,
        p.masks_dir() / name,
        int(iw * scale),
        int(ih * scale),
        feather=req.feather,
    )
    return {
        "region": {"kind": "brush", "brush": name, "feather": 0.0},
        "coverage": round(coverage, 4),
    }


# ---- reuse: duplicate a shot, save a look -------------------------------
class DupReq(BaseModel):
    shot_index: int


@app.post("/api/projects/{slug}/duplicate-shot")
def duplicate_shot(slug: str, req: DupReq):
    """Copy a shot, and its painted regions with it.

    The masks are copied rather than shared -- two shots pointing at one PNG
    would mean editing either one silently changed the other.
    """
    import copy as _copy

    p = _project_or_404(slug)
    shots = list(p.data.get("shots") or [])
    if not shots:
        raise HTTPException(409, "there is no shot to duplicate")
    i = max(0, min(req.shot_index, len(shots) - 1))
    dup = _copy.deepcopy(shots[i])
    for layer in dup.get("layers") or []:
        region = layer.get("region") or {}
        brush = region.get("brush")
        if not brush:
            continue
        src = p.masks_dir() / brush
        if not src.exists():
            continue
        new_name = f"copy-{uuid.uuid4().hex[:6]}-{brush}"[-90:]
        shutil.copyfile(src, p.masks_dir() / new_name)
        region["brush"] = new_name
    dup.pop("preset", None)
    shots.insert(i + 1, dup)
    p.data["shots"] = shots
    p.save()
    return {"shots": shots, "index": i + 1}


class SavePresetReq(BaseModel):
    name: str
    shot: dict


@app.post("/api/projects/{slug}/save-preset")
def save_project_preset(slug: str, req: SavePresetReq):
    p = _project_or_404(slug)
    if not req.name.strip():
        raise HTTPException(400, "give the preset a name")
    pid = presetsmod.save_user_preset(
        req.name.strip(), req.shot, mask_dir=str(p.masks_dir())
    )
    return {"id": pid, "presets": presetsmod.presets_as_list()}


@app.delete("/api/presets/{preset_id:path}")
def delete_preset(preset_id: str):
    try:
        ok = presetsmod.delete_user_preset(preset_id)
    except KeyError as e:
        raise HTTPException(400, str(e))
    if not ok:
        raise HTTPException(404, "no such saved preset")
    return {"presets": presetsmod.presets_as_list()}


# ---- bulk: a shot per image, and the ambience list ----------------------
# ---- the local text model -----------------------------------------------
#
# This is what the AI Studio backdrop button became. There is no image
# generator on this machine, only small text models through Jan, so the app asks
# them for the two things they are actually good at: writing the upload text,
# and choosing from a list the app supplies.
@app.get("/api/jan/status")
def jan_status():
    return janmod.status()


class UploadTextReq(BaseModel):
    mood: str = ""
    extra: str = ""


@app.post("/api/projects/{slug}/write-upload-text")
def write_upload_text(slug: str, req: UploadTextReq):
    """Draft the title, blurb and tags for this mix."""
    p = _project_or_404(slug)
    songs = p.playlist_paths()
    if not songs:
        raise HTTPException(409, "add some songs first")
    durations = seqmod.song_durations(songs)
    spans, one_pass = seqmod.audio_spans(
        durations, p.data.get("song_gap", 0.0), p.data.get("song_crossfade", 0.0)
    )
    _paths, passes = seqmod.expand_for_target(
        songs,
        durations,
        p.data.get("song_gap", 0.0),
        p.data.get("song_crossfade", 0.0),
        p.data.get("target_seconds"),
    )
    items = tracklistmod.entries(
        spans, p.data.get("cards") or [], [os.path.basename(s) for s in songs]
    )
    shots = p.data.get("shots") or []
    mood = req.mood or ", ".join(
        str(sh.get("preset") or sh.get("image") or "") for sh in shots[:3]
    )
    try:
        out = janmod.write_upload_text(
            [it["title"] for it in items],
            (one_pass * passes) / 60.0,
            mood=mood,
            ambience=(p.data.get("ambience") or {}).get("bed", ""),
            extra=req.extra,
        )
    except janmod.JanUnavailable as e:
        raise HTTPException(503, str(e))
    return out


class DescribeLookReq(BaseModel):
    description: str
    shot_index: int = 0
    apply: bool = True


@app.post("/api/projects/{slug}/describe-look")
def describe_look(slug: str, req: DescribeLookReq):
    """Say what you want in words; the model picks from what exists."""
    p = _project_or_404(slug)
    if not req.description.strip():
        raise HTTPException(400, "describe the look you want")
    effects = [e["id"] for e in effects_as_list()]
    emitters = [e["id"] for e in emitters_as_list()]
    presets = [x["id"] for x in presetsmod.presets_as_list()]
    try:
        chosen = janmod.choose_look(req.description, effects, emitters, presets)
    except janmod.JanUnavailable as e:
        raise HTTPException(503, str(e))

    if not req.apply:
        return chosen
    shots = list(p.data.get("shots") or [])
    if not shots:
        raise HTTPException(409, "add a background first")
    i = max(0, min(req.shot_index, len(shots) - 1))
    shot = shots[i]
    if chosen["preset"]:
        suggestions = []
        if shot.get("image"):
            try:
                suggestions = auto_regions(slug, AutoReq(image=shot["image"]))[
                    "regions"
                ]
            except HTTPException:
                suggestions = []
        shot = presetsmod.apply_to(
            chosen["preset"], shot, suggestions, mask_dir=str(p.masks_dir())
        )
    if chosen["emitters"]:
        shot["emitters"] = [
            {"id": e, "params": {}, "depth": 0.6} for e in chosen["emitters"]
        ]
    if chosen["look"]:
        shot["look"] = {**(shot.get("look") or {}), **chosen["look"]}
    shots[i] = shot
    p.data["shots"] = shots
    p.save()
    return {**chosen, "shot": shot}


class ApplyAllReq(BaseModel):
    preset: str = ""
    grade: str = ""
    grade_amount: float = 0.7
    auto_regions: bool = True


@app.post("/api/projects/{slug}/apply-look-to-all")
def apply_look_to_all(slug: str, req: ApplyAllReq):
    """One look across every shot -- what the simple editor is built around.

    Each shot keeps its own background, and its regions are detected against
    that background rather than being copied from the first one, so a preset
    lands correctly on a sky in one picture and a lake in another.
    """
    p = _project_or_404(slug)
    shots = list(p.data.get("shots") or [])
    if not shots:
        raise HTTPException(409, "add a picture first")

    touched = 0
    for i, shot in enumerate(shots):
        if req.preset:
            found = []
            if req.auto_regions and shot.get("image"):
                try:
                    found = auto_regions(slug, AutoReq(image=shot["image"]))["regions"]
                except HTTPException:
                    found = []
            try:
                shot = presetsmod.apply_to(
                    req.preset, shot, found, mask_dir=str(p.masks_dir())
                )
            except KeyError:
                raise HTTPException(404, f"no such preset: {req.preset}")
        if req.grade:
            shot["look"] = {
                **(shot.get("look") or {}),
                "grade": req.grade,
                "grade_amount": float(req.grade_amount),
            }
        shots[i] = shot
        touched += 1
    p.data["shots"] = shots
    p.save()
    return {"shots": shots, "touched": touched}


@app.get("/api/grades")
def get_grades():
    return gradesmod.grades_as_list()


# ---- snapshots -----------------------------------------------------------
class SnapshotReq(BaseModel):
    label: str = ""


@app.get("/api/projects/{slug}/snapshots")
def list_snapshots(slug: str):
    return snapshotsmod.listing(_project_or_404(slug))


@app.post("/api/projects/{slug}/snapshots")
def take_snapshot(slug: str, req: SnapshotReq):
    p = _project_or_404(slug)
    sid = snapshotsmod.take(p, req.label)
    return {"id": sid, "snapshots": snapshotsmod.listing(p)}


@app.post("/api/projects/{slug}/snapshots/{snapshot_id}/restore")
def restore_snapshot(slug: str, snapshot_id: str):
    p = _project_or_404(slug)
    try:
        shots = snapshotsmod.restore(p, snapshot_id)
    except KeyError as e:
        raise HTTPException(404, str(e))
    return {"shots": shots, "data": p.data}


@app.delete("/api/projects/{slug}/snapshots/{snapshot_id}")
def delete_snapshot(slug: str, snapshot_id: str):
    p = _project_or_404(slug)
    if not snapshotsmod.delete(p, snapshot_id):
        raise HTTPException(404, "no such snapshot")
    return {"snapshots": snapshotsmod.listing(p)}


# ---- a project as a file -------------------------------------------------
class ExportReq(BaseModel):
    include_media: bool = False


@app.post("/api/projects/{slug}/export")
def export_project(slug: str, req: ExportReq):
    p = _project_or_404(slug)
    out = p.dir / f"{p.slug}{projectfilemod.SUFFIX}"
    path, size = projectfilemod.export(p, out, include_media=req.include_media)
    return {
        "file": os.path.basename(path),
        "size_bytes": size,
        "includes_media": req.include_media,
    }


@app.get("/api/projects/{slug}/export-file")
def export_file(slug: str):
    p = _project_or_404(slug)
    f = p.dir / f"{p.slug}{projectfilemod.SUFFIX}"
    if not f.exists():
        raise HTTPException(404, "export it first")
    return FileResponse(str(f), media_type="application/zip", filename=f.name)


@app.post("/api/projects/import")
def import_project(file: UploadFile):
    """Restore a .pfproj into a new project."""
    tmp = _save_upload(file)
    try:
        info = projectfilemod.inspect(tmp)
        name = str(info["name"] or "imported project")[:300]
        target = projmod.create(name, unique=True)
        projectfilemod.restore(tmp, target)
    except (ValueError, KeyError) as e:
        raise HTTPException(400, str(e))
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return target.summary()


class DuplicateReq(BaseModel):
    name: str = Field("", max_length=300)
    include_songs: bool = True


@app.post("/api/projects/{slug}/duplicate")
def duplicate_project(slug: str, req: DuplicateReq):
    """Copy a project, or use it as a template without its songs."""
    import copy as _copy

    src = _project_or_404(slug)
    dst = projmod.create(
        req.name.strip() or f"{src.data.get('name', slug)} copy", unique=True
    )
    dst.data.update(_copy.deepcopy(src.data))
    dst.data["name"] = req.name.strip() or f"{src.data.get('name', slug)} copy"

    for sub in ("masks", "assets"):
        folder = src.dir / sub
        if folder.is_dir():
            shutil.copytree(folder, dst.dir / sub, dirs_exist_ok=True)
    if req.include_songs:
        for name in src.data.get("playlist") or []:
            f = src.dir / name
            if f.is_file():
                shutil.copyfile(f, dst.dir / name)
    else:
        dst.data["playlist"] = []
        dst.data["cards"] = []
        dst.data["audio"] = ""
        dst.data["song_gain"] = []
    dst.save()
    return dst.summary()


# ---- levelling and the pre-flight report --------------------------------
@app.post("/api/projects/{slug}/level-playlist")
def level_playlist(slug: str):
    """Measure every song and even them out."""
    p = _project_or_404(slug)
    songs = p.playlist_paths()
    if not songs:
        raise HTTPException(409, "add some songs first")
    levels = [seqmod.measure_loudness(s) for s in songs]
    gains = seqmod.auto_gains(songs)
    p.data["song_gain"] = gains
    p.save()
    usable = [x for x in levels if x is not None]
    return {
        "gains": gains,
        "before_lufs": levels,
        "spread_before": (
            round(max(usable) - min(usable), 1) if len(usable) > 1 else 0.0
        ),
    }


@app.get("/api/projects/{slug}/preflight")
def preflight_check(slug: str):
    """What would go wrong if you uploaded this."""
    p = _project_or_404(slug)
    songs = p.playlist_paths()
    spans, duration = [], 0.0
    if songs:
        durations = seqmod.song_durations(songs)
        gap = p.data.get("song_gap", 0.0)
        xfade = p.data.get("song_crossfade", 0.0)
        spans, one_pass = seqmod.audio_spans(durations, gap, xfade)
        _paths, passes = seqmod.expand_for_target(
            songs, durations, gap, xfade, p.data.get("target_seconds")
        )
        spans = seqmod.repeat_spans(spans, passes, one_pass)
        duration = one_pass * passes
    items = preflightmod.check_project(p, spans, duration)
    renders = sorted(p.renders_dir().glob("*.mp4"))
    if renders:
        items += preflightmod.check_render(str(renders[-1]), duration)
    return {
        "items": items,
        "counts": preflightmod.summarise(items),
        "checked_render": renders[-1].name if renders else None,
    }


# ---- one action, every deliverable ---------------------------------------
class BatchExportReq(BaseModel):
    formats: list[str] = ["long_1080p", "shorts_1080x1920"]
    thumbnail: bool = True
    title: str = ""
    subtitle: str = ""


@app.post("/api/projects/{slug}/export-all")
def export_all(slug: str, req: BatchExportReq):
    """Queue every deliverable an upload needs, through the usual worker."""
    p = _project_or_404(slug)
    if not p.playlist_paths():
        raise HTTPException(409, "add some songs first")
    wanted = [f for f in req.formats if f in {x["id"] for x in formats.as_list()}]
    if not wanted:
        raise HTTPException(400, "none of those formats exist")

    jobs = []
    original = p.data.get("format")
    for fmt_id in wanted:
        p.data["format"] = fmt_id
        p.save()
        jobs.append(
            {
                "format": fmt_id,
                "job_id": start_job(
                    "render", slug, _render_make_target(p, preview=False)
                ).id,
            }
        )
    p.data["format"] = original
    p.save()

    if req.thumbnail:

        def make_thumb(job):
            def target():
                renders = sorted(p.renders_dir().glob("*.mp4"))
                if not renders:
                    raise RuntimeError("nothing rendered to grab a thumbnail from")
                dst = p.thumbs_dir() / f"{p.slug}_thumb.png"
                rendermod.grab_thumbnail(
                    str(renders[-1]),
                    str(dst),
                    t_seconds=8.0,
                    title=req.title,
                    subtitle=req.subtitle,
                    scrim=0.25,
                )
                return {"thumbnail": dst.name}

            return target

        jobs.append(
            {
                "format": "thumbnail",
                "job_id": start_job("thumbnail", slug, make_thumb).id,
            }
        )
    return {"jobs": jobs}


@app.get("/api/ambience")
def get_ambience():
    return ambiencemod.beds_as_list()


@app.get("/api/ambience/{bed_id}/preview")
def preview_ambience(bed_id: str, seconds: float = 6.0):
    """A short sample, so you can hear a bed before committing a render to it."""
    import io as _io
    import wave as _wave

    try:
        audio = ambiencemod.generate(bed_id, seconds=max(2.0, min(15.0, seconds)))
    except KeyError:
        raise HTTPException(404, "no such ambience")
    buf = _io.BytesIO()
    with _wave.open(buf, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(ambiencemod.SR)
        w.writeframes((audio * 32767.0).astype("<i2").tobytes())
    from fastapi.responses import Response

    return Response(content=buf.getvalue(), media_type="audio/wav")


class BulkShotsReq(BaseModel):
    images: list[str]
    hold: float = 20.0
    transition: str = "dissolve"
    transition_s: float = 1.5
    replace: bool = False


@app.post("/api/projects/{slug}/shots-from-images")
def shots_from_images(slug: str, req: BulkShotsReq):
    """One shot per image -- a slideshow, built out of the machinery that
    already exists rather than a second code path."""
    p = _project_or_404(slug)
    have = set(p.data.get("assets") or [])
    picked = [os.path.basename(n) for n in req.images if os.path.basename(n) in have]
    if not picked:
        raise HTTPException(400, "none of those images are attached to this project")
    template = (p.data.get("shots") or [{}])[0]
    made = []
    for name in picked:
        shot = {
            k: v
            for k, v in template.items()
            if k in ("camera", "look", "loop_seconds", "mode")
        }
        shot.update(
            {
                "image": name,
                "hold": float(req.hold),
                "transition": req.transition,
                "transition_s": float(req.transition_s),
                "layers": [],
                "images": [],
                "emitters": [],
            }
        )
        made.append(shot)
    p.data["shots"] = made if req.replace else (p.data.get("shots") or []) + made
    p.save()
    return {"shots": p.data["shots"], "added": len(made)}


# ---- the tracklist you paste under the video ----------------------------
@app.get("/api/projects/{slug}/tracklist")
def get_tracklist(slug: str):
    p = _project_or_404(slug)
    songs = p.playlist_paths()
    if not songs:
        return {"description": "", "items": [], "warnings": ["No songs yet."]}
    durations = seqmod.song_durations(songs)
    spans, total = seqmod.audio_spans(
        durations, p.data.get("song_gap", 0.0), p.data.get("song_crossfade", 0.0)
    )
    built = tracklistmod.build(
        spans,
        p.data.get("cards") or [],
        [os.path.basename(s) for s in songs],
        total,
        header=p.data.get("description_header", ""),
    )
    built.pop("ffmetadata", None)
    return built


# --------------------------------------------------------------------------
# the AMV studio
#
# Everything the beat-cut editor needs. The registries are served straight out
# of their tables, so a new editing style or beat effect appears in the picker
# with its controls the moment it is added -- no route changes here.
# --------------------------------------------------------------------------
@app.get("/api/edit-styles")
def get_edit_styles():
    return {
        "styles": editstylesmod.styles_as_list(),
        "default": editstylesmod.DEFAULT_STYLE,
    }


@app.get("/api/beat-effects")
def get_beat_effects():
    return {"effects": beatfxmod.fx_as_list()}


@app.get("/api/amv-transitions")
def get_amv_transitions():
    return {"transitions": editstylesmod.transition_list()}


def _features_for(p, fps=30.0):
    """The project's analysis, from cache if it is there."""
    path = p.features_path(fps)
    if path.exists():
        try:
            return analyze.load_features(str(path))
        except Exception:
            pass
    songs = p.playlist_paths() or ([p.audio_path()] if p.audio_path() else [])
    if not songs:
        raise HTTPException(400, "add a song first")
    feats = analyze.analyze(songs[0], fps)
    try:
        analyze.save_features(str(path), feats)
    except Exception:
        pass
    return feats


def _music_map_for(p, fps=30.0):
    feats = _features_for(p, fps)
    return musicmapmod.map_music(feats)


@app.get("/api/projects/{slug}/music-map")
def get_music_map(slug: str):
    """Tempo, the bar grid and the song's sections.

    This is what the timeline draws its ruler from, and what the planner cuts
    to. Returned in full so the editor can show the same structure the renderer
    is working to rather than an approximation of it."""
    p = _project_or_404(slug)
    m = musicmapmod.jsonable(_music_map_for(p))
    # the per-frame vocal flag is large and the editor only needs its shape
    vocal = m.pop("vocal", [])
    m["vocal_fraction"] = round(sum(1 for v in vocal if v) / max(1, len(vocal)), 3)
    return m


class EditPlanReq(BaseModel):
    style: str = ""
    intensity: float = 1.0
    min_shot: float = 0.25
    max_shot: float = 12.0
    fit: str = "cover"
    crop_letterbox: bool = True
    reuse_penalty: float = 0.55
    transition_override: str = ""
    analysis_seconds: int = 0


@app.post("/api/projects/{slug}/edit-plan")
def build_edit_plan(slug: str, req: EditPlanReq):
    """Plan the edit without rendering it.

    The whole point of the timeline: you see every cut, which clip fills it and
    why, and can change the style or the intensity and watch the plan redraw,
    all without waiting for an encode. Planning is milliseconds once the clips
    have been looked at once."""
    p = _project_or_404(slug)
    pool = None
    for a in p.resolved_assets():
        if a and os.path.isdir(a):
            pool = a
            break
    if not pool:
        raise HTTPException(400, "attach a folder of video clips first")

    dna = amvplanmod.scan_and_analyse(pool, max_seconds=int(req.analysis_seconds or 0))
    dna = {k: v for k, v in dna.items() if v.get("segments")}
    if not dna:
        raise HTTPException(400, "no readable video files in that folder")

    music = _music_map_for(p)
    songs = p.playlist_paths() or ([p.audio_path()] if p.audio_path() else [])
    durations = seqmod.song_durations(songs)
    _spans, total = seqmod.audio_spans(
        durations, p.data.get("song_gap", 0.0), p.data.get("song_crossfade", 0.0)
    )
    style = editstylesmod.get_style(req.style or editstylesmod.DEFAULT_STYLE)
    out = amvplanmod.plan(
        music,
        dna,
        style,
        total or music.get("duration") or 0.0,
        {
            "intensity": req.intensity,
            "min_shot": req.min_shot,
            "max_shot": req.max_shot,
            "fit": req.fit,
            "crop_letterbox": req.crop_letterbox,
            "reuse_penalty": req.reuse_penalty,
        },
    )
    if req.transition_override and req.transition_override in editstylesmod.TRANSITIONS:
        meta = editstylesmod.TRANSITIONS[req.transition_override]
        for i, sh in enumerate(out["shots"]):
            if i:
                sh["transition"] = meta["id"]
                sh["transition_ms"] = int(meta["ms"])

    out["duration"] = total
    out["sections"] = music.get("sections") or []
    out["bpm"] = music.get("bpm")
    out["downbeats"] = music.get("downbeats") or []
    out["drops"] = music.get("drops") or []
    out["clips"] = [
        {
            "path": k,
            "name": os.path.basename(k),
            "duration": v.get("duration"),
            "letterbox": v.get("letterbox"),
            "cuts": len(v.get("cuts") or []),
        }
        for k, v in sorted(dna.items())
    ]
    return out


@app.post("/api/projects/{slug}/analyse-clips")
def analyse_clips(slug: str):
    """Look at every clip in the folder. The slow step, run as a job."""
    p = _project_or_404(slug)
    pool = None
    for a in p.resolved_assets():
        if a and os.path.isdir(a):
            pool = a
            break
    if not pool:
        raise HTTPException(400, "attach a folder of video clips first")

    def make_target(job):
        job.log(f"looking at the clips in {os.path.basename(pool)}…")
        dna = amvplanmod.scan_and_analyse(pool, progress=job.progress)
        good = [d for d in dna.values() if d.get("segments")]
        job.log(f"{len(good)} of {len(dna)} files readable")
        for d in sorted(good, key=lambda d: d.get("name", "")):
            st = shotdnamod.window_stats(d, 0.0, min(4.0, d.get("duration", 1.0)))
            job.log(
                f"  {d.get('name')}: {d.get('duration', 0):.1f}s — {shotdnamod.describe(st)}"
            )
        return {"clips": len(good)}

    return {"job_id": start_job("analyse-clips", slug, make_target).id}


# --------------------------------------------------------------------------
# a look taken from the artwork itself
# --------------------------------------------------------------------------
class AutoLookReq(BaseModel):
    asset: str = ""
    shot_index: int = -1
    apply: bool = True


@app.post("/api/projects/{slug}/auto-look")
def auto_look(slug: str, req: AutoLookReq):
    """Read a background image and build a whole look out of it.

    Not a filter applied on top of the picture -- the grade, the light and the
    weather are all read *from* the picture, so a new background arrives already
    lit to match itself."""
    p = _project_or_404(slug)
    name = req.asset
    if not name and 0 <= req.shot_index < len(p.data.get("shots") or []):
        name = (p.data["shots"][req.shot_index] or {}).get("image", "")
    if not name:
        raise HTTPException(400, "pick a picture first")
    path = p.assets_dir() / name
    if not path.exists():
        raise HTTPException(404, "no such image")

    look = palettemod.look_from_image(str(path))
    if req.apply and 0 <= req.shot_index < len(p.data.get("shots") or []):
        shot = p.data["shots"][req.shot_index]
        # A shot stores its colour under `look` and its movement under
        # `camera`; those are the two the renderer reads. Writing the lot into
        # `params` looked like it worked and changed nothing at all.
        look_p, camera_p, extra = palettemod.split_for_shot(look["params"])
        shot.setdefault("look", {}).update(look_p)
        shot.setdefault("camera", {}).update(camera_p)
        if extra:
            # scene-level parameters (sky_clouds today) belong to the project
            p.data.setdefault("params", {}).update(extra)
        p.save()
    return look


# --------------------------------------------------------------------------
# static
#
# Mounted last, and it has to stay last: the "/" mount matches every path,
# so any route declared after it is unreachable.
# --------------------------------------------------------------------------
if os.path.isdir(SHARED_DIR):
    app.mount("/shared", StaticFiles(directory=SHARED_DIR), name="shared")
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
