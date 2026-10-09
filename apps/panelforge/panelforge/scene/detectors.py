"""Model-backed steps, each with its classical fallback.

    people(bgr)        -> [{"box", "score"}]      YOLOv8 person, else from faces/mask
    faces(bgr)         -> [{"box", "score"}]      YOLOv8 face, else nothing
    foreground(bgr)    -> uint8 mask or None      ISNet anime-seg
    embed(crops)       -> (N, 768) or None        CCIP identity features
    ccip_diff(feats)   -> (N, N) or None          CCIP difference head
    depth(bgr, masks)  -> float 0..1, near = 1    Depth Anything V2, else heuristic

Preprocessing follows each model's own project code (deepghs imgutils for the
YOLO and CCIP models, SkyTNT anime-segmentation, the Hugging Face processor
config for Depth Anything).
"""

from __future__ import annotations

import math
from typing import Any

import cv2
import numpy as np

from . import geom, imaging, registry


def _run(key: str, feed: np.ndarray) -> np.ndarray | None:
    sess: Any = registry.session(key)
    if sess is None:
        return None
    name = sess.get_inputs()[0].name
    return sess.run(None, {name: feed})[0]


# ---------------------------------------------------------------- YOLO


def _yolo(
    key: str, bgr: np.ndarray, threshold: float, max_size: int, iou: float = 0.6
) -> list[dict] | None:
    h, w = bgr.shape[:2]
    r = min(1.0, max_size / max(h, w))
    nw = int(math.ceil(w * r / 32) * 32)
    nh = int(math.ceil(h * r / 32) * 32)
    rgb = cv2.cvtColor(cv2.resize(bgr, (nw, nh)), cv2.COLOR_BGR2RGB)
    feed = (rgb.transpose(2, 0, 1)[None].astype(np.float32)) / 255.0
    out = _run(key, feed)
    if out is None:
        return None
    pred = out[0]
    if pred.shape[0] < pred.shape[1]:  # (4 + classes, anchors)
        pred = pred.T
    scores = pred[:, 4:].max(axis=1)
    keep = scores >= threshold
    pred, scores = pred[keep], scores[keep]
    sx, sy = w / nw, h / nh
    boxes = [
        [(cx - bw / 2) * sx, (cy - bh / 2) * sy, bw * sx, bh * sy]
        for cx, cy, bw, bh in pred[:, :4]
    ]
    picked = geom.nms(boxes, scores.tolist(), iou)
    return [
        {"box": geom.clip(boxes[i], w, h), "score": round(float(scores[i]), 3)}
        for i in picked
        if boxes[i][2] > 4 and boxes[i][3] > 4
    ]


def windows(h: int, w: int, ratio: float = 1.3, overlap: float = 0.3):
    """Row ranges that cut a tall webtoon panel into roughly ratio*w tall
    windows with overlap, so small faces are not shrunk away."""
    win = int(w * ratio)
    if h <= win * 1.2:
        return [(0, h)]
    step = max(1, int(win * (1 - overlap)))
    starts = list(range(0, max(1, h - win), step))
    if starts[-1] + win < h:
        starts.append(h - win)
    return [(y, min(h, y + win)) for y in starts]


def suppress_contained(dets: list[dict], frac: float = 0.8) -> list[dict]:
    """Drop a box mostly inside a better-scoring box (tile-cut duplicates)."""
    dets = sorted(dets, key=lambda d: -d["score"])
    kept: list[dict] = []
    for d in dets:
        a = max(1.0, geom.area(d["box"]))
        if any(
            geom.intersection(d["box"], k["box"]) / a > frac
            or geom.iou(d["box"], k["box"]) > 0.5
            for k in kept
        ):
            continue
        kept.append(d)
    return kept


def _yolo_tiled(
    key: str, bgr: np.ndarray, threshold: float, max_size: int
) -> list[dict] | None:
    h, w = bgr.shape[:2]
    found: list[dict] = []
    wins = windows(h, w)
    passes = [(0, h, max_size)] if len(wins) == 1 else [(0, h, 1280)]
    passes += [(y0, y1, max_size) for y0, y1 in wins] if len(wins) > 1 else []
    for y0, y1, size in passes:
        got = _yolo(key, bgr[y0:y1], threshold, size, iou=0.5)
        if got is None:
            return None
        for d in got:
            d["box"] = [d["box"][0], d["box"][1] + y0, d["box"][2], d["box"][3]]
            found.append(d)
    return suppress_contained(found)


def faces(bgr: np.ndarray) -> list[dict]:
    found = _yolo_tiled("face", bgr, registry.FACE_THRESHOLD, 960)
    return [f for f in (found or []) if min(f["box"][2], f["box"][3]) >= 14]


def people(bgr: np.ndarray, face_list: list[dict], fg: np.ndarray | None) -> list[dict]:
    found = _yolo_tiled("person", bgr, registry.PERSON_THRESHOLD, 800)
    h, w = bgr.shape[:2]
    if found is None:
        found = []
        # Fallback 1: large foreground blobs from the segmentation mask.
        if fg is not None:
            n, _, stats, _ = cv2.connectedComponentsWithStats(
                (fg > 127).astype(np.uint8)
            )
            for i in range(1, n):
                x, y, bw, bh, a = stats[i]
                if a > 0.01 * h * w:
                    found.append(
                        {"box": [int(x), int(y), int(bw), int(bh)], "score": 0.3}
                    )
    # Faces with no person around them become people (close-ups, crowds).
    for f in face_list:
        if not any(
            geom.intersection(f["box"], p["box"]) > 0.6 * geom.area(f["box"])
            for p in found
        ):
            fx, fy, fw, fh = f["box"]
            body = geom.clip(geom.expand(f["box"], 0.9, 0.5, 0.9, 4.0), w, h)
            if fg is not None:
                sub = fg[body[1] : body[1] + body[3], body[0] : body[0] + body[2]] > 127
                if sub.any():
                    ys, xs = np.where(sub)
                    tight = [
                        body[0] + int(xs.min()),
                        body[1] + int(ys.min()),
                        int(xs.max() - xs.min() + 1),
                        int(ys.max() - ys.min() + 1),
                    ]
                    if geom.intersection(tight, f["box"]) > 0.5 * fw * fh:
                        body = tight
            found.append(
                {"box": body, "score": round(f["score"] * 0.8, 3), "from_face": True}
            )
    return found


# ---------------------------------------------------------------- segmentation


def foreground(bgr: np.ndarray) -> np.ndarray | None:
    """Character mask (uint8 0..255) for the whole panel, or None."""
    h0, w0 = bgr.shape[:2]
    wins = windows(h0, w0, ratio=1.4)
    if len(wins) > 1:
        full = np.zeros((h0, w0), np.uint8)
        for y0, y1 in wins:
            part = foreground(bgr[y0:y1])
            if part is None:
                return None
            full[y0:y1] = np.maximum(full[y0:y1], part)
        return full
    s = 1024
    h, w = (s, int(s * w0 / h0)) if h0 > w0 else (int(s * h0 / w0), s)
    h, w = max(1, h), max(1, w)
    ph, pw = s - h, s - w
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB).astype(np.float32) / 255
    feed = np.zeros((s, s, 3), np.float32)
    feed[ph // 2 : ph // 2 + h, pw // 2 : pw // 2 + w] = cv2.resize(rgb, (w, h))
    out = _run("seg", feed.transpose(2, 0, 1)[None])
    if out is None:
        return None
    m = out[0, 0, ph // 2 : ph // 2 + h, pw // 2 : pw // 2 + w]
    m = cv2.resize(m, (w0, h0))
    return (np.clip(m, 0, 1) * 255).astype(np.uint8)


def character_mask(
    bgr: np.ndarray, box: list[int], fg: np.ndarray | None
) -> tuple[np.ndarray, str]:
    """Mask for one character (panel size): the model mask inside the box, or
    GrabCut when the model is missing or found nothing there."""
    x, y, w, h = box
    if fg is not None:
        m = np.zeros_like(fg)
        m[y : y + h, x : x + w] = fg[y : y + h, x : x + w]
        if (m > 127).sum() > 0.08 * max(1, w * h):
            return m, "anime-seg"
    return imaging.grabcut_mask(bgr, box), "grabcut"


# ---------------------------------------------------------------- identity


def embed(crops_bgr: list[np.ndarray]) -> np.ndarray | None:
    if not crops_bgr:
        return None
    if registry.session("ccip_feat") is None:
        return None
    feats = []
    for crop in crops_bgr:
        rgb = cv2.cvtColor(
            cv2.resize(crop, (384, 384), interpolation=cv2.INTER_LINEAR),
            cv2.COLOR_BGR2RGB,
        )
        x = (rgb.astype(np.float32) / 255 - 0.5) / 0.5
        out = _run("ccip_feat", x.transpose(2, 0, 1)[None])
        if out is None:
            return None
        feats.append(out[0])
    return np.stack(feats).astype(np.float32)


def ccip_diff(feats: np.ndarray) -> np.ndarray | None:
    """Pairwise CCIP difference; below registry.CCIP_SAME_THRESHOLD = same."""
    if feats is None or len(feats) == 0:
        return None
    out = _run("ccip_metrics", feats.astype(np.float32))
    return None if out is None else np.asarray(out, dtype=np.float64)


# ---------------------------------------------------------------- depth


DEPTH_KEY = "depth_base"


def _depth_once(bgr: np.ndarray, key: str, short: int = 518, long_cap: int = 1036):
    h0, w0 = bgr.shape[:2]
    r = short / min(h0, w0)
    if max(h0, w0) * r > long_cap:
        r = long_cap / max(h0, w0)
    nh = max(14, int(round(h0 * r / 14)) * 14)
    nw = max(14, int(round(w0 * r / 14)) * 14)
    rgb = cv2.cvtColor(
        cv2.resize(bgr, (nw, nh), interpolation=cv2.INTER_CUBIC), cv2.COLOR_BGR2RGB
    )
    mean = np.array([0.485, 0.456, 0.406], np.float32)
    std = np.array([0.229, 0.224, 0.225], np.float32)
    x = (rgb.astype(np.float32) / 255 - mean) / std
    out = _run(key, x.transpose(2, 0, 1)[None])
    if out is None:
        return None
    return cv2.resize(
        out[0].astype(np.float32), (w0, h0), interpolation=cv2.INTER_CUBIC
    )


def depth(
    bgr: np.ndarray, char_masks: list[np.ndarray], key: str | None = None
) -> tuple[np.ndarray, str]:
    """Relative depth, near = larger. Tall panels run in overlapping windows;
    each window is fitted (scale and offset, least squares) to the part
    already placed, so near and far stay consistent down the whole panel."""
    key = key or DEPTH_KEY
    h0, w0 = bgr.shape[:2]
    name = registry.MODELS[key].repo.split("/")[-1]
    if registry.session(key) is None:
        return imaging.heuristic_depth(h0, w0, char_masks), "heuristic"
    wins = windows(h0, w0, ratio=1.5, overlap=0.35)
    if len(wins) == 1:
        d = _depth_once(bgr, key)
        if d is None:
            return imaging.heuristic_depth(h0, w0, char_masks), "heuristic"
        return d, name
    acc = np.zeros((h0, w0), np.float32)
    wsum = np.zeros((h0, w0), np.float32)
    filled_to = 0
    for y0, y1 in wins:
        part = _depth_once(bgr[y0:y1], key)
        if part is None:
            return imaging.heuristic_depth(h0, w0, char_masks), "heuristic"
        if filled_to > y0:
            prev = acc[y0:filled_to] / np.maximum(wsum[y0:filled_to], 1e-6)
            cur = part[: filled_to - y0]
            a_mat = np.stack([cur.ravel(), np.ones(cur.size, np.float32)], axis=1)
            (a, b), *_ = np.linalg.lstsq(a_mat, prev.ravel(), rcond=None)
            if a > 0:
                part = part * a + b
        ramp = np.minimum(np.arange(y1 - y0) + 1, np.arange(y1 - y0)[::-1] + 1)
        ramp = np.minimum(1.0, ramp / max(1.0, 0.15 * (y1 - y0))).astype(np.float32)
        if y0 == 0:
            ramp[: len(ramp) // 2] = 1.0
        if y1 == h0:
            ramp[len(ramp) // 2 :] = 1.0
        acc[y0:y1] += part * ramp[:, None]
        wsum[y0:y1] += ramp[:, None]
        filled_to = y1
    return acc / np.maximum(wsum, 1e-6), name + " (tiled)"
