"""Orchestrates a source module's fetch_title/fetch_chapter into the on-disk
layout CONTRACTS.md describes, verifying every page and writing chapter.json.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

from .. import paths, store
from ..sources import find_for_url, get as get_source
from . import verify as verify_mod


def _sha1(path: Path) -> str:
    h = hashlib.sha1()
    h.update(path.read_bytes())
    return h.hexdigest()


def fetch_title(url: str, job) -> dict:
    """POST /api/fetch/title -> {title, series, chapters:[...]}."""
    name = find_for_url(url) or "generic"
    src = get_source(name)
    job.log(f"using source '{name}' for {url}")
    info = src.fetch_title(url, job)
    series_slug = paths.slug(info["title"])
    series_dir = paths.series_dir(series_slug)
    if not (series_dir / "series.json").exists():
        store.write(
            series_dir / "series.json",
            {
                "schema": 1,
                "series": series_slug,
                "title": info["title"],
                "source": {"site": getattr(src, "SITE", name), "url": url},
                "format": "webtoon",
            },
        )
    return {"title": info["title"], "series": series_slug, "chapters": info["chapters"]}


def fetch_one_chapter(
    series: str, source_name: str, chapter_url: str, number: float, title: str, job
) -> dict:
    src = get_source(source_name)
    chapter = paths.chapter_slug(number)
    cdir = paths.chapter_dir(series, chapter)
    cdir.mkdir(parents=True, exist_ok=True)
    job.log(f"fetching chapter {number} from {chapter_url}")
    raw_pages = src.fetch_chapter(chapter_url, cdir, job)
    pages_dir = cdir / "pages"
    pages = []
    for p in sorted(raw_pages, key=lambda p: p["idx"]):
        fpath = pages_dir / Path(p["file"]).name
        pages.append(
            {
                "idx": p["idx"],
                "file": p["file"],
                "w": p["w"],
                "h": p["h"],
                "sha1": _sha1(fpath),
                "capture": p.get("capture", "download"),
            }
        )
    result = verify_mod.verify_chapter_pages(pages, pages_dir)
    if not result["ok"]:
        job.log(
            f"chapter {number}: {len(result['problems'])} page problem(s): {result['problems'][:5]}"
        )
    doc = {
        "schema": 1,
        "series": series,
        "chapter": chapter,
        "number": number,
        "title": title or f"Chapter {number:g}",
        "source": {"site": getattr(src, "SITE", source_name), "url": chapter_url},
        "layout": "strip",
        "reading": "ttb",
        "pages": pages,
    }
    store.write(cdir / "chapter.json", doc)
    return {"chapter": chapter, "pages": len(pages), "verify": result}


def pick_group(chapters: list[dict], group: Optional[str], job=None) -> list[dict]:
    """One entry per chapter number: the wanted scan group when the chapter
    has it, else the first listed. Emerson wants the WebToon scans of Bad
    Born Blood, not Asura's; a site can list both."""
    by_num: dict[float, list[dict]] = {}
    for c in chapters:
        by_num.setdefault(c["number"], []).append(c)
    out = []
    missing = 0
    for num in sorted(by_num):
        options = by_num[num]
        hit = next((c for c in options if group and c.get("group") == group), None)
        if group and hit is None and any(c.get("group") for c in options):
            missing += 1
        out.append(hit or options[0])
    if group and missing and job is not None and hasattr(job, "log"):
        job.log(
            f"{missing} chapter(s) have no {group!r} version; took the first listed"
        )
    return out


def fetch_chapters(
    url: Optional[str],
    series: Optional[str],
    chapters_wanted,
    job,
    group: Optional[str] = None,
) -> dict:
    """POST /api/fetch/chapters. Either a title URL (fetch its list first) or
    an existing series (use its stored source + a fresh title fetch to get
    URLs again, since only chapter.json for already-fetched chapters is kept).
    """
    if url:
        info = fetch_title(url, job)
        series = info["series"]
        chapters = info["chapters"]
        source_name = find_for_url(url) or "generic"
    else:
        if not series:
            raise ValueError("need either url or series")
        sdoc = store.read(paths.series_dir(series) / "series.json")
        if not sdoc:
            raise ValueError(f"no such series: {series}")
        title_info = fetch_title(sdoc["source"]["url"], job)
        chapters = title_info["chapters"]
        source_name = find_for_url(sdoc["source"]["url"]) or "generic"

    assert series is not None

    chapters = pick_group(chapters, group, job)
    if chapters_wanted != "all":
        wanted = set(float(n) for n in chapters_wanted)
        chapters = [c for c in chapters if c["number"] in wanted]

    done = []
    for i, c in enumerate(chapters):
        job.check() if hasattr(job, "check") else None
        job.progress(i / max(1, len(chapters)))
        done.append(
            fetch_one_chapter(
                series, source_name, c["url"], c["number"], c.get("title", ""), job
            )
        )
    return {"series": series, "chapters": done}
