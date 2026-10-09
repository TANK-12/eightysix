"""FastAPI backend for NovelForge, replacing the customtkinter GUI.

Reuses every bit of business logic (novelforge/engine.py, project.py,
janclient.py, catalog.py, codex.py, stylelib.py) completely unchanged -- none
of it ever depended on customtkinter. What's new here is only the delivery
mechanism: a JobManager runs generation/outline work on a background thread
exactly like the desktop app's worker thread did, but instead of pushing
Tk-queue events for a 90ms `.after()` pump to drain one widget-insert at a
time, events go on a plain queue that an SSE endpoint drains and BATCHES
(every ~120ms, or immediately if the queue is empty) into one network
message. That batching is the actual fix for the old app's worst perf
complaint: hundreds of individual per-token textbox inserts per chapter.
"""

import asyncio
import contextlib
import json
import os
import queue
import sys
import threading
import time
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from novelforge import (
    audiobook as ttsmod,
    config,
    export as exportmod,
    presets as presetsmod,
    research as researchmod,
)
from novelforge.catalog import Catalog
from novelforge.codex import codex_stats
from novelforge.continuation import SPIN_PRESETS, CorpusIngest
from novelforge.engine import NovelEngine
from novelforge.janclient import JanClient, KillSwitch, ram_is_low
from novelforge.outline import parse_outline_text
from novelforge.project import RESET_PARTS, Project, Series, slugify, tidy_field
from novelforge.stylelib import StyleLibrary
from novelforge import project as projectmod

HERE = os.path.dirname(os.path.abspath(__file__))
app = FastAPI(title="NovelForge")

# Jan the Forge way (shared/forge_jan.py): this app's own model per role,
# saved in ~/.config/forge/jan/novelforge.json, and a model this app loaded is
# released after it sits idle. "writer" drafts the prose; "planner" builds
# outlines, Free-Rein worlds, style notes and voice casting, and falls back to
# the writer when unset.
ROLES = ("writer", "planner")
_SHARED_DIR = os.environ.get("FORGE_SHARED_DIR") or os.path.join(
    HERE, "..", "..", "shared"
)
if os.path.isdir(_SHARED_DIR) and _SHARED_DIR not in sys.path:
    sys.path.insert(0, _SHARED_DIR)
try:
    import forge_jan

    JAN = forge_jan.mount(app, "novelforge", roles=ROLES)
except Exception as _jan_error:  # standalone, outside a Forge checkout
    print(f"[novelforge] shared Jan settings unavailable: {_jan_error}")
    JAN = None


# --------------------------------------------------------------------------
# App-wide state (one process, mirrors what NovelForgeApp held as self.*)
# --------------------------------------------------------------------------
class AppState:
    def __init__(self):
        self.settings = config.load_settings()
        self.catalog = Catalog()
        self.style_lib = StyleLibrary()
        self.models_path = (
            self.settings.get("models_path") or config.default_models_path()
        )
        self.client = JanClient(
            self.settings.get("api_base", config.DEFAULT_API_BASE),
            timeout=self.settings.get("request_timeout", 900),
        )
        self.jobs: dict[str, "Job"] = {}
        self.active_job_id: str | None = None
        # Scan for real models once at startup, off the main thread so a slow or
        # hung Jan /v1/models request can't delay the backend coming up. The
        # catalog starts empty until this lands; the frontend also fires
        # /api/refresh-models on load and when the model list is pointed at.
        threading.Thread(target=self._startup_scan, daemon=True).start()

    def _startup_scan(self):
        try:
            self.catalog.refresh(self.client, self.models_path)
        except Exception:
            pass

    def save_settings(self):
        config.save_settings(self.settings)

    def refresh_client(self):
        self.client = JanClient(
            self.settings.get("api_base", config.DEFAULT_API_BASE),
            timeout=self.settings.get("request_timeout", 900),
        )


state = AppState()


# --------------------------------------------------------------------------
# Background jobs (outline / generate), bridged to SSE
# --------------------------------------------------------------------------
class Job:
    def __init__(self, kind, project_name):
        self.id = uuid.uuid4().hex[:12]
        self.kind = kind
        self.project_name = project_name
        self.status = "running"  # running | done | error
        self.error = None
        self.kill = KillSwitch()
        self.events: queue.Queue = queue.Queue()
        self.thread = None

    def log(self, msg):
        self.events.put({"type": "log", "text": msg})

    def progress(self, **kw):
        self.events.put({"type": "progress", **kw})

    def stream(self, text):
        self.events.put({"type": "stream", "text": text})

    def finish(self, status, error=None):
        self.status = status
        self.error = error
        self.events.put({"type": status, "error": error})


def _run_job(job: Job, target_fn, models=()):
    try:
        with contextlib.ExitStack() as held:
            # Mark the models as in use for the whole job, so the idle
            # release never unloads one between two requests of a run.
            for m in models:
                if JAN is not None and m:
                    held.enter_context(JAN.using(m))
            target_fn()
        job.finish("done")
    except Exception as e:
        job.finish("error", str(e))
    finally:
        if state.active_job_id == job.id:
            state.active_job_id = None


def _prune_jobs(keep=20):
    """Finished jobs are kept so a client can still ask how one ended, but not
    forever -- this backend can stay up for days across many runs."""
    finished = [j for j in state.jobs.values() if j.status != "running"]
    for j in finished[:-keep] if len(finished) > keep else []:
        state.jobs.pop(j.id, None)


def start_job(kind, project_name, make_target_fn, models=()):
    """make_target_fn(job) -> callable; deferred so the job (and its log/
    progress/stream callbacks) exists before the engine that needs them is
    built, without running anything until the single active-job check passes."""
    current = state.jobs.get(state.active_job_id) if state.active_job_id else None
    if current and current.status == "running":
        raise HTTPException(
            409, "Another job is already running -- wait for it or stop it first."
        )
    job = Job(kind, project_name)
    _prune_jobs()
    state.jobs[job.id] = job
    state.active_job_id = job.id
    target_fn = make_target_fn(job)
    job.thread = threading.Thread(
        target=_run_job, args=(job, target_fn, tuple(models)), daemon=True
    )
    job.thread.start()
    return job


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------
class CreateProject(BaseModel):
    name: str


class BiblePatch(BaseModel):
    preset: str | None = None
    title: str | None = None
    genre: str | None = None
    protagonist: str | None = None
    plot: str | None = None
    pinned_facts: str | None = None
    inspiration_notes: str | None = None
    style_directives: str | None = None
    world_doc: str | None = None
    outline: str | None = None
    story_scope: str | None = None
    planned_books: int | None = None
    arc_synopsis: str | None = None


class OutlineRequest(BaseModel):
    target_chapters: int = 20
    keep_existing: bool = False  # "Continue outline": keep what is planned
    careful: bool | None = None  # one critique pass; None = the setting


class ResetRequest(BaseModel):
    parts: list[str]


class RewindRequest(BaseModel):
    from_chapter: int


class GenerateRequest(BaseModel):
    target_chapters: int = 20
    target_words_per_chapter: int = 3500
    model: str | None = None
    max_tokens_per_call: int | None = None
    context_budget: int | None = None
    prose_temperature: float | None = None
    structure_temperature: float | None = None
    auto_codex: bool | None = None
    auto_summary: bool | None = None


class FreeReinRequest(BaseModel):
    # "overwrite filled fields too" -- when true, build_world may replace an
    # already-filled genre/protagonist/plot and append to an existing world doc.
    expand_existing: bool = False


class StopRequest(BaseModel):
    hard: bool = False
    keep_partial: bool = True


class SettingsPatch(BaseModel):
    # Open-ended: the settings dict already has ~30 keys with defaults in
    # config.py and the desktop app only ever touches a handful at a time.
    values: dict


# --------------------------------------------------------------------------
# Projects
# --------------------------------------------------------------------------
@app.get("/api/projects")
def list_projects():
    # has_cover lets the Home list decide between a real cover thumbnail and a
    # generated placeholder, instead of firing a request per project that 404s.
    out = []
    for n in Project.list_all():
        try:
            has_cover = bool(exportmod.cover_for(Project(n)))
        except Exception:
            has_cover = False
        out.append({"name": n, **Project.quick_stats(n), "has_cover": has_cover})
    return out


@app.post("/api/projects")
def create_project(req: CreateProject):
    if not req.name.strip():
        raise HTTPException(400, "name is required")
    _check_name_length(req.name)
    p = Project(req.name)
    p.save()
    return _project_detail(p)


def _project_detail(p: Project):
    return {
        "name": p.name,
        "bible": p.bible,
        "state": p.state,
        "codex_stats": codex_stats(p.codex),
        "chapter_count": p.chapter_count(),
        "total_words": p.total_words(),
        "scope_label": p.scope_label(),
    }


def _existing(name: str) -> Project:
    """The project, or a 404 -- Project() alone would create an empty one."""
    if not Project.exists(name):
        raise HTTPException(404, f"no project called {name}")
    return Project(name)


def _existing_folder(name: str) -> Project:
    """For destructive routes: the name must be the project's folder name
    exactly. "???" slugifies to "untitled" and "My Book" to "My_Book", so a
    loose name would trash some other project."""
    if slugify(name) != name:
        raise HTTPException(404, f"no project called {name}")
    return _existing(name)


def _refuse_if_busy(name: str):
    job = state.jobs.get(state.active_job_id) if state.active_job_id else None
    if job and job.status == "running" and slugify(job.project_name) == slugify(name):
        raise HTTPException(409, "a job is running on this project; stop it first")


@app.get("/api/projects/{name}")
def get_project(name: str):
    # Project() makes the folder, so a read of a name that is not there (a
    # stale link, a typo) used to leave an empty project on Home.
    if not _known(projectmod.PROJECTS_DIR, name):
        raise HTTPException(404, f"no project called {name}")
    p = Project(name)
    return _project_detail(p)


def _known(base_dir: str, name: str) -> bool:
    return os.path.isdir(os.path.join(base_dir, projectmod.slugify(name)))


def _check_name_length(name: str) -> None:
    # A name becomes a folder name: past the file system's limit it was a 500.
    # Bytes count too: 100 CJK characters are 300 bytes, past the 255 limit.
    if len(name) > 120 or len(projectmod.slugify(name).encode("utf-8")) > 200:
        raise HTTPException(
            400, "name is too long (120 characters at most, fewer in some scripts)"
        )


@app.delete("/api/projects/{name}")
def delete_project(name: str):
    """Moves the project folder to ~/NovelMakerData/.trash; nothing is erased."""
    p = _existing_folder(name)
    _refuse_if_busy(name)
    series = p.bible.get("series")
    if series and Series.exists(series):
        Series(series).remove_book(p.name)
    return {"trashed_to": p.trash()}


@app.put("/api/projects/{name}/bible")
def update_bible(name: str, patch: BiblePatch):
    p = Project(name)
    values = patch.model_dump(exclude_none=True)
    outline = values.pop("outline", None)
    for k, v in values.items():
        p.bible[k] = tidy_field(k, v) if isinstance(v, str) else v
    if outline is not None and outline != p.bible.get("outline", ""):
        _refuse_if_busy(name)
        p.set_outline_lines(parse_outline_text(outline))
    p.save()
    return _project_detail(p)


@app.post("/api/projects/{name}/reset")
def reset_project(name: str, req: ResetRequest):
    p = _existing_folder(name)
    _refuse_if_busy(name)
    unknown = [x for x in req.parts if x not in RESET_PARTS]
    if unknown or not req.parts:
        raise HTTPException(400, f"parts must be some of {', '.join(RESET_PARTS)}")
    done = p.reset(req.parts)
    return {"reset": done, **_project_detail(p)}


@app.post("/api/projects/{name}/rewind")
def rewind_project(name: str, req: RewindRequest):
    """Delete chapter N and everything after it (moved to the trash)."""
    p = _existing_folder(name)
    _refuse_if_busy(name)
    if req.from_chapter < 1:
        raise HTTPException(400, "from_chapter starts at 1")
    removed = p.rewind(req.from_chapter)
    p.save()
    return {"removed": removed, **_project_detail(p)}


@app.delete("/api/projects/{name}/codex")
def delete_codex_entry(name: str, bucket: str, key: str):
    p = _existing_folder(name)
    _refuse_if_busy(name)
    if not p.delete_codex_entry(bucket, key):
        raise HTTPException(404, "no such codex entry")
    return {"codex": p.codex, "stats": codex_stats(p.codex)}


@app.get("/api/presets")
def list_presets():
    return presetsmod.summaries()


@app.get("/api/presets/{pid}")
def get_preset(pid: str):
    found = presetsmod.load_presets().get(pid)
    if not found:
        raise HTTPException(404, "no such preset")
    return found


@app.get("/api/projects/{name}/codex")
def get_codex(name: str):
    p = Project(name)
    return {"codex": p.codex, "stats": codex_stats(p.codex)}


@app.get("/api/projects/{name}/chapters/{n}")
def get_chapter(name: str, n: int):
    p = Project(name)
    text = p.load_chapter(n)
    if not text:
        raise HTTPException(404, f"chapter {n} not found")
    return {
        "n": n,
        "title": p.chapter_title(n),
        "text": text,
        "words": len(text.split()),
    }


# --------------------------------------------------------------------------
# Outline / Generate jobs
# --------------------------------------------------------------------------
def _role_setting(role):
    if JAN is None:
        return ""
    try:
        return JAN.settings()["models"].get(role, "")
    except Exception:
        return ""


def _resolve_model(model=None, role="writer"):
    """Which model a job uses: the one asked for, else this role's own
    setting, else (for the planner) the writer's, else the legacy saved
    `model` setting -- each only while it is really installed -- else the
    first model that is. An empty catalog (Jan down, scan pending) trusts
    the choice as given."""
    models = state.catalog.models
    chain = [model, _role_setting(role)]
    if role != "writer":
        chain.append(_role_setting("writer"))
    chain.append(state.settings.get("model"))
    for chosen in chain:
        if chosen and (chosen in models or not models):
            return chosen
    return models[0] if models else None


@app.post("/api/projects/{name}/outline")
def generate_outline(name: str, req: OutlineRequest):
    p = Project(name)
    model = _resolve_model(None, role="planner")
    if not model:
        raise HTTPException(409, "no model available -- check Jan is running")
    profile = state.catalog.profile(model)

    def make_target(job):
        engine = NovelEngine(
            p,
            state.client,
            model,
            state.style_lib,
            profile,
            state.settings,
            log=job.log,
            progress=job.progress,
            stream=job.stream,
            kill=job.kill,
        )
        job.log(f"Planning with {model} ({profile.get('label')} profile).")
        return lambda: engine.build_outline(
            req.target_chapters, keep_existing=req.keep_existing, careful=req.careful
        )

    job = start_job("outline", name, make_target, models=(model,))
    return {"job_id": job.id, "model": model}


@app.post("/api/projects/{name}/generate")
def start_generation(name: str, req: GenerateRequest):
    p = Project(name)
    low, ram = ram_is_low(float(state.settings.get("min_free_ram_gb", 2.5)))

    model = _resolve_model(req.model)
    planner = _resolve_model(None, role="planner")
    if not model:
        raise HTTPException(409, "no model available -- check Jan is running")
    profile = state.catalog.profile(model)

    gen_settings = dict(state.settings)
    for key in (
        "max_tokens_per_call",
        "context_budget",
        "prose_temperature",
        "structure_temperature",
        "auto_codex",
        "auto_summary",
    ):
        val = getattr(req, key)
        if val is not None:
            gen_settings[key] = val
    state.settings.update(gen_settings)
    state.save_settings()

    p.state["target_chapters"] = req.target_chapters
    p.state["target_words_per_chapter"] = req.target_words_per_chapter
    p.save()

    def make_target(job):
        engine = NovelEngine(
            p,
            state.client,
            model,
            state.style_lib,
            profile,
            gen_settings,
            log=job.log,
            progress=job.progress,
            stream=job.stream,
            kill=job.kill,
            planner=planner,
        )
        job.log(
            f"Writing with {model}"
            + (f", planning with {planner}" if planner and planner != model else "")
            + "."
        )
        return lambda: engine.run(req.target_chapters, req.target_words_per_chapter)

    job = start_job("generate", name, make_target, models=(model, planner))
    return {"job_id": job.id, "model": model, "ram_warning": ram if low else None}


@app.post("/api/projects/{name}/free-rein")
def free_rein(name: str, req: FreeReinRequest):
    """Free-Rein: multi-pass world + cast build, scaled by the world_depth
    setting. Seeds come from whatever genre/protagonist/plot are already saved
    on the bible (blank is fine -- build_world invents what's missing)."""
    p = Project(name)
    model = _resolve_model(None, role="planner")
    if not model:
        raise HTTPException(409, "no model available -- check Jan is running")
    profile = state.catalog.profile(model)

    def make_target(job):
        engine = NovelEngine(
            p,
            state.client,
            model,
            state.style_lib,
            profile,
            state.settings,
            log=job.log,
            progress=job.progress,
            stream=job.stream,
            kill=job.kill,
        )
        job.log(f"Building the world with {model}.")
        return lambda: engine.build_world(
            p.bible.get("genre", ""),
            p.bible.get("protagonist", ""),
            p.bible.get("plot", ""),
            expand_existing=req.expand_existing,
        )

    job = start_job("free-rein", name, make_target, models=(model,))
    return {"job_id": job.id}


# --------------------------------------------------------------------------
# Continue a Series (corpus ingest + open-ended "write N more chapters")
# --------------------------------------------------------------------------
class ContinueIngestRequest(BaseModel):
    pdf_paths: list[str]
    spin_directive: str = ""
    extra_notes: str = ""


class ContinueRunRequest(BaseModel):
    n_more: int = 3
    target_words_per_chapter: int = 3500
    model: str | None = None


@app.get("/api/continuation/spin-presets")
def spin_presets():
    return SPIN_PRESETS


@app.post("/api/projects/{name}/continue-ingest")
def continue_ingest(name: str, req: ContinueIngestRequest):
    p = Project(name)
    model = _resolve_model(None, role="planner")
    if not model:
        raise HTTPException(409, "no model available -- check Jan is running")

    def make_target(job):
        ingest = CorpusIngest(
            p,
            state.client,
            model,
            state.style_lib,
            state.settings,
            log=job.log,
            kill=job.kill,
        )
        return lambda: ingest.run(
            req.pdf_paths,
            spin_directive=req.spin_directive,
            extra_notes=req.extra_notes,
        )

    job = start_job("continue-ingest", name, make_target, models=(model,))
    return {"job_id": job.id}


@app.post("/api/projects/{name}/continue-run")
def continue_run(name: str, req: ContinueRunRequest):
    p = Project(name)
    if not p.bible.get("continuation_mode"):
        raise HTTPException(409, "run continue-ingest on this project first")
    model = _resolve_model(req.model)
    planner = _resolve_model(None, role="planner")
    if not model:
        raise HTTPException(409, "no model available -- check Jan is running")
    profile = state.catalog.profile(model)

    def make_target(job):
        engine = NovelEngine(
            p,
            state.client,
            model,
            state.style_lib,
            profile,
            state.settings,
            log=job.log,
            progress=job.progress,
            stream=job.stream,
            kill=job.kill,
            planner=planner,
        )
        return lambda: engine.continue_run(req.n_more, req.target_words_per_chapter)

    job = start_job("continue-run", name, make_target, models=(model, planner))
    return {"job_id": job.id}


@app.post("/api/jobs/{job_id}/stop")
def stop_job(job_id: str, req: StopRequest):
    job = state.jobs.get(job_id)
    if not job:
        raise HTTPException(404, "no such job")
    if req.hard:
        job.kill.request_hard(keep_partial=req.keep_partial)
    else:
        job.kill.request_soft()
    return {"ok": True}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = state.jobs.get(job_id)
    if not job:
        raise HTTPException(404, "no such job")
    return {
        "id": job.id,
        "kind": job.kind,
        "project": job.project_name,
        "status": job.status,
        "error": job.error,
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
                item = await asyncio.to_thread(job.events.get, True, 5.0)
                batch.append(item)
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
            # Drain whatever else is already queued so a burst of tokens
            # becomes one SSE message instead of one per token.
            deadline = time.time() + 0.12
            while time.time() < deadline:
                try:
                    batch.append(job.events.get_nowait())
                except Exception:
                    break

            merged_stream = "".join(e["text"] for e in batch if e["type"] == "stream")
            others = [e for e in batch if e["type"] != "stream"]
            if merged_stream:
                yield f"data: {json.dumps({'type': 'stream', 'text': merged_stream})}\n\n"
            for e in others:
                yield f"data: {json.dumps(e)}\n\n"
                if e["type"] in ("done", "error"):
                    return

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# --------------------------------------------------------------------------
# Series
# --------------------------------------------------------------------------
@app.get("/api/series")
def list_series():
    return [Series(n).data | {"name": n} for n in Series.list_all()]


@app.get("/api/series/{name}")
def get_series(name: str):
    if not _known(projectmod.SERIES_DIR, name):
        raise HTTPException(404, f"no series called {name}")
    return Series(name).data | {"name": name}


class CreateSeries(BaseModel):
    name: str
    planned_books: int = 1
    arc_synopsis: str = ""


class AddBookToSeries(BaseModel):
    project_name: str
    title: str = ""
    one_line: str = ""


class SetBookStatus(BaseModel):
    project_name: str
    status: str


class SeriesPatch(BaseModel):
    planned_books: int | None = None
    arc_synopsis: str | None = None
    world_doc: str | None = None


@app.post("/api/series")
def create_series(req: CreateSeries):
    if not req.name.strip():
        raise HTTPException(400, "name is required")
    _check_name_length(req.name)
    s = Series(req.name)
    s.data["planned_books"] = req.planned_books
    s.data["arc_synopsis"] = req.arc_synopsis
    s.save()
    return s.data | {"name": s.name}


@app.put("/api/series/{name}")
def update_series(name: str, patch: SeriesPatch):
    s = Series(name)
    s.data.update(patch.model_dump(exclude_none=True))
    s.save()
    return s.data | {"name": name}


@app.post("/api/series/{name}/books")
def add_book_to_series(name: str, req: AddBookToSeries):
    s = Series(name)
    s.add_book(req.project_name, title=req.title, one_line=req.one_line)
    p = Project(req.project_name)
    p.bible["series"] = s.name
    p.bible["book_index"] = s.book_index_of(req.project_name)
    p.bible["planned_books"] = s.data.get("planned_books", 1)
    p.bible["arc_synopsis"] = s.data.get("arc_synopsis", "")
    p.bible["story_scope"] = "series"
    p.save()
    return s.data | {"name": name}


@app.delete("/api/series/{name}")
def delete_series(name: str):
    """Moves the series folder to the trash; its books are kept and unlinked."""
    if not Series.exists(name):
        raise HTTPException(404, "no such series")
    series = Series(name)
    # Trashing a series rewrites each book's bible to unlink it.
    for book in series.data.get("books", []):
        _refuse_if_busy(book)
    return {"trashed_to": series.trash()}


@app.delete("/api/series/{name}/books/{project_name}")
def remove_book_from_series(name: str, project_name: str):
    if not Series.exists(name):
        raise HTTPException(404, "no such series")
    _refuse_if_busy(project_name)
    s = Series(name)
    s.remove_book(project_name)
    return s.data | {"name": name}


@app.put("/api/series/{name}/status")
def set_book_status(name: str, req: SetBookStatus):
    s = Series(name)
    s.set_status(req.project_name, req.status)
    return s.data | {"name": name}


# --------------------------------------------------------------------------
# Models / settings
# --------------------------------------------------------------------------
@app.get("/api/state")
def get_state():
    up = state.client.ping()
    return {
        "settings": state.settings,
        "models": state.catalog.models,
        "roles": {r: _resolve_model(None, role=r) for r in ROLES},
        "role_settings": {r: _role_setting(r) for r in ROLES},
        "idle_minutes": JAN.settings()["idle_minutes"] if JAN is not None else None,
        "jan_up": up,
        "active_job_id": state.active_job_id,
        "scan_count": state.catalog.scan_count,
        "api_count": state.catalog.api_count,
        "models_path": state.models_path,
    }


def _using(model):
    return JAN.using(model) if JAN is not None else contextlib.nullcontext()


@app.post("/api/refresh-models")
def refresh_models():
    models = state.catalog.refresh(state.client, state.models_path)
    return {
        "models": models,
        "jan_up": state.client.ping(),
        "scan_count": state.catalog.scan_count,
        "api_count": state.catalog.api_count,
        "models_path": state.models_path,
    }


@app.get("/api/settings")
def get_settings():
    return state.settings


@app.post("/api/settings")
def update_settings(patch: SettingsPatch):
    state.settings.update(patch.values)
    state.save_settings()
    if "api_base" in patch.values or "request_timeout" in patch.values:
        state.refresh_client()
    if "models_path" in patch.values:
        state.models_path = patch.values["models_path"] or config.default_models_path()
    return state.settings


# --------------------------------------------------------------------------
# Export & cover art
# --------------------------------------------------------------------------
class ExportRequest(BaseModel):
    formats: list[str] = ["epub", "pdf", "txt"]


class QuickCoverRequest(BaseModel):
    accent_hex: str = "#1f6feb"
    dark: bool = True
    style: str = "gradient"  # gradient | duotone | minimal
    width: int = 1600
    height: int = 2400


class ImportCoverRequest(BaseModel):
    src_path: str


class EditCoverRequest(BaseModel):
    crop_ratio: float | None = None
    brightness: float = 1.0
    contrast: float = 1.0
    title_text: str = ""
    author_text: str = ""
    accent_hex: str = "#1f6feb"
    dark_text: bool = False


@app.get("/api/projects/{name}/export/meta")
def export_meta(name: str):
    p = Project(name)
    return {"cover": exportmod.cover_for(p), "formats": list(exportmod.FORMATS)}


@app.post("/api/projects/{name}/export")
def run_export(name: str, req: ExportRequest):
    p = Project(name)
    log_lines = []
    results = exportmod.export_book(
        p, req.formats, settings=state.settings, log=log_lines.append
    )
    return {
        "results": [{"format": f, "result": r} for f, r in results],
        "log": log_lines,
    }


@app.get("/api/projects/{name}/cover")
def get_cover(name: str):
    p = Project(name)
    cover = exportmod.cover_for(p)
    if not cover:
        raise HTTPException(404, "no cover set")
    return FileResponse(cover)


@app.post("/api/projects/{name}/cover/quick")
def quick_cover(name: str, req: QuickCoverRequest):
    p = Project(name)
    import os

    out_path = os.path.join(p.dir, "cover.png")
    exportmod.quick_cover(
        p,
        out_path,
        accent_hex=req.accent_hex,
        dark=req.dark,
        style=req.style,
        width=req.width,
        height=req.height,
        author=state.settings.get("author_name", ""),
    )
    return {"cover": out_path}


@app.post("/api/projects/{name}/cover/import")
def import_cover(name: str, req: ImportCoverRequest):
    p = Project(name)
    try:
        cover = exportmod.import_cover(p, req.src_path)
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    return {"cover": cover}


@app.post("/api/projects/{name}/cover/edit")
def edit_cover(name: str, req: EditCoverRequest):
    p = Project(name)
    src = exportmod.cover_for(p)
    if not src:
        raise HTTPException(409, "no cover to edit -- import or generate one first")
    edited = exportmod.edit_cover(
        src,
        src,
        crop_ratio=req.crop_ratio,
        brightness=req.brightness,
        contrast=req.contrast,
        title_text=req.title_text,
        author_text=req.author_text,
        accent_hex=req.accent_hex,
        dark_text=req.dark_text,
    )
    exportmod.set_cover(p, edited)
    return {"cover": edited}


# --------------------------------------------------------------------------
# References: style library (PDF ingestion, style/content analysis) + research
# --------------------------------------------------------------------------
class AddSourceRequest(BaseModel):
    name: str
    pdf_path: str


class AnalyzeRequest(BaseModel):
    model: str | None = None


class ResearchRequest(BaseModel):
    query: str


@app.get("/api/style-sources")
def list_style_sources():
    out = []
    for name in state.style_lib.names():
        src = state.style_lib.get(name)
        out.append(
            {
                "name": name,
                "enabled": src.get("enabled", True),
                "word_count": src.get("word_count", 0),
                "chunks": len(src.get("chunks", [])),
                "has_style_notes": bool(src.get("style_notes")),
                "has_content_summary": bool(src.get("content_summary")),
            }
        )
    return out


@app.get("/api/style-sources/{name}")
def get_style_source(name: str):
    src = state.style_lib.get(name)
    if not src:
        raise HTTPException(404, "no such source")
    return {"name": name, **src}


@app.post("/api/style-sources")
def add_style_source(req: AddSourceRequest):
    try:
        text = StyleLibrary.extract_pdf_text(req.pdf_path)
    except Exception as e:
        raise HTTPException(400, str(e))
    if not text.strip():
        raise HTTPException(400, "no extractable text in that PDF")
    n_chunks = state.style_lib.add_source(req.name, text)
    return {"name": req.name, "chunks": n_chunks}


@app.delete("/api/style-sources/{name}")
def remove_style_source(name: str):
    state.style_lib.remove_source(name)
    return {"ok": True}


@app.put("/api/style-sources/{name}/enabled")
def set_style_source_enabled(name: str, enabled: bool):
    state.style_lib.set_enabled(name, enabled)
    return {"ok": True}


@app.post("/api/style-sources/{name}/analyze-style")
def analyze_style_source(name: str, req: AnalyzeRequest):
    model = _resolve_model(req.model, role="planner")
    if not model:
        raise HTTPException(409, "no model available -- check Jan is running")
    try:
        with _using(model):
            notes = state.style_lib.analyze_style(state.client, model, name)
    except Exception as e:
        raise HTTPException(502, str(e))
    return {"style_notes": notes}


@app.post("/api/style-sources/{name}/summarize")
def summarize_style_source(name: str, req: AnalyzeRequest):
    model = _resolve_model(req.model, role="planner")
    if not model:
        raise HTTPException(409, "no model available -- check Jan is running")
    try:
        with _using(model):
            summary = state.style_lib.summarize_content(state.client, model, name)
    except Exception as e:
        raise HTTPException(502, str(e))
    return {"content_summary": summary}


@app.post("/api/research")
def research_lookup(req: ResearchRequest):
    return {"result": researchmod.lookup(req.query)}


# --------------------------------------------------------------------------
# Audiobook / TTS
# --------------------------------------------------------------------------
@app.get("/api/tts/catalog")
def tts_catalog():
    return [
        {
            "id": vid,
            "label": desc,
            "installed": ttsmod.voice_installed(vid, state.settings),
        }
        for vid, desc in ttsmod.VOICE_CATALOG
    ]


@app.get("/api/tts/installed")
def tts_installed():
    rows = ttsmod.installed_report(state.settings)
    return [
        {"id": vid, "label": label, "bytes": size, "in_catalog": in_cat}
        for vid, label, size, in_cat in rows
    ]


@app.delete("/api/tts/voices")
def tts_delete_voice(vid: str):
    return {"removed": ttsmod.delete_voice(vid, state.settings)}


class TtsPreviewRequest(BaseModel):
    vid: str
    text: str | None = None
    pitch: float = 1.0
    pace: float = 1.0


@app.post("/api/tts/preview")
def tts_preview(req: TtsPreviewRequest):
    out_path = os.path.join(
        ttsmod.voices_dir(state.settings), f"_preview_{uuid.uuid4().hex[:8]}.wav"
    )
    try:
        ttsmod.preview_voice(
            req.vid,
            out_path,
            state.settings,
            text=req.text,
            pitch=req.pitch,
            pace=req.pace,
        )
    except Exception as e:
        raise HTTPException(502, str(e))
    return {"path": out_path}


@app.get("/api/tts/preview-file")
def tts_preview_file(path: str):
    voices_root = os.path.abspath(ttsmod.voices_dir(state.settings))
    if not os.path.abspath(path).startswith(voices_root) or not os.path.isfile(path):
        raise HTTPException(404, "no such preview file")
    return FileResponse(path, media_type="audio/wav")


@app.get("/api/projects/{name}/voice-map")
def get_voice_map(name: str):
    p = Project(name)
    return {
        "voice_map": ttsmod.load_voice_map(p, state.settings),
        "character_names": ttsmod.character_names(p),
    }


class VoiceMapPatch(BaseModel):
    narrator: str | None = None
    mode: str | None = None
    characters: dict | None = None
    inflections: dict | None = None


@app.put("/api/projects/{name}/voice-map")
def update_voice_map(name: str, patch: VoiceMapPatch):
    p = Project(name)
    vmap = ttsmod.load_voice_map(p, state.settings)
    vmap.update(patch.model_dump(exclude_none=True))
    ttsmod.save_voice_map(p, vmap)
    return {"voice_map": vmap}


class CastVoicesRequest(BaseModel):
    model: str | None = None


@app.post("/api/projects/{name}/cast-voices")
def cast_voices_endpoint(name: str, req: CastVoicesRequest):
    p = Project(name)
    model = _resolve_model(req.model, role="planner")
    if not model:
        raise HTTPException(409, "no model available -- check Jan is running")
    try:
        with _using(model):
            cast = ttsmod.cast_voices(p, state.client, model, state.settings)
    except Exception as e:
        raise HTTPException(502, str(e))
    vmap = ttsmod.load_voice_map(p, state.settings)
    vmap["characters"].update(cast.get("characters", {}))
    if cast.get("narrator"):
        vmap["narrator"] = cast["narrator"]
    ttsmod.save_voice_map(p, vmap)
    return {"voice_map": vmap}


class AudiobookBuildRequest(BaseModel):
    keep_wavs: bool = False


@app.post("/api/projects/{name}/audiobook/build")
def build_audiobook_endpoint(name: str, req: AudiobookBuildRequest):
    p = Project(name)
    vmap = ttsmod.load_voice_map(p, state.settings)

    def make_target(job):
        def work():
            return ttsmod.build_audiobook(
                p,
                settings=state.settings,
                vmap=vmap,
                log=job.log,
                progress=job.progress,
                kill=job.kill,
                keep_wavs=req.keep_wavs,
            )

        return work

    job = start_job("audiobook", name, make_target)
    return {"job_id": job.id}


@app.get("/api/projects/{name}/audiobook/file")
def get_audiobook_file(name: str):
    p = Project(name)
    out_dir = os.path.join(p.dir, "audiobook")
    title = p.bible.get("title") or p.name.replace("_", " ").title()
    from novelforge.project import slugify as _slug

    for fmt in ttsmod.AUDIO_FORMATS:
        path = os.path.join(out_dir, f"{_slug(title)}.{fmt}")
        if os.path.isfile(path):
            return FileResponse(path)
    raise HTTPException(404, "no audiobook rendered yet")


# The shared Forge frontend kit (forge.css / forge.js) lives one level above
# apps/ so all three tools share one copy. Mounted before the catch-all "/"
# mount below, which would otherwise swallow the path. Skipped when missing so
# the app still runs standalone outside a Forge checkout.
if os.path.isdir(_SHARED_DIR):
    app.mount("/shared", StaticFiles(directory=_SHARED_DIR), name="shared")

app.mount(
    "/", StaticFiles(directory=os.path.join(HERE, "static"), html=True), name="static"
)
