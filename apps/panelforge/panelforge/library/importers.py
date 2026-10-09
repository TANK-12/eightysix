"""Import chapters from a folder, CBZ, CBR or PDF, or a raw multipart upload.

Every importer ends up with plain image files in
``<chapter_dir>/pages/NNN.ext``, verified the same way a fetch is, and a
``chapter.json`` with ``capture: "import"``.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

from .. import paths, store
from . import verify as verify_mod

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}

# unrar/7z/bsdtar are all present on this machine (checked 2026-09-17), so
# CBR extraction works without installing anything.
_CBR_TOOLS = [
    ("unrar", ["unrar", "x", "-y", "-inul"]),
    ("7z", ["7z", "x", "-y"]),
    ("bsdtar", ["bsdtar", "-x", "-f"]),
]


def _sha1(path: Path) -> str:
    h = hashlib.sha1()
    h.update(path.read_bytes())
    return h.hexdigest()


def _sorted_images(folder: Path) -> list[Path]:
    return sorted(
        (p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXT),
        key=lambda p: str(p).lower(),
    )


def _write_chapter(
    series: str, number: float, title: str, srcs: list[Path], job, source_label: str
) -> dict:
    chapter = paths.chapter_slug(number)
    cdir = paths.chapter_dir(series, chapter)
    pages_dir = cdir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    pages = []
    for idx, src in enumerate(srcs, start=1):
        data = src.read_bytes()
        chk = verify_mod.mf.verify_page_bytes(data)
        if not chk.ok:
            job.log(f"page {idx} ({src.name}): {chk.reason}")
            continue
        ext = src.suffix.lstrip(".").lower() or "png"
        fname = f"{idx:03d}.{ext}"
        (pages_dir / fname).write_bytes(data)
        pages.append(
            {
                "idx": idx,
                "file": f"pages/{fname}",
                "w": chk.width,
                "h": chk.height,
                "sha1": _sha1(pages_dir / fname),
                "capture": "import",
            }
        )
    result = verify_mod.verify_chapter_pages(pages, pages_dir)
    if not result["ok"]:
        job.log(f"import: {len(result['problems'])} page problem(s)")
    doc = {
        "schema": 1,
        "series": series,
        "chapter": chapter,
        "number": number,
        "title": title or f"Chapter {number:g}",
        "source": {"site": source_label, "url": ""},
        "layout": "strip",
        "reading": "ttb",
        "pages": pages,
    }
    store.write(cdir / "chapter.json", doc)
    _ensure_series(series, title if number == 1 else series)
    return {"chapter": chapter, "pages": len(pages), "verify": result}


def _ensure_series(series: str, title_guess: str) -> None:
    sfile = paths.series_dir(series) / "series.json"
    if not sfile.exists():
        store.write(
            sfile,
            {
                "schema": 1,
                "series": series,
                "title": title_guess or series,
                "source": {"site": "import", "url": ""},
                "format": "webtoon",
            },
        )


def import_folder(
    path: str, series: Optional[str], number: Optional[float], job
) -> dict:
    folder = Path(path).expanduser()
    if not folder.is_dir():
        raise ValueError(f"not a folder: {path}")
    series = series or paths.slug(folder.name)
    number = number if number is not None else 1
    imgs = _sorted_images(folder)
    if not imgs:
        raise ValueError(f"no images found under {path}")
    job.log(f"importing {len(imgs)} image(s) from folder {path}")
    return _write_chapter(series, number, folder.name, imgs, job, "import-folder")


def import_cbz(path: str, series: Optional[str], number: Optional[float], job) -> dict:
    p = Path(path).expanduser()
    series = series or paths.slug(p.stem)
    number = number if number is not None else 1
    with tempfile.TemporaryDirectory(prefix="pf-cbz-") as tmp:
        with zipfile.ZipFile(p) as zf:
            zf.extractall(tmp)
        imgs = _sorted_images(Path(tmp))
        if not imgs:
            raise ValueError(f"no images found inside {path}")
        job.log(f"importing {len(imgs)} image(s) from CBZ {p.name}")
        return _write_chapter(series, number, p.stem, imgs, job, "import-cbz")


def import_cbr(path: str, series: Optional[str], number: Optional[float], job) -> dict:
    p = Path(path).expanduser()
    series = series or paths.slug(p.stem)
    number = number if number is not None else 1
    tool = None
    for name, cmd in _CBR_TOOLS:
        if shutil.which(cmd[0]):
            tool = (name, cmd)
            break
    if tool is None:
        raise ValueError(
            "no CBR/RAR extractor found on this system (checked unrar, 7z, bsdtar); "
            "report this rather than installing packages without review"
        )
    name, cmd = tool
    with tempfile.TemporaryDirectory(prefix="pf-cbr-") as tmp:
        subprocess.run(cmd + [str(p)], cwd=tmp, capture_output=True, check=True)
        imgs = _sorted_images(Path(tmp))
        if not imgs:
            raise ValueError(f"no images found inside {path} (extracted with {name})")
        job.log(f"importing {len(imgs)} image(s) from CBR {p.name} (via {name})")
        return _write_chapter(series, number, p.stem, imgs, job, "import-cbr")


def import_pdf(path: str, series: Optional[str], number: Optional[float], job) -> dict:
    import pymupdf as fitz

    p = Path(path).expanduser()
    series = series or paths.slug(p.stem)
    number = number if number is not None else 1
    with tempfile.TemporaryDirectory(prefix="pf-pdf-") as tmp:
        tmp_dir = Path(tmp)
        doc = fitz.open(p)
        imgs = []
        for i in range(1, doc.page_count + 1):
            page = doc[i - 1]
            pix = page.get_pixmap(dpi=200)
            out = tmp_dir / f"{i:04d}.png"
            pix.save(out)
            imgs.append(out)
        doc.close()
        if not imgs:
            raise ValueError(f"no pages found inside {path}")
        job.log(f"importing {len(imgs)} page(s) from PDF {p.name}")
        return _write_chapter(series, number, p.stem, imgs, job, "import-pdf")


def import_path(path: str, series: Optional[str], number: Optional[float], job) -> dict:
    p = Path(path).expanduser()
    if p.is_dir():
        return import_folder(path, series, number, job)
    ext = p.suffix.lower()
    if ext == ".cbz" or ext == ".zip":
        return import_cbz(path, series, number, job)
    if ext == ".cbr" or ext == ".rar":
        return import_cbr(path, series, number, job)
    if ext == ".pdf":
        return import_pdf(path, series, number, job)
    raise ValueError(f"unsupported file type: {ext}")


def import_upload(
    files: list[tuple[str, bytes]], series: Optional[str], number: Optional[float], job
) -> dict:
    """files: list of (filename, bytes) from a multipart drag-and-drop."""
    series = series or "uploaded"
    number = number if number is not None else 1
    with tempfile.TemporaryDirectory(prefix="pf-upload-") as tmp:
        tmp_dir = Path(tmp)
        for name, data in files:
            (tmp_dir / Path(name).name).write_bytes(data)
        imgs = _sorted_images(tmp_dir)
        if not imgs:
            raise ValueError("no images in upload")
        job.log(f"importing {len(imgs)} uploaded image(s)")
        return _write_chapter(series, number, series, imgs, job, "import-upload")
