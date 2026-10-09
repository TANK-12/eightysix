"""Scene endpoints: analyze job, scene.json, cast (names, merges, splits) and
assets. Voices are set through the audio endpoints only."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..scene import cast as cast_mod
from .. import jobs, paths, store, subjob
from ..scene import pipeline

router = APIRouter(prefix="/api")

ASSET_KINDS = ("cast", "extras", "backgrounds", "props")


def _chapter(series: str, chapter: str) -> Path:
    d = paths.chapter_dir(series, chapter)
    if not (d / "chapter.json").exists():
        raise HTTPException(404, f"no chapter {series}/{chapter}")
    return d


def _cast_path(series: str) -> Path:
    return paths.series_dir(series) / "cast.json"


@router.post("/chapters/{series}/{chapter}/analyze")
def analyze_chapter(series: str, chapter: str):
    cdir = _chapter(series, chapter)
    job = jobs.start(
        "analyze",
        f"Analysing scenes and cast in {series} {chapter}",
        lambda j: subjob.run_in_child(j, "analyze", cdir),
        lane="cpu",
        series=series,
        chapter=chapter,
    )
    return {"job_id": job.id}


@router.get("/chapters/{series}/{chapter}/scene")
def get_scene(series: str, chapter: str):
    cdir = _chapter(series, chapter)
    doc = store.read(cdir / "scene.json", None)
    if doc is None:
        raise HTTPException(404, "analyze has not run")
    return doc


@router.get("/chapters/{series}/{chapter}/scene/stats")
def scene_stats(series: str, chapter: str):
    cdir = _chapter(series, chapter)
    st = store.read(cdir / "work" / "scene" / "stats.json", None)
    if st is None:
        raise HTTPException(404, "analyze has not run")
    return st


@router.get("/series/{series}/cast")
def get_cast(series: str):
    doc = store.read(_cast_path(series), None)
    if doc is None:
        raise HTTPException(404, "no cast yet: run analyze")
    return doc


class CastEdit(BaseModel):
    rename: dict[str, str] | None = (
        None  # id -> name (cast) or label (extras, backgrounds)
    )
    merge: list[list[str]] | None = None  # groups of cast ids; the first id survives
    promote: list[str] | None = None  # extra ids that become cast
    colors: dict[str, str] | None = None
    # appearance key "chapter/panel:index" -> a cast id, "new" (one new
    # character for every "new" in this request) or "none" (not a person).
    # Split = assign the wrong crops to "new"; drop = assign to "none".
    assign: dict[str, str] | None = None
    chapter: str | None = None  # for records that predate per-chapter keys


def _chapter_apps(cdir: Path) -> list[dict]:
    """This chapter's appearance records, as cast.apply_assignments wants them."""
    sc = store.read(cdir / "scene.json", None) or {}
    return [
        {
            "panel_id": pid,
            "index": i,
            "cutout": c.get("cutout"),
            "face": c.get("face"),
            "box": c.get("box"),
            "area_frac": c.get("area_frac"),
        }
        for pid, sp in sc.get("panels", {}).items()
        for i, c in enumerate(sp.get("characters", []))
    ]


def _apply_edit(doc: dict, edit: CastEdit, chapter_dirs: list[Path]) -> dict:
    by_id = {c["id"]: c for c in doc["cast"]}
    extras = {x["id"]: x for x in doc["extras"]}
    remap: dict[str, str] = {}
    ledger: dict[str, str] = doc.setdefault("assignments", {})
    default_chapter = edit.chapter or (chapter_dirs[-1].name if chapter_dirs else "")

    def record(entry: dict, target: str) -> None:
        for x in entry.get("appearances", []):
            key = cast_mod.appearance_key(
                x.get("chapter") or default_chapter, x["panel_id"], x["index"]
            )
            ledger[key] = target

    for xid in edit.promote or []:
        x = extras.pop(xid, None)
        if x is None:
            continue
        n = len(by_id) + 1
        cid = f"c{n:02d}"
        while cid in by_id:
            n += 1
            cid = f"c{n:02d}"
        by_id[cid] = {
            "id": cid,
            "name": x.get("label") or f"character {n}",
            "auto_name": f"character {n}",
            "color": "#c0c0c0",
            "samples": x.get("samples", []),
            "embedding": None,
            "voice": x.get("voice"),
            "rig": None,
            "model3d": None,
            "appearances": x.get("appearances", []),
            "panels": x.get("panels", []),
            "edited": True,
        }
        remap[xid] = cid
    for group in edit.merge or []:
        keep = [g for g in group if g in by_id]
        if len(keep) < 2:
            continue
        head = by_id[keep[0]]
        record(head, keep[0])
        for other in keep[1:]:
            o = by_id.pop(other)
            record(o, keep[0])
            head["appearances"] = head.get("appearances", []) + o.get("appearances", [])
            head["panels"] = sorted(
                set(head.get("panels", [])) | set(o.get("panels", []))
            )
            head["samples"] = (head.get("samples", []) + o.get("samples", []))[:6]
            if not head.get("voice") and o.get("voice"):
                head["voice"] = o["voice"]
            remap[other] = keep[0]
        head["edited"] = True
    for cid, name in (edit.rename or {}).items():
        if cid in by_id:
            by_id[cid]["name"] = name
            by_id[cid]["edited"] = True
        elif cid in extras:
            extras[cid]["label"] = name
        for b in doc.get("backgrounds", []):
            if b["id"] == cid:
                b["label"] = name
    for cid, color in (edit.colors or {}).items():
        if cid in by_id:
            by_id[cid]["color"] = color
    doc["cast"] = list(by_id.values())
    doc["extras"] = list(extras.values())
    new_id: str | None = None
    for key, target in (edit.assign or {}).items():
        if target == "new":
            new_id = new_id or cast_mod.free_cast_id(doc)
            target = new_id
        ledger[key] = target
    if remap or edit.assign:
        series_dir = chapter_dirs[0].parent.parent if chapter_dirs else None
        for cdir in chapter_dirs:
            sc = store.read(cdir / "scene.json", None)
            if not sc or series_dir is None:
                continue
            cast_mod.apply_assignments(
                doc, cdir.name, _chapter_apps(cdir), cdir, series_dir
            )
            cast_mod.sync_scene_ids(sc, doc, cdir.name)
            for s in sc.get("speakers", {}).values():
                if s.get("speaker") in remap:
                    s["speaker"] = remap[s["speaker"]]
            store.write(cdir / "scene.json", sc)
    return doc


def _appearance_items(series: str, chapter: str, placements=None) -> list[dict]:
    cdir = paths.chapter_dir(series, chapter)
    sc = store.read(cdir / "scene.json", None)
    if sc is None:
        raise HTTPException(404, "no scene.json yet: run analyze")
    items = []
    for pid, sp in sc.get("panels", {}).items():
        for i, c in enumerate(sp.get("characters", [])):
            placement = c.get("placement") or (
                "cast"
                if c.get("cast_id")
                else "extra" if c.get("extra_id") else "unplaced"
            )
            if placements and placement not in placements:
                continue
            items.append(
                {
                    "key": cast_mod.appearance_key(chapter, pid, i),
                    "panel_id": pid,
                    "index": i,
                    "placement": placement,
                    "cast_id": c.get("cast_id") or c.get("extra_id"),
                    "score": c.get("score"),
                    "area_frac": c.get("area_frac"),
                    "face": c.get("face") is not None,
                    "image": (
                        f"/data/series/{series}/chapters/{chapter}/{c['cutout']}"
                        if c.get("cutout")
                        else None
                    ),
                }
            )
    items.sort(key=lambda x: (x["placement"] != "unplaced", -(x["area_frac"] or 0)))
    return items


@router.get("/series/{series}/cast/unsorted")
def unsorted_appearances(series: str, chapter: str):
    """Crops the grouping did not place: faceless people that matched nobody
    (`unplaced`) and boxes judged not to be people (`rejected`), with the
    ledger key the cast tab uses to assign them by hand."""
    return {
        "chapter": chapter,
        "items": _appearance_items(series, chapter, ("unplaced", "rejected")),
    }


@router.get("/series/{series}/cast/appearances")
def all_appearances(series: str, chapter: str):
    """Every appearance of the chapter with its cast id and ledger key, for
    the per-character crop strips in the cast tab."""
    items = _appearance_items(series, chapter)
    items.sort(key=lambda x: (x["panel_id"], x["index"]))
    return {"chapter": chapter, "items": items}


@router.put("/series/{series}/cast")
def put_cast(series: str, body: dict):
    """Either a whole cast.json to store, or an edit {rename, merge, promote, colors, assign}."""
    path = _cast_path(series)
    doc = store.read(path, None)
    if doc is None:
        raise HTTPException(404, "no cast yet: run analyze")
    if "cast" in body and isinstance(body["cast"], list):
        old_voices = {c["id"]: c.get("voice") for c in doc["cast"]}
        for c in body["cast"]:
            c.setdefault("voice", old_voices.get(c["id"]))
        doc = {**doc, **body}
    else:
        chapters = sorted((paths.series_dir(series) / "chapters").glob("*"))
        doc = _apply_edit(doc, CastEdit(**body), chapters)
    store.write(path, doc)
    return doc


@router.get("/series/{series}/assets/{kind}")
def get_assets(series: str, kind: str):
    if kind not in ASSET_KINDS:
        raise HTTPException(404, f"unknown asset kind {kind}")
    doc = store.read(_cast_path(series), None) or {}
    items = doc.get(kind, [])
    folder = paths.series_dir(series) / "assets" / kind
    files = (
        sorted(
            str(f.relative_to(paths.series_dir(series))) for f in folder.rglob("*.png")
        )
        if folder.exists()
        else []
    )
    return {"kind": kind, "items": items, "files": files}
