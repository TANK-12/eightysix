"""Where the music changes: one segment per stretch of the chapter that
keeps a mood, not one per panel.

The scene analysis gives every panel a mood, and it flips constantly (chapter
1 of the test series: 123 panels, 60 mood runs, most of them one panel long),
so music placed per panel crossfaded every few seconds and sounded like a
radio being retuned. Here a segment is at least a scene: each scene takes its
most frequent mood (ties go to the stronger feeling), neighbouring scenes
that agree join up, and a scene too short to carry a change joins the one
before it.
"""

from __future__ import annotations

from collections import Counter

MIN_PANELS = 4  # a stretch shorter than this cannot start its own music
# ties between moods in a scene go to the one earlier in this list
STRENGTH = ("action", "tense", "mystery", "sad", "happy", "calm")


def _rank(mood: str) -> int:
    return STRENGTH.index(mood) if mood in STRENGTH else len(STRENGTH)


def _dominant(moods: list[str]) -> str:
    counts = Counter(moods)
    best = max(counts.values())
    return min((m for m, c in counts.items() if c == best), key=_rank)


def segments(
    panels: list[tuple[str, str, str | None]], min_panels: int = MIN_PANELS
) -> list[dict]:
    """[(panel id, mood, scene id or None), ...] in reading order ->
    [{"from_panel", "to_panel", "mood", "panels"}, ...].

    Panels without a scene id form scenes from runs of one mood, so the
    fallback (moods guessed from balloons) still gets the smoothing."""
    if not panels:
        return []
    # 1. scenes in reading order, each with its dominant mood
    scenes: list[dict] = []
    for n, (pid, mood, sid) in enumerate(panels):
        if sid is not None:
            key = sid
        elif (
            scenes
            and scenes[-1]["key"].startswith("run-")
            and scenes[-1]["moods"][-1] == mood
        ):
            key = scenes[-1]["key"]  # scene-less panels: a run of one mood is a scene
        else:
            key = f"run-{n}"
        if scenes and scenes[-1]["key"] == key:
            scenes[-1]["ids"].append(pid)
            scenes[-1]["moods"].append(mood)
        else:
            scenes.append({"key": key, "ids": [pid], "moods": [mood]})
    runs = [{"ids": s["ids"], "mood": _dominant(s["moods"])} for s in scenes]
    # 2. short stretches join the one before (the first joins the next)
    merged: list[dict] = []
    for r in runs:
        if merged and (len(r["ids"]) < min_panels or merged[-1]["mood"] == r["mood"]):
            merged[-1]["ids"] += r["ids"]
            continue
        merged.append({"ids": list(r["ids"]), "mood": r["mood"]})
    if len(merged) > 1 and len(merged[0]["ids"]) < min_panels:
        first = merged.pop(0)
        merged[0]["ids"] = first["ids"] + merged[0]["ids"]
    # 3. joining may have made neighbours agree
    out: list[dict] = []
    for r in merged:
        if out and out[-1]["mood"] == r["mood"]:
            out[-1]["ids"] += r["ids"]
        else:
            out.append({"ids": list(r["ids"]), "mood": r["mood"]})
    return [
        {
            "from_panel": r["ids"][0],
            "to_panel": r["ids"][-1],
            "mood": r["mood"],
            "panels": len(r["ids"]),
        }
        for r in out
    ]
