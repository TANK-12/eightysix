"""Builds script.json lines from bubbles.json plus scene.json cues
(CONTRACTS.md). Pure functions, testable with fixtures -- no file IO here.

Rules:
- bubble kind "sfx" is skipped: those become sound-effect entries, handled by
  panelforge/sfx, not spoken lines.
- caption bubbles are always spoken by the narrator.
- the speaker is the bubble's own if set, else scene.json's `speakers` guess.
- emotion comes from panelforge.audio.emotion: punctuation + kind, then the
  page cues gathered by `line_context` (bubble style, the speaker's face in
  that panel, the panel's mood, action and acoustics, and how big the
  balloon is relative to the chapter's others).
- rebuilding never discards a line Emerson edited (`edited: true`, e.g. via
  the per-line voice endpoint): it is carried over as-is. A line whose
  emotion he set by hand (`emotion.source == "user"`, via the per-line
  emotion endpoint) keeps that emotion while its text still follows the
  bubble.
"""

from __future__ import annotations

import statistics

from . import emotion


def _box_area(b: dict) -> float:
    box = b.get("box") or [0, 0, 0, 0]
    try:
        return max(0.0, float(box[2]) * float(box[3]))
    except (IndexError, TypeError, ValueError):
        return 0.0


def _median_area(bubbles_doc: dict) -> float:
    areas = [
        _box_area(b)
        for b in bubbles_doc.get("bubbles", [])
        if b.get("kind") != "sfx" and _box_area(b) > 0
    ]
    return statistics.median(areas) if areas else 0.0


def _speaker_for(bubble: dict, scene_doc: dict | None) -> str | None:
    kind = bubble.get("kind") or "speech"
    if kind == "caption":
        return "narrator"
    if bubble.get("speaker"):
        return bubble["speaker"]
    guess = ((scene_doc or {}).get("speakers") or {}).get(bubble.get("id"))
    if guess and guess.get("speaker"):
        return guess["speaker"]
    return None


def _context_for(bubble: dict, scene_doc: dict | None, median_area: float) -> dict:
    ctx: dict = {"style": bubble.get("style") or {}}
    area = _box_area(bubble)
    if median_area > 0 and area > 0:
        ctx["balloon_scale"] = round((area / median_area) ** 0.5, 3)
    panel = ((scene_doc or {}).get("panels") or {}).get(bubble.get("panel_id"))
    if not panel:
        return ctx
    if panel.get("mood"):
        ctx["mood"] = panel["mood"]
    if panel.get("action"):
        ctx["action"] = panel["action"]
    if panel.get("acoustics"):
        ctx["acoustics"] = panel["acoustics"]
    speaker = _speaker_for(bubble, scene_doc)
    if speaker and speaker != "narrator":
        for ch in panel.get("characters", []):
            if ch.get("cast_id") == speaker and ch.get("expression"):
                ctx["expression"] = ch["expression"]
                break
    return ctx


def line_context(
    bubbles_doc: dict, scene_doc: dict | None, bubble_id: str
) -> dict | None:
    """The cue context `build_script` used for one bubble, so the per-line
    emotion endpoint can recompute the automatic rules on request."""
    bubble = next(
        (b for b in bubbles_doc.get("bubbles", []) if b.get("id") == bubble_id), None
    )
    if bubble is None:
        return None
    return _context_for(bubble, scene_doc, _median_area(bubbles_doc))


def build_script(
    bubbles_doc: dict,
    existing_script: dict | None = None,
    scene_doc: dict | None = None,
) -> dict:
    existing_by_bubble: dict[str, dict] = {}
    if existing_script:
        for ln in existing_script.get("lines", []):
            if ln.get("bubble_id"):
                existing_by_bubble[ln["bubble_id"]] = ln

    median_area = _median_area(bubbles_doc)
    lines = []
    n = 0
    for b in bubbles_doc.get("bubbles", []):
        if b.get("kind") == "sfx":
            continue
        prior = existing_by_bubble.get(b["id"])
        if prior and prior.get("edited"):
            lines.append(prior)
            continue

        n += 1
        text = (b.get("text") or "").strip()
        kind = b.get("kind") or "speech"
        speaker = _speaker_for(b, scene_doc)
        prior_em = (prior or {}).get("emotion") or {}
        if prior_em.get("source") == "user":
            em = prior_em
        else:
            em = emotion.rules_for(text, kind, _context_for(b, scene_doc, median_area))
        line = {
            "id": f"l{n:04d}",
            "bubble_id": b["id"],
            "speaker": speaker,
            "text": emotion.normalize_text(text),
            "kind": kind,
            "emotion": em,
            "audio": prior.get("audio") if prior else None,
            "dur": prior.get("dur") if prior else None,
        }
        # a prior non-edited line with the same text keeps its rendered
        # audio, so an unrelated bubble edit elsewhere doesn't force a
        # re-synth of every line; cache.key() double-checks this at
        # synthesis time regardless.
        if prior and (prior.get("text") != line["text"] or prior.get("emotion") != em):
            line["audio"], line["dur"] = None, None
        lines.append(line)

    sfx = existing_script.get("sfx", []) if existing_script else []
    music = existing_script.get("music", []) if existing_script else []
    return {"schema": 1, "lines": lines, "sfx": sfx, "music": music}
