#!/usr/bin/env python3
"""Scoreboard for the Eighty Six wave: one row per session, same bot runs every time.

Runs the look half (tools/bot/score_look.json) on Low, Medium and High, and the movement half
(tools/bot/score_move.json, from track A, writing logs/score_move.json) when it exists, then appends one row to the scoreboard doc
in ~/Forge/docs/library/juggernaut/. Never measure while a Blender job runs; this refuses to.

Usage: tools/scoreboard.py --who "B4 part 1 (Tetsu)" [--note "what changed"] [--dry]
"""

import argparse
import datetime
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOC = (
    pathlib.Path.home()
    / "Forge/docs/library/juggernaut/2026-10-01-eightysix-scoreboard.md"
)
PRESETS = ["low", "medium", "high"]
MOVE_LOG = (
    ROOT / "logs/score_move.json"
)  # flat keys, written by track A's score_move bot run
MOVE_KEYS = [
    ("top_speed_kmh", "top km/h"),
    ("t0_50_s", "0-50 km/h s"),
    ("slide_m", "slide m"),
    ("slide_turn_deg", "slide turn deg"),
    ("stuck_events", "stuck"),
    ("belly_scrapes_flat", "belly scrapes (flat)"),
    ("air_turn_deg_s", "air turn deg/s"),
    ("recoil_dv_m_s", "recoil dv m/s"),
]

HEADER = """# Eighty Six scoreboard

date: 2026-10-01 · for: both · started by lane B4 (Tetsu)

One row per session, from the same bot runs every time (PLAN.md 'Raising the bar'): `tools/scoreboard.py`.
Look half: `tools/bot/score_look.json` on Ashen valley, per preset: fps at the start viewpoint standing
("view") and walking toward the town ("walk"), 1920x1080, no Blender job running. Its six fixed shots are in
the folder named in the last column. Movement half: `tools/bot/score_move.json` (track A) writes `logs/score_move.json`; "-" until it exists.
No session makes a number worse without saying why in its results. Readings on this laptop swing by up to
about 10 % between identical runs, and any other Godot running (even headless tests) cuts them by a third or more,
so the script refuses to run then.

| Date | Session | Low view / walk | Medium view / walk | High view / walk | {move} | Shots | Note |
|---|---|---|---|---|{move_sep}---|---|
"""


def blender_busy() -> bool:
    return (
        subprocess.run(["pgrep", "-f", "[b]lender -b"], capture_output=True).returncode
        == 0
    )


def godot_busy() -> bool:
    """Another Godot running (a second bot run) cut the iGPU frame rate by a third or more here (lane B4, images/137 and 140)."""
    return subprocess.run(["pgrep", "-x", "godot"], capture_output=True).returncode == 0


def run_bot(script: str, preset: str) -> pathlib.Path:
    out = subprocess.run(
        [
            str(ROOT / "tools/bot_run.sh"),
            script,
            f"--preset={preset}",
            f"--name={script}-{preset}",
        ],
        capture_output=True,
        text=True,
    )
    folder = pathlib.Path(out.stdout.strip().splitlines()[-1])
    if not (folder / "report.json").exists():
        sys.exit(f"scoreboard: {script} on {preset} left no report ({folder})")
    return folder


def measures(folder: pathlib.Path) -> dict:
    report = json.loads((folder / "report.json").read_text())
    return {m["label"]: m for m in report.get("measures", [])}


def look_cell(folder: pathlib.Path) -> str:
    m = measures(folder)
    return " / ".join(
        f"{m[k]['avg_fps']:.1f}" if k in m else "-" for k in ("view", "walk")
    )


def move_cells(ran: bool) -> list[str]:
    if not ran or not MOVE_LOG.exists():
        return ["-"] * len(MOVE_KEYS)
    score = json.loads(MOVE_LOG.read_text())
    return [str(score.get(k, "-")) for k, _ in MOVE_KEYS]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--who", required=True)
    ap.add_argument("--note", default="")
    ap.add_argument(
        "--dry", action="store_true", help="print the row, do not write the doc"
    )
    args = ap.parse_args()
    if blender_busy():
        sys.exit("scoreboard: a Blender job is running; frame rates would be wrong")
    if godot_busy():
        sys.exit(
            "scoreboard: another Godot is running (tests or a bot run); frame rates would be wrong"
        )
    cells = []
    shots = ""
    for preset in PRESETS:
        folder = run_bot("score_look", preset)
        cells.append(look_cell(folder))
        if preset == "medium":
            shots = f"images/{folder.name}"
    ran_move = False
    if (ROOT / "tools/bot/score_move.json").exists():
        MOVE_LOG.unlink(missing_ok=True)
        run_bot("score_move", "medium")
        ran_move = True
    row = [
        datetime.date.today().isoformat(),
        args.who,
        *cells,
        *move_cells(ran_move),
        shots,
        args.note,
    ]
    line = "| " + " | ".join(row) + " |"
    print(line)
    if args.dry:
        return
    if not DOC.exists():
        move = " | ".join(label for _, label in MOVE_KEYS)
        DOC.write_text(HEADER.format(move=move, move_sep="---|" * len(MOVE_KEYS)))
    with DOC.open("a") as f:
        f.write(line + "\n")


if __name__ == "__main__":
    main()
