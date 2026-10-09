# Lane A1 helper: the Eighty Six hub entry and the add-on list

date: 2026-09-29 · for: Claude (a helper session started by Sora, ejb-83, lane A1) · Emerson okayed splitting A1

Read `~/Forge/sessions/juggernaut-alpha/PLAN.md` (the A1 section and "How the sessions run") first. Emerson's rules
for this wave: strong base over speed; READMEs are append-only logs (add a dated entry, never rewrite or delete
earlier text; mark claims **verified** with the check, or **reasoned**); no subagents.

**You own:** `~/Forge/apps/eightysix/` (new) and `~/Forge/sessions/juggernaut-alpha/results/A1-hub.md` and
`results/A1-addons.md`. Claim them on the crew board `forge` at start
(`python3 ~/.claude/skills/crew/crew.py claim forge <your id> <paths>`). **Do not edit anything in
`~/Games/eightysix/`**: Sora is building the game there; you only read it. Do not touch other Forge apps.
Follow the `forge-session` and `verify` skills (black, pyright against the app's own venv, pytest, a headless
Chrome screenshot of the page).

## Job 1: the hub entry (apps/eightysix)
A Forge app like the others (`forge_app.json` + FastAPI `web_app:app` + `static/` + its own `.venv` with fastapi,
uvicorn, httpx, pytest). Port **8464**, section `play`, order 7, label "Eighty Six", tagline along the lines of
"Juggernaut walker game (Godot)", icon and accent your choice (dark, cold cyan fits the game's first theme
`#8fe3ff` on `#05080c`). Look at `apps/relay` or `apps/arcade` for the manifest shape. Game root comes from
env `EIGHTYSIX_ROOT`, default `~/Games/eightysix` (tests point it at a temp folder).

The page (one screen, looks good, no ALL-CAPS copy):
- **Play**: if `<root>/build/linux/eightysix.x86_64` exists and is executable, run it; otherwise run
  `godot --path <root>`. **Open in Godot editor**: `godot -e --path <root>`. Both detached
  (`start_new_session=True`), output to `~/Forge/outputs/eightysix-launch.log`. Say which one ran.
- **Tests**: show `<root>/logs/tests-last.json` (shape below). A "Run tests" button runs
  `<root>/tools/run_tests.sh` in the background (it may not exist yet: then say so, don't fail) and refreshes.
- **Frame rates**: the newest `<root>/logs/fps/*.json` per preset (low, medium, high, ultra) in a table with the
  target and whether it was met. Empty state when there are none.
- **Check images**: `<root>/images/NNN-name/*.png`: the newest folder's images as thumbnails (click to enlarge),
  a picker for older folders. Serve images through an endpoint locked to `<root>/images` (no path escape).
- **README**: the "Current state" section of `<root>/README.md` and its newest log entry, as plain text.

File contracts (Sora writes these from the game; code against them now, with fixtures in tests):
- `logs/tests-last.json`: `{"when": "2026-09-29T21:30:00", "passed": 12, "failed": 0, "seconds": 3.1,
  "tests": [{"name": "test_registry.gd:test_all_load", "ok": true, "message": ""}]}`
- `logs/fps/<stamp>-<preset>.json`: `{"when": "...", "map": "test_range", "preset": "medium",
  "target_fps": 45, "avg_fps": 51.2, "p1_low_fps": 38.0, "min_fps": 30.5, "frame_ms_avg": 19.5,
  "seconds": 20.0, "resolution": [1920, 1080], "render_scale": 0.8, "gpu": "Intel(R) Iris(R) Xe Graphics",
  "blender_running": false}` (`target_fps` may be null for ultra: show "no target").
- Check images: `images/<3-digit number>-<name>/<anything>.png`, plus an optional `report.json` in the folder.

Verify: pytest (fixtures for every contract, missing files, path-escape attempt on the image endpoint, play
command choice with and without a build), black, pyright with `--pythonpath ./.venv/bin/python`, and a headless
Chrome screenshot of the page with fixture data (look at it). Do **not** restart Forge; say in your handoff that
the hub picks the new app up on its next start. Write `apps/eightysix/README.md` (what, how, verified list,
append-only log).

## Job 2: the add-on list (results/A1-addons.md)
For Emerson to pick from (install nothing into the game). Candidates are already on this laptop in
`~/Forge/shared/godot_addons/` (see each folder's plugin.cfg and any FORGE-PATCH.md) plus anything clearly useful
you find for this game: terrain (Terrain3D by TokisanGames), tests (GUT by bitwes), and whatever fits procedural
animation, IK, AI, debug drawing, sky and weather, scattering. For each: upstream repo URL, licence, version on
this laptop against the newest release (check the real repo), last release date, whether it supports Godot 4.7,
what it would do for Eighty Six, and a recommendation (yes / later / no). Skip anything you cannot trace to a
named, maintained source.

## When done
Append a dated entry to `results/A1-hub.md` (what, verified checks, file paths, what is next), post on the board
to ejb-83 "hub entry ready", release your claims, and stop. If you pass 97% of the hey account's 5-hour meter
(`CLAUDE_CONFIG_DIR=~/.local/share/forge/claude/profiles/hey python3 ~/.claude/tools/usage.py`), write the handoff
and stop.
