"""Whole-chapter page verification, used after fetch and after import.

Reuses forge_mangafetch's per-page checks (decode, dims, blank) and adds the
cross-page seam check CONTRACTS/HANDOFF describe: the brightness jump at
neighbouring page boundaries should look the same for a canvas-screenshot
page as for a plain download, or the canvas page is probably a stray
tile/half-draw.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "shared")
)
import forge_mangafetch as mf  # noqa: E402

SEAM_WARN = 30.0  # brightness-unit jump that looks suspicious vs. neighbours' median


def verify_chapter_pages(pages: list[dict], pages_dir: Path) -> dict:
    """pages: the chapter.json-style list (idx, file, w, h, capture, ...).

    Returns {"ok": bool, "problems": [{"idx":.., "reason":..}], "seam_max": float}.
    """
    problems: list[dict] = []
    blobs: dict[int, bytes] = {}
    for p in sorted(pages, key=lambda p: p["idx"]):
        fpath = pages_dir / os.path.basename(p["file"])
        try:
            data = fpath.read_bytes()
        except OSError as e:
            problems.append({"idx": p["idx"], "reason": f"missing file: {e}"})
            continue
        chk = mf.verify_page_bytes(data, expect_w=p.get("w"), expect_h=p.get("h"))
        if not chk.ok:
            problems.append({"idx": p["idx"], "reason": chk.reason})
        blobs[p["idx"]] = data

    seams = []
    idxs = sorted(blobs)
    for a, b in zip(idxs, idxs[1:]):
        if b != a + 1:
            continue
        try:
            seams.append((b, mf.seam_score(blobs[a], blobs[b])))
        except Exception:
            continue
    seam_max = max((s for _, s in seams), default=0.0)
    if seams:
        med = sorted(s for _, s in seams)[len(seams) // 2]
        for idx, s in seams:
            if s > SEAM_WARN and s > med * 4:
                problems.append(
                    {"idx": idx, "reason": f"seam jump {s:.1f} (median {med:.1f})"}
                )

    return {"ok": not problems, "problems": problems, "seam_max": seam_max}
