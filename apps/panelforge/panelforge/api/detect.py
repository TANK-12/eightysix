"""Detect endpoints: strip, panels, bubbles and OCR for one chapter. See
CONTRACTS.md "detect". Edits arrive through the PUT endpoints; every item
whose content changed is marked edited so re-detect keeps it.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from fastapi.responses import FileResponse, Response

from .. import jobs, paths, store, subjob
from ..detect import pipeline

router = APIRouter(prefix="/api")

_PANEL_FIELDS = ("box", "kind", "shape", "polygon", "order")
_BUBBLE_FIELDS = (
    "box",
    "kind",
    "text",
    "tail",
    "speaker",
    "panel_id",
    "order",
    "style",
)


def _chapter(series: str, chapter: str) -> Path:
    d = paths.chapter_dir(series, chapter)
    if not (d / "chapter.json").exists():
        raise HTTPException(404, f"no chapter {series}/{chapter}")
    return d


def _mark_edits(old: list[dict], new: list[dict], fields) -> list[dict]:
    by_id = {o["id"]: o for o in old}
    out = []
    for item in new:
        prev = by_id.get(item.get("id"))
        if prev is None:
            item = {**item, "edited": True, "source": "user"}
        elif any(item.get(f) != prev.get(f) for f in fields):
            item = {**item, "edited": True}
        out.append(item)
    return out


@router.post("/chapters/{series}/{chapter}/detect")
def detect_chapter(series: str, chapter: str, ocr: bool = True):
    cdir = _chapter(series, chapter)
    job = jobs.start(
        "detect",
        f"Detecting panels and bubbles in {series} {chapter}",
        lambda j: subjob.run_in_child(j, "detect", cdir, ocr=ocr),
        lane="cpu",
        series=series,
        chapter=chapter,
    )
    return {"job_id": job.id}


@router.get("/chapters/{series}/{chapter}/detect/stats")
def detect_stats(series: str, chapter: str):
    cdir = _chapter(series, chapter)
    st = store.read(cdir / "work" / "detect" / "stats.json", None)
    if st is None:
        raise HTTPException(404, "detect has not run")
    return st


@router.get("/chapters/{series}/{chapter}/panels")
def get_panels(series: str, chapter: str):
    cdir = _chapter(series, chapter)
    doc = store.read(cdir / "panels.json", None)
    if doc is None:
        raise HTTPException(404, "detect has not run")
    return doc


@router.put("/chapters/{series}/{chapter}/panels")
def put_panels(series: str, chapter: str, doc: dict):
    cdir = _chapter(series, chapter)
    if not isinstance(doc.get("panels"), list):
        raise HTTPException(422, "body needs a panels list")
    old = (store.read(cdir / "panels.json", {}) or {}).get("panels", [])
    panels = _mark_edits(old, doc["panels"], _PANEL_FIELDS)
    for n, p in enumerate(panels, 1):
        p["order"] = n
    out = {"schema": 1, "panels": panels}
    store.write(cdir / "panels.json", out)
    return out


@router.get("/chapters/{series}/{chapter}/bubbles")
def get_bubbles(series: str, chapter: str):
    cdir = _chapter(series, chapter)
    doc = store.read(cdir / "bubbles.json", None)
    if doc is None:
        raise HTTPException(404, "detect has not run")
    return doc


@router.put("/chapters/{series}/{chapter}/bubbles")
def put_bubbles(series: str, chapter: str, doc: dict):
    cdir = _chapter(series, chapter)
    if not isinstance(doc.get("bubbles"), list):
        raise HTTPException(422, "body needs a bubbles list")
    old = (store.read(cdir / "bubbles.json", {}) or {}).get("bubbles", [])
    bubbles = _mark_edits(old, doc["bubbles"], _BUBBLE_FIELDS)
    for n, b in enumerate(bubbles, 1):
        b["order"] = n
    out = {"schema": 1, "bubbles": bubbles}
    store.write(cdir / "bubbles.json", out)
    return out


@router.get("/chapters/{series}/{chapter}/panels/{pid}/image")
def panel_image(series: str, chapter: str, pid: str):
    cdir = _chapter(series, chapter)
    f = cdir / "work" / "detect" / "panels" / f"{pid}.png"
    if f.exists():
        return FileResponse(f, media_type="image/png")
    # the crops under work/ are a cache that a clean-up can remove; the
    # panel's box on the strip is the real record, so cut it from there
    import cv2

    from ..detect.strip import StripReader, build_strip

    doc = store.read(cdir / "panels.json", {"panels": []})
    p = next((x for x in doc.get("panels", []) if x.get("id") == pid), None)
    strip = store.read(cdir / "strip.json", None)
    if not strip:
        try:
            strip = build_strip(cdir)
        except ValueError:
            strip = None
    if p is None or not p.get("box") or not strip:
        raise HTTPException(404, f"no crop for {pid}")
    crop = StripReader(cdir, strip, cache_pages=2).crop([int(v) for v in p["box"]])
    if crop.size == 0:
        raise HTTPException(404, f"panel {pid!r} is outside the strip")
    if crop.shape[1] > PANEL_THUMB_W:
        h = max(1, round(crop.shape[0] * PANEL_THUMB_W / crop.shape[1]))
        crop = cv2.resize(crop, (PANEL_THUMB_W, h), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 82])
    if not ok:
        raise HTTPException(500, "could not encode the crop")
    return Response(buf.tobytes(), media_type="image/jpeg")


PANEL_THUMB_W = 640  # a panel cut from the strip is only shown as a thumbnail


BUBBLE_PAD = 14  # pixels of strip kept around a balloon crop


@router.get("/chapters/{series}/{chapter}/bubbles/{bid}/image")
def bubble_image(series: str, chapter: str, bid: str):
    """The balloon as drawn, cut from the strip with a little margin, so
    the lines editor can show which words a line is."""
    import cv2

    from ..detect.strip import StripReader

    cdir = _chapter(series, chapter)
    doc = store.read(cdir / "bubbles.json", {"bubbles": []})
    b = next((x for x in doc.get("bubbles", []) if x.get("id") == bid), None)
    if b is None:
        raise HTTPException(404, f"no balloon {bid!r}")
    strip = store.read(cdir / "strip.json", None)
    if not strip:
        raise HTTPException(404, "no strip.json for this chapter")
    x, y, w, h = (int(v) for v in b["box"])
    reader = StripReader(cdir, strip, cache_pages=2)
    rows = reader.rows(y - BUBBLE_PAD, y + h + BUBBLE_PAD)
    x0, x1 = max(0, x - BUBBLE_PAD), min(reader.width, x + w + BUBBLE_PAD)
    crop = rows[:, x0:x1]
    if crop.size == 0:
        raise HTTPException(404, f"balloon {bid!r} is outside the strip")
    ok, buf = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 82])
    if not ok:
        raise HTTPException(500, "could not encode the crop")
    return Response(buf.tobytes(), media_type="image/jpeg")


# ------------------------------------------------------------ series words --


class SeriesWords(BaseModel):
    words: list[str] = []  # always in the reader's glossary
    banned: list[str] = []  # never in it


@router.get("/series/{series}/words")
def get_series_words(series: str):
    """The reader's glossary for a series: learned names plus the words a
    person added or banned (`glossary.json` in the series folder)."""
    from ..detect import normalize as N

    sdir = paths.series_dir(series)
    chapters = sorted(sdir.glob("chapters/*"))
    learned = N.learn_glossary(chapters[0] if chapters else sdir / "chapters" / "-")
    extra = N.read_series_words(sdir)
    return {"learned": sorted(learned), **extra}


@router.put("/series/{series}/words")
def put_series_words(series: str, body: SeriesWords):
    sdir = paths.series_dir(series)
    if not sdir.exists():
        raise HTTPException(404, f"no series {series!r}")
    doc = {
        "words": sorted({w.strip() for w in body.words if w.strip()}),
        "banned": sorted({w.strip() for w in body.banned if w.strip()}),
    }
    store.write(sdir / "glossary.json", doc)
    return {"ok": True, **doc}
