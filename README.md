# Eighty Six (0.1 alpha)

date: 2026-09-29 · for: both (Emerson and every Claude session) · started by lane A1 (Sora, ejb-83)

A Juggernaut game built from scratch in Godot 4.7.2 with Jolt physics. You walk a Juggernaut over rocky ground
and fight basic Legion AI. The wave plan is `~/Forge/sessions/juggernaut-alpha/PLAN.md`, with Emerson's physics
and combat supplement beside it.

**How this file works (Emerson, 2026-09-29):** it is an append-only log. Sessions **add and update**; they never
rewrite or delete earlier text. Each session adds a dated entry to the log at the bottom saying what happened, what
changed and what is done, and marks every claim **verified** (with the check that was run) or **reasoned** (not run).
The "Current state" section may be updated in place, but only to keep it true; the history stays in the log.

## Current state
(Kept true by each session; the log below has the history.)

- Lane A1 (foundation) **done** 2026-09-30 (part 2). Next: lane A2 (locomotion) on the B1 export.
- Tests: `tools/run_tests.sh` 55 passed, 0 failed (headless, `--fixed-fps 120`); tool tests
  `python3 -m unittest discover -s tools/tests` 6 passed.
- Check runs: `tools/bot_run.sh smoke` plays menus, every settings page, loading, the range (walk, charge
  jump, run, skid), pause, off screen on the real GPU; screenshots in `images/NNN-smoke/`.
- Frame rates (`tools/fps_log.py`, 1080p, test range with the stand-in, off screen, uncapped, Iris Xe,
  no Blender job): Low 96.1 · Medium 54.1 · High 45.8 · Ultra 15.1 fps (targets 60 / 45 / 30 / none: all met).
  High was retuned from measured costs; logs in `logs/fps/`.
- Juggernaut export v2 synced into `assets/models/juggernaut/` (`tools/sync_models.py`); it loads and its
  contract test passes. The mech entry stays `planned` until A2 makes it walk.
- Linux export: `export_presets.cfg` and `tools/export.sh` ready; waits on Emerson's yes to the Godot export
  templates. Until then the hub's Play runs `godot --path ~/Games/eightysix`.

## Log

### 2026-09-29 · lane A1 · Sora (ejb-83) · started
- Created `~/Games/eightysix/` (empty Godot project folders, git repo, fonts). Nothing verified yet.

### 2026-09-30 · lane A1 · Sora (ejb-83) · part 1 stopped (Emerson asked for the handoff)
What happened: built the foundation's code and data; the first headless test run found 7 failures; stopped
before fixing them. Full handoff, file map and next steps: `~/Forge/sessions/juggernaut-alpha/results/A1.md`.

What changed:
- 14 registries in `data/` (mechs, parts with per-joint actuators, weapons, enemies, maps, graphics_presets,
  themes, input with a hidden hardcore scheme, settings, sounds, music, tuning, rumble, tips).
- Autoloads: Registry, Settings, Controls, UiTheme, Graphics, AudioMix, Rumble, Game, Bot.
- Menus drawn from data: main menu, settings (5 sections, 19 pages, key rebinding), pause, loading screen;
  two themes that switch live.
- A throwaway test range (rocky noise terrain with matching Jolt height-map collision, boulders, slabs) and a
  stand-in box walker: mass summed from its parts, one collider per part, leg hitboxes that follow two-bone
  IK legs, spring suspension, grip-capped drive, skid turn, hold-to-charge jump with no air control, body tilt
  to aim; chase camera with a simple cockpit view; test HUD.
- Own headless test runner with GUT-named asserts (`tools/run_tests.sh`), ten test files.

Verified: headless import clean; `tools/run_tests.sh` 27 passed, 7 failed (2026-09-29 21:18). What the 27
cover is listed in results/A1.md. The Forge hub tile `~/Forge/apps/eightysix` was built and tested by a
helper session (20/20 pytest, screenshot against fixtures).

Reasoned only (not run): everything visual in a real window, controller rumble, presets on real hardware,
frame rates. No screenshots, no fps log, no Linux export (templates not installed; waiting on Emerson).

### 2026-09-30 · lane A1 · Yuna (ejb-27) · part 2 done
What happened: fixed the 7 failures, built the check tools, looked at every screen, measured every preset,
synced B1's export. Handoff: `~/Forge/sessions/juggernaut-alpha/results/A1.md`.

What changed:
- Tests step at the game's own 1/120 s (`--fixed-fps 120`); the old `Engine.time_scale = 4` made each step
  1/30 s. Stand-in legs count as loaded only within their rest length plus `load_margin_m`, so a mech just off
  the ground cannot drive or steer. `Bot.frame_stats` 1% low is the average of the slowest 1% of frames.
- Off-screen bot runs: the desktop is GNOME, so `tools/bot_run.sh` starts a private headless `mutter`
  (virtual 1920x1080 monitor, own D-Bus, sound off) and the game draws on the real Iris Xe. Mailbox
  presentation (`MESA_VK_WSI_PRESENT_MODE=mailbox`) stops the game waiting on that compositor's vsync, which
  stalled about one run in three. A heartbeat file catches any stall: thread states go to `stall.txt` and the
  run is retried once. Bot scripts `tools/bot/smoke.json`, `fps_route.json`; step types in `tools/bot/README.md`.
- UI fixes found in the screenshots: the settings screen was 0x0 (code-built controls need
  `set_anchors_and_offsets_preset`), the pause menu and HUD ignored the theme (a CanvasLayer cuts theme
  inheritance; `UiTheme.adopt()` fixes it and follows theme switches), the main menu status line ran off
  screen, the help panel showed the previous page, pad labels were cut off, toggles now show On/Off in the
  value column, long labels trim instead of pushing their column.
- `tools/fps_log.py`: refuses while Blender renders; per preset it logs measured fps, 1% low, GPU and CPU ms
  per frame and an uncapped estimate to `logs/fps/`. The High preset lost SDFGI, SSR, deep fog and TAA
  (measured: 20, 3.8, 5.7 and 5.7 ms of GPU) and went from 15 to 45.8 fps; Ultra keeps them.
- `tools/sync_models.py` + `tools/model_sources.json` (one entry per model folder), `export_presets.cfg`,
  `tools/export.sh`, `tests/test_models.gd`. The hub tile judges a capped fps record by its estimate.

Verified: 55/55 game tests and 6/6 tool tests (2026-09-30); smoke runs with 29 screenshots each, looked at
(menus, all 20 settings pages, loading, range, HUD, pause); fps table above from `logs/fps/20260930-062852-*`;
v2 glb import clean and its contract test passes; hub 21/21 pytest.

Reasoned only: controller rumble and pad capture on a real DualSense; window modes on the real desktop; the
stall cause (the game waits in `drm_syncobj_array_wait_timeout` under FIFO; no GPU hang in the kernel log;
mailbox made 7 of 7 runs clean, not proof).
