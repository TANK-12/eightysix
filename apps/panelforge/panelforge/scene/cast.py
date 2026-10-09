"""From per-panel character appearances to a series cast.

Appearances are clustered with CCIP embeddings (when the model ran) blended
with hair and body colour histograms; two characters drawn in the same
panel can never be one person (cannot-link). Clusters seen often enough
become cast, the rest extras. Existing cast.json entries keep their id,
name, colour and voice: a new cluster is matched to an old entry by the
overlap of its appearances (panel id + character index).

Hand edits live in the `assignments` ledger of cast.json: appearance key
(`chapter/panel:index`) -> cast id, or "none" for "not a person". Merge,
split, assign and drop all write the ledger, and `apply_assignments` replays
it after every analysis, so what Emerson fixed by hand stays fixed when the
automatic grouping runs again.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from . import cluster, detectors, registry

HAIR_THRESHOLD = 0.35
BODY_THRESHOLD = 0.5

# What counts as a drawing of a person at all. The person detector also fires
# on caption boxes, gloves, machinery and emblems; those boxes used to be
# clustered into "characters", which filled the cast list with junk.
MIN_SCORE = 0.35  # detector confidence
MIN_AREA_FRAC = 0.012  # of the panel: smaller is a detail, not a character
FACELESS_MIN_SCORE = 0.55  # no face found: only a confident box counts
FACELESS_MIN_AREA = 0.05  # ... and it has to be a decent size
TEXT_OVERLAP_MAX = 0.55  # mostly a speech balloon or caption, so not a person
CLUSTER_QUANTILE = 0.15  # see cluster.quantile_linkage
# Deliberately tight. Judged by eye on chapter 1 with tools/cast_sheet.py:
# 1.2 merges four or five people into one entry, 1.0 keeps them apart at the
# cost of one character sometimes arriving as two entries. Splitting a wrong
# merge means moving appearances one by one; merging two entries is two
# clicks in the cast tab, so the cheap mistake is the one to make.
CLUSTER_THRESHOLD = 1.0
# A cluster is cast (named, voiced, in the list) only when the person shows
# up often enough: in two or more chapters, or in this many panels. Everyone
# else is an extra. Emerson: "only make characters out of people who show up
# often enough".
CAST_MIN_PANELS = 6
CAST_MIN_CHAPTERS = 2
# ... and with this many pictures that show a face. Measured on ten chapters
# of Bad Born Blood: every junk entry (armour, a gun, machinery) had 1-2
# faced crops with dozens of faceless ones attached; every real character
# had at least 11.
CAST_MIN_FACED = 3
REJECTED = -1  # label for an appearance that is not a person
UNPLACED = -2  # a faceless person that matched no character: no cast, no extra
# A faceless appearance joins a character only when this close to the
# character's faced pictures (blended units: 1.0 is the clustering threshold).
ATTACH_THRESHOLD = 0.85
ATTACH_QUANTILE = 0.25
# After clustering, a cluster is cut in two when its faced members split
# into halves whose median cross distance is over this: a few look-alike
# pairs (same uniform, same hair) can glue two people together at the low
# quantile, and the median is what tells a real character from a glued one.
SPLIT_MEDIAN = 1.05
SPLIT_MIN_SIDE = 3
PALETTE = (
    "#e0564f",
    "#4f8fe0",
    "#4fc48a",
    "#e0b04f",
    "#b06be0",
    "#e07b4f",
    "#4fd0e0",
    "#e04f9d",
    "#8ee04f",
    "#a08060",
    "#6080a0",
    "#d0d0d0",
)


def _face_matrix(app: list[dict]) -> np.ndarray | None:
    """CCIP distance between head crops, NaN wherever one side has no face.

    `blend` skips a NaN pair for that part only, so appearances drawn from
    behind still cluster on the whole-person embedding and colour, while two
    faces are judged face to face.
    """
    n = len(app)
    have = [i for i, a in enumerate(app) if a.get("ccip_face") is not None]
    if len(have) < 2:
        return None
    feats = np.array([app[i]["ccip_face"] for i in have], np.float32)
    sub = detectors.ccip_diff(feats)
    if sub is None or sub.shape != (len(have), len(have)):
        return None
    out = np.full((n, n), np.nan)
    for a, i in enumerate(have):
        for b, j in enumerate(have):
            out[i, j] = sub[a, b]
    return out


def _dist(app: list[dict]) -> np.ndarray:
    n = len(app)
    parts = []
    ccip = np.array([a["ccip"] for a in app if a.get("ccip") is not None], np.float32)
    if len(ccip) == n and n > 1:
        d = detectors.ccip_diff(ccip)
        if d is not None and d.shape == (n, n):
            parts.append((d, registry.CCIP_SAME_THRESHOLD, 3.0))
    faces = _face_matrix(app)
    if faces is not None:
        parts.append((faces, registry.CCIP_SAME_THRESHOLD, 4.0))
    hair = np.array([a["hair"] for a in app], np.float64)
    body = np.array([a["body"] for a in app], np.float64)
    if hair.shape[1:] == (22,):
        parts.append((cluster.chi2_matrix(hair), HAIR_THRESHOLD, 1.0))
    if body.shape[1:] == (22,):
        parts.append((cluster.chi2_matrix(body), BODY_THRESHOLD, 0.6))
    if not parts:
        return np.full((n, n), cluster.INF)
    return cluster.blend(parts)


def is_person(a: dict) -> bool:
    """Whether an appearance looks like a drawing of a person.

    The person detector is generous: caption boxes, a gloved hand, a robot
    arm, a logo and near-empty crops all come back as boxes. Clustering them
    produced a cast list full of things that are not characters, so they are
    dropped here, before any identity work. The appearance itself stays in
    scene.json; it just never becomes cast or an extra.
    """
    score = float(a.get("score") or 0.0)
    area = float(a.get("area_frac") or 0.0)
    if score < MIN_SCORE or area < MIN_AREA_FRAC:
        return False
    if float(a.get("text_overlap") or 0.0) > TEXT_OVERLAP_MAX:
        return False
    if a.get("face") is None and (
        score < FACELESS_MIN_SCORE or area < FACELESS_MIN_AREA
    ):
        return False
    return True


def panel_key(a: dict) -> str:
    """chapter/panel: panel ids repeat from chapter to chapter."""
    return f"{a.get('chapter', '')}/{a['panel_id']}"


def akey(a: dict, chapter: str = "") -> str:
    """The ledger key of an appearance record: chapter/panel:index."""
    return appearance_key(a.get("chapter") or chapter, a["panel_id"], a["index"])


def _cannot_links(sub: list[dict], idx: list[int]) -> list[list[int]]:
    """Groups of positions in `idx` drawn in the same panel: two people in one
    panel are never the same character."""
    same_panel: dict[str, list[int]] = {}
    for pos, j in enumerate(idx):
        same_panel.setdefault(panel_key(sub[j]), []).append(pos)
    return [v for v in same_panel.values() if len(v) > 1]


def load_chapter_appearances(cdir: Path) -> tuple[list[dict], dict[str, str]]:
    """Appearance records of an analysed chapter, from its scene.json and
    the per-panel feature caches, with the chapter name on every record.
    Returns (records, panel id -> scene id)."""
    import json

    from . import geom, panel as panel_mod, panelsrc

    scene_path = cdir / "scene.json"
    if not scene_path.exists():
        return [], {}
    scene = json.loads(scene_path.read_text())
    panels, bubbles = panelsrc.load(cdir)
    by_panel = panelsrc.bubbles_by_panel(bubbles)
    by_id = {p["id"]: p for p in panels}
    app: list[dict] = []
    for pid, rec in scene["panels"].items():
        chars = rec.get("characters") or []
        if not chars or pid not in by_id:
            continue
        folder = cdir / (rec.get("depth") or "x/x").rsplit("/", 1)[0]
        feats = (
            np.load(folder / "feats.npz") if (folder / "feats.npz").exists() else None
        )
        local = panel_mod._bubble_boxes_local(by_id[pid], by_panel.get(pid, []))
        for i, c in enumerate(chars):
            box = c.get("box") or [0, 0, 0, 0]
            over = max(
                [
                    geom.intersection(box, b["box"]) / max(1.0, geom.area(box))
                    for b in local
                ]
                or [0.0]
            )
            has_face_feat = (
                feats is not None
                and "face_has" in feats
                and feats["face_has"].shape[0] > i
                and bool(feats["face_has"][i])
            )
            app.append(
                {
                    "chapter": cdir.name,
                    "chapter_dir": cdir,
                    "panel_id": pid,
                    "index": i,
                    "ccip": (
                        feats["ccip"][i]
                        if feats is not None and feats["ccip"].shape[0] > i
                        else None
                    ),
                    "ccip_face": (
                        feats["ccip_face"][i]
                        if feats is not None and has_face_feat
                        else None
                    ),
                    "hair": feats["hair"][i] if feats is not None else np.zeros(22),
                    "body": feats["body"][i] if feats is not None else np.zeros(22),
                    "face": c.get("face"),
                    "box": box,
                    "score": c.get("score") if c.get("score") is not None else 0.0,
                    "text_overlap": round(over, 3),
                    "area_frac": c.get("area_frac", 0.0),
                    "cutout": c.get("cutout"),
                }
            )
    scene_of = {pid: rec.get("scene_id", "") for pid, rec in scene["panels"].items()}
    return app, scene_of


def _two_sides(block: np.ndarray) -> tuple[list[int], list[int]]:
    """Partition the members of one cluster into two sides (2-medoids).

    Seeded with the two most different pictures, so one look-alike pair
    cannot chain the two people together the way agglomerative linkage does.
    """
    n = len(block)
    i, j = np.unravel_index(int(np.argmax(block)), block.shape)
    sides: tuple[list[int], list[int]] = ([int(i)], [int(j)])
    for _ in range(8):
        new_sides: tuple[list[int], list[int]] = ([], [])
        for k in range(n):
            # the side a picture is closer to on the median, not to one seed,
            # so a single look-alike pair cannot pull it across
            da = float(np.median(block[k, [m for m in sides[0] if m != k] or sides[0]]))
            db = float(np.median(block[k, [m for m in sides[1] if m != k] or sides[1]]))
            new_sides[0 if da <= db else 1].append(k)
        if not new_sides[0] or not new_sides[1] or new_sides == sides:
            break
        sides = new_sides
    return sides


def _split_glued(labels: list[int], dist: np.ndarray, faced: list[int]) -> list[int]:
    """Cut clusters whose faced members are really two groups (see SPLIT_MEDIAN)."""
    labels = list(labels)
    next_label = max(labels) + 1 if labels else 0
    todo = sorted(set(labels))
    while todo:
        lab = todo.pop(0)
        mem = [j for j in faced if labels[j] == lab]
        if len(mem) < 2 * SPLIT_MIN_SIDE:
            continue
        block = dist[np.ix_(mem, mem)]
        a, b = _two_sides(block)
        if min(len(a), len(b)) < SPLIT_MIN_SIDE:
            continue
        cross = float(np.median(block[np.ix_(a, b)]))
        within = max(
            float(np.median(block[np.ix_(a, a)])), float(np.median(block[np.ix_(b, b)]))
        )
        if cross < SPLIT_MEDIAN or cross < 1.3 * within:
            continue
        for k in b:
            labels[mem[k]] = next_label
        todo.extend([lab, next_label])
        next_label += 1
    return labels


def _labels(sub: list[dict], dist: np.ndarray) -> list[int]:
    """Cluster labels for the people, identities decided by the faces.

    Every junk cluster on the chapter-1 contact sheet (hands, an eye, a gun,
    armour, an emblem) was made of appearances without a face, and the rows
    that mixed two characters were glued together by faceless body crops,
    which embed on clothes rather than on who is wearing them. So a character
    is only ever founded by pictures with a face. A faceless appearance then
    joins the character whose faced pictures it is closest to, if that is
    under `ATTACH_THRESHOLD` and no member of that character shares its
    panel; otherwise it stays `UNPLACED` -- still a person in its panel for
    the camera, never a new cast entry or an extra. A chapter where the face
    finder found nothing at all is clustered on whole bodies as before.
    """
    n = len(sub)
    faced = [j for j in range(n) if sub[j].get("face") is not None]
    if not faced:
        return cluster.quantile_linkage(
            dist,
            CLUSTER_THRESHOLD,
            _cannot_links(sub, list(range(n))),
            CLUSTER_QUANTILE,
        )
    fl = cluster.quantile_linkage(
        dist[np.ix_(faced, faced)],
        CLUSTER_THRESHOLD,
        _cannot_links(sub, faced),
        CLUSTER_QUANTILE,
    )
    labels = [UNPLACED] * n
    for pos, j in enumerate(faced):
        labels[j] = fl[pos]
    labels = _split_glued(labels, dist, faced)
    members: dict[int, list[int]] = {}
    for j in faced:
        members.setdefault(labels[j], []).append(j)
    for j in range(n):
        if labels[j] != UNPLACED:
            continue
        best_lab, best = None, ATTACH_THRESHOLD
        for lab, mem in members.items():
            if any(panel_key(sub[m]) == panel_key(sub[j]) for m in mem):
                continue
            s = float(np.quantile(dist[j, mem], ATTACH_QUANTILE))
            if s < best:
                best, best_lab = s, lab
        if best_lab is not None:
            labels[j] = best_lab
            members[best_lab].append(j)
    return labels


def group(app: list[dict], scene_of: dict[str, str]) -> tuple[list[int], set[int]]:
    """Cluster labels per appearance, and the set of labels that are cast.

    Appearances that are not people get label `REJECTED` and are left out of
    the clustering entirely.
    """
    if not app:
        return [], set()
    keep = [i for i, a in enumerate(app) if is_person(a)]
    if not keep:
        return [REJECTED] * len(app), set()
    sub = [app[i] for i in keep]
    dist = _dist(sub)
    sub_labels = _labels(sub, dist)
    labels = [REJECTED] * len(app)
    for j, i in enumerate(keep):
        labels[i] = sub_labels[j]
    panels_of: dict[int, set[str]] = {}
    chapters_of: dict[int, set[str]] = {}
    faced_of: dict[int, int] = {}
    for a, lab in zip(sub, sub_labels):
        panels_of.setdefault(lab, set()).add(panel_key(a))
        chapters_of.setdefault(lab, set()).add(a.get("chapter", ""))
        faced_of[lab] = faced_of.get(lab, 0) + (1 if a.get("face") is not None else 0)
    cast = {
        lab
        for lab in panels_of
        if lab != UNPLACED
        and faced_of.get(lab, 0) >= CAST_MIN_FACED
        and (
            len(chapters_of[lab]) >= CAST_MIN_CHAPTERS
            or len(panels_of[lab]) >= CAST_MIN_PANELS
        )
    }
    return labels, cast


def appearance_key(chapter: str, panel_id: str, index: int) -> str:
    return f"{chapter}/{panel_id}:{index}"


SAMPLE_HEAD_ZOOM = 2.4  # the card picture: head, hair and shoulders


def sample_image(a: dict, chapter_dir: Path) -> np.ndarray | None:
    """The picture that stands for an appearance on a cast card.

    The whole cutout is the worst choice: the biggest crop of a character is
    often a body fragment, a hand holding a gun, or a blurred close-up, and
    Emerson could not tell who a card was. When a face was found, the card
    shows the head with some room around it instead.
    """
    import cv2

    src = Path(a.get("chapter_dir") or chapter_dir) / (a.get("cutout") or "")
    if not a.get("cutout") or not src.exists():
        return None
    img = cv2.imread(str(src), cv2.IMREAD_UNCHANGED)
    if img is None:
        return None
    face, box = a.get("face"), a.get("box")
    if not face or not box:
        return img
    h, w = img.shape[:2]
    fx, fy, fw, fh = (float(v) for v in face)
    fx, fy = fx - float(box[0]), fy - float(box[1])  # face is in panel coords
    cx, cy = fx + fw / 2, fy + fh / 2
    half = max(fw, fh) * SAMPLE_HEAD_ZOOM / 2
    x0, y0 = int(max(0, cx - half)), int(max(0, cy - half * 0.9))
    x1, y1 = int(min(w, cx + half)), int(min(h, cy + half * 1.1))
    if x1 - x0 < 16 or y1 - y0 < 16:
        return img
    return img[y0:y1, x0:x1]


def _write_samples(cid: str, best: list[dict], chapter_dir: Path, series_dir: Path):
    """Write up to three card pictures into assets/cast/<cid>/ and return their paths."""
    import cv2

    folder = series_dir / "assets" / ("cast" if cid.startswith("c") else "extras") / cid
    folder.mkdir(parents=True, exist_ok=True)
    for f in folder.glob("s*.png"):
        f.unlink()
    samples = []
    for k, a in enumerate(best[:3], 1):
        img = sample_image(a, chapter_dir)
        if img is not None and cv2.imwrite(str(folder / f"s{k}.png"), img):
            samples.append(f"{folder.relative_to(series_dir)}/s{k}.png")
    return samples


def _best_first(apps: list[dict]) -> list[dict]:
    return sorted(
        apps, key=lambda a: (a.get("face") is None, -(a.get("area_frac") or 0))
    )


def new_cast_entry(cid: str, n: int) -> dict:
    return {
        "id": cid,
        "name": f"character {n}",
        "auto_name": f"character {n}",
        "color": PALETTE[(n - 1) % len(PALETTE)],
        "samples": [],
        "embedding": None,
        "voice": None,
        "rig": None,
        "model3d": None,
        "appearances": [],
        "panels": [],
        "edited": True,
    }


def free_cast_id(doc: dict) -> str:
    taken = {c["id"] for c in doc.get("cast", [])} | {
        x["id"] for x in doc.get("extras", [])
    }
    n = len(doc.get("cast", [])) + 1
    while f"c{n:02d}" in taken:
        n += 1
    return f"c{n:02d}"


def apply_assignments(
    doc: dict,
    chapter: str,
    app: list[dict],
    chapter_dir: Path,
    series_dir: Path,
) -> dict:
    """Replay the ledger for one chapter onto `doc` (cast.json), in place.

    `app` holds this chapter's appearance records (panel_id, index, cutout,
    face, area_frac), which are needed to move a crop the clustering never
    placed and to refresh sample pictures. An entry left with no appearances
    is dropped; a target id that does not exist yet becomes a new character.
    """
    ledger: dict[str, str] = doc.get("assignments") or {}
    prefix = f"{chapter}/"
    todo = {k: v for k, v in ledger.items() if k.startswith(prefix)}
    if not todo:
        doc.setdefault("assignments", ledger)
        return doc
    by_key = {appearance_key(chapter, a["panel_id"], a["index"]): a for a in app}
    entries: dict[str, dict] = {c["id"]: c for c in doc.get("cast", [])}
    entries.update({x["id"]: x for x in doc.get("extras", [])})
    touched: set[str] = set()
    for key, target in todo.items():
        a = by_key.get(key)
        if a is None:
            continue  # the appearance no longer exists (panels re-detected)
        for e in entries.values():
            before = len(e.get("appearances", []))
            e["appearances"] = [
                x
                for x in e.get("appearances", [])
                if not (
                    x["panel_id"] == a["panel_id"]
                    and x["index"] == a["index"]
                    and (x.get("chapter") or chapter) == chapter
                )
            ]
            if len(e["appearances"]) != before:
                touched.add(e["id"])
        if target == "none":
            continue
        e = entries.get(target)
        if e is None:
            e = new_cast_entry(target, len(doc.get("cast", [])) + 1)
            entries[target] = e
            doc.setdefault("cast", []).append(e)
        e.setdefault("appearances", []).append(
            {"panel_id": a["panel_id"], "index": a["index"], "chapter": chapter}
        )
        touched.add(target)
    for cid in touched:
        e = entries[cid]
        e["panels"] = sorted({x["panel_id"] for x in e["appearances"]})
        mine = [
            by_key[appearance_key(chapter, x["panel_id"], x["index"])]
            for x in e["appearances"]
            if (x.get("chapter") or chapter) == chapter
            and appearance_key(chapter, x["panel_id"], x["index"]) in by_key
        ]
        if mine and cid.startswith("c"):
            e["samples"] = _write_samples(
                cid, _best_first(mine), chapter_dir, series_dir
            )
    doc["cast"] = [c for c in doc.get("cast", []) if c.get("appearances")]
    doc["extras"] = [x for x in doc.get("extras", []) if x.get("appearances")]
    doc["assignments"] = ledger
    return doc


def sync_scene_ids(scene: dict, doc: dict, chapter: str) -> dict:
    """Set every appearance's cast_id, extra_id and placement in a scene.json
    from the cast document (entries plus the ledger), in place."""
    where: dict[tuple[str, int], str] = {}
    for e in doc.get("cast", []) + doc.get("extras", []):
        for x in e.get("appearances", []):
            if (x.get("chapter") or chapter) == chapter:
                where[(x["panel_id"], x["index"])] = e["id"]
    ledger = doc.get("assignments") or {}
    for pid, sp in scene.get("panels", {}).items():
        for i, c in enumerate(sp.get("characters", [])):
            cid = where.get((pid, i))
            if cid:
                c["cast_id"] = cid if cid.startswith("c") else None
                c["extra_id"] = cid if cid.startswith("x") else None
                c["placement"] = "cast" if cid.startswith("c") else "extra"
                continue
            c["cast_id"] = c["extra_id"] = None
            if ledger.get(appearance_key(chapter, pid, i)) == "none":
                c["placement"] = "rejected"
            elif c.get("placement") in ("cast", "extra"):
                c["placement"] = "unplaced"
    return scene


def _overlap(a: set[str], b: set[str]) -> float:
    return len(a & b) / max(1, len(a | b))


def build(
    app: list[dict],
    labels: list[int],
    cast_labels: set[int],
    old: dict | None,
    series_dir: Path,
    chapter_dir: Path,
) -> tuple[dict, dict[int, str]]:
    """cast.json (names, voices and colours kept from `old`) and label -> id."""
    old = old or {}
    groups: dict[int, list[int]] = {}
    for i, lab in enumerate(labels):
        if lab in (REJECTED, UNPLACED):  # no cast entry, no extra
            continue
        groups.setdefault(lab, []).append(i)
    order = sorted(
        groups, key=lambda lab: (-len({panel_key(app[i]) for i in groups[lab]}), lab)
    )
    old_cast = {c["id"]: c for c in old.get("cast", [])}
    old_extras = {x["id"]: x for x in old.get("extras", [])}
    # Hand-assigned appearances go where the ledger says, so they take no
    # part in matching clusters to old entries, and the ids they point at are
    # reserved: a fresh cluster may not take a name Emerson has already used.
    chapter = chapter_dir.name
    ledger = dict(old.get("assignments") or {})
    reserved = {v for v in ledger.values() if v != "none"}
    taken: set[str] = set()
    out_cast: list[dict] = []
    out_extras: list[dict] = []
    label_to_id: dict[int, str] = {}

    def match(pool: dict[str, dict], keys: set[str]) -> dict | None:
        best, best_v = None, 0.0
        for cid, entry in pool.items():
            if cid in taken:
                continue
            v = _overlap(
                keys,
                {
                    akey(a, chapter)
                    for a in entry.get("appearances", [])
                    if akey(a, chapter) not in ledger
                },
            )
            if v > best_v:
                best, best_v = entry, v
        return best if best_v >= 0.3 else None

    for lab in order:
        idx = groups[lab]
        keys = {
            akey(app[i], chapter) for i in idx if akey(app[i], chapter) not in ledger
        }
        is_cast = lab in cast_labels
        pool = old_cast if is_cast else old_extras
        prev = match(pool, keys)
        if prev is None and is_cast:
            prev = match(
                old_extras, keys
            )  # an extra promoted to cast keeps nothing but its label
            prev = None if prev is None else {"auto_name": prev.get("label")}
        best = sorted(
            idx, key=lambda i: (app[i].get("face") is None, -app[i].get("area_frac", 0))
        )[:3]
        apps = [
            {
                "panel_id": app[i]["panel_id"],
                "index": app[i]["index"],
                "chapter": app[i].get("chapter") or chapter_dir.name,
            }
            for i in idx
        ]
        if is_cast:
            n = len(out_cast) + 1
            cid = str(prev["id"]) if prev and prev.get("id") else f"c{n:02d}"
            while cid in taken or (cid in reserved and cid != (prev or {}).get("id")):
                n += 1
                cid = f"c{n:02d}"
            taken.add(cid)
            samples = _write_samples(
                cid, [app[i] for i in best], chapter_dir, series_dir
            )
            entry = {
                "id": cid,
                "name": (prev or {}).get("name")
                or (prev or {}).get("auto_name")
                or f"character {n}",
                "auto_name": f"character {n}",
                "color": (prev or {}).get("color") or PALETTE[(n - 1) % len(PALETTE)],
                "samples": samples,
                "embedding": None,
                "voice": (prev or {}).get("voice"),
                "rig": (prev or {}).get("rig"),
                "model3d": (prev or {}).get("model3d"),
                "appearances": apps,
                "panels": sorted({a["panel_id"] for a in apps}),
            }
            out_cast.append(entry)
        else:
            n = len(out_extras) + 1
            xid = str(prev["id"]) if prev and prev.get("id") else f"x{n:02d}"
            while xid in taken or (xid in reserved and xid != (prev or {}).get("id")):
                n += 1
                xid = f"x{n:02d}"
            taken.add(xid)
            i0 = best[0]
            entry = {
                "id": xid,
                "label": (prev or {}).get("label") or f"extra {n}",
                "samples": _write_samples(
                    xid,
                    [app[i0]],
                    Path(app[i0].get("chapter_dir") or chapter_dir),
                    series_dir,
                ),
                "voice": (prev or {}).get("voice"),
                "appearances": apps,
                "panels": sorted({a["panel_id"] for a in apps}),
            }
            out_extras.append(entry)
        label_to_id[lab] = entry["id"]
    # entries the ledger points at survive with their name, colour and voice
    # even when no cluster matched them; the ledger fills them next
    for cid in sorted(reserved):
        if cid in taken or cid not in old_cast:
            continue
        taken.add(cid)
        out_cast.append({**old_cast[cid], "appearances": [], "panels": []})
    doc: dict[str, Any] = {
        "schema": 1,
        "cast": out_cast,
        "narrator": old.get("narrator") or {"voice": None},
        "extras": out_extras,
        "backgrounds": old.get("backgrounds") or [],
        "props": old.get("props") or [],
        "assignments": old.get("assignments") or {},
    }
    for ch in sorted({a.get("chapter") or chapter_dir.name for a in app}):
        mine = [a for a in app if (a.get("chapter") or chapter_dir.name) == ch]
        cdir = Path(mine[0].get("chapter_dir") or chapter_dir)
        apply_assignments(doc, ch, mine, cdir, series_dir)
    return doc, label_to_id
