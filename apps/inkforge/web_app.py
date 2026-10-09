"""InkForge -- read the existing Komikku manga library, and PDFs, in Forge.

Komikku (~/.local/share/komikku/) already tracks and downloads a manga
library; this app never writes to komikku.db -- it is opened read-only so
InkForge can never corrupt or race with Komikku itself. Reading progress is
tracked separately, in this app's own data dir. PDFs are imported (rasterized
to PNG with pymupdf, the same call PanelForge's importer uses) into that same
data dir and read through the same page viewer.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

ROOT = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(ROOT, "static")
SHARED_DIR = os.environ.get("FORGE_SHARED_DIR") or os.path.join(
    ROOT, "..", "..", "shared"
)

KOMIKKU_DB = Path(
    os.environ.get("INKFORGE_KOMIKKU_DB")
    or os.path.expanduser("~/.local/share/komikku/komikku.db")
)
KOMIKKU_DATA_DIR = Path(
    os.environ.get("INKFORGE_KOMIKKU_DATA_DIR")
    or os.path.expanduser("~/.local/share/komikku")
)
DATA_DIR = Path(
    os.environ.get("INKFORGE_DATA_DIR") or os.path.expanduser("~/InkForgeData")
)
PDF_DIR = DATA_DIR / "pdfs"
LIBRARY_FILE = PDF_DIR / "library.json"
PROGRESS_FILE = DATA_DIR / "progress.json"
# Requests run in a thread pool, so two at once could each read a JSON file,
# change it and write it back, and one change would be lost: one lock covers
# every read-modify-write of library.json and progress.json.
_STATE_LOCK = threading.Lock()
MAX_KEY_LEN = 300

app = FastAPI(title="InkForge")


def _komikku_conn() -> sqlite3.Connection:
    uri = f"file:{KOMIKKU_DB}?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    return con


def _natural_key(name: str):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", name)]


def _chapter_dir(manga_name: str, chapter_num) -> Optional[Path]:
    """Find <server>/<manga name>/<chapter num> under Komikku's data dir.

    Komikku stores each source under its own server-slug folder; we don't
    know which server a given manga came from ahead of time, so search the
    handful of server directories rather than hardcoding one.
    """
    if not KOMIKKU_DATA_DIR.is_dir():
        return None
    # Komikku's chapter folders are named without a trailing ".0" (e.g. "36"),
    # but the db's `num` column has REAL affinity, so a whole chapter number
    # comes back as a float (36.0) -- format it the way the folder is named.
    num_str = f"{chapter_num:g}" if isinstance(chapter_num, float) else str(chapter_num)
    for server_dir in KOMIKKU_DATA_DIR.iterdir():
        if not server_dir.is_dir():
            continue
        candidate = server_dir / manga_name / num_str
        if candidate.is_dir():
            return candidate
    return None


def _list_pages(chapter_dir: Path) -> list[str]:
    exts = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    names = [p.name for p in chapter_dir.iterdir() if p.suffix.lower() in exts]
    return sorted(names, key=_natural_key)


def _num_sort_key(num):
    try:
        return float(num)
    except (TypeError, ValueError):
        return 0.0


def _chapter_summary(row: sqlite3.Row) -> dict:
    """A chapter row, with `pages` turned from Komikku's page-metadata JSON
    blob into a plain page count for the shelf/chapter-list UI."""
    d = dict(row)
    try:
        d["pages"] = len(json.loads(d["pages"]) or [])
    except (TypeError, ValueError, json.JSONDecodeError):
        d["pages"] = 0
    return d


def _read_json_dict(path: Path) -> dict:
    """A JSON object from `path`, or {} when it is missing, unreadable or not
    an object (a hand-edited or half-written file must not break the app)."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, data: dict) -> None:
    """Write through a temp file and rename, so a crash mid-write leaves the
    old file whole instead of an empty or cut-off one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.replace(tmp, path)


def _load_progress() -> dict:
    return _read_json_dict(PROGRESS_FILE)


def _save_progress(data: dict) -> None:
    _write_json(PROGRESS_FILE, data)


def _load_pdf_library() -> dict:
    data = _read_json_dict(LIBRARY_FILE)
    return {k: v for k, v in data.items() if isinstance(v, dict)}


def _save_pdf_library(data: dict) -> None:
    _write_json(LIBRARY_FILE, data)


def _chapter_location(chapter_id: int) -> Path:
    """The folder holding a Komikku chapter's pages, or an HTTP error that
    says plainly why there is none."""
    if not KOMIKKU_DB.exists():
        raise HTTPException(404, "Komikku's library was not found")
    try:
        con = _komikku_conn()
        try:
            row = con.execute(
                "SELECT chapters.num AS num, mangas.name AS manga_name "
                "FROM chapters JOIN mangas ON mangas.id = chapters.manga_id "
                "WHERE chapters.id = ?",
                (chapter_id,),
            ).fetchone()
        finally:
            con.close()
    except sqlite3.Error as e:
        raise HTTPException(503, f"could not read Komikku library: {e}")
    if row is None:
        raise HTTPException(404, "no such chapter")
    chapter_dir = _chapter_dir(row["manga_name"], row["num"])
    if chapter_dir is None:
        raise HTTPException(404, "chapter has no downloaded pages on disk")
    return chapter_dir


class ProgressUpdate(BaseModel):
    page: int = Field(ge=0, le=1_000_000)


def _check_key(item_key: str) -> None:
    if not item_key or len(item_key) > MAX_KEY_LEN:
        raise HTTPException(400, "progress key must be 1-300 characters")


@app.get("/api/library")
def library():
    mangas: list[dict] = []
    komikku_error = ""
    if KOMIKKU_DB.exists():
        try:
            con = _komikku_conn()
            try:
                rows = con.execute(
                    "SELECT id, name, authors, status FROM mangas WHERE in_library = 1"
                ).fetchall()
                for m in rows:
                    chapters = con.execute(
                        "SELECT id, title, num, pages, downloaded, "
                        "read_progress, last_page_read_index "
                        "FROM chapters WHERE manga_id = ? AND downloaded = 1",
                        (m["id"],),
                    ).fetchall()
                    if not chapters:
                        continue
                    out_chapters = [_chapter_summary(c) for c in chapters]
                    out_chapters.sort(key=lambda c: _num_sort_key(c["num"]))
                    mangas.append(
                        {
                            "id": m["id"],
                            "name": m["name"],
                            "authors": m["authors"],
                            "status": m["status"],
                            "chapters": out_chapters,
                        }
                    )
            finally:
                con.close()
        except sqlite3.Error as e:
            # The imported PDFs are still readable: report the Komikku
            # problem beside them instead of failing the whole library.
            komikku_error = f"Could not read Komikku's library ({e})."
    return {
        "mangas": mangas,
        "pdfs": list(_load_pdf_library().values()),
        "komikku_error": komikku_error,
    }


@app.get("/api/komikku/chapter/{chapter_id}/pages")
def komikku_chapter_pages(chapter_id: int):
    return {"pages": _list_pages(_chapter_location(chapter_id))}


@app.get("/api/komikku/page/{chapter_id}/{page_name}")
def komikku_page(chapter_id: int, page_name: str):
    path = _chapter_location(chapter_id) / page_name
    if path.name != page_name or not path.is_file():
        raise HTTPException(404, "no such page")
    return FileResponse(path)


@app.post("/api/pdf/import")
async def import_pdf(file: UploadFile):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "only .pdf files can be imported")

    doc_id = uuid.uuid4().hex[:12]
    doc_dir = PDF_DIR / doc_id
    try:
        page_count = await run_in_threadpool(_store_and_rasterize, file, doc_dir)
    except OSError as exc:
        # Disk full or no permission: the file may be fine, so say what failed.
        shutil.rmtree(doc_dir, ignore_errors=True)
        raise HTTPException(500, f"Could not save the import ({exc.strerror or exc}).")
    except Exception:
        # Only this import's own fresh folder is removed: a half-made import
        # must not linger as a broken shelf entry or eat disk space.
        shutil.rmtree(doc_dir, ignore_errors=True)
        raise HTTPException(400, "That file is not a readable PDF.")
    if page_count == 0:
        shutil.rmtree(doc_dir, ignore_errors=True)
        raise HTTPException(400, "That PDF has no pages.")

    entry = {
        "id": doc_id,
        "title": Path(file.filename).stem[:200] or "Untitled",
        "pages": page_count,
        "added": time.time(),
    }
    with _STATE_LOCK:
        library_data = _load_pdf_library()
        library_data[doc_id] = entry
        _save_pdf_library(library_data)
    return entry


def _store_and_rasterize(file: UploadFile, doc_dir: Path) -> int:
    """Stream the upload to disk (never the whole file in memory) and render
    every page to PNG. Runs in a worker thread so a long book does not freeze
    the server's other requests. Returns the page count."""
    import pymupdf as fitz

    pages_dir = doc_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    source_path = doc_dir / "source.pdf"
    file.file.seek(0)
    with source_path.open("wb") as out:
        shutil.copyfileobj(file.file, out, 1024 * 1024)
    with source_path.open("rb") as f:
        if b"%PDF-" not in f.read(1024):
            raise ValueError("no PDF header")

    doc = fitz.open(source_path)
    try:
        page_count = doc.page_count
        for i in range(page_count):
            pix = doc[i].get_pixmap(dpi=200)
            pix.save(pages_dir / f"{i:04d}.png")
    finally:
        doc.close()
    return page_count


@app.get("/api/pdf/{doc_id}/page/{n}")
def pdf_page(doc_id: str, n: int):
    library_data = _load_pdf_library()
    if doc_id not in library_data:
        raise HTTPException(404, "no such imported PDF")
    path = PDF_DIR / doc_id / "pages" / f"{n:04d}.png"
    if not path.is_file():
        raise HTTPException(404, "no such page")
    return FileResponse(path)


@app.get("/api/progress/{item_key:path}")
def get_progress(item_key: str):
    _check_key(item_key)
    entry = _load_progress().get(item_key)
    if not isinstance(entry, dict) or not isinstance(entry.get("page"), int):
        # `saved: false` lets the reader fall back to Komikku's own position.
        return {"page": 0, "saved": False}
    return {**entry, "page": max(0, entry["page"]), "saved": True}


@app.post("/api/progress/{item_key:path}")
def set_progress(item_key: str, body: ProgressUpdate):
    _check_key(item_key)
    with _STATE_LOCK:
        data = _load_progress()
        data[item_key] = {"page": body.page, "at": time.time()}
        _save_progress(data)
    return {"ok": True}


if os.path.isdir(SHARED_DIR):
    app.mount("/shared", StaticFiles(directory=SHARED_DIR), name="shared")
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
