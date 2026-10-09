# Eighty Six: the evening wave of 2026-10-08 (legs, Legion models, textures, first 0.2 systems)

date: 2026-10-08 · for: both (Emerson, and any Claude session with no history) · written by Riku (ejb-6a)

The task doc for this wave. It sits beside the plans it works from: `2026-10-08-spec-and-roadmap-to-complete.md`
(the spec), `2026-10-08-aaa-plan-and-engine-portability.md` (the AAA plan), `2026-10-07-roadmap-to-beta.md` and the honest
handoff `2026-10-07-handoff.md`. The game's own log entry is the last 2026-10-08 entry in `~/Games/eightysix/DEVLOG.md`.

## What Emerson asked (21:30)

1. Open the roadmap, critique and plan docs (done: opened in GNOME Text Editor, and the four plan docs sent to the
   WhatsApp chat through Relay at 21:45; Relay's outbox took them and none failed; the chat itself was not looked at).
2. Start work down the path to greatness (the spec's 0.2 and the AAA plan's N1 groundwork, below).
3. Fix the legs that keep getting stuck in the ground now and then.
4. The textures for everything but the Juggernaut.
5. The models of the two larger Legion (Grauwolf, Löwe).
He asked for critic agents and, later, many more helpers (ultracode). Helpers ran as Opus workflows; GPU runs went one at
a time through `flock /tmp/claude-86/gpu.lock`.

## Done and verified

### Legs stuck in the ground (GitHub issue 1): fixed, commit 2f0abd2
- **How it was found:** five investigators, one hypothesis each (hard landings, the 0.3 m re-seat rule, the leg fold, map
  streaming, the real model's legs). Three of them landed on the same cause independently; streaming and the re-seat rule
  were measured and ruled out as the cause of what Emerson sees.
- **Cause:** after a crash that left the Juggernaut tumbling or lying on its side or back, `_fold_on_ground`
  (`scripts/mech/standin_mech.gd`) kept only knee, ankle and sole centre clear of the ground, while the drawn legs are armour
  round those points (knee guard 0.21 m out, thigh and shin 0.18-0.21 m). The visible thigh or shin sat up to 0.26 m in the
  ground for 41-831 ticks (0.3-6.9 s).
- **Fix:** the legs' own collision hulls (the export's convex hulls) count in the fold when the mech is off its feet, on
  fewer than three legs, standing up, or a knee or mid-leg is within `feet.skin_near_m` (0.35 m) of the ground under its
  foot; the foot only when airborne or tipped and not pushing. A tumble no longer leaves a foot's target under its ground,
  a foot sunk past `reseat_m` re-seats out of turn, and a foot the ground rises over by more than `feet.sink_reseat_m`
  (0.05 m) re-seats. The player's own ground always draws at 1 m (big maps: its tile ring; Ashen valley: its 3x3 chunks),
  so a far camera such as the Handler view no longer shows coarser ground over the collider.
- **Verified:** `tests/test_legs_ground.gd` 16/16 (its repro cases failed before the fix); `test_clip` 26/26; `test_righting`
  14/14, `test_mech` 6/6, `test_juggernaut` 26/26, `test_physics` 5/5, `test_flip` 10/10, `test_feel` 4/4, `test_slide` 5/5,
  `test_leg_gap` 14/14, `test_big_map` 10/10, `test_small_map` 16/16. The 79 investigation cases are kept in `tests/hunt/`
  (`tools/run_tests.sh --dir=hunt`, out of the everyday suite): 100 passed, 10 failed after the fix, of which 4 test the
  old design or a model of the LOD rings, 2 measure the coarse mesh itself (by design), and 2 are open (below).
- **Not checked:** on screen (no GPU run for the legs). **Open:** the toe can poke 0.06-0.17 m into a ledge riser for 7-18
  ticks walking up a 0.3-1 m step; feet after a forced collider swap in a crater (never seen in play: tiles are primed
  before a mech is placed and arrive in time).

### The Grauwolf and the Löwe: reshaped, commit 937f5a7 (milestone m18, a second round is queued)
- Grauwolf: swept X side profile, V head with lenses and visor, capsule rocket box, feather fins, broad plate legs and
  blades. Löwe: long wedge turret, face block with a big round lens, hexagonal shoulder plates, chin block with cyan strips,
  swept fin, broad plate legs. The Ameise is unchanged. Part names, joints and masses unchanged.
- **Verified:** `test_legion` 14/14, `test_ai` 14/14, `test_damage`, `test_combat`, the 14 unit tests in `~/Models/legion`;
  sheets beside the refs in `~/Models/legion/images/20` to `25`; in game `images/705-legion-reshape-after`.
- **The critic's open findings (round two):** the Löwe's shoulder plates and face block are smaller than the anime's (each
  plate should be wider than the face block and stick out far past it); the Grauwolf's glowing visor triangle reads as a
  cartoon grin (in the anime the lower V is a smooth curved shield in hull colour, the purple is scene light); the in-game
  check has no front views; the Grauwolf lost its solid front when the visor moved onto the head joint (needs a small
  body-parented chin guard, with the 6 m blade still landing); minor: the feather fan should rise from the top rear, the
  rocket box should be a rounded box, the README size table needs the new heights.

### First 0.2 / N1 systems (each built, criticised and fixed; each has its own dated doc in this folder)
- **Save game** (`scripts/core/save_game.gd`; b285f67, ff6b385): versioned JSON, atomic writes, three rotating autosaves,
  migrations, refuses NaN or broken data. 20/20 tests. Doc `2026-10-08-save-game.md`.
- **Mission beats** (`scripts/mission/beats.gd`; 5cc4b6e, b9af2e8): a beats list per mission, eight triggers and eight
  actions, radio lines by dialogue id. Doc `2026-10-08-beats.md`.
- **Run log / telemetry** (`scripts/core/telemetry.gd`, `tools/telemetry_report.py`; f69ffde, d21ab09): one JSON-lines log
  per level visit (bots always; play behind Settings > Play log, off by default). Doc `2026-10-08-telemetry.md`.
- **Golden file** (`data/golden.json`, `tests/test_golden.gd`; 0edede5, 3197d60): 29 measured engine-neutral figures.
  **Open:** the fall-limit figure still moves with the drop grid (critic, second round). Doc `2026-10-08-golden.md`.
- **Act I script draft** (`data/dialogue/act1.json`, `tools/dialogue_lint.py`, `tools/dialogue_script.py`; c6ee75e,
  521d3a9): 438 lines for M0-M2, the night talks and the combat calls; lint 0 errors; a second critic accepted it.
  **For Emerson to read:** `2026-10-08-act1-script-draft.md`.

### Textures: first pass done, commit 03adbc8 (a second round is queued)
- 13 new 2K CC0 Poly Haven world sets and the Legion's own paint (ambientCG PaintedMetal004), 49 MB in the repo. Texture
  sets and which set each ground slot uses are now data (`data/kit.json` "texture_sets" and "ground_sets", per-map
  overrides in each map's palette; `tools/fetch_kit_textures.py` downloads from the list). The ground's tone comes from an
  aerial dirt photo instead of the noise that made the orange blotches; cliffs have near, mid and far rock layers; house
  walls have real window depth, sills, storey bands, corner stones and grime; roofs have proper tiles; the Legion's field
  livery is clean pale paint (the black cow-print blotches are gone). The Juggernaut is unchanged (Hangar shots differ by
  run noise only).
- **Verified:** test_textures 5/5, test_world_look 10/10, test_mech_look 4/4, test_look3 6/6, test_tone 5/5, test_hangar
  18/18, test_kit 10/10, test_small_map, test_big_map, test_real_maps; tone by `tools/histogram.py` (saturation 0.392 to
  0.407, clipping unchanged); before/after on High in `images/687` to `717` (sheets in `images/717-tex-before-after/`).
- **Frame rate on High (old to new, one sitting):** Ashen valley 35.7 to 32.5, Sector 86 38.8 to 35.7, Palouse 39.7 to
  37.9 (inside its noise), Allegheny 29.8 to 27.1: about 8-10 % on four maps. Disk: 49 MB repo, about 240 MB import
  cache (the mobile texture formats are imported too), 760 MB of check images, 159 MB download cache.
- **The critic's open findings (round two):** the cliff relief tilts the wrong way on half the faces (a sign bug in
  ground.gdshader's tri_tilt); close rock on Sector 86 shows fine horizontal stripes (the mid layer uses the same layered
  set); Brilon's streets got darker and show the dirt photo's tracks (keep the macro tone off paved surfaces); Ashen
  valley's road turned orange like the dirt (go back to grey gravel there); the Legion paint now reads almost plain
  (raise its contrast to 0.4-0.5, scale about 2, darker bare metal, grime 0.18); a stretched pale streak artefact on
  Palouse's moderate slopes; Sector 86's cliffs warm while its palette says slate grey (a decision for Emerson).
- **Fixed by Riku after the pass:** the far backdrop hills now wear the cliffs' own far rock set (they were the old grey
  1K rock; `GroundLook.slot_texture`, test in test_textures); the test runner resets every setting to its default before
  testing, so tests no longer run on Emerson's own choices (his settings.cfg has preset low and foot dust off, which
  failed test_look's foot-dust test).
- Not confirmed: the textures helper saw "the chase view in first person" in late bot runs; the chase shots in images 687,
  701 and 716 are all third person.

## Whole-suite check (23:50)
`tools/run_tests.sh` (all of tests/): **638 passed, 1 failed**, the same on a second run. The failure is
`test_grapple.gd:test_climbs_a_ledge_in_reach` ("the climb ends once it is over"). It is order-dependent: it passes alone,
in its own file and after either half of the 24 files that run before it (bisected), and it fails with the pre-fix leg
code too, so it is not the legs fix. Likely something cumulative over a long run; cause not found. The same run with the
pre-fix leg code failed 9 of test_legs_ground's 16 cases, so the regression set does catch the bug.

## Next: wave three (queued, not started: the 5-hour usage window was at 82 % at 22:56)
One helper and one critic each, in this order of value (the first two need short GPU bot runs, one at a time):
1. **Legion round two:** the four critic findings above, then a front-view in-game check.
1b. **Textures round two:** the critic's six findings above, then the same before/after bots on High.
2. **The radio speaks the script** (AAA feature 1, spec 5.2 P0): `scripts/ui/radio.gd` gets `say_text(speaker, text)` and
   picks dialogue lines by conditions, priority and cool-down, never repeating within minutes.
3. **The missing beat triggers** (`mission_start`, `mission_won`, `after`, `ally_destroyed`; the Act I file lists them).
4. **Campaign runner** (spec 5.1 P0): a campaign file (acts, missions in order, base scenes) on top of SaveGame, with
   Continue and New campaign.
5. **A path grid on Ashen valley** (spec 5.6 P0): no more Legion pile-ups in shell craters.
6. **Measure the Legion's hit rate** (D13's default) and **where shells land against the crosshair** (spec 5.5 P0),
   headless, numbers into this folder; change nothing until the numbers say what is off.
7. **The 559 names** Shin carries into M0 (spec 4.4, AAA plan 9.9), with a lint.
8. **The golden fall-limit figure** (the critic's second-round finding).
Later, needing the GPU: the night preset for M0, the Handler view's pan and zoom, the off-screen bot stall (handoff bug 6).

## Decisions for Emerson (each helper's, with the default it used)
- **save game:** Measures in the save (bests: time_s, accuracy, longest_kill_m, score) are kept to 3 decimal places (1 ms, 1 mm, 0.1 %) so the round trip is exact despite the Godot JSON parser being one bit off on 1 in 10 doubles. Finer values are rounded on save.
- **save game:** Version 1 is a paper format (the flat layout spec 5.1 first described). No shipped build ever wrote it; it exists as the first real link of the migration chain. The current version is 2.
- **save game:** Continue resumes the newest readable file of the four, main save or autosave, by a shared save counter (meta.seq). A checkpoint autosave made after the last main save therefore wins.
- **save game:** SaveGame is a plain class (class_name), not an autoload, because project.godot is not my file. A later campaign runner or menu can hold one instance, or Riku can add an autoload.
- **save game:** Starting a new campaign does not set the old one aside: the old campaign's autosaves stay on disk with lower seq numbers until they rotate out. Whether New campaign should copy the old save aside first is a menu decision for later.
- **save game:** Squad fallen entries carry {id, mission}, so the names screen can place each death at its beat. names starts empty: the 559 names Shin carries into M0 are not written yet (spec 4.4).
- **mission beats:** Waves count from 1 in beat data (as the HUD and summary show them) and from 0 in code.
- **mission beats:** Each beat fires once; there are no repeating beats.
- **mission beats:** Units spawned by a beat join the current wave, so that wave is not cleared while they are alive.
- **mission beats:** A 'scripted' ending counts as a win in the after-action records and shows the normal end screen until a campaign runner exists.
- **mission beats:** The demo beats are in a test-only mission (status 'test'), not in ashen_first_contact.
- **run log:** A run is one level visit, not one game session, so restarting a mission starts a new log.
- **run log:** The play log setting is off by default and sits on Gameplay > Menus and theme in its own Play log group, under the key telemetry.play_log.
- **run log:** A fall means the mech tipped past the righting angle (is_tipped). Hard landings are not logged; adding them is one entry in telemetry.json plus a link to the mech's landed signal.
- **run log:** The struggle weights in the report are a first guess: a hit counts 1, a lost part 3, a fall 2, a death 5 (TROUBLE_WEIGHTS at the top of telemetry_report.py).
- **run log:** The report counts a spike line at exactly the threshold, because the game rounds frame_ms to 0.1 ms after the strict over-50 check.
- **run log:** Bot logs stay in user://telemetry/bot, rotated to 20. They are not copied into the bot's images output folder; report.json holds the path instead.
- **golden file:** Penetration does not change with range or angle. The rule is just penetration_mm against armour_mm, so the golden file says APFSDS goes through 180 mm at 100 m and at 2 km, square on and at 60 degrees, while its impact speed drops from 1548 to 1510 m/s. Making it fall with impact speed and angle would be a design change, and the golden numbers would then be re-measured on purpose.
- **golden file:** No 57 mm round can go through a Löwe's hull: 240 mm of armour against 180 (APFSDS), 140 (heavy AP) and 220 (HEAT). A hull hit deals only 15 % of the round's damage, so its legs, knees and weak points are the only way in. This is recorded, not judged.
- **golden file:** The fall a leg survives is measured in test bench mode, because game mode has no fall damage yet. Its edge is uneven between about 7 and 11 m, depending on how the body lands. The file records the first breaking drop of a 0.25 m upward scan from 4 m (7.25 m breaks, 7.0 m survives). If you would rather have a steadier figure, such as the share of drops that break across a band of heights, it is one new rule method.
- **golden file:** Re-measuring is deliberate. tools/golden_measure.py --write only fills entries that have never been measured, unless you name the entries to re-measure, so only re-measure after a tuning change you have played and kept.
- **Act I script:** Callsigns on the link in M0 to M2 (setup 7), real names only in base scenes among the 86; Lev calls Shin 'Shin'.
- **Act I script:** The eight main combat speakers are Shin, Raiden, Theo, Kurena, Anju, Kaie, Daiya and Lena. Kujo gets 12 calls (M0 only, each needing him alive); the old Handler gets 4.
- **Act I script:** Subtitle limits: 2 lines of 42 characters (the common streaming limit; the brief said about 40), at most 17 characters a second. Default display time: minimum 1.5 s, 14 characters a second plus 0.5 s.
- **Act I script:** Combat calls cool down 240 s; the file's no-repeat window is 180 s per event per mission.
- **Act I script:** In N0 Lena says 'I'm sorry about Sirius': the act's one condolence, a formula rather than a stated feeling, and she only knows his callsign. Cut it if it reads as melodrama.
- **Act I script:** Invented and marked [new]: the Halberd squadron rescued in M0; which squad member calls Daiya's cat which of its four canon names (Theo Whitey, Kujo Blackie, Anju Calico, Kurena Kitty); the history class staged as slides plus Lena's withdrawn note.
- **Act I script:** Lena keeps her script through M2 ('still on her script, but quicker') and only speaks plainly from M5, per setup 17.
- **Act I script:** Lines are keyed by id in an 'entries' object, as the registry does, not kept as a list; duplicate ids are caught when the file is parsed.
