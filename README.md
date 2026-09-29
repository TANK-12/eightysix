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

- Lane A1 (foundation) in progress.
- 2026-09-30: A1 part 1 stopped. Tests 27 passed, 7 failed (causes and fixes listed in
  `~/Forge/sessions/juggernaut-alpha/results/A1.md`). Nothing has been looked at in a real window yet.

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
