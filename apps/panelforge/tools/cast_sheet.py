"""Contact sheet of the cast finder's clusters, to judge it by eye.

    .venv/bin/python tools/cast_sheet.py <series> <chapter> [out.jpg] [quantile] [threshold]
    .venv/bin/python tools/cast_sheet.py <series> --series [out.jpg]

The second form draws the cast *as the app has it* (cast.json ids over every
analysed chapter, one row per character, the biggest crops from any chapter,
the chapter drawn on each crop) instead of re-clustering one chapter. That
is the form to judge the cross-chapter grouping with.

Reads the analysed chapter (scene.json plus the per-panel cache), re-runs
`cast.group` with the current thresholds and writes a JPEG with one row per
cluster and the biggest cutouts across it. A good row is the same person
drawn several ways; a bad row mixes two people or holds crops that are not
people at all. Printed numbers: how many appearances were dropped by
`cast.is_person`, how many clusters came out, and the cluster sizes.
"""

import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from panelforge import paths  # noqa: E402
from panelforge.scene import cast as cast_mod  # noqa: E402
from panelforge.scene import geom, panel as panel_mod, panelsrc  # noqa: E402

CELL = 110
COLS = 8
ROWS = 12


def appearances(cdir: Path) -> tuple[list[dict], dict[str, str]]:
    """This chapter's appearance records (the shared loader in cast.py)."""
    return cast_mod.load_chapter_appearances(cdir)


def cell(cdir: Path, a: dict) -> np.ndarray | None:
    img = cv2.imread(str(cdir / (a.get("cutout") or "")), cv2.IMREAD_UNCHANGED)
    if img is None:
        return None
    if img.ndim == 3 and img.shape[2] == 4:
        alpha = img[:, :, 3:4] / 255.0
        img = (img[:, :, :3] * alpha + 255 * (1 - alpha)).astype(np.uint8)
    h, w = img.shape[:2]
    s = min(CELL / max(1, h), CELL / max(1, w))
    return cv2.resize(img, (max(1, int(w * s)), max(1, int(h * s))))


def main(series: str, chapter: str, out: str, quantile=None, threshold=None) -> None:
    if quantile is not None:
        cast_mod.CLUSTER_QUANTILE = quantile
    if threshold is not None:
        cast_mod.CLUSTER_THRESHOLD = threshold
    print(
        f"quantile {cast_mod.CLUSTER_QUANTILE}, threshold {cast_mod.CLUSTER_THRESHOLD}"
    )
    cdir = paths.chapter_dir(series, chapter)
    app, scene_of = appearances(cdir)
    labels, cast_labels = cast_mod.group(app, scene_of)
    dropped = sum(1 for lab in labels if lab == cast_mod.REJECTED)
    unplaced = sum(1 for lab in labels if lab == cast_mod.UNPLACED)
    sizes: dict[int, int] = {}
    for lab in labels:
        if lab not in (cast_mod.REJECTED, cast_mod.UNPLACED):
            sizes[lab] = sizes.get(lab, 0) + 1
    print(
        f"{len(app)} appearances, {dropped} dropped as not people, "
        f"{unplaced} faceless left unplaced"
    )
    print(
        f"{len(sizes)} clusters ({len(cast_labels)} cast), sizes {sorted(sizes.values(), reverse=True)}"
    )
    rows = sorted(sizes, key=lambda lab: -sizes[lab])[:ROWS]
    sheet = np.full((CELL * max(1, len(rows)), CELL * COLS, 3), 255, np.uint8)
    for r, lab in enumerate(rows):
        items = sorted(
            [a for a, x in zip(app, labels) if x == lab],
            key=lambda a: -a.get("area_frac", 0),
        )[:COLS]
        for c, a in enumerate(items):
            img = cell(cdir, a)
            if img is None:
                continue
            sheet[
                r * CELL : r * CELL + img.shape[0], c * CELL : c * CELL + img.shape[1]
            ] = img
    cv2.imwrite(out, sheet)
    print("wrote", out)


def series_sheet(series: str, out: str) -> None:
    """One row per cast entry in cast.json, crops from every chapter."""
    sdir = paths.series_dir(series)
    doc = json.loads((sdir / "cast.json").read_text())
    per_chapter: dict[str, dict[tuple[str, int], dict]] = {}
    for cdir in sorted((sdir / "chapters").glob("*")):
        if (cdir / "scene.json").exists():
            app, _ = appearances(cdir)
            per_chapter[cdir.name] = {(a["panel_id"], a["index"]): a for a in app}
    cast = doc.get("cast", [])
    print(
        f"{len(cast)} cast, {len(doc.get('extras', []))} extras, chapters {sorted(per_chapter)}"
    )
    sheet = np.full((CELL * max(1, len(cast)), CELL * COLS, 3), 255, np.uint8)
    for r, entry in enumerate(cast):
        items = []
        for x in entry.get("appearances", []):
            a = per_chapter.get(x.get("chapter") or "", {}).get(
                (x["panel_id"], x["index"])
            )
            if a is not None:
                items.append((x.get("chapter") or "", a))
        chapters = sorted({ch for ch, _ in items})
        print(
            f"  {entry['id']} {entry.get('name')}: {len(items)} crops, chapters {chapters}"
        )
        items.sort(key=lambda t: -t[1].get("area_frac", 0))
        # spread the row over chapters: up to COLS crops, round-robin by chapter
        by_ch: dict[str, list] = {}
        for ch, a in items:
            by_ch.setdefault(ch, []).append(a)
        picked = []
        while len(picked) < COLS and any(by_ch.values()):
            for ch in sorted(by_ch):
                if by_ch[ch] and len(picked) < COLS:
                    picked.append((ch, by_ch[ch].pop(0)))
        for c, (ch, a) in enumerate(picked):
            img = cell(paths.chapter_dir(series, ch), a)
            if img is None:
                continue
            cv2.putText(
                img, ch[-2:], (3, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 255), 1
            )
            sheet[
                r * CELL : r * CELL + img.shape[0], c * CELL : c * CELL + img.shape[1]
            ] = img
    cv2.imwrite(out, sheet)
    print("wrote", out)


if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) >= 2 and args[1] == "--series":
        series_sheet(args[0], args[2] if len(args) > 2 else "cast-series.jpg")
        raise SystemExit(0)
    if len(args) < 2:
        print(__doc__)
        raise SystemExit(2)
    main(
        args[0],
        args[1],
        args[2] if len(args) > 2 else "cast-sheet.jpg",
        float(args[3]) if len(args) > 3 else None,
        float(args[4]) if len(args) > 4 else None,
    )
