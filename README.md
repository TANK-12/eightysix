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

- Lane A1 (foundation) **done** 2026-09-30 (part 2). Lane A2 (locomotion) part 1 **in progress**: the real
  Juggernaut walks on the test range; gait tuning against the anime reference and the fps/10-minute checks
  are next (part 2).
- Tests: `tools/run_tests.sh` 60 passed, 0 failed (headless, `--fixed-fps 120`); tool tests
  `python3 -m unittest discover -s tools/tests` 6 passed.
- Check runs: `tools/bot_run.sh smoke` plays menus, every settings page, loading, the range (walk, charge
  jump, run, skid), pause, off screen on the real GPU; screenshots in `images/NNN-smoke/`.
  `tools/bot_run.sh jg_check` is the new one: the real Juggernaut standing then walking, `images/026-jg_check/`.
- Frame rates (`tools/fps_log.py`, 1080p, test range with the stand-in, off screen, uncapped, Iris Xe,
  no Blender job): Low 96.1 · Medium 54.1 · High 45.8 · Ultra 15.1 fps (targets 60 / 45 / 30 / none: all met).
  High was retuned from measured costs; logs in `logs/fps/`. **Not yet re-measured with the real Juggernaut
  mesh in place of the stand-in** (lane A2 part 2).
- Juggernaut export v3 synced into `assets/models/juggernaut/` (`tools/sync_models.py`); it loads and its
  contract test passes. `mechs.json` `juggernaut_m2` status is now **ready**: `tools/build_juggernaut_data.py`
  generated its real parts/legs/stance/actuators from the export, and `scripts/mech/juggernaut_mech.gd` (lane
  A1's gait/physics, the real skinned mesh on top) builds and walks it. The test range now spawns the real
  Juggernaut, not the stand-in.
- Linux export **works** (2026-09-30): the official Godot 4.7.2 export templates are installed (Linux x86_64
  only, `~/.local/share/godot/export_templates/4.7.2.stable/`). `tools/export.sh` builds
  `build/linux/eightysix.x86_64` + `eightysix.pck` in about 3 s; `tools/bot_run.sh smoke --build` plays the
  smoke run on that build off screen. `build/` is git-ignored, so re-export after changes. The hub's Play still
  runs `godot --path ~/Games/eightysix`.

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

### 2026-09-30 · lane A2 · Hina (relay-6-work) · part 1
What happened: read B1's export v3 (note #404, landed mid-session), built the real Juggernaut into the game
data and gait, and got it standing and walking on the test range with its own skinned mesh. Full handoff:
`~/Forge/sessions/juggernaut-alpha/results/A2.md`.

What changed:
- `tools/build_juggernaut_data.py`: generates `data/parts.json` (72 entries: thigh/shin/foot per leg, the 39
  other real parts as fixed chassis pieces, 17 actuators) and `data/mechs.json`'s `juggernaut_m2` (parts,
  legs, stance, cameras, sockets) straight from `assets/models/juggernaut/juggernaut_mk2.json`'s real joints,
  hulls and masses; re-run it after every `tools/sync_models.py juggernaut`. The RigidBody3D's local origin is
  the model's "body" bone (chest height), matching the stand-in's convention (hips sit below it).
- `scripts/mech/juggernaut_mech.gd`: extends `standin_mech.gd` (same springs, drive, turn, skid, charge jump,
  two-bone leg IK), so the walk uses the stand-in's already-tested physics with the real hip positions, leg
  lengths, mass and centre of mass instead of placeholders. Only the visual changes: the four legs' real
  thigh/shin/foot meshes are detached from the glb's skeleton (never re-posed; a `set_bone_global_pose_override`
  approach was considered and dropped for time) and driven by the same transform the stand-in already computes
  for its invisible box legs, plus a fixed rest-pose offset. The chassis, gun and sub-arms are locked to the
  body (no traverse) so they need no extra code, just the auto-generated placeholder box meshes hidden.
- `scripts/mech/standin_mech.gd`: the leg-step swing time and lift height were hardcoded consts; they now read
  `tuning.json`'s new `"step"` block (default unchanged) so a subclass can retune them. `data/tuning.json`
  `"juggernaut"` block overrides `step.swing_s`/`lift_m` from `~/Models/juggernaut/refs/anime-motion/ANALYSIS.md`
  (0.5 s step cycle, duty about 0.62 walking, knee lifting well above the hull); drive speed, run duty, the
  skid's outward brace and the jump's leg-stretch pose are not tuned yet (part 2). Also added `"ankle"` and
  `"gun_elevation"` to `tuning.json`'s shared `"motors"` block (real actuators reference these by joint kind,
  same as the stand-in's).
- `data/parts.json` actuator entries carry B1's real `static_torque_nm`, `game_motor_figures` (the real max
  torque/speed, for lane B6) and `bench` figures; a linear-equivalent view (`peak_force_n`, `no_load_speed_m_s`,
  `stroke_m`, `lever_arm_m`) is added for the existing charge-jump maths, which only knows linear rams --
  **reasoned, not measured**, for the rotary hip/ankle joints; lane B6 replaces it with real rotary bench
  physics. Actuator `mass_kg` is 0 (their real mass is already the coxa/thigh/shin/ram_cyl/ram_rod hull parts;
  counting it again would double the total).
- `scripts/world/test_range.gd`: `MECH_ID` is now `juggernaut_m2`, not `standin`.
- `tests/test_juggernaut.gd` (new): the export status flips to `ready`; mass matches the export's
  `total_mass_kg` exactly (12,254.5 kg, no part dropped or doubled); the real meshes replace the hidden boxes;
  it stands at 4/4 legs, walks forward without falling or tipping over, and a planted, non-stepping foot does
  not slip. `tests/test_mech.gd`'s `test_planned_mechs_are_not_built` flips to expect `juggernaut_m2` buildable.

Verified: `tools/run_tests.sh` 60 passed, 0 failed (2026-09-30); the mass check in
`tools/build_juggernaut_data.py`'s own output matches the export's `total_mass_kg` to the kg;
`tools/bot_run.sh jg_check` (`images/026-jg_check/`, 0 errors): the real Juggernaut stands on 4/4 legs then
walks at 23 km/h with its legs visibly moving (not frozen at the bind pose); black and pyright clean on
`tools/build_juggernaut_data.py`.

Only reasoned (not measured or tuned): the rest stance comes straight from the export's own bind pose, which
is quite crouched (hip only about 0.93 m off the ground) and the screenshot shows the legs a little more
splayed than the anime reference's tighter stance -- ANALYSIS.md's run duty, low wide-splay body, skid brace
and jump leg-stretch pose are not built yet; fps has not been re-measured with the real mesh (498k/130k
triangles, much heavier than the stand-in's boxes); the sole sockets, gun/subarm sockets and cockpit camera
sit in the glb's bind pose and are not read by any code yet; the 10-minute no-fall bot soak from
`results/A1.md` "For lane A2" is not run (only a short walk, `tests/test_juggernaut.gd` and `jg_check`).
Leg collision boxes are sized from each part's hull bounding box in its own segment frame, shrunk 30% for the
diagonal-in-box effect -- a reasoned approximation, not the split convex hulls B1 exported. All lane A2 part 2
work.

### 2026-09-30 · Kaito (ejb-89) · first Linux build
What happened: Emerson said yes to the export templates (question 6 in `results/A1.md`); Hotaru (ejb-54) wrote
the steps and stopped before downloading. This session did them.

Changed:
- Installed `Godot_v4.7.2-stable_export_templates.tpz` from the godotengine/godot GitHub release (1,281,349,702
  bytes; SHA-512 matches both the release's `SHA512-SUMS.txt` and the brief). Kept only
  `linux_release.x86_64`, `linux_debug.x86_64` and `version.txt` (141 MB) in
  `~/.local/share/godot/export_templates/4.7.2.stable/`; the 1.28 GB download was deleted.
- `tools/bot_run.sh --build`: plays a bot script on the exported game instead of the project folder (no
  `--path`, the script is handed over as a file path because the pack leaves out `tools/`; exits 2 if there is no
  build). Documented in `tools/bot/README.md`.

Verified:
- `tools/export.sh` exit 0 in 3 s: `eightysix.x86_64` 73,519,416 bytes + `eightysix.pck` 23,116,276 bytes.
- The pack holds all 14 `data/*.json` and `assets/models/juggernaut/juggernaut_mk2.json` (paths read from the
  pack); `tests/`, `tools/`, `images/`, `logs/` are left out.
- `build/linux/eightysix.x86_64 --headless --quit-after 600`: exit 0, no errors.
- `tools/bot_run.sh smoke --build --name=build_smoke`: exit 0, 29 screenshots, 0 errors, Iris Xe
  (`images/066-build_smoke/`). `godot.log` starts `Godot Engine v4.7.2.stable.official`, so the template ran,
  not the system Godot. Looked at: main menu, settings (graphics quality), the range with the real Juggernaut
  walking at 23 km/h, pause; all render as in the source runs.

Not checked: the build in a window on the real desktop (only off screen), the debug template
(`tools/export.sh --debug`), and fps of the build. The build is the tree as of 16:25, from before Hayato's
(ejb-0a) A2 part 4 changes (B1 v5 sync and more). It is stale once those land: re-run `tools/export.sh` and
`tools/bot_run.sh smoke --build`.
