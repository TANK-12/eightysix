"""Render endpoints: styles and transitions registries, the timeline (auto
build, get, put), previews (style comparison, one panel, one shot) and the
full chapter render. See CONTRACTS.md "render".

Long work runs as a job in lane "render" so a preview never blocks detect or
scene analysis, and files under ~/PanelForgeData come back as /data/... urls.
"""

from __future__ import annotations

import copy
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import jobs, paths, store, styles, transitions
from ..render import encode
from ..render import timeline as TL
from ..render.inputs import ChapterInputs
from ..render.renderer import render_timeline

router = APIRouter(prefix="/api")

PREVIEW_HEIGHT = 360


# ---------------------------------------------------------------- helpers --


def _cdir(series: str, chapter: str) -> Path:
    cdir = paths.chapter_dir(series, chapter)
    if not (cdir / "chapter.json").exists():
        raise HTTPException(404, f"no chapter {series}/{chapter}")
    return cdir


def _url(path: Path) -> str:
    rel = Path(path).resolve().relative_to(paths.DATA_ROOT.resolve())
    return "/data/" + rel.as_posix()


def _timeline_path(cdir: Path) -> Path:
    return cdir / "timeline.json"


def _timeline(cdir: Path, inp: ChapterInputs | None = None, log=None) -> dict:
    """The saved timeline, or a freshly built and saved one."""
    tl = store.read(_timeline_path(cdir))
    if tl and tl.get("shots"):
        return tl
    inp = inp or ChapterInputs(cdir)
    tl = TL.build(inp, tl, log=log)
    store.write(_timeline_path(cdir), tl)
    return tl


def _merged_style_settings(tl: dict, given: dict | None) -> dict | None:
    """The timeline's per-style knobs with the request's laid over them,
    style by style, so setting the scroll width leaves the 3D layers alone."""
    if not given:
        return None
    merged = copy.deepcopy((tl.get("settings") or {}).get("style_settings") or {})
    for name, knobs in given.items():
        if isinstance(knobs, dict):
            merged[name] = {**merged.get(name, {}), **knobs}
    return merged


def _with_settings(tl: dict, **over) -> dict:
    over = {k: v for k, v in over.items() if v is not None}
    settings = {**TL.DEFAULT_SETTINGS, **(tl.get("settings") or {}), **over}
    return {**tl, "settings": settings}


def _shots_for_panels(tl: dict, panel_ids: list[str]) -> list[dict]:
    wanted = set(panel_ids)
    shots = [
        s
        for s in tl.get("shots", [])
        if s.get("panel_id") in wanted or set(s.get("panels") or []) & wanted
    ]
    if not shots:
        raise ValueError("none of those panels has a shot in the timeline")
    return copy.deepcopy(shots)


def _limit_shots(
    tl: dict, shot_ids: list[str] | None, max_seconds: float | None
) -> list[str] | None:
    """Which shot ids a render should cover.

    An explicit list, or the first ``max_seconds`` worth of shots from the
    start, or None for the whole chapter. Timeline order is kept and
    timeline.json is never rewritten, so a short look-see render does not
    disturb the saved chapter.
    """
    shots = tl.get("shots", [])
    if shot_ids:
        wanted = set(shot_ids)
        chosen = [s for s in shots if s.get("id") in wanted]
        if not chosen:
            raise ValueError("none of those shots is in the timeline")
    else:
        chosen = list(shots)
    if max_seconds and max_seconds > 0:
        kept: list[dict] = []
        total = 0.0
        for s in chosen:
            if kept and total >= max_seconds:
                break
            kept.append(s)
            total += float(s.get("dur") or 0.0)
        chosen = kept
    if not shot_ids and len(chosen) == len(shots):
        return None
    return [s["id"] for s in chosen]


def _check_style(style: str | None) -> str | None:
    if style is not None and style not in styles.REGISTRY:
        raise HTTPException(400, f"unknown style {style!r}")
    return style


def _safe_name(name: str | None, default: str) -> str:
    stem = paths.slug(Path(name).stem) if name else default
    return stem + ".mp4"


# -------------------------------------------------------------- registries --


@router.get("/styles")
def list_styles():
    return {"styles": styles.listing(), "default": TL.DEFAULT_SETTINGS["style"]}


@router.get("/transitions")
def list_transitions():
    return {"transitions": transitions.listing(), "default": "auto"}


# ---------------------------------------------------------------- timeline --


@router.get("/chapters/{series}/{chapter}/timeline")
def get_timeline(series: str, chapter: str):
    cdir = _cdir(series, chapter)
    tl = store.read(_timeline_path(cdir))
    if not tl:
        raise HTTPException(404, "no timeline yet: post timeline/auto to build one")
    return tl


@router.put("/chapters/{series}/{chapter}/timeline")
def put_timeline(series: str, chapter: str, body: dict):
    cdir = _cdir(series, chapter)
    old = store.read(_timeline_path(cdir))
    try:
        tl = TL.apply_put(old, body)
    except TL.TimelineError as e:
        raise HTTPException(400, str(e))
    store.write(_timeline_path(cdir), tl)
    return tl


class AutoBody(BaseModel):
    settings: dict = {}


@router.post("/chapters/{series}/{chapter}/timeline/auto")
def auto_timeline(series: str, chapter: str, body: AutoBody | None = None):
    cdir = _cdir(series, chapter)
    overrides = dict((body.settings if body else {}) or {})
    _check_style(overrides.get("style"))

    def work(job):
        inp = ChapterInputs(cdir)
        job.log(f"{len(inp.panels)} panels from {inp.panel_source}")
        existing = store.read(_timeline_path(cdir))
        tl = TL.build(inp, existing, overrides=overrides, log=job.log)
        store.write(_timeline_path(cdir), tl)
        kept = sum(1 for s in tl["shots"] if s.get("edited"))
        job.log(f"{len(tl['shots'])} shots planned, {kept} edited ones kept")
        return {
            "shots": len(tl["shots"]),
            "edited_kept": kept,
            "duration": tl.get("duration"),
        }

    job = jobs.start(
        "timeline-auto",
        "Planning camera and transitions",
        work,
        lane="render",
        series=series,
        chapter=chapter,
    )
    return {"job_id": job.id}


# ---------------------------------------------------------------- previews --


class PreviewBody(BaseModel):
    kind: str = "panel"
    panels: list[str] = []
    panel_id: str | None = None
    style: str | None = None
    height: int | None = None
    fps: int | None = None
    styles: list[str] = []
    audio: bool = False


@router.post("/chapters/{series}/{chapter}/preview")
def preview(series: str, chapter: str, body: PreviewBody):
    cdir = _cdir(series, chapter)
    _check_style(body.style)
    height = int(body.height or PREVIEW_HEIGHT)
    if body.kind == "styles":
        panel_ids = list(body.panels[:5])
        if not panel_ids:
            raise HTTPException(400, "styles preview needs panels")
        names = [s for s in (body.styles or styles.enabled()) if s in styles.REGISTRY]
        if not names:
            raise HTTPException(400, "no styles to preview")
        return {
            "job_id": _styles_preview_job(
                series, chapter, cdir, panel_ids, names, height, body.fps
            ).id
        }
    if body.kind == "panel":
        if not body.panel_id:
            raise HTTPException(400, "panel preview needs panel_id")
        return {
            "job_id": _panel_preview_job(
                series,
                chapter,
                cdir,
                body.panel_id,
                body.style,
                height,
                body.fps,
                body.audio,
            ).id
        }
    raise HTTPException(400, "kind must be styles or panel")


def _styles_preview_job(series, chapter, cdir, panel_ids, names, height, fps):
    def work(job):
        inp = ChapterInputs(cdir)
        tl = _timeline(cdir, inp, log=job.log)
        shots = _shots_for_panels(tl, panel_ids)
        out_dir = cdir / "previews"
        out_dir.mkdir(parents=True, exist_ok=True)
        videos: dict[str, str] = {}
        files = []
        for n, name in enumerate(names):
            job.check()
            job.log(f"style {name} ({n + 1}/{len(names)})")
            sub = _with_settings(
                {**tl, "shots": shots}, style=name, height=height, fps=fps
            )
            out = out_dir / f"styles-{name}.mp4"
            render_timeline(
                cdir,
                TL.retime(sub),
                out,
                preview=True,
                audio=False,
                job=job,
                inputs=inp,
            )
            videos[name] = _url(out)
            files.append(out)
            job.progress((n + 1) / (len(names) + 1))
        grid = None
        if len(files) > 1:
            job.log("tiling the comparison grid")
            gw, gh = TL.out_size({**tl.get("settings", {}), "height": height})
            cols = 2 if gw > gh else 3
            grid_path = out_dir / "styles-grid.mp4"
            labels = [styles.REGISTRY[n].label for n in names]
            encode.hstack_grid(files, labels, grid_path, cols=cols, cell=(gw, gh))
            grid = _url(grid_path)
        return {"videos": videos, "grid": grid, "panels": panel_ids}

    return jobs.start(
        "preview-styles",
        "Previewing styles",
        work,
        lane="render",
        series=series,
        chapter=chapter,
    )


def _panel_preview_job(series, chapter, cdir, panel_id, style, height, fps, audio):
    def work(job):
        inp = ChapterInputs(cdir)
        if panel_id not in inp.by_id:
            raise ValueError(f"no panel {panel_id}")
        tl = _timeline(cdir, inp, log=job.log)
        shots = _shots_for_panels(tl, [panel_id])
        sub = _with_settings(
            {**tl, "shots": shots}, style=style, height=height, fps=fps
        )
        out = cdir / "previews" / f"panel-{panel_id}{'-' + style if style else ''}.mp4"
        res = render_timeline(
            cdir, TL.retime(sub), out, preview=True, audio=audio, job=job, inputs=inp
        )
        return {
            "video": _url(out),
            "file": str(out),
            "style": sub["settings"]["style"],
            "probe": res["probe"],
        }

    return jobs.start(
        "preview-panel",
        f"Previewing {panel_id}",
        work,
        lane="render",
        series=series,
        chapter=chapter,
    )


class ShotRenderBody(BaseModel):
    style: str | None = None
    preview: bool = True
    height: int | None = None


@router.post("/chapters/{series}/{chapter}/shots/{shot_id}/render")
def render_shot(
    series: str, chapter: str, shot_id: str, body: ShotRenderBody | None = None
):
    """Re-render one shot after an edit; the clip cache means the next full
    render reuses it."""
    cdir = _cdir(series, chapter)
    body = body or ShotRenderBody()
    _check_style(body.style)
    tl = store.read(_timeline_path(cdir))
    if not tl or not any(s.get("id") == shot_id for s in tl.get("shots", [])):
        raise HTTPException(404, f"no shot {shot_id} in the timeline")

    def work(job):
        inp = ChapterInputs(cdir)
        tl = _timeline(cdir, inp, log=job.log)
        sub = _with_settings(
            tl,
            style=body.style,
            height=body.height or (PREVIEW_HEIGHT if body.preview else None),
        )
        folder = "previews" if body.preview else "renders"
        out = cdir / folder / f"shot-{shot_id}.mp4"
        res = render_timeline(
            cdir,
            sub,
            out,
            preview=body.preview,
            audio=True,
            job=job,
            shot_ids=[shot_id],
            inputs=inp,
        )
        return {
            "video": _url(out),
            "file": str(out),
            "shot_id": shot_id,
            "probe": res["probe"],
        }

    job = jobs.start(
        "render-shot",
        f"Rendering shot {shot_id}",
        work,
        lane="render",
        series=series,
        chapter=chapter,
    )
    return {"job_id": job.id}


# ------------------------------------------------------------------ render --


class RenderBody(BaseModel):
    aspect: str | None = None
    bubbles: str | None = None
    style: str | None = None
    out_name: str | None = None
    height: int | None = None
    fps: int | None = None
    subtitles: bool | None = None
    audio: bool = True
    # Settings the render tab offers; None keeps whatever the timeline has.
    mode: str | None = None
    pace: float | None = None
    motion_strength: float | None = None
    transition: str | None = None
    effects: float | None = None
    backdrop: str | None = None
    sound: str | None = None  # full, music or silent
    layers: float | None = None  # 0..1, cutout layers in the 3D style
    style_settings: dict | None = None  # {style name: {knob: value}}, see styles
    # Render only part of the chapter: an explicit list of shot ids, or the
    # first max_seconds worth of shots. Both leave timeline.json alone.
    shot_ids: list[str] | None = None
    max_seconds: float | None = None


def _unused_path(out: Path) -> Path:
    """Never overwrite an earlier render: three renders of the same style
    and aspect used to land on one file name and only the last survived."""
    if not out.exists():
        return out
    n = 2
    while out.with_name(f"{out.stem}-{n}{out.suffix}").exists():
        n += 1
    return out.with_name(f"{out.stem}-{n}{out.suffix}")


def _mode_for_style(style, mode, tl: dict, log=None):
    """The render mode, given an explicitly asked-for style.

    Scroll mode gives every shot the scroll style, so asking for another
    style (Cinematic 3D, 2.5D puppets...) in scroll mode would silently get
    the scroll reader; the explicit style wins and the film goes panel to
    panel instead. No style, or the scroll style, leaves the mode alone."""
    if style in (None, "scroll"):
        return mode
    current = mode or (tl.get("settings") or {}).get("mode")
    if current != "scroll":
        return mode
    if log:
        log(f"style {style} asked for, so panel to panel instead of scroll")
    return "panel-to-panel"


@router.post("/chapters/{series}/{chapter}/render")
def render_chapter(series: str, chapter: str, body: RenderBody | None = None):
    cdir = _cdir(series, chapter)
    body = body or RenderBody()
    _check_style(body.style)
    if body.aspect not in (None, "16:9", "9:16"):
        raise HTTPException(400, "aspect must be 16:9 or 9:16")
    if body.bubbles not in (None, "keep", "erase"):
        raise HTTPException(400, "bubbles must be keep or erase")
    if body.mode not in (None, "panel-to-panel", "page-reveal", "scroll"):
        raise HTTPException(400, "mode must be panel-to-panel, page-reveal or scroll")
    if body.backdrop not in (None, "auto", "blur", "stretch", "black"):
        raise HTTPException(400, "backdrop must be auto, blur, stretch or black")
    if body.sound not in (None, "full", "music", "silent"):
        raise HTTPException(400, "sound must be full, music or silent")
    if body.layers is not None and not 0.0 <= body.layers <= 1.0:
        raise HTTPException(400, "layers must be between 0 and 1")
    if body.shot_ids:
        saved = store.read(_timeline_path(cdir)) or {}
        known = {s.get("id") for s in saved.get("shots", [])}
        missing = [i for i in body.shot_ids if i not in known]
        if known and missing:
            raise HTTPException(404, f"no shot {missing[0]} in the timeline")

    def work(job):
        inp = ChapterInputs(cdir)
        tl = _timeline(cdir, inp, log=job.log)
        mode = _mode_for_style(body.style, body.mode, tl, log=job.log)
        tl = _with_settings(
            tl,
            aspect=body.aspect,
            bubbles=body.bubbles,
            style=body.style,
            height=body.height,
            fps=body.fps,
            subtitles=body.subtitles,
            mode=mode,
            pace=body.pace,
            motion_strength=body.motion_strength,
            transition=body.transition,
            effects=body.effects,
            backdrop=body.backdrop,
            sound=body.sound,
            layers=body.layers,
            style_settings=_merged_style_settings(tl, body.style_settings),
        )
        st = tl["settings"]
        saved = (store.read(_timeline_path(cdir)) or {}).get("settings", {})
        replan = {
            k: st[k]
            for k in ("sound", "mode", "aspect", "pace", "style_settings")
            if st.get(k, TL.DEFAULT_SETTINGS.get(k))
            != saved.get(k, TL.DEFAULT_SETTINGS.get(k))
        }
        respoken = TL.lines_respoken(cdir, tl)
        if replan or respoken:
            # dwell times depend on whether the voices play, the shots on
            # the mode (scroll plans, reveal groups) and the aspect, and on
            # how long each line takes to say, so a film with different
            # settings or re-spoken lines is re-planned in memory; edited
            # shots and the saved file stay
            why = [f"{k}={v}" for k, v in replan.items()]
            if respoken:
                why.append(f"{len(respoken)} re-spoken line(s)")
            job.log("re-planning shots for " + ", ".join(why))
            tl = TL.build(inp, tl, overrides=replan, log=job.log)
            tl = _with_settings(tl, **{k: st[k] for k in st})
        if st.get("mode") == "scroll":
            st["style"] = "scroll"  # the shots all carry it; the name and list say so
        name = _safe_name(
            body.out_name,
            f"{series}-{chapter}-{st['style']}-{st['aspect'].replace(':', 'x')}",
        )
        out = _unused_path(cdir / "renders" / name)
        shot_ids = _limit_shots(tl, body.shot_ids, body.max_seconds)
        count = len(shot_ids) if shot_ids is not None else len(tl["shots"])
        part = "" if shot_ids is None else f" of {len(tl['shots'])}"
        job.log(
            f"{count}{part} shots, {st['style']}, {st['aspect']}, bubbles {st['bubbles']}"
        )
        res = render_timeline(
            cdir, tl, out, audio=body.audio, job=job, shot_ids=shot_ids, inputs=inp
        )
        job.log(
            f"wrote {out.name}: {res['probe'].get('duration', 0):.1f} s, {res['rendered']} shots rendered, {res['reused']} reused"
        )
        # a sidecar beside the film says how it was made (style, sound,
        # aspect...), so the render list can show it; Emerson: "I want to know
        # not just the name but also what style was used"
        store.write(
            out.with_suffix(".json"),
            {
                "settings": st,
                "shots": len(shot_ids or tl["shots"]),
                "seconds": res.get("probe", {}).get("duration"),
            },
        )
        return {**res, "file": str(out), "url": _url(out), "settings": st}

    job = jobs.start(
        "render",
        f"Rendering {series} {chapter}",
        work,
        lane="render",
        series=series,
        chapter=chapter,
    )
    return {"job_id": job.id}


@router.get("/renders")
def list_renders():
    items = []
    root = paths.SERIES_ROOT
    if root.exists():
        for series_dir in sorted(root.iterdir()):
            chapters = series_dir / "chapters"
            if not chapters.is_dir():
                continue
            for cdir in sorted(chapters.iterdir()):
                rdir = cdir / "renders"
                if not rdir.is_dir():
                    continue
                for f in rdir.glob("*.mp4"):
                    if ".part" in f.name or ".video" in f.name:
                        continue
                    st = f.stat()
                    made = store.read(f.with_suffix(".json"), None) or {}
                    settings = made.get("settings") or {}
                    items.append(
                        {
                            "series": series_dir.name,
                            "chapter": cdir.name,
                            "name": f.name,
                            "style": settings.get("style"),
                            "sound": settings.get("sound"),
                            "aspect": settings.get("aspect"),
                            "seconds": made.get("seconds"),
                            "file": str(f),
                            "url": _url(f),
                            "size": st.st_size,
                            "mtime": st.st_mtime,
                            "age": round(time.time() - st.st_mtime),
                        }
                    )
    items.sort(key=lambda r: -r["mtime"])
    return {"renders": items}
