"""Re-detect keeps what Emerson fixed and keeps ids stable.

Rules, for panels and bubbles alike:

- A new item that overlaps an old one (IoU at least MATCH_IOU) takes the old
  item's id, so script lines and timeline shots that point at it stay valid.
- If that old item was edited, the old item wins entirely.
- An edited old item with no match is kept as it was (the detector missed
  what Emerson drew in), placed by its position.
- New items with no match get fresh ids after the highest old one.
- Unedited old items with no match are dropped.

Contract addition: ids are stable across re-detect for items that still
overlap their previous box.
"""

from __future__ import annotations

import re

MATCH_IOU = 0.5


def iou(a, b) -> float:
    ax0, ay0, aw, ah = a
    bx0, by0, bw, bh = b
    ix = max(0, min(ax0 + aw, bx0 + bw) - max(ax0, bx0))
    iy = max(0, min(ay0 + ah, by0 + bh) - max(ay0, by0))
    inter = ix * iy
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def _num(item_id: str) -> int:
    m = re.search(r"(\d+)$", item_id or "")
    return int(m.group(1)) if m else 0


def merge(
    old: list[dict], new: list[dict], prefix: str, reading: str = "ttb"
) -> list[dict]:
    """Merged list in reading order, ids assigned as described above."""
    if not old:
        return list(new)
    used: set[int] = set()
    out: list[dict] = []
    for item in new:
        best, best_iou = None, 0.0
        for k, o in enumerate(old):
            if k in used:
                continue
            v = iou(item["box"], o["box"])
            if v > best_iou:
                best, best_iou = k, v
        if best is not None and best_iou >= MATCH_IOU:
            used.add(best)
            o = old[best]
            if o.get("edited"):
                out.append(dict(o))
            else:
                out.append({**item, "id": o["id"]})
        else:
            out.append({**item, "id": ""})
    for k, o in enumerate(old):
        if k not in used and o.get("edited"):
            out.append(dict(o))
    next_id = max([_num(o["id"]) for o in old] + [0]) + 1
    for item in out:
        if not item["id"]:
            item["id"] = f"{prefix}{next_id:04d}"
            next_id += 1
    key = (
        (lambda i: (i["box"][1], i["box"][0]))
        if reading == "ttb"
        else (
            lambda i: (
                i["box"][1] // 200,
                -i["box"][0] if reading == "rtl" else i["box"][0],
            )
        )
    )
    out.sort(key=key)
    for n, item in enumerate(out, 1):
        item["order"] = n
    return out
