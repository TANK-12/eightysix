"""Everything scene learns from one panel on its own, cached on disk.

A panel's cache folder is named by a content key (its box plus the SHA-1 of
the pages it covers), so re-running analysis after detect renumbers panels,
or after nothing changed at all, reuses the work. Bubble edits only redo the
background, which is the one output that depends on them.

    work/scene/cache/<key>/record.json   characters, saliency, speed lines, stats
                           feats.npz      CCIP embeddings and colour histograms
                           cut_<i>.png    character cutouts (RGBA, cropped to box)
                           mask.png       union of character masks
                           bg.png         background, characters and bubbles removed
                           depth.png      16-bit, near = bright
                           prop_<i>.png   props (RGBA)
                           sfx_<i>.png    SFX lettering (RGBA)
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from . import detectors, geom, imaging, registry, rig

VERSION = 4  # bump to invalidate every cached panel
BG_VERSION = 2

MIN_PERSON_FRAC = 0.012  # of panel area
SKIP_KINDS = ("caption-only", "transition")


def content_key(panel: dict, strip: dict, chapter: dict) -> str:
    sha = {p["idx"]: p.get("sha1", "") for p in chapter.get("pages") or []}
    x, y, w, h = panel["box"]
    touched = [
        sha.get(s["page_idx"], str(s["page_idx"]))
        for s in strip["segments"]
        if s["strip_y"] < y + h and s["strip_y"] + s["h"] > y
    ]
    raw = json.dumps([VERSION, panel["box"], panel.get("polygon"), touched])
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def bubbles_key(local_bubbles: list[dict]) -> str:
    raw = json.dumps(
        [BG_VERSION, sorted((b["box"], b.get("kind")) for b in local_bubbles)]
    )
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


def _polygon_mask(panel: dict, w: int, h: int) -> np.ndarray | None:
    poly = panel.get("polygon")
    if not poly:
        return None
    m = np.zeros((h, w), np.uint8)
    pts = np.array(
        [[px - panel["box"][0], py - panel["box"][1]] for px, py in poly], np.int32
    )
    cv2.fillPoly(m, [pts], (255,))
    return m


def _rgba(bgr: np.ndarray, alpha: np.ndarray, box: list[int]) -> np.ndarray:
    x, y, w, h = box
    out = cv2.cvtColor(bgr[y : y + h, x : x + w], cv2.COLOR_BGR2BGRA)
    out[..., 3] = alpha[y : y + h, x : x + w]
    return out


HEAD_ZOOM = 1.7  # around the face box, to take in hair and collar


def _head_crop(bgr: np.ndarray, char: dict) -> np.ndarray | None:
    """The head and hair of one character, or None when no face was found."""
    face = char.get("face")
    if not face:
        return None
    h, w = bgr.shape[:2]
    fx, fy, fw, fh = face
    cx, cy = fx + fw / 2, fy + fh / 2
    half_w, half_h = fw * HEAD_ZOOM / 2, fh * HEAD_ZOOM / 2
    x0, y0 = int(max(0, cx - half_w)), int(max(0, cy - half_h))
    x1, y1 = int(min(w, cx + half_w)), int(min(h, cy + half_h))
    if x1 - x0 < 8 or y1 - y0 < 8:
        return None
    return bgr[y0:y1, x0:x1]


def _hair_and_body_hist(bgr, mask, box, face) -> tuple[np.ndarray, np.ndarray]:
    x, y, w, h = box
    crop = bgr[y : y + h, x : x + w]
    m = mask[y : y + h, x : x + w]
    body = imaging.colour_hist(crop, m)
    if face:
        fx, fy, fw, fh = face
        hb = geom.clip(
            [fx - 0.3 * fw, fy - 0.45 * fh, fw * 1.6, fh * 0.65],
            bgr.shape[1],
            bgr.shape[0],
        )
        hm = mask[hb[1] : hb[1] + hb[3], hb[0] : hb[0] + hb[2]]
        hair = imaging.colour_hist(
            bgr[hb[1] : hb[1] + hb[3], hb[0] : hb[0] + hb[2]], hm
        )
    else:
        top = crop[: max(1, h // 5)]
        hair = imaging.colour_hist(top, m[: max(1, h // 5)])
    return hair, body


def _bubble_boxes_local(panel: dict, local_bubbles: list[dict]) -> list[dict]:
    ox, oy = panel["box"][0], panel["box"][1]
    return [
        {**b, "box": [b["box"][0] - ox, b["box"][1] - oy, b["box"][2], b["box"][3]]}
        for b in local_bubbles
    ]


def sfx_alpha(crop: np.ndarray) -> np.ndarray:
    """Lettering mask for an SFX box: pixels far from the box's border colour
    (lettering sits on art, so the border is mostly background)."""
    if crop.size == 0:
        return np.zeros(crop.shape[:2], np.uint8)
    lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB).astype(np.float32)
    border = np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]])
    ref = np.median(border, axis=0)
    dist = np.linalg.norm(lab - ref, axis=2)
    spread = float(np.percentile(np.linalg.norm(border - ref, axis=1), 90))
    m = (dist > max(28.0, spread * 1.6)).astype(np.uint8) * 255
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    n, lab_img, stats, _ = cv2.connectedComponentsWithStats(m)
    keep = np.zeros_like(m)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] >= 0.004 * m.size:
            keep[lab_img == i] = 255
    return cv2.GaussianBlur(keep, (3, 3), 0)


def analyze(
    bgr: np.ndarray,
    panel: dict,
    local_bubbles: list[dict],
    folder: Path,
    rel_folder: str,
    want_bg: bool = True,
) -> dict[str, Any]:
    """Analyse one panel and write its cache folder. Returns the record."""
    folder.mkdir(parents=True, exist_ok=True)
    h, w = bgr.shape[:2]
    kind = panel.get("kind", "panel")
    poly = _polygon_mask(panel, w, h)
    if poly is not None:
        bgr = bgr.copy()
        bgr[poly == 0] = 255
    bubbles = _bubble_boxes_local(panel, local_bubbles)
    rec: dict[str, Any] = {
        "version": VERSION,
        "panel_id": panel["id"],
        "size": [w, h],
        "kind": kind,
        "models": {},
    }

    art = kind not in SKIP_KINDS and min(w, h) >= 48
    face_list = detectors.faces(bgr) if art else []
    fg = detectors.foreground(bgr) if art else None
    rec["models"]["seg"] = "anime-seg" if fg is not None else "grabcut"
    people = detectors.people(bgr, face_list, fg) if art else []
    rec["models"]["people"] = (
        "yolo" if registry.session("person") is not None else "faces+mask"
    )

    # Text balloons are not people: drop detections that are mostly bubble.
    balloon_boxes = [b["box"] for b in bubbles] or (
        imaging.find_balloons(bgr) if art else []
    )
    rec["balloons_fallback"] = [] if bubbles else balloon_boxes
    people = [
        p
        for p in people
        if geom.area(p["box"]) >= MIN_PERSON_FRAC * w * h
        and not any(
            geom.intersection(p["box"], bb) > 0.6 * geom.area(p["box"])
            for bb in balloon_boxes
        )
    ]
    people.sort(key=lambda p: (p["box"][0], p["box"][1]))

    chars: list[dict] = []
    masks: list[np.ndarray] = []
    crops: list[np.ndarray] = []
    hairs, bodies = [], []
    used_faces: set[int] = set()
    for idx, p in enumerate(people):
        box = p["box"]
        # The best face inside this person, not already taken.
        cand = [
            (fi, f)
            for fi, f in enumerate(face_list)
            if fi not in used_faces
            and geom.intersection(f["box"], box) > 0.7 * geom.area(f["box"])
        ]
        face = None
        if cand:
            fi, f = max(cand, key=lambda t: (t[1]["score"], -t[1]["box"][1]))
            used_faces.add(fi)
            face = f["box"]
        mask, src = detectors.character_mask(bgr, box, fg)
        if poly is not None:
            mask = cv2.bitwise_and(mask, poly)
        facing = rig.facing(
            face, box, mask[box[1] : box[1] + box[3], box[0] : box[0] + box[2]]
        )
        cut = _rgba(bgr, mask, box)
        cv2.imwrite(str(folder / f"cut_{idx}.png"), cut)
        hair, body = _hair_and_body_hist(bgr, mask, box, face)
        hairs.append(hair)
        bodies.append(body)
        crops.append(bgr[box[1] : box[1] + box[3], box[0] : box[0] + box[2]])
        masks.append(mask)
        r = rig.build(
            box,
            face,
            facing,
            w,
            h,
            mask[box[1] : box[1] + box[3], box[0] : box[0] + box[2]],
        )
        chars.append(
            {
                "box": box,
                "score": p["score"],
                "face": face,
                "facing": facing,
                "mask_source": src,
                "cutout": f"{rel_folder}/cut_{idx}.png",
                "area_frac": round(geom.area(box) / float(w * h), 4),
                "rig": r,
            }
        )
    rec["characters"] = chars
    rec["faces_unmatched"] = [
        f["box"] for fi, f in enumerate(face_list) if fi not in used_faces
    ]

    feats = detectors.embed(crops) if crops else None
    rec["models"]["identity"] = "ccip" if feats is not None else "colour"
    # A second embedding of the head alone. The whole-person crop is mostly
    # clothes and background, so two characters in the same uniform look
    # alike and one character who changes clothes does not; the head is what
    # actually says who someone is.
    head_crops = [(i, _head_crop(bgr, ch)) for i, ch in enumerate(chars)]
    head_at = [i for i, c in head_crops if c is not None]
    heads = [c for _, c in head_crops if c is not None]
    head_feats = detectors.embed(heads) if heads else None
    face_feats = np.zeros((len(chars), 768), np.float32)
    face_has = np.zeros(len(chars), bool)
    if head_feats is not None:
        for row, i in enumerate(head_at):
            face_feats[i] = head_feats[row]
            face_has[i] = True
    np.savez_compressed(
        folder / "feats.npz",
        ccip=feats if feats is not None else np.zeros((0, 768), np.float32),
        ccip_face=face_feats,
        face_has=face_has,
        hair=np.array(hairs, np.float64).reshape(-1, 22),
        body=np.array(bodies, np.float64).reshape(-1, 22),
    )

    union = np.zeros((h, w), np.uint8)
    for m in masks:
        union = np.maximum(union, m)
    cv2.imwrite(str(folder / "mask.png"), union)

    # Understanding: saliency, speed lines, colour.
    all_faces = [c["face"] for c in chars if c["face"]] + rec["faces_unmatched"]
    rec["saliency"] = imaging.saliency_points(bgr, all_faces)
    rec["speed_lines"] = imaging.speed_lines(bgr) if art else None
    rec["stats"] = imaging.lab_stats(bgr)
    grey = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    rec["stats"]["edges"] = float((cv2.Canny(grey, 80, 200) > 0).mean())

    # Depth.
    d, dsrc = (
        detectors.depth(bgr, masks)
        if art
        else (imaging.heuristic_depth(h, w, masks), "heuristic")
    )
    if masks:  # characters are never behind their own background
        near = np.percentile(d, 90)
        for m in masks:
            sel = m > 127
            if sel.any():
                d = np.where(
                    sel, np.maximum(d, np.float32(near * 0.9 + d.max() * 0.1)), d
                )
    cv2.imwrite(str(folder / "depth.png"), imaging.to_depth16(d))
    rec["models"]["depth"] = dsrc
    rec["depth"] = f"{rel_folder}/depth.png"

    # Props: foreground pieces the segmenter found outside every person.
    props = []
    if fg is not None:
        rest = ((fg > 127) & (union < 128)).astype(np.uint8)
        rest = cv2.morphologyEx(rest, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        n, lab, stats, _ = cv2.connectedComponentsWithStats(rest)
        for i in range(1, n):
            x, y, bw, bh, a = stats[i]
            box = [int(x), int(y), int(bw), int(bh)]
            if not (0.004 * w * h <= a <= 0.25 * w * h) or min(bw, bh) < 20:
                continue
            if any(
                geom.intersection(box, c["box"]) > 0.5 * geom.area(box) for c in chars
            ):
                continue
            if any(
                geom.intersection(box, bb) > 0.4 * geom.area(box)
                for bb in balloon_boxes
            ):
                continue
            alpha = np.where(lab == i, fg, 0).astype(np.uint8)
            k = len(props)
            cv2.imwrite(str(folder / f"prop_{k}.png"), _rgba(bgr, alpha, box))
            props.append({"box": box, "image": f"{rel_folder}/prop_{k}.png"})
            union = np.maximum(union, alpha)
    rec["props"] = props

    # SFX lettering from detect's sfx boxes.
    sfx = []
    for b in bubbles:
        if b.get("kind") != "sfx":
            continue
        box = geom.clip(b["box"], w, h)
        if box[2] < 4 or box[3] < 4:
            continue
        crop = bgr[box[1] : box[1] + box[3], box[0] : box[0] + box[2]]
        alpha = sfx_alpha(crop)
        k = len(sfx)
        rgba = cv2.cvtColor(crop, cv2.COLOR_BGR2BGRA)
        rgba[..., 3] = alpha
        cv2.imwrite(str(folder / f"sfx_{k}.png"), rgba)
        sfx.append(
            {
                "box": box,
                "text": b.get("text", ""),
                "image": f"{rel_folder}/sfx_{k}.png",
            }
        )
    rec["sfx"] = sfx

    if want_bg:
        background(bgr, rec, bubbles, union, folder, rel_folder)
    return rec


def background(
    bgr: np.ndarray,
    rec: dict,
    bubbles: list[dict],
    union: np.ndarray | None,
    folder: Path,
    rel_folder: str,
) -> None:
    """Remove characters, props, bubbles and SFX, fill the holes, and store
    the background plus its location signature in the record."""
    h, w = bgr.shape[:2]
    if union is None:
        union = cv2.imread(str(folder / "mask.png"), cv2.IMREAD_GRAYSCALE)
        if union is None:
            union = np.zeros((h, w), np.uint8)
    hole = (union > 96).astype(np.uint8) * 255
    for b in [bb["box"] for bb in bubbles] + rec.get("balloons_fallback", []):
        x, y, bw, bh = geom.clip(geom.expand(b, 0.04, 0.04, 0.04, 0.04), w, h)
        hole[y : y + bh, x : x + bw] = 255
    hole = cv2.dilate(hole, np.ones((9, 9), np.uint8))
    frac = float((hole > 0).mean())
    feature_mask = hole
    rec["bg_feature"] = imaging.layout_feature(bgr, feature_mask).round(6).tolist()
    rec["bg_hole_frac"] = round(frac, 4)
    if rec.get("kind") in SKIP_KINDS or frac > 0.85:
        rec["background"] = None
    else:
        filled, how = fill(bgr, hole)
        cv2.imwrite(str(folder / "bg.png"), filled)
        rec["background"] = f"{rel_folder}/bg.png"
        rec["models"]["inpaint"] = how


def fill(bgr: np.ndarray, hole: np.ndarray) -> tuple[np.ndarray, str]:
    return imaging.inpaint(bgr, hole), "opencv"
