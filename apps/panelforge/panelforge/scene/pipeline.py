"""The analyze job: panels + bubbles -> scene.json (chapter) and cast.json (series).

    from panelforge.scene.pipeline import run_analyze
    run_analyze(chapter_dir, job)

Per panel the heavy work (panel.analyze) is cached by content key under
work/scene/cache/<key>/, so re-runs after edits only redo what changed.
Then: scenes and locations from background signatures, cast clustering,
mood / action / expression / acoustics rules, speaker guesses.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import numpy as np

from .. import store
from . import cast as cast_mod
from . import cluster, geom, panel, panelsrc, speakers, understand

SCENE_CUT = (
    0.75  # chi-square distance between consecutive backgrounds that starts a new scene
)
LOCATION_SAME = 0.55


def _log(job, msg: str) -> None:
    if job is not None:
        job.log(msg)


def _record_for(
    strip: dict,
    chapter: dict,
    reader,
    p: dict,
    local_bubbles: list[dict],
    chapter_dir: Path,
    job,
) -> dict:
    key = panel.content_key(p, strip, chapter)
    rel = f"work/scene/cache/{key}"
    folder = chapter_dir / rel
    bkey = panel.bubbles_key(local_bubbles)
    rec = store.read(folder / "record.json", None)
    if rec and rec.get("version") == panel.VERSION and (folder / "depth.png").exists():
        if rec.get("bubbles_key") != bkey:
            bgr = reader.crop(p["box"])
            panel.background(
                bgr, rec, panel._bubble_boxes_local(p, local_bubbles), None, folder, rel
            )
            rec["bubbles_key"] = bkey
            store.write(folder / "record.json", rec)
        return rec
    bgr = reader.crop(p["box"])
    rec = panel.analyze(bgr, p, local_bubbles, folder, rel)
    rec["bubbles_key"] = bkey
    store.write(folder / "record.json", rec)
    return rec


def _scenes(
    panels: list[dict], recs: dict[str, dict]
) -> tuple[dict[str, str], dict[str, str]]:
    """panel id -> scene id, and scene id -> location id (same place, same id)."""
    scene_of: dict[str, str] = {}
    feats: list[np.ndarray] = []
    scene_feats: list[list[np.ndarray]] = []
    sid = 0
    prev: np.ndarray | None = None
    for p in panels:
        f = recs[p["id"]].get("bg_feature")
        v = np.asarray(f[:216], np.float64) if f else None
        cut = prev is None or v is None
        if not cut and prev is not None and v is not None:
            cut = cluster.chi2_matrix(np.stack([prev, v]))[0, 1] > SCENE_CUT
        if cut and (sid == 0 or v is not None):
            sid += 1
            scene_feats.append([])
        scene_of[p["id"]] = f"s{sid:02d}"
        if v is not None:
            prev = v
            scene_feats[-1].append(v)
    means = [np.mean(fs, axis=0) if fs else None for fs in scene_feats]
    loc_of: dict[str, str] = {}
    centroids: list[np.ndarray] = []
    for k, m in enumerate(means, 1):
        s = f"s{k:02d}"
        if m is None:
            loc_of[s] = (
                f"loc{len(centroids) + 1:02d}"
                if not centroids
                else loc_of.get(f"s{k - 1:02d}", "loc01")
            )
            continue
        j = None
        if centroids:
            d = cluster.chi2_matrix(np.stack(centroids + [m]))[-1, :-1]
            j = int(np.argmin(d)) if d.min() < LOCATION_SAME else None
        if j is None:
            centroids.append(m)
            j = len(centroids) - 1
        loc_of[s] = f"loc{j + 1:02d}"
    return scene_of, loc_of


def _to_scene_char(c: dict, cid: str | None, placement: str = "cast") -> dict:
    return {
        "cast_id": cid if cid and cid.startswith("c") else None,
        "extra_id": cid if cid and cid.startswith("x") else None,
        # cast, extra, unplaced (a faceless person that matched nobody) or
        # rejected (not a person); the last two have no id, and the UI can
        # offer them as unsorted crops to assign by hand
        "placement": placement,
        "box": c["box"],
        "face": c.get("face"),
        "facing": c.get("facing"),
        "cutout": c.get("cutout"),
        "area_frac": c.get("area_frac"),
        # the detector's confidence, kept so the person filter in
        # cast.is_person can be re-tuned without re-running the models
        "score": c.get("score"),
        "expression": None,
    }


def run_analyze(chapter_dir: Path, job=None) -> dict:
    chapter_dir = Path(chapter_dir)
    chapter = store.read(chapter_dir / "chapter.json")
    if not chapter:
        raise ValueError(f"no chapter.json in {chapter_dir}")
    series_dir = chapter_dir.parent.parent
    panels, bubbles = panelsrc.load(chapter_dir)
    if not panels:
        raise ValueError("detect has not run: no panels.json")
    strip = panelsrc.strip_for(chapter_dir)
    reader = panelsrc.Strip(chapter_dir, strip)
    by_panel = panelsrc.bubbles_by_panel(bubbles)

    recs: dict[str, dict] = {}
    for n, p in enumerate(panels):
        if job is not None:
            job.check()
        recs[p["id"]] = _record_for(
            strip, chapter, reader, p, by_panel.get(p["id"], []), chapter_dir, job
        )
        if job is not None:
            job.progress(0.85 * (n + 1) / len(panels))
            if (n + 1) % 10 == 0:
                job.log(f"{n + 1}/{len(panels)} panels analysed")
    _log(job, f"{len(panels)} panels analysed")

    scene_of, loc_of = _scenes(panels, recs)
    _log(
        job,
        f"{len(set(scene_of.values()))} scenes, {len(set(loc_of.values()))} locations",
    )

    app: list[dict] = []
    for p in panels:
        rec = recs[p["id"]]
        feats = None
        npz = (
            chapter_dir / rec.get("depth", "").rsplit("/", 1)[0] / "feats.npz"
            if rec.get("depth")
            else None
        )
        if npz and npz.exists():
            feats = np.load(npz)
        for i, c in enumerate(rec.get("characters") or []):
            ccip = face_feat = None
            hair = body = np.zeros(22)
            if feats is not None:
                if feats["ccip"].shape[0] > i:
                    ccip = feats["ccip"][i]
                if (
                    "face_has" in feats
                    and feats["face_has"].shape[0] > i
                    and feats["face_has"][i]
                ):
                    face_feat = feats["ccip_face"][i]
                if feats["hair"].shape[0] > i:
                    hair, body = feats["hair"][i], feats["body"][i]
            box = c.get("box") or [0, 0, 0, 0]
            over = 0.0
            for b in panel._bubble_boxes_local(p, by_panel.get(p["id"], [])):
                inter = geom.intersection(box, b["box"])
                over = max(over, inter / max(1.0, geom.area(box)))
            app.append(
                {
                    "chapter": chapter_dir.name,
                    "chapter_dir": chapter_dir,
                    "panel_id": p["id"],
                    "index": i,
                    "ccip": ccip,
                    "ccip_face": face_feat,
                    "hair": hair,
                    "body": body,
                    "face": c.get("face"),
                    "box": box,
                    "score": c.get("score", 0.0),
                    "text_overlap": round(over, 3),
                    "area_frac": c.get("area_frac", 0.0),
                    "cutout": c.get("cutout"),
                }
            )
    # The cast is a series matter: every other analysed chapter's people join
    # the grouping, so one character keeps one id across chapters and only
    # someone seen often enough (cast.CAST_MIN_*) becomes cast.
    mine = len(app)
    others = 0
    for cdir in sorted((series_dir / "chapters").glob("*")):
        if cdir == chapter_dir or not (cdir / "scene.json").exists():
            continue
        more, more_scenes = cast_mod.load_chapter_appearances(cdir)
        app.extend(more)
        scene_of.update({f"{cdir.name}/{k}": v for k, v in more_scenes.items()})
        others += 1
    if others:
        _log(job, f"grouping cast over {others + 1} chapters ({len(app)} appearances)")
    labels, cast_labels = cast_mod.group(app, scene_of)
    old_cast = store.read(series_dir / "cast.json", None)
    cast_doc, label_to_id = cast_mod.build(
        app, labels, cast_labels, old_cast, series_dir, chapter_dir
    )
    for cdir in sorted((series_dir / "chapters").glob("*")):
        if cdir == chapter_dir:
            continue
        other_scene = store.read(cdir / "scene.json", None)
        if other_scene:
            cast_mod.sync_scene_ids(other_scene, cast_doc, cdir.name)
            store.write(cdir / "scene.json", other_scene)
    app, labels = app[:mine], labels[:mine]
    id_of = {
        (a["panel_id"], a["index"]): label_to_id[lab]
        for a, lab in zip(app, labels)
        if lab in label_to_id
    }
    placement_of = {
        (a["panel_id"], a["index"]): (
            "rejected"
            if lab == cast_mod.REJECTED
            else (
                "unplaced"
                if lab == cast_mod.UNPLACED
                else ("cast" if lab in cast_labels else "extra")
            )
        )
        for a, lab in zip(app, labels)
    }
    _log(
        job,
        f"{len(app)} appearances -> {len(cast_doc['cast'])} cast, {len(cast_doc['extras'])} extras",
    )

    # Backgrounds per location: the cleanest, largest one.
    best_bg: dict[str, tuple[float, str, str]] = {}
    for p in panels:
        rec = recs[p["id"]]
        if not rec.get("background"):
            continue
        loc = loc_of[scene_of[p["id"]]]
        score = (1.0 - float(rec.get("bg_hole_frac", 1.0))) * (
            p["box"][2] * p["box"][3]
        ) ** 0.5
        if loc not in best_bg or score > best_bg[loc][0]:
            best_bg[loc] = (score, rec["background"], p["id"])
    bg_dir = series_dir / "assets" / "backgrounds"
    bg_dir.mkdir(parents=True, exist_ok=True)
    old_bgs = {b["id"]: b for b in (old_cast or {}).get("backgrounds", [])}
    backgrounds = []
    for loc in sorted(best_bg):
        bid = "bg" + loc[3:]
        shutil.copyfile(chapter_dir / best_bg[loc][1], bg_dir / f"{bid}.png")
        panels_here = [p["id"] for p in panels if loc_of[scene_of[p["id"]]] == loc]
        backgrounds.append(
            {
                "id": bid,
                "label": old_bgs.get(bid, {}).get("label")
                or f"location {int(loc[3:])}",
                "image": f"assets/backgrounds/{bid}.png",
                "panels": panels_here,
                "sample_panel": best_bg[loc][2],
            }
        )
    cast_doc["backgrounds"] = backgrounds
    store.write(series_dir / "cast.json", cast_doc)

    out_panels: dict[str, Any] = {}
    chars_by_pid: dict[str, list[dict]] = {}
    for p in panels:
        rec = recs[p["id"]]
        local = panel._bubble_boxes_local(p, by_panel.get(p["id"], []))
        action = understand.action_level(rec, local)
        mood, mood_why = understand.mood(rec, local, action)
        chars = []
        for i, c in enumerate(rec.get("characters") or []):
            sc = _to_scene_char(
                c, id_of.get((p["id"], i)), placement_of.get((p["id"], i), "cast")
            )
            chars.append(sc)
        chars_by_pid[p["id"]] = chars
        loc = loc_of[scene_of[p["id"]]]
        label = next(
            (b["label"] for b in backgrounds if b["id"] == "bg" + loc[3:]),
            f"location {int(loc[3:])}",
        )
        out_panels[p["id"]] = {
            "scene_id": scene_of[p["id"]],
            "location": label,
            "location_id": loc,
            "mood": mood,
            "mood_why": mood_why,
            "action": action,
            "characters": chars,
            "background": rec.get("background"),
            "depth": rec.get("depth"),
            "saliency": rec.get("saliency") or [],
            "sfx_text": [
                {"box": s["box"], "text": s.get("text", ""), "image": s.get("image")}
                for s in rec.get("sfx") or []
            ],
            "speed_lines": rec.get("speed_lines"),
            "rigs": [
                {"char_index": i, **(c.get("rig") or {})}
                for i, c in enumerate(rec.get("characters") or [])
                if c.get("rig")
            ],
            "props": rec.get("props") or [],
            "acoustics": understand.acoustics(rec, local, p),
            "stats": rec.get("stats"),
            "models": rec.get("models"),
        }
    # hand assignments (cast.json ledger) win over the automatic grouping
    cast_mod.sync_scene_ids({"panels": out_panels}, cast_doc, chapter_dir.name)
    panels_by_id = {p["id"]: p for p in panels}
    spk = speakers.guess(bubbles, panels_by_id, chars_by_pid)
    # Expressions: from what each character says in the panel plus the mood.
    for p in panels:
        sp = out_panels[p["id"]]
        local = by_panel.get(p["id"], [])
        for c in sp["characters"]:
            who = c["cast_id"] or c["extra_id"]
            spoken = [
                b for b in local if who and spk.get(b["id"], {}).get("speaker") == who
            ]
            c["expression"] = understand.expression(c, spoken, sp["mood"], sp["action"])
    scene_doc = {"schema": 1, "panels": out_panels, "speakers": spk}
    store.write(chapter_dir / "scene.json", scene_doc)
    st = {
        "panels": len(panels),
        "scenes": len(set(scene_of.values())),
        "locations": len(set(loc_of.values())),
        "appearances": len(app),
        "cast": len(cast_doc["cast"]),
        "extras": len(cast_doc["extras"]),
        "with_background": sum(1 for v in out_panels.values() if v["background"]),
        "with_depth": sum(1 for v in out_panels.values() if v["depth"]),
        "speakers_guessed": len(spk),
        "moods": {
            m: sum(1 for v in out_panels.values() if v["mood"] == m)
            for m in understand.MOODS
        },
    }
    store.write(chapter_dir / "work" / "scene" / "stats.json", st)
    _log(job, f"scene.json written: {st}")
    if job is not None:
        job.progress(1.0)
    return st
