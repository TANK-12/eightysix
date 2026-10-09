# Eighty Six (Forge hub tile)

date: 2026-09-29 · for: both (Emerson and every Claude session) · written by the lane A1 helper
(Rin, via Relay, started by Sora/ejb-83)

**How this file works:** append-only log. Sessions add a dated entry at the bottom; the
"Current state" section is kept true but the history stays. Claims are marked **verified**
(with the check that was run) or **reasoned**.

## What this is

A Forge app (`apps/eightysix/`) that is the hub tile for **Eighty Six**, the from-scratch
Godot 4.7 Juggernaut walker game lane A1 is building in the separate `~/Games/eightysix`
repo (see `~/Forge/sessions/juggernaut-alpha/PLAN.md`). This app owns no game logic — it
reads the game's file contracts (test results, per-preset fps logs, check images, the
README) and can launch the game or its editor, the same shape as every other Forge app:
its own `.venv`, its own `forge_app.json`, a FastAPI backend, a static frontend.

Port **8464**, section `play`, order 7. Game root comes from env `EIGHTYSIX_ROOT`,
default `~/Games/eightysix`.

## How it works

- `GET /api/status` — the resolved game root and whether it exists yet.
- `GET /api/tests` — `<root>/logs/tests-last.json` verbatim (plus `"available"` and `"running"`); `{"available": false, "running": ...}` if the file is not there yet.
- `POST /api/tests/run` — runs `<root>/tools/run_tests.sh` detached, logged to `outputs/eightysix-launch.log`; returns `{"started": false, "reason": ...}` instead of failing if the script does not exist yet or a run is already going.
- `GET /api/fps` — the newest record per preset (low/medium/high/ultra) from `<root>/logs/fps/*.json`, each tagged `met_target` (`true`/`false`/`null` when there is no target, i.e. ultra).
- `GET /api/images` — the check-image folders under `<root>/images/`, newest first by the `NNN-` numeric prefix.
- `GET /api/images/{folder}` — the `.png` files in that folder plus its `report.json` if present.
- `GET /api/images/{folder}/{file}` — serves one image, locked to `<root>/images` (rejects any path-escape attempt, `.png` only).
- `GET /api/readme` — `<root>/README.md`'s "Current state" section and its newest `### `-headed log entry (the file's last one), as plain text.
- `POST /api/play` — runs `<root>/build/linux/eightysix.x86_64` if it exists and is executable, otherwise `godot --path <root>`; says which one ran.
- `POST /api/play/editor` — runs `godot -e --path <root>`.

All launches are detached (`start_new_session=True`), logged to `~/Forge/outputs/eightysix-launch.log`.

Standalone: `cd ~/Forge/apps/eightysix && FORGE_SHARED_DIR=~/Forge/shared .venv/bin/python -m uvicorn web_app:app --host 127.0.0.1 --port 8464`

## Verified

- **20/20 pytest pass** (`.venv/bin/python -m pytest tests/ -q`, 2026-09-29): every
  file contract shape (tests-last.json, fps/*.json for a normal and a null-target
  preset, images/report.json), the missing-file case for each endpoint, a path-escape
  attempt on the image endpoint (both the URL-normalised and the percent-encoded
  form, plus a direct unit test of the guard function), and the play/editor command
  choice with and without a build present (subprocess.Popen mocked, real calls never
  made in tests).
- **black** run on `web_app.py`, `tests/conftest.py`, `tests/test_web_app.py` — reformatted two of the three, no further diffs on a second run.
- **pyright --pythonpath ./.venv/bin/python** on the same three files — 0 errors, 0 warnings.
- **Headless Chrome screenshot** (Flatpak Chrome, `--headless=new`, 2026-09-29) of the
  page served against a hand-built fixture `EIGHTYSIX_ROOT` (a passing-and-failing test
  entry, three fps presets including a null-target ultra, two check-image folders with
  a `report.json`, a two-entry README): every panel rendered — tests summary and list,
  fps table with met/missed colouring, image thumbnails with a folder picker, README
  current-state and newest-log-entry text. No white-on-white or missing-token issues.
  No headless Chrome process was left running afterward (`pgrep -fc -- --headless=new`
  checked clean; the one hit during the check was the grep command's own argv, not a
  live process). The server process and its port (8464) were also confirmed stopped
  afterward, and the scratch fixture directory removed.
- Server log during the screenshot check showed only 200s (one harmless 404 for
  `/favicon.ico`, which the page does not reference).

## Reasoned, not run

- A real launch of `godot --path`, `godot -e --path` or a real Linux build binary —
  only the command-selection logic was exercised (Popen mocked); no game window was
  actually opened during this check.
- The real game's file contracts, once lane A1 writes them — this app is coded and
  tested against fixtures matching the shapes documented in
  `sessions/juggernaut-alpha/A1-helper-hub.md`, not against live output yet.
- Picking the app up inside a running Forge window — Forge was **not** restarted for
  this check, per instructions; the hub picks up a new `apps/` entry on its next start.

## Log

### 2026-09-29 · lane A1 helper (Rin, via Relay) · hub entry built
- Created `apps/eightysix/` (own `.venv` with fastapi/uvicorn/httpx/pytest,
  `forge_app.json` on port 8464, `web_app.py`, `static/index.html`, `tests/`).
- Coded the five game-state panels (tests, frame rates, check images, README) and two
  launch actions (play, editor) against the file contracts in `A1-helper-hub.md`.
- Verified as listed above. Did not touch `~/Games/eightysix/` (read-only) or any
  other Forge app. Did not restart Forge.

### 2026-09-30 · lane A1 part 2 · Yuna (ejb-27)
- Checked against the game's real output for the first time: tests-last.json (55 passed), four fps logs,
  25 check-image folders, the README state. **Verified**: `/api/fps`, `/api/tests`, `/api/images` answered with
  the real files, and a headless-Chrome screenshot of the page on a spare port (18464) showed them.
- `/api/fps` now also returns `met_by` ("measured" or "estimate"): a record whose `vsync_cap_hz` sits at or
  near its target is judged by `est_uncapped_fps`, because a capped average cannot pass the cap. The table
  gained a 1% low column; the "Est. uncapped" column and a note appear only when some record is capped
  (since mailbox presentation, off-screen runs are not). New test `test_fps_capped_record_is_judged_by_its_estimate`;
  pytest 21/21, black and pyright clean.

### 2026-09-30 · Kaito (ejb-89/ejb-4f) · Play through the game's launcher, Versions panel, share zips
- `POST /api/play` now runs the game's `tools/play.sh` (always up to date: rebuilds when the source changed,
  saves each changed build as a numbered version); `{"version": "N"}` plays a saved version (validated: a
  number, `latest` or `previous`). The old build / `godot --path` fallbacks stay for a game without the launcher.
- `GET /api/versions` reads `build/versions/NNN-*/VERSION.json` and each version's `share/*.zip`;
  `POST /api/share` starts `tools/builds.py share` (Windows, Linux, macOS zips) in the background.
- Page: a Versions card (one row per version with its Play button and share zip names) and a "Make share zips"
  button. `postJSON` can now send a JSON body.
- **Verified:** pytest 25 passed (4 new), black + pyright clean; headless-Chrome screenshot on port 18465
  against the real game folder showed versions 002 and 001 with their zips. Not checked: the page inside the
  running Forge window (Forge not restarted); the Play button clicked in a real browser (tests mock Popen, and
  the same `play.sh` was run from the desktop launcher instead).
