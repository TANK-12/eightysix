"""library: fetch, import, Kindle PDF export, MediaForge link.

See CONTRACTS.md "library" for the endpoint list and chapter.json shape.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .. import batch, jobs, paths, store
from ..library import fetch as fetch_mod
from ..library import importers
from ..library import kindle as kindle_mod
from ..library import mediaforge_link
from ..sources import list_sources

router = APIRouter()


# ---------------------------------------------------------------------------
# series / chapters
# ---------------------------------------------------------------------------


@router.get("/api/series")
def list_series():
    out = []
    if paths.SERIES_ROOT.is_dir():
        for sdir in sorted(paths.SERIES_ROOT.iterdir()):
            doc = store.read(sdir / "series.json")
            if doc:
                out.append(doc)
    return {"series": out}


@router.get("/api/series/{s}")
def get_series(s: str):
    doc = store.read(paths.series_dir(s) / "series.json")
    if not doc:
        raise HTTPException(404, "no such series")
    return doc


@router.get("/api/series/{s}/chapters")
def list_chapters(s: str):
    cdir = paths.series_dir(s) / "chapters"
    out = []
    if cdir.is_dir():
        for c in sorted(cdir.iterdir()):
            doc = store.read(c / "chapter.json")
            if doc:
                out.append(doc)
    return {"chapters": out}


@router.get("/api/sources")
def get_sources():
    return {"sources": list_sources()}


# ---------------------------------------------------------------------------
# fetch
# ---------------------------------------------------------------------------


class FetchTitleReq(BaseModel):
    url: str


@router.post("/api/fetch/title")
def fetch_title(req: FetchTitleReq):
    def work(job):
        return fetch_mod.fetch_title(req.url, job)

    job = jobs.start(
        "fetch-title", f"Fetching title list: {req.url}", work, lane="net", url=req.url
    )
    return {"job_id": job.id}


class FetchChaptersReq(BaseModel):
    url: Optional[str] = None
    series: Optional[str] = None
    chapters: Union[list[float], str] = "all"
    group: Optional[str] = None  # scan group to prefer, e.g. "WebToon"


@router.post("/api/fetch/chapters")
def fetch_chapters(req: FetchChaptersReq):
    if not req.url and not req.series:
        raise HTTPException(400, "need either url or series")

    def work(job):
        return fetch_mod.fetch_chapters(
            req.url, req.series, req.chapters, job, group=req.group
        )

    job = jobs.start(
        "fetch-chapters",
        f"Fetching chapters: {req.url or req.series}",
        work,
        lane="net",
        url=req.url,
        series=req.series,
    )
    return {"job_id": job.id}


# ---------------------------------------------------------------------------
# import
# ---------------------------------------------------------------------------


class ImportPathReq(BaseModel):
    path: str
    series: Optional[str] = None
    number: Optional[float] = None


@router.post("/api/import/path")
def import_path(req: ImportPathReq):
    def work(job):
        return importers.import_path(req.path, req.series, req.number, job)

    job = jobs.start("import", f"Importing {req.path}", work, lane="cpu", path=req.path)
    return {"job_id": job.id}


@router.post("/api/import/upload")
async def import_upload(
    files: list[UploadFile] = File(...),
    series: Optional[str] = Form(None),
    number: Optional[float] = Form(None),
):
    payload = [(f.filename or "page", await f.read()) for f in files]

    def work(job):
        return importers.import_upload(payload, series, number, job)

    job = jobs.start(
        "import-upload", f"Importing {len(payload)} uploaded file(s)", work, lane="cpu"
    )
    return {"job_id": job.id}


@router.get("/api/mediaforge/downloads")
def mediaforge_downloads(root: Optional[str] = None):
    return mediaforge_link.list_downloads(root)


class ImportMediaForgeReq(BaseModel):
    path: str
    series: Optional[str] = None
    number: Optional[float] = None


@router.post("/api/import/mediaforge")
def import_mediaforge(req: ImportMediaForgeReq):
    def work(job):
        return mediaforge_link.import_from_mediaforge(
            req.path, req.series, req.number, job
        )

    job = jobs.start(
        "import-mediaforge", f"Importing from MediaForge: {req.path}", work, lane="cpu"
    )
    return {"job_id": job.id}


# ---------------------------------------------------------------------------
# Kindle PDF export
# ---------------------------------------------------------------------------


class ExportPdfReq(BaseModel):
    series: str
    chapters: Union[list[str], str] = "all"
    preset: str = "kindle"


@router.post("/api/export/pdf")
def export_pdf(req: ExportPdfReq):
    if req.preset not in ("kindle", "full"):
        raise HTTPException(400, "preset must be 'kindle' or 'full'")

    def work(job):
        chapters = kindle_mod.resolve_chapters(req.series, req.chapters)
        if not chapters:
            raise ValueError("no chapters found to export")
        name = (
            f"{req.series}-{req.preset}.pdf"
            if len(chapters) > 1
            else f"{req.series}-{chapters[0]}-{req.preset}.pdf"
        )
        out_path = paths.series_dir(req.series) / "exports" / name
        kindle_mod.export_pdf(req.series, chapters, req.preset, out_path, job)
        return {
            "file": str(out_path),
            "url": f"/data/series/{req.series}/exports/{name}",
        }

    job = jobs.start(
        "export-pdf", f"Exporting {req.series} ({req.preset})", work, lane="cpu"
    )
    return {"job_id": job.id}


# ---------------------------------------------------------------------------
# page images
# ---------------------------------------------------------------------------


@router.get("/api/chapters/{s}/{c}/pages/{idx}")
def get_page(s: str, c: str, idx: int):
    doc = store.read(paths.chapter_dir(s, c) / "chapter.json")
    if not doc:
        raise HTTPException(404, "no such chapter")
    page = next((p for p in doc["pages"] if p["idx"] == idx), None)
    if not page:
        raise HTTPException(404, "no such page")
    fpath = paths.chapter_dir(s, c) / page["file"]
    if not fpath.exists():
        raise HTTPException(404, "page file missing on disk")
    return FileResponse(str(fpath))


# --------------------------------------------------------------- bulk runs --


class RunReq(BaseModel):
    """A range of chapters ("0001".."0010", or numbers 1..10) and the steps
    to run for each; missing chapters are fetched when "fetch" is a step."""

    chapters: list[str] = []
    first: Optional[float] = None
    last: Optional[float] = None
    steps: list[str] = list(batch.STEPS)
    group: Optional[str] = None
    preview_voice: Optional[str] = None
    cast: bool = True  # let the model cast voices before the voice step
    render: dict = {}
    timeline: dict = {}


@router.post("/api/series/{series}/run")
def run_series(series: str, req: RunReq, request: Request):
    """Every chosen step, chapter after chapter, as one job (lane "batch")."""
    chapters = list(req.chapters)
    if not chapters and req.first is not None:
        last = req.last if req.last is not None else req.first
        chapters = [
            paths.chapter_slug(float(n)) for n in range(int(req.first), int(last) + 1)
        ]
    if not chapters:
        raise HTTPException(400, "give chapters, or first and last")
    bad = [s for s in req.steps if s not in batch.STEPS]
    if bad:
        raise HTTPException(
            400, f"unknown step(s) {bad}; steps are {list(batch.STEPS)}"
        )
    base = str(request.base_url).rstrip("/")
    opts = {
        "group": req.group,
        "preview_voice": req.preview_voice,
        "cast": req.cast,
        "render": req.render,
        "timeline": req.timeline,
    }

    def work(job):
        return batch.run_batch(base, series, chapters, list(req.steps), opts, job)

    job = jobs.start(
        "batch",
        f"Running {len(chapters)} chapter(s) of {series}: {', '.join(req.steps)}",
        work,
        lane="batch",  # its own lane: the steps it starts use the others
        series=series,
        chapters=chapters,
        steps=list(req.steps),
    )
    return {"job_id": job.id, "chapters": chapters}
