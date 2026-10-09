"""The detect job: pages -> strip.json, panels.json (with crops), bubbles.json.

    from panelforge.detect.pipeline import run_detect
    run_detect(chapter_dir, job)          # job may be None

Re-runs keep edited items and stable ids (merge.py). Panel crops that no
longer belong to a panel are removed from work/detect/panels/.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .. import store
from . import bubbles as BU
from . import merge
from . import normalize as N
from . import panels as P
from . import strip as ST


def _progress(job, a: float, b: float):
    if job is None:
        return None
    return lambda f: job.progress(a + (b - a) * float(f))


def _log(job, msg: str) -> None:
    if job is not None:
        job.log(msg)


def stats(panels: list[dict], bubbles: list[dict]) -> dict:
    """Plain numbers about a detect result, for the UI and the handoff docs."""
    kinds: dict[str, int] = {}
    for p in panels:
        kinds[p["kind"]] = kinds.get(p["kind"], 0) + 1
    bkinds: dict[str, int] = {}
    for b in bubbles:
        bkinds[b["kind"]] = bkinds.get(b["kind"], 0) + 1
    confs = [b["ocr_conf"] for b in bubbles if b.get("text")]
    with_text = sum(1 for b in bubbles if b.get("text"))
    panels_with_bubbles = len({b["panel_id"] for b in bubbles if b.get("panel_id")})
    styles = [b.get("style") or {} for b in bubbles]
    return {
        "panels": len(panels),
        "panel_kinds": kinds,
        "bubbles": len(bubbles),
        "bubble_kinds": bkinds,
        "bubbles_with_text": with_text,
        "ocr_conf_mean": round(float(np.mean(confs)), 3) if confs else 0.0,
        "panels_with_bubbles": panels_with_bubbles,
        "bubbles_unassigned": sum(1 for b in bubbles if not b.get("panel_id")),
        "italic": sum(1 for s in styles if s.get("italic")),
        "wavy": sum(1 for s in styles if s.get("wavy")),
        "trembling": sum(1 for s in styles if s.get("trembling")),
        "bold_words": sum(len(s.get("bold_words") or []) for s in styles),
        "edited_panels": sum(1 for p in panels if p.get("edited")),
        "edited_bubbles": sum(1 for b in bubbles if b.get("edited")),
    }


def run_detect(chapter_dir: Path, job=None, ocr: bool = True) -> dict:
    chapter_dir = Path(chapter_dir)
    chapter = store.read(chapter_dir / "chapter.json")
    if not chapter:
        raise ValueError(f"no chapter.json in {chapter_dir}")
    reading = chapter.get("reading", "ttb")
    old_panels = (store.read(chapter_dir / "panels.json", {}) or {}).get("panels", [])
    old_bubbles = (store.read(chapter_dir / "bubbles.json", {}) or {}).get(
        "bubbles", []
    )

    strip = ST.build_strip(chapter_dir)
    store.write(chapter_dir / "strip.json", strip)
    reader = ST.StripReader(chapter_dir, strip)
    _log(
        job,
        f"strip {strip['width']}x{strip['height']} from {len(strip['segments'])} pages",
    )
    if job is not None:
        job.check()

    learned = N.learn_glossary(chapter_dir)
    if learned:
        _log(job, f"{len(learned)} words learned from the series' other chapters")
    regs = P.detect_regions(reader, reading, _progress(job, 0.02, 0.30))
    panels = P.to_panel_dicts(regs, strip)
    panels = merge.merge(old_panels, panels, "p", reading)
    for p in panels:
        p["image"] = f"work/detect/panels/{p['id']}.png"
    _log(
        job,
        f"{len(panels)} panels ({sum(1 for p in panels if p.get('edited'))} kept from edits)",
    )
    crop_dir = chapter_dir / "work" / "detect" / "panels"
    crop_dir.mkdir(parents=True, exist_ok=True)
    keep = {Path(p["image"]).name for p in panels}
    for f in crop_dir.glob("p*.png"):
        if f.name not in keep:
            f.unlink()
    for n, p in enumerate(panels):
        if job is not None:
            job.check()
        P.save_crop(reader, p, chapter_dir)
        if job is not None:
            job.progress(0.30 + 0.05 * (n + 1) / len(panels))
    store.write(chapter_dir / "panels.json", {"schema": 1, "panels": panels})

    if ocr:
        bubbles = BU.detect_bubbles(
            reader, panels, reading, _progress(job, 0.35, 0.97), lambda m: _log(job, m)
        )
    else:
        bubbles = []
    bubbles = merge.merge(old_bubbles, bubbles, "b", reading)
    grown = P.grow_to_text(panels, bubbles, strip)
    if grown:
        for p in panels:
            if p["id"] in grown:
                P.save_crop(reader, p, chapter_dir)
        store.write(chapter_dir / "panels.json", {"schema": 1, "panels": panels})
        _log(job, f"{len(grown)} panel boxes grown to cover their lettering")
    store.write(chapter_dir / "bubbles.json", {"schema": 1, "bubbles": bubbles})
    st = stats(panels, bubbles)
    store.write(chapter_dir / "work" / "detect" / "stats.json", st)
    _log(
        job,
        f"{st['bubbles']} bubbles, {st['bubbles_with_text']} with text, mean OCR confidence {st['ocr_conf_mean']}",
    )
    if job is not None:
        job.progress(1.0)
    return st
