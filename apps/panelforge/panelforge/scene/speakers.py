"""Who says each bubble: rules only, explained in `why`.

Evidence, strongest first:
  1. caption boxes belong to the narrator;
  2. the bubble's tail points at a face (or into a character's box);
  3. a bubble joined to the previous one continues that speaker;
  4. the panel has exactly one character;
  5. two people talking in turn: the next unexplained bubble goes to the
     other one (within a panel, and carried across panels);
  6. the nearest face to the bubble;
  7. no one drawn: continuity from earlier panels.

Output matches scene.json `speakers`: {bubble_id: {speaker, conf, why}}.
scene never writes bubbles.json; the editor applies these guesses.
"""

from __future__ import annotations

import math
from typing import Any

from . import geom

TAIL_MAX_ANGLE = 35.0  # degrees between the tail and the direction to a face
JOIN_GAP = 12  # px: bubbles closer than this are one balloon


def _speaker_key(ch: dict) -> str | None:
    return ch.get("cast_id") or ch.get("extra_id")


def _face_point(ch: dict) -> tuple[float, float]:
    face = ch.get("face")
    if face:
        return geom.center(face)
    x, y, w, h = ch["box"]
    return x + w / 2, y + min(h, w) * 0.35


def _gap(a: list[int], b: list[int]) -> float:
    dx = max(0, max(a[0], b[0]) - min(a[0] + a[2], b[0] + b[2]))
    dy = max(0, max(a[1], b[1]) - min(a[1] + a[3], b[1] + b[3]))
    return math.hypot(dx, dy)


def _by_tail(bubble_box, tail, chars) -> tuple[int, float] | None:
    """Index of the character the tail aims at, with a confidence."""
    bx, by = geom.center(bubble_box)
    tx, ty = tail
    direction = (tx - bx, ty - by)
    best = None
    for i, ch in enumerate(chars):
        if geom.contains_point(ch["box"], tx, ty) and ch.get("face") is None:
            score = 0.75
        else:
            fx, fy = _face_point(ch)
            ang = geom.angle_between(direction, (fx - bx, fy - by))
            if ang > TAIL_MAX_ANGLE:
                continue
            reach = math.hypot(fx - tx, fy - ty) / max(
                1.0, math.hypot(fx - bx, fy - by)
            )
            score = 0.9 - 0.3 * ang / TAIL_MAX_ANGLE - 0.1 * min(1.0, reach)
        if best is None or score > best[1]:
            best = (i, score)
    return best


def guess(
    bubbles: list[dict],
    panels: dict[str, dict],
    characters: dict[str, list[dict]],
) -> dict[str, dict[str, Any]]:
    """bubbles: bubbles.json entries (strip coords). panels: id -> panels.json
    entry (strip box). characters: panel id -> scene characters (panel coords)."""
    out: dict[str, dict[str, Any]] = {}
    history: list[str] = []  # speakers in reading order, across panels
    prev: dict | None = None
    prev_speaker: str | None = None

    ordered = sorted(bubbles, key=lambda b: (b.get("order", 0), b["id"]))
    for b in ordered:
        kind = b.get("kind", "speech")
        pid = b.get("panel_id")
        if kind == "sfx":
            prev = None
            continue
        if kind == "caption":
            out[b["id"]] = {"speaker": "narrator", "conf": 0.8, "why": "caption box"}
            history.append("narrator")
            prev, prev_speaker = b, "narrator"
            continue

        panel = panels.get(pid or "")
        ox, oy = (panel["box"][0], panel["box"][1]) if panel else (0, 0)
        box = [b["box"][0] - ox, b["box"][1] - oy, b["box"][2], b["box"][3]]
        chars = [c for c in characters.get(pid or "", []) if _speaker_key(c)]
        people = sorted({_speaker_key(c) for c in chars} - {None})
        talkers = [h for h in history if h != "narrator"]
        other = None
        if len(talkers) >= 1:
            last = talkers[-1]
            earlier = [h for h in reversed(talkers) if h != last]
            if earlier:
                other = earlier[0]

        result: dict[str, Any] | None = None
        tail = b.get("tail")
        if tail and chars:
            hit = _by_tail(box, (tail[0] - ox, tail[1] - oy), chars)
            if hit:
                result = {
                    "speaker": _speaker_key(chars[hit[0]]),
                    "conf": round(hit[1], 2),
                    "why": "tail points at face",
                }
        if (
            result is None
            and prev is not None
            and prev.get("panel_id") == pid
            and prev_speaker
            and prev_speaker != "narrator"
            and _gap(prev["box"], b["box"]) <= JOIN_GAP
        ):
            result = {
                "speaker": prev_speaker,
                "conf": 0.6,
                "why": "joined to the previous bubble",
            }
        if result is None and len(people) == 1:
            result = {
                "speaker": people[0],
                "conf": 0.65,
                "why": "only character in panel",
            }
        if result is None and len(people) >= 2:
            bx, by = geom.center(box)
            dists = sorted(
                (math.hypot(bx - _face_point(c)[0], by - _face_point(c)[1]), k)
                for c in chars
                if (k := _speaker_key(c))
            )
            near_d, near = dists[0]
            second_d = next((d for d, k in dists if k != near), math.inf)
            clear = near_d < 0.6 * second_d
            last = talkers[-1] if talkers else None
            if not clear and last in people:
                partner = next((p for p in people if p != last), None)
                result = {
                    "speaker": partner,
                    "conf": 0.5,
                    "why": "alternating dialogue",
                }
            else:
                result = {
                    "speaker": near,
                    "conf": 0.55 if clear else 0.4,
                    "why": "nearest face",
                }
        if result is None and not people and talkers:
            if other is not None and len(talkers) >= 2 and talkers[-2] == other:
                result = {
                    "speaker": other,
                    "conf": 0.4,
                    "why": "alternating dialogue",
                }
            else:
                result = {
                    "speaker": talkers[-1],
                    "conf": 0.3,
                    "why": "continues from earlier panel",
                }
        if result is None:
            result = {"speaker": None, "conf": 0.0, "why": "no evidence"}

        out[b["id"]] = result
        if result["speaker"]:
            history.append(result["speaker"])
        prev, prev_speaker = b, result["speaker"]
    return out
