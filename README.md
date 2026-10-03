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

- Lane A1 (foundation) **done** 2026-09-30 (part 2). Lane A2 (locomotion) **done** 2026-09-30 (parts 1-4). Lane A3
  (combat, grapple, climbing, damage) part 1 **done** 2026-09-30: see `~/Forge/sessions/juggernaut-alpha/results/A3.md`.
- Tests: `tools/run_tests.sh` 396 passed, 0 failed (2026-10-03, version 014). Before: 265 passed, 0 failed (2026-10-02, end of A4 part 5 (Kaede, relay-16); a few minutes earlier 259 passed, 1 failed: `test_scripts` on another session's unfinished `big_map.gd`). Before: 229 passed, 0 failed (2026-10-02, A4 part 4 (Tetsu/Ren, ejb-3e), with B5's big map tests in the tree). Before: 205 passed, 0 failed (2026-10-01, end of A4 part 3 (Ami/Tetsu, ejb-a4)). Before: 194 passed, 0 failed (A4 part 3, the two flaky AI tests fixed, see the log). Before: 191 passed, 1 failed (2026-10-01, A4 part 2 (Kenji): the 1 was a Löwe first-round test made honest by ranging, rewritten after and passing 3 of 3 alone; full rerun left for the version save). Before: 190 passed, 1 failed (2026-10-01, end of B4 sound part 2 (Noa); the 1 is test_ai, A4 part 2 in progress). Before: `tools/run_tests.sh` 170 passed, 5 failed (2026-10-01, end of lane B4 part 2: the 5 are the audio session's uncommitted work (3), A4's Legion (1) and an order-dependent `test_grapple` ledge climb that passes alone; `tools/tests` 16 passed). End of lane B4 part 1: 149 passed, 0 failed. `python3 -m unittest discover -s tools/audio` 6 passed. After photo mode: 148 passed. After A3 part 5: 145 passed, 0 failed. After A3 part 4: 135 passed, 0 failed. Earlier: 120 passed, 0 failed (2026-09-30, after A3 part 3). Earlier: 79 passed, 0 failed (headless, `--fixed-fps 120`); tool tests
  `python3 -m unittest discover -s tools/tests` 6 passed.
- Check runs: `tools/bot_run.sh smoke` plays menus, every settings page, loading, the range (walk, charge
  jump, run, skid), pause, off screen on the real GPU; screenshots in `images/NNN-smoke/`.
  `tools/bot_run.sh jg_check`: the real Juggernaut standing, walking, running (latest `images/067-jg_check/`).
  `tools/bot_run.sh long_walk`: the 10-minute no-fall soak.
  `tools/bot_run.sh combat_check`: the gun, reload, combat HUD, wire anchor swing and recoil dodge
  (latest `images/080-combat_check/`). `tools/bot_run.sh air_check`: tilt-aim, a running jump with air
  control, swinging and pitching in flight and a mid-air shot (latest `images/086-air_check/`).
- **Mission and Legion AI (lane A4 part 2, 2026-10-01).** Deploy plays "First contact" on Ashen valley (data/missions.json:
  Ameise scouts, a Grauwolf pack, a Löwe push; objective HUD; win/lose screens with Restart mission). Brains in
  scripts/ai/ (sight, hearing, packs, patrol/alert/attack/retreat). HE shells push by real blast physics
  (scripts/combat/blast.gd). `tools/bot_run.sh a4_mission` and `a4_fps_legion`. How to play: PLAYTEST.md.
- **Physics only (Emerson, A3 part 4, 2026-10-01)**: the Juggernaut weighs its realistic 5,423 kg (B1's
  `realistic_mass.json`, read by `tools/build_juggernaut_data.py`). Recoil is the real projectile + gas impulse
  (1.03 m/s on the body in the air). In flight nothing pushes it: the legs swing and tuck to turn it (angular
  momentum conserved, 4-6 deg/s), the gun's recoil and the wire are the only other forces. The wire anchor fires
  where you look (camera crosshair, look pitch to +75 deg), limited by the sub-arms; winch 120 kW, 16 mm cable
  breaks at 170 kN, pay-out while hanging abseils at 4 m/s. Gallop 70 km/h; Ctrl / L2 at speed is an analog,
  directional slide (Settings > Gameplay > Physics > Movement: slide friction, slide turn rate). The belly clears
  flat ground at a gallop and in a crouch. `tools/bot_run.sh score_move` measures all of it on Ashen valley and
  writes `logs/score_move.json` for `tools/scoreboard.py`. Sub-arm 12.7 mm guns on right mouse / R1 (A3 part 5):
  both arms fire in turn and aim at the crosshair; `tools/bot_run.sh sub_check`. **Photo mode** (O since A4 part 3, was P; or pause >
  Photo mode): time freezes, HUD hides, orbit camera, F12 saves to `~/Pictures/Eighty Six/`
  (`tools/bot_run.sh photo_check`; results/A4.md).
- **Look and sound (lane B4 part 1, 2026-10-01).** The grain was FSR 1's sharpening (Settings > Graphics >
  Sharpening, 0 % by default). SSAO is off on Medium and High (7-10 ms, no visible difference on these maps). Ashen
  valley opens on the "golden afternoon" weather with valley height fog and a film grade (`weather.json` "grade",
  `scripts/world/film_grade.gd`). The Juggernaut wears worn paint (`data/finishes.json`, Settings > Gameplay >
  Mech finish). Shrubs are leaf clusters on stems, the rim has peaks, spurs and road passes, far hills stand
  beyond the edge (`scripts/world/backdrop.gd`), the town has 21 ruins along its street with rubble where walls
  fell. **Sound:** `Sfx` autoload (`scripts/audio/sfx.gd`) plays `data/sounds.json` entries in 3D, gunfire and
  far impacts arrive at the speed of sound, sounds behind hills and walls are muffled, fast guns share a few
  voices; every mech gets `MechSounds` (footsteps by surface, landing, servos, skid, winch, gun, casing) from its
  existing signals; the reverb follows the zone you are in (town vs valley). The 24 sounds are synthesized from
  recipes (`tools/audio/recipes.json`, `tools/audio/synth.py`) and levelled by real loudness. Review page:
  `tools/audio/review_page.py --serve` (http://127.0.0.1:8687/), then `tools/audio/promote.py`. Mix check:
  `tools/bot_run.sh b4_sound_check` then `tools/audio/sound_check.py` (records the game's own sound). Scoreboard:
  `tools/scoreboard.py`. Detail: `~/Forge/sessions/juggernaut-alpha/results/B4.md`.
- **Real sounds and music (lane B4 part 2, 2026-10-01).** Settings > Audio > **Sounds**: a pick (which recording)
  and a level for every sound, from 1,816 downloaded CC0/free sounds (`~/Forge/shared/sound_library/`,
  `tools/audio/fetch_library.py`; per-sound choices by `tools/audio/pick_choices.py` from `tools/audio/choices.json`
  into `assets/audio/lib/`). Settings > Audio > **Music**: menu / exploring / combat track, Shuffle or Off, song
  language, Skip; tracks in `assets/audio/86/` (personal use: git-ignored, `.gdignore` keeps Godot from importing or exporting them; moved there from `~/Music/86` by Emerson 2026-10-02), listed in `data/music.json` by
  `tools/audio/fetch_music.py`; `Music` autoload. The gun was capped by Godot's 3D `max_db` (+3 dB); lifted.
- **Look, lane B4 part 2 (2026-10-01).** Undertaker's emblem (headless skeleton with a shovel) on both cockpit
  side panels as a worn decal: `data/emblems.json`, `scripts/look/emblem.gd`, the editable picture
  `assets/textures/emblems/undertaker.svg`, Settings > Gameplay > Juggernaut > Emblem. Dust from each foot at a run
  (`scripts/look/foot_dust.gd`, `tuning.json` "foot_dust", Settings > Graphics > Dust from the feet, off on Low;
  about 2 fps at a full gallop on Medium). The river's gorge bends away past the map edge with the water running on
  (`maps.json` backdrop `bend_m`, `water_reach_m`); the slab that hung across it was far-hill vertices skipping the
  edge height, fixed. **Versions:** Play (`tools/play.sh`, `builds.py ensure`) never numbers a version now; save one
  with `python3 tools/builds.py save --note "what is in it"`, refused while git shows uncommitted changes.
- **Look and sound, lane B4 part 3 (2026-10-01, Emerson's notes).** Sun calmer (golden_afternoon 1.6 energy at
  26 deg, haze toward it cut, sky disc 18 -> 6, glow per weather above a threshold: `weather.json` `glow_intensity`,
  `glow_threshold`); ground pebble detail and relief fade with distance (`ground.gdshader` `detail_*`, `relief_*`):
  the grain. No synth sounds by default (BigSoundBank CC0 recordings; `choices.json` `pick`, `pick_choices.py
  --only`, seamless loop cuts). Music: Settings > Audio > Music defaults to **Soundtrack, in order** (the OST album,
  `music.json` set "ost", carries on across contexts and launches, `user://music.cfg`); one original of each OP/ED
  (set "song"); covers and the preview reel only with **Extra tracks** on (`show_if`). Selectors: the left half of
  "‹ value ›" steps back. Tests never write Emerson's settings (`tests/runner.gd`).
- **Dirt builds up, lane B4 part 4 (2026-10-02).** `scripts/look/grime_buildup.gd` (`GrimeBuildup`, on every
  Juggernaut beside FootDust) adds dirt on top of the finish's grime from ground covered (dirt far more than rock,
  none on steel, more at a run), hard landings and skids; dust also mattes the paint (`tuning.json`
  `grime_buildup`). A new sortie starts at the finish's own wear; Settings > Gameplay > **Dirt builds up** off washes
  it. Live: +0.23 per km at a gallop (`tools/bot_run.sh b4_grime`, `grime_extra` in each sample; bot samples now
  merge any mech add-on's `bot_sample()`). At the cap the legs read brown and mottled (`images/251`).
- **Big map, lane B5 part 1 (2026-10-02): Sector 86 frontier, 4 km.** Streamed ground: `scripts/world/big/`
  (`BigTerrain` height as a pure function of x and z with an 8 m overview at load, `BigStream` 1 m tiles with their
  own HeightMapShape3D around every mech and the camera made on worker threads, `BigScatter`, `BigTowns` +
  `data/town_styles.json`), `scripts/world/big_map.gd`, `scenes/levels/big_map.tscn`. River, lake, fords, four
  towns, outcrops, crater fields. **Destruction:** `scripts/world/destructible.gd` (kit pieces with hit points;
  the struck piece and those in the ammo's reach break into debris, unsupported floors fall, below 35 % a building
  collapses; `tuning.json` "destruction"); the big map's towns use it. Tests `test_big_map` 7/7,
  `test_destruction` 5/5. Bot runs `b5_big_map` (viewpoint tour + walk + fps) and `b5_destroy` (real HE rounds
  into Kreuzberg: two blocks to 54 % and 47 %, `images/264`). Medium walking 46-54 fps on a shared GPU.
- **Big map, lane B5 part 2 (2026-10-02).** **Frontier sweep** mission on the big map (`data/missions.json`, maps.json
  `mission`; `scripts/mission/mission_run.gd` `MissionRun` is the shared start + bot hooks; the small map still has its
  own copies). **Ash river bridge** on the west road (`scripts/world/big/big_bridges.gd`; a road marked `"bridged"`
  gets no ford, the river stays deep and its banks steepen; kit `bridge` has `abutment_m` and steel `bearing_m`:
  a span needs both bearings, so HE near a pier drops two spans; `Destructible` pieces have `needs`). Grapple points follow
  broken buildings (`Destructible.sync_anchors`); the small map's buildings and walls are Destructibles. Big-map frame
  rates on a quiet GPU, walking: Low 105, Medium 64, High 48, Ultra 15 (`~/Forge/docs/library/juggernaut/2026-10-02-eightysix-bigmap-fps.md`).
  Tests `test_big_bridge` 8/8, `test_big_map` 9/9, `test_mission` 6/6, `test_destruction` 7/7; full suite 272/272 at the end of the part. A burnt-out truck (`wreck_truck`) sits in the towns' empty lots. Missions: an alerted wave can have `track_s` (told where the player is every 4 s) so the Legion cross the 4 km map.
  Bot runs `b5_bridge`, `b5_mission`, `b5_fps`. Details and what is only reasoned:
  `~/Forge/sessions/juggernaut-alpha/results/B5.md` part 2.
- **Big map, lane B5 part 3 (2026-10-02, Relay 20).** The Ash bridge's steel bearings are **marked on the HUD**
  (orange diamonds within 250 m, `Destructible.weak_points`/`weak_marks`, kit piece flag `weak`). **Bridge mission
  beat:** wave 3 of the Frontier sweep is a column of three Grauwolf that waits on the west road until the
  Juggernaut is within 450 m, then crosses the bridge in formation ignoring it (mission group keys `route`,
  `once`, `trigger_m`; `LegionBrain` route and `_holds_formation`); drop the bridge under them (HE on a bearing)
  and they fall into the river and take **fall damage** (`LegionMech._track_fall`, enemies.json `fall`). The
  Legion's steering refuses drops it cannot take and (routed columns only) water deeper than 0.6 m. **Objective
  guide:** the objective box shows the nearest Legion's distance and compass bearing and the heading tape a
  diamond (`Mission.guide()`, setting `gameplay.objective_guide`). Rim mountains have sharp crests
  (`rim_crag_m`). Town props: a better burnt-out truck and new `rail_car`, `power_pole`, `crate_stack`,
  `sandbag_wall` kit pieces in the towns' lots; steel materials less metallic. The wire bites 55-62 degree slopes
  live (`b5_wire_slopes`). **Legion path-finding** (`scripts/ai/legion_nav.gd`, a 16 m A* grid; bridges are corridors that
  close when a span falls) and an **upright keel** for the Legion (they were rolling onto their backs on the hills);
  the Frontier sweep's last wave still stalls far from the player, not diagnosed (results/B5.md part 3 item 11). Interior relief measured: 94 % of the ground under 30 degrees. Bot runs `b5_weak`,
  `b5_wire_slopes`, `b5_rim`, `b5_bridge_column`, `b5_bridge_drop`, `b5_guide`, `b5_props`, `b5_finale_walk`.
  Tests: `test_mission` 11, `test_ai` 25, `test_legion` 11, `test_big_bridge` 9, `test_destruction` 10, `test_nav` 5;
  full suite 288 passed, 0 failed (headless). Details, what was tried and what is only reasoned:
  `~/Forge/sessions/juggernaut-alpha/results/B5.md` part 3.
- Frame rates on **Ashen valley** (lane B4 end, 1920x1080, off screen, no Blender, no other Godot, sound on): Low
  85.1 / 73.4, Medium 51.5 / 47.7, High 41.1 / 37.9 fps (start viewpoint standing / walking): **all three targets met**
  (60 / 45 / 30). The town street 49 fps on Medium. Doc: `~/Forge/docs/library/juggernaut/2026-10-01-eightysix-scoreboard.md`.
- Frame rates (`tools/fps_log.py`, 1080p, test range with the stand-in, off screen, uncapped, Iris Xe,
  no Blender job): Low 96.1 · Medium 54.1 · High 45.8 · Ultra 15.1 fps (targets 60 / 45 / 30 / none: all met).
  High was retuned from measured costs; logs in `logs/fps/`. **Not yet re-measured with the real Juggernaut
  mesh in place of the stand-in** (lane A2 part 2).
- Juggernaut export **v5** synced (2026-09-30). Every Juggernaut collider (chassis and leg hitboxes) is B1's own
  convex hull, read from the synced export json; the feet stand at B1's sole sockets and lie flat on slopes; the
  visible model sits on its colliders (it was 1.41 m above them until A2 part 4). The legs run through the model's
  real hip, knee and ankle joints. The gun and chassis are fixed to the body: Gameplay settings "Body tilts to aim"
  and "Gun rests raised when parked" exist but are off by default. Settings > Gameplay > Juggernaut has Emerson's
  live play-testing controls: ride height, foot spread, leg length, metal shine.
- Juggernaut export v3 synced into `assets/models/juggernaut/` (`tools/sync_models.py`); it loads and its
  contract test passes. `mechs.json` `juggernaut_m2` status is now **ready**: `tools/build_juggernaut_data.py`
  generated its real parts/legs/stance/actuators from the export, and `scripts/mech/juggernaut_mech.gd` (lane
  A1's gait/physics, the real skinned mesh on top) builds and walks it. The test range now spawns the real
  Juggernaut, not the stand-in.
- **Playing, versions, sharing** (2026-09-30): `tools/play.sh` is the one way to play. It rebuilds the game
  first when anything that goes into the export changed (a few seconds; `tools/builds.py ensure`), saves each
  build whose pack differs as a numbered version in `build/versions/NNN-YYYY-MM-DD_HHMM/`, then runs it; if the
  rebuild fails it plays the last good version. The desktop launcher "Eighty Six"
  (`~/.local/share/applications/eightysix.desktop`, right-click: previous version, or from the project folder)
  and the Forge hub's Play both call it; the hub's Versions panel plays any saved version.
  `python3 tools/builds.py share` makes Windows, Linux and macOS zips for friends (each with a HOW-TO-RUN.txt)
  in `build/share/` (SHARE_DIR in `tools/builds.py`; only the newest version's set is kept, older zips are deleted). Platforms are one entry each in `tools/platforms.json`; templates for all
  three are installed. `build/` is git-ignored and nothing deletes a version.

## Log

### 2026-09-29 · lane A1 · Sora (ejb-83) · started
- Created `~/Games/eightysix/` (empty Godot project folders, git repo, fonts). Nothing verified yet.

### 2026-09-30 · lane A1 · Sora (ejb-83) · part 1 stopped (Emerson asked for the handoff)
What happened: built the foundation's code and data; the first headless test run found 7 failures; stopped
before fixing them. Full handoff, file map and next steps: `~/Forge/sessions/juggernaut-alpha/results/A1.md`.

What changed:
- 14 registries in `data/` (mechs, parts with per-joint actuators, weapons, enemies, maps, graphics_presets,
  themes, input with a hidden hardcore scheme, settings, sounds, music, tuning, rumble, tips).
- Autoloads: Registry, Settings, Controls, UiTheme, Graphics, AudioMix, Sfx, Music, Rumble, Game, Bot.
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

### 2026-09-30 · lane A2 · Hayato (ejb-0a) · part 4 done, lane A2 done
Synced B1's export v5. Every Juggernaut collider is now B1's own convex hull instead of a box (54 chassis
pieces, 12 leg hitboxes that follow the legs exactly as the meshes do). Hull points are read at build time from
the synced export json (`MechBuilder.model_hulls`) rather than copied into `parts.json`. The feet stand at B1's
sole sockets (a ray per foot through the sole's rest point), lie flat on slopes and re-seat after landings; the
springs and the rest of the physics are unchanged.

Fixed: since A2 part 1 the visible model was drawn 1.41 m above its own physics body (the glb's origin is the
ground, the body's is the chest). Found by the new hull-on-mesh test. Before/after: `images/065-jg_check/01`
and `images/067-jg_check/01`.

Then Emerson's notes from playing the old build: the gun's pitch threw away its bone's rest rotation and stood the
barrel about 80 deg off its line (fixed, now measured by a test); the gun and aim are fixed to the body by default
(two Gameplay settings keep the old behaviour, off); the leg IK now runs through the model's real hip, knee and
ankle joints, so the parts no longer drift apart while walking (old chain: 7.9 cm knee gap on a 0.6 m step; new:
0.0).

Then his look notes, made adjustable so he can test playing positions himself: Settings > Gameplay > Juggernaut
(ride height, foot spread, leg length, metal shine; live; defaults a notch taller, steeper, longer-legged and
less shiny than the model).

Verified: `tools/run_tests.sh` 74 passed, 0 failed (was 65; 9 new tests).
`tools/bot_run.sh jg_check` screenshots looked at (`images/067-jg_check/`). 10-minute soak clean before the leg and stance changes (`images/069-long_walk/`);
the final-code soak is logged in results/A2.md. Linux build re-exported and smoke-played, 29 shots, 0 errors
(`images/071-build_smoke/`).
Reasoned only: the gun's colliders stay level while the gun is raised at rest (lane A3). Details:
`~/Forge/sessions/juggernaut-alpha/results/A2.md` "Part 4".

### 2026-09-30 · Kaito (ejb-89/ejb-4f) · always-up-to-date launcher, saved versions, share zips for 3 platforms
Emerson asked for: the game findable in his app search, launchable from the desktop and from Forge, always up
to date, with version control, shareable with friends, on Windows, Linux and Mac.

Changed:
- `tools/builds.py` (new): `ensure` (rebuild when a fingerprint of every exported file's path, size and
  change time differs; save a version when the pack's sha256 differs; the unchanged Godot binary is
  hard-linked between versions, so a version costs about its 22 MB pack), `path`, `list`, `export`, `share`.
  `tools/platforms.json` (new registry): linux / windows / macos with preset, file, templates, how-to-run text,
  and what never needs a rebuild. `tools/play.sh` (new). `tools/export.sh` now `tools/export.sh [linux|windows|macos]`.
- `export_presets.cfg`: Windows (x86_64, pck beside the exe, no rcedit) and macOS (universal, built-in ad-hoc
  signing, not notarised) presets. `project.godot`: `import_etc2_astc=true` (Godot refuses a universal macOS
  export without it; the Linux and Windows presets keep ETC2/ASTC off so their packs do not grow).
- Windows (`windows_release_x86_64.exe`, debug + console) and macOS (`macos.zip`) templates added beside the
  Linux ones (462 MB in total), from the same SHA-512-checked release file.
- Desktop launcher + icon (`~/.local/share/icons/eightysix.svg`); Forge hub: Play goes through `tools/play.sh`,
  new Versions panel (`/api/versions`, play a version, "Make share zips" -> `/api/share`).

Verified:
- `python3 -m unittest discover -s tools/tests`: 13 passed (7 new in `test_builds.py`: builds once, docs and
  images never trigger a rebuild, a change makes version 2 and keeps 1 with one shared binary, same pack is no
  new version, failed rebuild plays the last good one, share zips per platform with the exec bit kept).
  pyright and black clean on `tools/builds.py` and the test.
- Real run: `builds.py ensure` built and saved version 001 in 3 s; a second `ensure` did not rebuild; the
  project.godot change made 002. `builds.py share`: exit 0 in 23 s, three zips in
  `build/versions/002-2026-09-30_1645/share/` (linux, windows, macos), no errors or warnings in the log.
  The macOS zip holds a signed universal `Eighty Six.app`.
- The Windows build starts under Wine 11.18 (`--headless --quit-after 300`, exit 0, official 4.7.2 banner).
- `gtk-launch eightysix` (the desktop entry): play.sh rebuilt (export presets had changed), saw the same pack,
  made no new version and started 002; screenshot shows the game on the real desktop. Closed by PID.
- Forge hub: pytest 25 passed (4 new), black + pyright clean; headless-Chrome screenshot of the Versions panel
  against the real `build/versions/`.

Not checked: the Windows build with graphics (only headless under Wine), the macOS build on a Mac (no Mac
here; unsigned by Apple, so friends right-click, Open the first time), a friend on another machine. Versions
001-002 were built from the tree with Hayato's A2 part 4 changes not yet committed ("uncommitted changes" in
the list). No limit on how many versions pile up (about 22 MB each, plus about 195 MB when share zips are made).

### 2026-09-30 · lane A2 · Hayato (ejb-0a) · part 5: Emerson's playtest notes
He found it collapsing, running breaking it, no charge jump while running, a weak game-mode jump, tipping over in
normal use, and the knee rams coming off the legs in a charged jump. Cause of most of it, measured
(`tools/bot/run_check.json`): the springs hung from the hips, only 0.85 m apart, so the body balanced on a tiny
base (13.7 deg nose-up at rest, 0 of 180 sprint frames with 3+ legs loaded). Now each spring stands over its
foot. Game-mode jump: fires on 2 legs or just after leaving the ground, launches higher, leaps forward along the
stick, falls faster than it rises; bench mode unchanged. Game-mode keel against tipping past 12 deg (Balance
assist). The knee rams ride their thigh and shin mounts and aim at each other (`scripts/locomotion/leg_rams.gd`).

Verified: `tools/run_tests.sh` 79 passed, 0 failed (5 new tests, 3 red first). Range run `images/076-run_check`
and `077`: sprint on 4/4 legs, charge jump mid-run at about 10 m/s, lands and runs on, worst lean 14.6 deg.
Reasoned only: the keel's own effect (the anti-tip test passed before it); the ram colliders still sit at rest.
Details: `~/Forge/sessions/juggernaut-alpha/results/A2.md` "Part 5".

### 2026-09-30 · lane A3 · Kaede (relay-9-work) then Aiko (ejb-68) · part 1 done
Kaede wrote the combat, damage, grapple and climb scripts and their tests, but never ran them. Emerson had Relay
paused and Aiko took over: first compile, then 7 failures fixed (drop interpolation, debris naming and cap,
limp through the drive's `speed_scale`, grapple reel input, winch stall, sustained-overload snap, grapple
prefers high surfaces, climb holds until over the lip). Added `CombatHud`, the range's target plates and
gantry, and `tools/bot/combat_check.json`. Tests 97/98 (the 1 is B3's). Details and what's left:
`~/Forge/sessions/juggernaut-alpha/results/A3.md`.

### 2026-09-30 · lane A3 · Aiko (ejb-68) · part 1b: Emerson's air control and tilt-aim
Air control (steer with the stick, swing and pitch the chassis with the mouse in flight, fire mid-air), body-tilt
aim on by default, chase camera follows the aim pitch. New `tests/test_air.gd`; the old "no air control" and
"level by default" tests now set their settings off. 114/114 tests; `images/086-air_check/`.

### 2026-09-30 · lane B3 · Chihiro (ejb-73) · part 1: the small map and the asset kit
Emerson could not see the Relay session on B3 (Nene), so it was stopped and taken over here from Nene's data
(kit, weather, the small_map entry, four CC0 texture sets). Built the level "Ashen valley" (about 1 km): terrain
from maps.json with the river and lake below the water line, levelled roads and town, craters, a rim; chunked
near/far ground meshes over one height-field collider; the kit builders (rocks, plants, 57 mm round and case,
walls, ruins, bridge, mast, tank traps, rubble) with break_apart for B5; scatter; sky, clouds and four weathers.
It is now the first map in the list.

Verified: `tools/run_tests.sh` 116 passed, 0 failed (13 new). `images/097-small_map_check/`. Frame rates at the
start view: Low 75, Medium 36, High 23 (targets 60/45/30: Medium and High not met yet). Details and next steps:
`~/Forge/sessions/juggernaut-alpha/results/B3.md`.

### 2026-09-30 · lane A3 · Aiko (ejb-68) · part 2: look and feel
Chase camera keeps 6 m off the hull and tightens at speed; shake on fire, hits and skids. Skid dust was drawing black
balls at the feet: now one-shot puffs. Mech meshes on render layer 20 so ground gouges skip them. New bot checks
`skid_check` and `field_check` (on B3's Ashen valley). 116/116 tests.

### 2026-09-30 · lane B3 · Chihiro (ejb-73) · part 2: holes, anchors, town look
Three overlapping ground detail rings (1 m to 120 m, 2 m to 320 m, 4 m beyond); a first try left whole chunks
undrawn at the hand-over (water showing through, floating shrubs), fixed by an 8 m overlap. Grapple anchors on
ruins and walls now sit on the highest surviving block (a new test found 30 hanging in the air). Town ground in
patches, four close viewpoints, two shadow cascades up to 100 m, lighter shrubs, `level.probe()` for fps work.

Verified: B3's 14 tests pass; full run 119 passed, 2 failed, both in other lanes' uncommitted work in progress
(test_combat plate, test_juggernaut sprint legs), not touched by B3. Shots `images/115-small_map_check`.
Frame rate: Medium read 31-45 fps between identical runs on this laptop, so reaching 45 is not verified.

### 2026-09-30 · lane A3 · Aiko (ejb-68) · part 3: Emerson's sprint notes
Sprint legs no longer trail, straighten or fold: speed-scaled stride and cadence, strides gathered under the body,
firmer attitude at speed. Grapple aim assist from the level's grapple points; taller range plates; camera follows
the view setting live. 120/120 tests; `images/116-sprint_check/`. Next: physics-based air movement (results/A3.md).

### 2026-10-01 · lane A3 · Tetsu (ejb-d4) · part 4: realistic mass, physics-only air, aimed wire, 70 km/h and the slide
Commits `1dac32e` (4a) and `03e52f7` (4b). Realistic 5,423 kg mass from B1's table; real recoil (5,580 N s APFSDS)
with no game scales; air movement from leg swing only (12 deg in 2 s of held turn, total angular momentum 0.0);
wire anchor aimed by the crosshair with a real winch and cable (the abseil test found free-spooling snaps the
cable, so hanging pay-out lowers at 4 m/s); gallop 70.4 km/h, 0-50 km/h 1.25 s (600 kW drive power);
analog directional slide; belly scraping fixed (the run stance lowered the front exactly the belly's 0.46 m
clearance). New `test_slide.gd`; 135 passed, 0 failed. Ashen valley route `score_move` (`images/139-score_move`):
0 stuck events, 0 flat-ground belly scrapes, slide 43.5 m, recoil 1.03 m/s. Build: version 006. Details and the
"try this" note: `~/Forge/sessions/juggernaut-alpha/results/A3.md`.

### 2026-10-01 · lane A3 · Tetsu (ejb-d4) · part 5: sub-arm guns, legs at speed
Commits `accba14`, `73b9d3c`. The sub-arm 12.7 mm pair fires in turn, each arm slewing to the crosshair within
its reach; 60 N s recoil a round, belts' 140 kg on the sub-arms (mech 5,563.7 kg). Straightened legs in the
sprint/turn/charge/jump run 6-8% -> 0.23% (stride gather follows stride length, targets inside reach and clear
of the hip, overreaching feet step at once, lifted feet travel with the body). Winch drum ramps while hanging.
145 passed, 0 failed; `images/148-sub_check`, `images/151-score_move` (build 007).

### 2026-10-01 · track A · Tetsu (ejb-d4) · photo / inspect mode (first A4 piece)
Commit `fffa417`. `scripts/camera/photo_mode.gd`, `Game.open_photo()/close_photo()`, the Photo mode key (P) and
pause-menu button, bot `goto photo/game`. 148 passed, 0 failed; `images/155-photo_check`. Hangar and menu showcase
still to do (A4).

### 2026-10-01 · lane B4 · Tetsu (ejb-f5) · part 1: look pass, then sound
Grain found and removed (FSR 1 sharpening; measured 26 -> 12 fine-detail noise), SSAO off on Medium/High, golden
light with height fog and a film grade, worn-paint finishes, leaf-cluster shrubs, a rim of mountains with road
passes and far hills, 9 more ruins with rubble, grime on brick. Medium at the start view 37 -> 50 fps. Sound: a
synthesized library, `Sfx` and `MechSounds`, speed-of-sound delay, occlusion, voice caps, listener-zone reverb, a
review page and an in-game mix check (PASS: a 57 mm shot 23 dB over the median). Mistakes found by checks and fixed:
a reverb echo from circular FFT filtering, Area3D reverb sends that cut every sound 6-14 dB, all sounds equally loud
from peak normalising. Not done: music (see results/B4.md), Legion sounds hooked to A4's enemies, rumble by feel.


### 2026-10-01 · lane A4 · Koharu/Tetsu (ejb-a4) · part 1: Emerson's notes, the Legion's body
Commits `23bdc82`, `42fbf6e`, `e2d5798`. Mid-air flips from an off-centre launch push and a crouch tuck that
spins faster (`test_flip.gd` 4/4); the wire anchor dart falls and slows on its line, fire control lands it on the
crosshair, a dotted arc shows its path, Dyneema line and a 300 kW / 240 kN winch (`test_grapple.gd` 9/9); sprint
sideways 52 km/h and backwards 48 km/h (`test_juggernaut.gd`); Heavy AP overcharged round, 8,360 N s and 1510
damage (`test_combat.gd`). The Legion (`scripts/legion/legion_mech.gd`): Ameise, Grauwolf and Löwe from B2's
exports, mass from parts, leg IK, tripod and 4+4 gaits on springs, grip-capped drive and turn, damage zones and
weak points (`test_legion.gd` 5/5). No brains or mission yet; nothing Legion seen on screen yet. Details:
`~/Forge/sessions/juggernaut-alpha/results/A4.md`.


### 2026-10-01 · lane B4 · Kana (ejb-60) · part 2: emblem, foot dust, the gorge, the version rule
Commits `c6f7204`, `9961261`. Undertaker emblem decal from an editable SVG (`test_look.gd` emblem 2/2,
`images/176-b4_emblem`); dust from the feet at a run (dust 3/3, `images/180-b4_dust`, cost about 2 fps at a gallop
on Medium, `images/181-184`); the river's gorge bends out of sight with the water running on, and the 22 m slab
across it (far-hill vertices one and two cells inside the edge skipped the edge height) is gone
(`test_small_map.gd` 15/15, `images/188-b4_river_exit`). Answered Emerson's question about versions 007/008 and made
`builds.py` follow his rule (one version per committed part, `save --note`; `tools/tests` 16/16). Details:
`~/Forge/sessions/juggernaut-alpha/results/B4.md`.


- 2026-10-01, A4 side jobs (Haru, ejb-ca): `tests/runner.gd` frees what each test leaves under the root and
  releases held input after every test, and prints `LEFT` per file that leaks (sleeping debris at the origin made
  `test_grapple` ledge climb and `test_legion` fail only in the full run); compile failures now print. Full suite
  192 passed. Details: `~/Forge/sessions/juggernaut-alpha/results/A4-side.md`.

### 2026-10-01 · lane A4 · Kenji (relay-12) · part 2: brains, honest blast, mission, PLAYTEST
- Legion brains (scout, pack hunter, heavy) on enemies.json "ai" blocks. **Verified** tests/test_ai.gd 18/18.
- The Löwe's draft 90 kN s "wake" replaced by HE blast physics (Kinney-Graham, reflected, per collider, shadowed):
  a 120 mm HE burst 2 m off the Juggernaut gives 1.13 m/s. **Verified** test_ai.
- Mission loop: missions.json, Mission node, objective HUD, end screens, restart. **Verified** tests/test_mission.gd 4/4
  and bot runs images/206-209 (screens seen).
- Legion CPU: one hitbox Area3D per joint and the pose written per frame: wave 3 went 15 -> 40-49 fps. **Verified**
  images/210 vs 211. Lite model past 150 m: added, fps effect not proven.
- PLAYTEST.md written. No version saved (Aiko saves the combined one). Next: Legion sounds, scoreboard row, Hangar.

### 2026-10-01 · Tetsu · controller works in the menus
- Cause: Godot 4.7.2's built-in menu actions (`ui_accept`, `ui_cancel`, `ui_up/down/left/right`) carry
  keyboard keys only (checked by printing the InputMap), so a pad could not choose, back out or move focus;
  only the mouse worked in menus.
- Fix: those six actions are now entries in `data/input.json` (group Menus, context ui), so Controls builds
  them like every other action and they are rebindable: Cross chooses, Circle cancels, the d-pad and the
  left stick move; Enter / Kp Enter / Space, Escape and the arrow keys kept.
- Verified: new `test_controls.gd:test_menus_answer_the_pad` (both schemes, keys, buttons and stick at 0.8)
  passes; `test_controls` 8 of 8. The `test_mission.gd` compile failure in the same run is another
  session's uncommitted mission work, untouched. Not checked with the real pad by Claude.
- Not saved as a numbered version: `builds.py save` refuses while the mission work is uncommitted; the
  playable build was rebuilt with `builds.py ensure`.

### 2026-10-01 · lane A4 · Ami/Tetsu (ejb-a4) · part 3: the two flaky AI tests, Kenji's part 2 committed
- Grauwolf pack spread (failed about 2 runs in 3): three causes. (1) Against a still target each wolf measured its flank
  angle off its own line to the target every think, so the spot turned with it; now latched per flank run. (2) Flank
  sides went by pack index, so a wolf on the left could draw the right flank; crossing, the keep-apart push held the
  pair side by side and both charged straight in. Now the pack's angles go out left to right by where each wolf
  stands (`pack_hunter.gd flank_angle`). (3) In the test the rockets sometimes destroyed the target, ending the
  hunt; the test's target now has armour no rocket gets through. **Verified** 8 of 8 runs, bearings -140/81/138 every time.
- Löwe ranging test: it scored where a round came down, so a round skimming over the mech scored 284 m. Now scored by
  the round's closest pass. **Verified** 6 of 6 runs (1.5-2.4 m). Full suite 194 passed, 0 failed.

### 2026-10-01 · lane B4 · Tetsu (ejb-21) · part 3: Emerson's notes on sun, grain, synth sounds, music, arrows
- Facing the sun (Medium): top third of the frame 160 -> 108 brightness, no white-out (`images/215` vs `216`).
  Grain was the ground's pebble detail (the probe on his Ultra settings, `images/212`, ruled out SDFGI, SSIL, SSR,
  SSAO, fog, MSAA, glow, shadow filter: at most 12 % each); fine-detail noise now 31-38 % lower on four views.
  Cost none: 88.2 vs 88.5 fps back to back (`images/218`, `219`).
- The seven sounds still on synth now default to recordings; every default is a recording. Music: 42-track OST in
  album order is the default; one original of each opening and ending; the 1-hour loops gone (to the trash,
  ~/Music/86 486 -> 257 MB); covers and preview reel behind Extra tracks.
- Selector arrows step both ways. A full test run had overwritten Emerson's own settings.cfg (restored from a read
  at 20:19); the runner now sends every test save to `user://test_*.cfg` (his file's checksum unchanged across a run).
- Tests: full suite 201 passed, 0 failed; `python3 -m unittest discover -s tools/audio` 11 passed. Commit fbf945c.
  Details: `~/Forge/sessions/juggernaut-alpha/results/B4.md` "Part 3".

### 2026-10-01 · lane A4 · Ami/Tetsu (ejb-a4) · part 3: Emerson's notes
- Flips: the flight computer leans the launch push just enough for `gameplay.flip_turns` (default 1) over the flight;
  front / back / side now 0.95 / 0.95 / 0.94 turns (side was 7.7), no foot in the ground on landing. test_flip 8/8.
- Park: P toggles the gun raise (`park` action); standing still no longer does. Photo mode moved to O. test_juggernaut.
- The 57 mm is solid on the frame: no barrel slide, the whole kick lands in the body in one tick. test_combat 13/13.
- Walk and run: the drive's moment from a push at the feet (half held back by the legs, smoothed): gallop start
  squats 1.3 deg (was 0), stop dips 2.3, turn leans 0.8. test_feel 4/4; score route 0-50 1.33 s (was 1.27).
- Details and what was tried and dropped: `~/Forge/sessions/juggernaut-alpha/results/A4.md` part 3.
- Later the same part: the comb of vertical stripes down the far cliffs came from the far ground's normals (the 2 m
  and 4 m rings took them from 1 m apart); `SmallMapTerrain._grid_normal` now spans the chunk's own step (test
  `test_far_ground_normals_follow_their_own_mesh`; `images/236` vs `245`). Commit 621cb21, in version 010.

### 2026-10-02 · lane A4 · Tetsu/Ren (ejb-3e) · part 4: Emerson's 010 notes, Legion legs and the 57 mm's mark
- **Legion walking, running, cliffs, the edge wall** (commit 0135a1b): active-suspension legs, footholds only
  where a foot could stand (no roofs, wall tops or cliff faces), footfalls by heading, stride grows with speed, no
  walking push on one leg; the brain probes three tracks ahead, keeps to `maps.json` `legion_area_half_m`, holds
  detours, backs out of dead ends. Verified: test_legion 9/9 and test_ai 20/20 (before/after numbers in
  ~/Forge/sessions/juggernaut-alpha/results/A4.md "Part 4"), bot `a4p4_legion_watch` (images/246 before, 258 after).
  B5 part 5 bots: `b5_hillside` (one of each Legion type on 15/27/24 degree hills, big map) and `b5_bridge_shell` (real HE at a bridge bearing); results in ~/Forge/sessions/juggernaut-alpha/results/B5.md "Part 5".
- **The 57 mm's own mark and the sub-arm guns** (commit 5f491b3): the mark sits where the round lands, with its
  range; the 12.7 mm guns have a small cross and a setting (fixed on the body by default / a little play / aimed by
  the arms). Verified: test_combat 15/15, bot `a4p4_aim` (images/265).
- Suite 229/229. Not done yet (part 5): aiming modes, cockpit view, the new HUD, the Juggernaut's legs crossing.

### 2026-10-02 · lane A4 · Kaede (relay-16) · part 5: legs crossing, cockpit view, HUD, aim modes, cockpit health
- **The Juggernaut's legs crossing** (note 8): measured with `tests/test_leg_gap.gd` (closest approach of any two legs'
  bones): a gallop put same-side legs 0.002 m apart, a front flip 0.009 m, in this tree and in version 009 (so not a 010
  regression). Fixed by keeping feet in hip order (`_keep_apart`, `data/tuning.json` `juggernaut.feet.apart_m` /
  `hip_pass_m`) and swivelling the knees clear (`_knee_swivel`, `swivel_*`): every scenario now >= 0.597 m (gallop
  0.849, front flip 0.601). Verified: 17 tests in test_leg_gap, test_juggernaut's straight-leg check, bot jg_check
  (images/290) and b4_grime (images/292, ends upright after 114 s of galloping and turning).
- **Cockpit view** (note 6): it was a dark tunnel (the eye is inside the canopy). The first-person camera now draws only
  the barrel and sub-arms (`mechs.json` `cockpit_show`, render layers in `CombatFx`; replaced by `cockpit_hide` in R3, below). Verified: test_cockpit 3/3,
  bot `a4p5_cockpit` (images/267 before, 282 after).
- **HUD** (note 7): one status block (speed, gait, speed bar, leg pips, attitude ball, jump charge ring), corner
  brackets, heading chip. Verified on screen: bot `a4p5_hud` (images/289), before images/265.
- **Aiming modes** (note 3): Settings > Gameplay > Physics > Aiming, "Stick sets the rate" / "Stick sets the angle".
  Verified: test_aim_modes 4/4. Not tried with a real pad.
- **Cockpit health** 1000 -> 2000 (NOTES.md; applied without asking): one rocket or blade no longer ends the sortie.
  Verified: test_damage (new test); not played through wave 2.
- Details and numbers: ~/Forge/sessions/juggernaut-alpha/results/A4.md "Part 5". Not done: Legion sounds (track B),
  Hangar and main-menu Juggernaut, move hints.
- **Move hints** (A4-side.md job 2): `data/hints.json` + `scripts/ui/move_hints.gd`, each hint once ever, Settings >
  Gameplay > HUD > Move hints. Verified: test_move_hints 5/5, bot `a4p5_hints` (images/294).

### 2026-10-02 · lane B5 part 6 · Tetsu (ejb-ab/ejb-36)
- **Native resolution on every preset** (Emerson: no upscaling or sharpening as the base): `graphics_presets.json`
  resolution_scale 1.0, bilinear, sharpening 0; settings defaults the same. Big map cost (one sitting): Low 64 / town 50
  fps (was 85 / 68), Medium 53 / town 42 (was 62 / 50). test_graphics 5/5.
- **The Löwe climbs out of the Frontier finale hollow**: a step may climb the grippable slope plus one ledge, feet that
  cannot grip can still bear weight (telemetry `b`), feet tuck under the hip to stand a sunk body up, and the brain's
  look-ahead allows one ledge per body length. Test `test_the_lowe_brain_finds_a_way_off_the_rough_patch` (3/3).
- Suite 295/295. **Version 011 saved** (6d763b5). Details: ~/Forge/sessions/juggernaut-alpha/results/B5.md "Part 6".

### 2026-10-02 · lane A4 · Sora (ejb-ef) · part 6: bigger shell hits and hit dust, wire anchor arc dots
- **Emerson's ask, bigger explosions and hit dust:** Settings > Graphics > World detail > Combat effects, "Shell hit
  size" and "Hit dust" (0.5-3.0x, default 1.6x; 1.0x is the old look). HE/HEAT shells get a fireball, flash and thrown
  clods; the default dart throws clods and a dust column off the ground (no fire); dust is bigger and lasts longer.
  Look only, damage and recoil untouched. Verified: tests/test_combat_fx.gd 5/5; combat, damage, destruction tests green.
- **Wire anchor arc** as screen-sized billboard dots (about 10 px), spread along short throws too. Verified:
  test_grapple 11/11 (8 dots on a 14 m throw).
- test_hud no longer errors on a stand-in mech's legs. Commit 7cde48e. Details: results/A4.md "Part 6".
- **Share zips** (B5 part 6 addendum): `python3 tools/builds.py share` zips the newest saved version for Windows, Linux and
  macOS into `build/share/`, built from that version's own commit, each with an install script (`tools/share/`) and
  HOW-TO-RUN.txt; older zips are deleted. `tools/builds.py clear-shares` deletes them all. Windows is one exe (data inside).
  Verified: tools/tests/test_builds.py 13/13; Linux install + run and Windows run (Wine) checked on the real 011 zips.

### 2026-10-02 · lane A4 · Nagi (relay-29) · part 7: Hangar, menu Juggernaut, Legion sounds, Dyneema mass
- **Hangar screen and the Juggernaut behind the main menu** (data/hangar.json, scripts/ui/hangar_stage.gd, hangar.gd,
  scenes/ui/hangar.tscn, main_menu.gd, `Game.goto_hangar()`, bot `goto: hangar`; settings `interface.menu_showcase` and
  `hangar.light`). Five light presets (Q / E), orbit, part picking with name and mass, O hides panels, F12 photo.
  **Verified:** tests/test_hangar.gd 17/17; screenshots images/409-hangar_check; fps off screen on the Iris Xe
  (images 404-406): menu showcase 81 / 84 / 87 on Low / Medium / High, Hangar 80-85, plain menu backdrop 145.
  Not screenshotted: the hover tooltip and the pad reticle. The variant picked in the Hangar does not change what Deploy spawns (A5).
- **Legion sounds:** mech_sounds.gd handles Legion mechs from an `enemies.json` "sounds" block; legion_mech.gd untouched.
  tests/test_legion_sounds.gd 5/5 (sound ids only; not listened to).
- **Dyneema mass:** 20 mm rope 0.22 kg/m, 17.6 kg per spool; table combat-loaded 5423 -> 5354 kg, game mech 5563.7 -> 5493.9 kg.
  tests/test_juggernaut.gd 27/27. Note: ~/Forge/docs/library/juggernaut/2026-10-02-dyneema-mass.md.
- Full suite on the shared tree: 387 passed, 3 failed, none in this part: test_audio x2 (music moved to assets/audio/86 by
  another session) and test_graphics apply (Ultra preset changed by the look pass). Details: results/A4.md "Part 7".

### 2026-10-02 · lane B6 part 2 · Tetsu (Relay 30, hey account) · bench grounds and HUD check
- **Two test grounds** for Test bench physics: maps `test_bench_flat` (400 m pad, painted marks every 10 m, two 8 degree
  ramps) and `test_bench_rough` (rock field, five 0.35 m steps 50 m ahead, 40 boulders; about 1.2 m of real relief, the
  noise is scaled by the interior range). `scripts/world/test_bench.gd` extends the test range, forces bench physics while
  the map is open and restores the old mode on exit, and spawns `Settings bench.design`. F6 resets the bench, F7 hides the
  readouts. Figures live in `data/bench.json` "grounds".
- **HUD moved** to the left of the screen (it sat on top of the hull panel) with bigger cells and text; checked on a real
  bot run, `tools/bot_run.sh bench_check` (images/414-bench_check: stand, walk, jump on the flat pad, stand and walk on
  the rough field).
- Verified: tests/test_bench.gd 29/29 (5 new ground tests); bot run 6 screenshots, 0 errors; full suite 386/390, the 4
  failures are not bench: test_audio x2 (music moved to assets/audio/86), test_graphics apply (preset changed by the look
  pass), test_scripts compile of scripts/ai/squad.gd (lane A5's unfinished file).
  Reasoned, not verified: heat never matters at 5.5 t (hottest joint 20.5 C after a walk and a jump), because parts.json
  sizes the actuators for the old 12.25 t. Measurements: ~/Forge/docs/library/eightysix/2026-10-02-bench-readouts.md.

### 2026-10-02 · lane A5 · Minato/Tetsu (ejb-42, hey) · part 1: the squad and the Handler view
Emerson moved the 86 music from `~/Music/86` into `assets/audio/86/` (he did not want it in his own music):
`data/music.json` paths are now relative to the project, `assets/audio/86/.gdignore` keeps Godot from importing
or exporting it, it is git-ignored and in every export preset's exclude filter (2182b8b). **Verified:** test_audio 18/18
(new `test_music_is_found_in_the_game_assets`).

Lane A5 part 1 (9adabae, 2ffe50d): allied Juggernauts from `data/squad.json` (Werewolf, Laughing Fox, Gunslinger, Snow
Witch), each a full physics Juggernaut with a `SquadPilot` that only works the controls (move stick, facing, sprint,
brake, body tilt). Orders 1 follow, 2 hold, 3 attack, 4 regroup; Tab opens the Handler view (tactical camera, Para-RAID
overlay, click to move, wheel or L1/R1 picks who). The Legion hunt the nearest Juggernaut. Settings > Gameplay > Squad
(default 2). **Verified:** `tools/run_tests.sh test_squad` 10/10 (move 86 m in 9.7 s, turn 55° and hit in 1.6 s, never fires
through a friendly, Legion retarget, Handler view), full suite 400 passed, 0 failed. **Not run yet:** the bot run
`a5_squad` and fps with the squad. Details: `~/Forge/sessions/juggernaut-alpha/results/A5.md`.

### 2026-10-02 · lane LOOK · Tetsu (Relay 26, hey account) · the world's look pass
- **Cause of the soft, grainy, slow ground: the kit textures were imported uncompressed with no mipmaps.** Godot only
  fixes that for textures it sees used in 3D in the editor; ours load from script. All 45 `assets/kit/textures/*/*.import`
  now have `compress/mode=2` and `mipmaps/generate=true` (test `test_every_kit_texture_is_compressed_and_mipmapped`).
  Big map Low 22.7 -> 49 fps from that alone.
- New CC0 ambientCG sets (listed in `assets/SOURCES.md`), `ground.gdshader` rewritten (dirt, turf, stones, gravel, rock,
  far-rock fade, palette uniforms, one fetch per layer), `masonry.gdshader` for brick/concrete/steel,
  `scripts/world/ground_look.gd`, a `palette` per map in `data/maps.json` (big map `frontier_morning` weather), bent
  grass and thinner shrub leaves. Ultra is MSAA 4x with no TAA (sharpness 15.5 against 4.5, `tools/sharpness.py`);
  saved settings still say TAA until the preset is picked again.
- Tools: `tools/bot/make_look_bots.py` writes `look_small.json` / `look_big.json` (8-10 fixed views per map),
  `tools/contact_sheet.py` makes before/after sheets. Before `images/392`, `393`; after `423`, `424`.
- fps (big map, off screen 1080p): Low 52 / Medium 44.5 / High 36.8 / Ultra 15 (vsync cap, GPU 130-160 ms);
  town 47.5 / 40.4 / 37.1. Before the pass Low 64 / Medium 53. Results: `results/LOOK.md`.
- **Verified:** shots on both maps, no shader errors, `test_world_look` 8/8, `test_graphics` 5/5, `test_kit` 6/6.
  **Not done:** model upgrades, decals, baked AO; export of the compressed textures not run.

### 2026-10-02 · lane A5 · Minato/Tetsu (ejb-42, hey) · part 2: way round walls, Handler polish, fps
Wingmen find a way round walls and back off when stuck (40 m wall, 15.9 s to a point 90 m off); a click on a Legion
marker in the Handler view orders an attack on it; the field HUDs hide in the Handler view; the first two wingmen walk
ahead on the flanks where the camera sees them; the squad is on the mission end screen. **Verified:** test_squad 11/11;
bot `images/436-a5_squad/` (Handler view, hold and regroup) and `images/437-hangar_check/` (0 errors); fps on Medium,
small map, one sitting: no squad 42.5 / walking 43.0, two wingmen 42.2 / 43.1 (`images/433-a5_fps_0`, `434-a5_fps_2`).
Also: `tests/test_scratch_bench.gd` (a B6 debugging leftover that re-ran every bench test) moved to
`~/Forge/sessions/juggernaut-alpha/archive/scratch/`, three stray uid files committed.

### 2026-10-03 · version 014 · Tetsu (hey) · Emerson's notes after playing 012
Bullet hits (12.7 mm, Legion MGs) reuse pooled emitters sized for a bullet with no light (12.7 mm ground fire on Medium
18.8 -> 36.5 fps, images/448 vs 450); every CombatFx emitter in local coordinates (a burst's first frame drew at the world
origin, the spawn on the test range: images/467 vs 468); flung armour ignores the mech it came off (it was knocking the
Juggernaut over, test_damage_ground); wingmen keep their hull in the cockpit view; `subgun_L/R` sockets at the sub-arm
fronts (builder + mechs.json); muzzle flash as a flame tongue with a strong light; no particle casts a shadow; chase camera
sweeps a sphere and rises over the mech when boxed in (test_camera_collision); Free roam + Keep exploring
(test_free_roam); gunner's optics on the wheel 1x/3x/6x/10x with a rangefinder (test_optics); HE dirt column and
Settings > Shell tracers. **Verified:** `tools/run_tests.sh` 396 passed, 0 failed, no script errors (2026-10-03);
bot shots images/447-471; scoreboard row 2026-10-03. **Not done:** ricochet/near-miss, aim measured, first-person look
(`~/Forge/sessions/juggernaut-alpha/2026-10-03-v015-brief.md`). Details: `results/V014.md`. Version 014 saved from d16fa79.

### 2026-10-03 · R3 · Relay 34 (hey) · first person with the whole mech
The cockpit camera (the pilot's seat, body (0, 0.33, -0.22)) sits inside the closed pod, so 014 drew only the barrel and
sub-arms (a spike and two dark blobs). `mechs.json` `cockpit_hide` now lists just the pod shell around the eye (canopy,
tub, side panels, lower side plates); everything else is drawn from the cockpit, and `MechCombat.set_cockpit_view` stops
that shell casting shadows while the camera is inside. **Verified:** test_cockpit 9/9 (shell hidden, 10 named parts
drawn, nearest drawn vertex 0.44 m from the eye, shadow off inside and back on outside), test_optics, test_models,
test_juggernaut, test_damage, test_move_hints, test_hangar green; bot shots before images/481-482, after 497/499/501.
**Not verified:** shadow shimmer in motion. test_squad's squad_size default check fails on this machine (4 vs 2), not
from this change. Details: `~/Forge/sessions/juggernaut-alpha/results/R3.md`.

### 2026-10-03 · v015 work · Tetsu (hey) · stopped at 75 % of the 5-hour meter (not saved as a version yet)
Verified (tests green, 0 SCRIPT ERROR in their logs): main-menu map list fits above the status line and scrolls
(test_ui 8/8, images/476-480); L2/R2 (Z/C) step the settings' left-column pages; Gameplay > Physics > Winch size
(default 1.4x, rope sized to it; test_grapple 12/12); tracers grow from the muzzle (were drawn up to 58 m behind it;
test_combat_fx 12/12); the wire is drawn along the dart's flown arc; rounds skip off the ground at grazing angles and a
passing supersonic round cracks with shake but no shove (test_ricochet 5/5); real-place terrain from a heightmap and
the **Palouse grassland** map (USGS lidar round Steptoe Butte, free roam; test_real_maps 2/2, images/505).
Relay sessions the same day: rumble (R2, fec6d04), first person (R3), ground texture (R1). Full suite not run after
these; fps of the Palouse not measured on a quiet GPU. Details and next steps:
`~/Forge/sessions/juggernaut-alpha/results/V015.md`; forest and city maps: `2026-10-03-maps-brief.md` there.
