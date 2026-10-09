"""Apply the model's stored page reading again without asking the model.

    .venv/bin/python tools/replay_llm.py <series> [chapters...]

Every line keeps the model's answer in `llm` (speaker, expression, intensity,
why). When the rules that decide which answers to take change (2026-09-19: a
caption box over a drawn character may become that character's thought), this
replays those answers through `llm_pass.apply` and prints the lines whose
speaker changed; hand-edited lines are left alone. Changed lines need
speaking again (the Lines editor's "Speak changed lines", or the chapter
voice job).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from panelforge import paths, store  # noqa: E402
from panelforge.audio import llm_pass  # noqa: E402


def replay(chapter_dir: Path) -> list[tuple[str, str | None, str | None]]:
    script = store.read(chapter_dir / "script.json", None)
    bubbles = store.read(chapter_dir / "bubbles.json", None)
    scene = store.read(chapter_dir / "scene.json", None)
    if not script or not bubbles:
        return []
    before = {ln["id"]: ln.get("speaker") for ln in script["lines"]}
    gathered = llm_pass.gather(script, bubbles, scene)
    answers = {}
    for g in gathered:
        ln = next(l for l in script["lines"] if l["id"] == g["id"])
        rec = ln.get("llm") or {}
        if rec.get("model") and rec.get("speaker"):
            answers[str(g["n"])] = {
                k: rec[k]
                for k in ("speaker", "expression", "intensity", "why")
                if k in rec
            }
    llm_pass.apply(script, gathered, answers)
    changed = [
        (ln["id"], before[ln["id"]], ln.get("speaker"))
        for ln in script["lines"]
        if ln.get("speaker") != before[ln["id"]]
    ]
    for ln in script["lines"]:
        if ln.get("speaker") != before[ln["id"]]:
            ln["audio"], ln["dur"] = None, None  # spoken by someone else now
    if changed:
        store.write(chapter_dir / "script.json", script)
    return changed


def main() -> None:
    series = sys.argv[1]
    chapters = sys.argv[2:] or sorted(
        p.name for p in (paths.series_dir(series) / "chapters").iterdir()
    )
    for c in chapters:
        changed = replay(paths.chapter_dir(series, c))
        print(f"{c}: {len(changed)} speaker(s) changed")
        for lid, a, b in changed:
            print(f"  {lid}: {a} -> {b}")


if __name__ == "__main__":
    main()
