# Lane A1 helper: hub entry + add-on list — results

date: 2026-09-29 · for: both · lane A1 helper (Rin, via Relay, started by Sora/ejb-83), per
`sessions/juggernaut-alpha/A1-helper-hub.md`

### 2026-09-29 · started, both jobs done

**Job 1 — the hub entry (`~/Forge/apps/eightysix/`)**

- Built as a normal Forge app: own `.venv` (fastapi, uvicorn, httpx, pytest), `forge_app.json`
  (port 8464, section `play`, order 7, accent `#8fe3ff`), `web_app.py`, `static/index.html`, `tests/`.
- Reads `EIGHTYSIX_ROOT` (default `~/Games/eightysix`) for: `logs/tests-last.json`,
  `logs/fps/*.json` per preset, `images/NNN-name/*.png` (+ optional `report.json`), and
  `README.md`'s "Current state" + newest log entry. Launches `POST /api/play` (build if present
  and executable, else `godot --path`) and `POST /api/play/editor` (`godot -e --path`), both
  detached and logged to `outputs/eightysix-launch.log`. Image serving is locked to
  `<root>/images` with a path-escape guard.
- **Verified:** 20/20 pytest (`.venv/bin/python -m pytest tests/ -q`) covering every file
  contract, every missing-file case, the path-escape guard (both a URL-normalised and a
  percent-encoded attempt, plus a direct unit test), and the play/build/editor command choice
  with Popen mocked. `black` run (reformatted 2 of 3 files, clean second pass). `pyright
  --pythonpath ./.venv/bin/python` on all three files: 0 errors. Headless Chrome screenshot
  (Flatpak, `--headless=new`) against a hand-built fixture root — every panel rendered
  correctly (tests summary+list, fps table with met/missed colouring, image thumbnails +
  folder picker, README text); no white-on-white; no leaked headless Chrome process afterward
  (checked with `pgrep -fc -- --headless=new`); server and port 8464 confirmed stopped; scratch
  fixture directory removed. Full detail and the "reasoned, not run" list are in
  `apps/eightysix/README.md`.
- **Not done / left for later:** the real game hasn't written its own
  `logs/tests-last.json`/`fps/*.json`/`images/` yet, so this app is only checked against
  fixtures matching the documented shapes — it should be glanced at again once Sora's game is
  actually producing those files. Forge was **not** restarted (per instructions); the hub
  picks up the new `apps/` entry on its next start.
- Did not touch `~/Games/eightysix/` (read-only, as instructed) or any other Forge app.

**Job 2 — the add-on list (`results/A1-addons.md`)**

- Checked all 12 folders already in `~/Forge/shared/godot_addons/` against their `plugin.cfg`
  / `.gdextension` (local version) and the real upstream GitHub repo (license, newest
  release/tag, last push, open issues) as of 2026-09-29.
- **Recommended now:** Terrain3D, GUT (but grab v9.7.1, not the 9.6.1 sitting here — 9.6.x
  targets Godot 4.6 and 9.7.x specifically fixes a Godot 4.7 return-type strictness issue),
  LimboAI, Phantom Camera (its own singleton-registration bug against Godot 4.7.1 was filed
  against this exact version and closed 2026-07-24 — worth a smoke test on install), Debug
  Draw 3D, Sky3D.
- **Later:** ProtonScatter (an **open** "not compatible with 4.7" issue as of 2026-09-18 — the
  local copy's declared version 4.2.0 doesn't even match any GitHub tag, likely pulled from
  the Codeberg mirror instead), Road Generator, Cyclops Level Builder.
- **No / not a fit:** Dialogic (nothing in PLAN.md needs branching dialogue), Godot-MToon-Shader
  and VRM (no VRM avatars in this game). VRM's `plugin.cfg` (2.0.1) and its own
  `FORGE-PATCH.md` (which describes patching "v2.1.0") disagree with each other — flagged as-is,
  not resolved, since neither this app nor lane A1 uses VRM.
- Godot 4.6+ restored built-in IK (FABRIK/CCDIK/two-bone/spline on `SkeletonModifier3D`), already
  present in the 4.7.2 install here, so no third-party IK/procedural-animation addon is needed
  for A2's foot placement; the one candidate found (`BobMervell/Procedural-Animation`) has no
  active maintainer and was left off the list on that basis.
- Nothing installed anywhere; this is a reasoning document for Emerson to pick from.

**Status:** both jobs done and verified as above. Releasing claims on `apps/eightysix`,
`results/A1-hub.md`, `results/A1-addons.md`.
