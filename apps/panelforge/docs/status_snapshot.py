"""Rewrites docs/STATUS.md every few minutes while the crew works. Uses no AI tokens.

Copies the crew board, each helper's own log, and a file inventory per area
into one file, so a fresh session (even on another Claude account) can see
exactly how far the build got. Stops by itself when every crew task is done,
or after 14 hours.

    setsid -f .venv/bin/python docs/status_snapshot.py
"""

import os
import subprocess
import time
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
OUT = APP / "docs" / "STATUS.md"
CREW = ["/usr/bin/python3", str(Path.home() / ".claude/skills/crew/crew.py")]
AREAS = {
    "library (helper-1)": ["panelforge/library", "panelforge/sources", "panelforge/api/library.py"],
    "detect (helper-2)": ["panelforge/detect", "panelforge/api/detect.py"],
    "scene (helper-3)": ["panelforge/scene", "panelforge/api/scene.py"],
    "audio (helper-4)": ["panelforge/audio", "panelforge/sfx", "panelforge/music", "panelforge/api/audio.py"],
    "render (helper-5)": ["panelforge/render", "panelforge/styles", "panelforge/camera", "panelforge/transitions", "panelforge/api/render.py"],
    "ui (helper-6)": ["static"],
}
INTERVAL = 180
LIMIT = 14 * 3600


def files(rel: str) -> list[str]:
    p = APP / rel
    if p.is_file():
        return [rel]
    if not p.is_dir():
        return []
    return sorted(
        str(f.relative_to(APP))
        for f in p.rglob("*")
        if f.is_file() and "__pycache__" not in f.parts
    )


def snapshot() -> bool:
    board = subprocess.run(
        CREW + ["status", "panelforge"], capture_output=True, text=True
    ).stdout
    tasks = board.split("claims:")[0]
    parts = [
        "# PanelForge live status",
        "",
        f"Written automatically by `docs/status_snapshot.py` at "
        f"{time.strftime('%Y-%m-%d %H:%M:%S')}. Read `HANDOFF.md` first; this "
        "file only says how far the build got.",
        "",
        "## Crew board",
        "",
        "```",
        tasks.strip(),
        "```",
        "",
        "## Files per area",
        "",
    ]
    for area, rels in AREAS.items():
        fs = [f for r in rels for f in files(r)]
        lines = 0
        for f in fs:
            try:
                lines += sum(1 for _ in open(APP / f, errors="ignore"))
            except OSError:
                pass
        parts.append(f"- **{area}**: {len(fs)} files, {lines} lines")
    tests = sorted(p.name for p in (APP / "tests").glob("test_*.py"))
    parts += ["", f"Tests present: {', '.join(tests) or 'none'}", ""]
    parts += ["## Helper logs (copied verbatim)", ""]
    for n in range(1, 7):
        log = APP / "docs" / "crew" / f"helper-{n}.md"
        parts.append(f"### helper-{n}")
        parts.append(log.read_text(errors="ignore").strip() if log.exists() else "_no log yet_")
        parts.append("")
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text("\n".join(parts) + "\n")
    os.replace(tmp, OUT)
    open_tasks = [l for l in tasks.splitlines() if l.strip()[:1].isdigit() and " done " not in l]
    return not open_tasks


if __name__ == "__main__":
    start = time.time()
    while time.time() - start < LIMIT:
        if snapshot():
            break
        time.sleep(INTERVAL)
