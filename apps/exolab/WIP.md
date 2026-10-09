# Exo Lab: work in progress

date: 2026-10-08 · for: both (Emerson and Claude) · Relay task 102 (helpers 104 suits, 106 game)

## Where it stands

Chunk 1 of the plan (`docs/2026-10-08-plan.md`, section 10) is built: the
physics core, four bench tests, the API, the tester page with the 3D VRM,
fitted suit and live mechanism, the editor and profiles. The suit shells
(task 104) are committed; the game first pass (task 106) is its own task and
is not covered here. Critic agents then tried to break chunk 1 and each
round of fixes (reports: `docs/2026-10-08-critic.md`, `-critic-2.md`,
`-critic-3.md`, `-critic-4.md`); every finding they confirmed is fixed (lists below),
except the few marked kept or reported only. A creative review and an
"Emerson's eyes" review gave the ideas list; what was built from them is
in "Reviews and the third critic" below.

Models: `exo_full` and `exo_lite` are ready. `spider_mech`, `biped_mech`,
`cyber_arm`, `cyber_leg` are listed as planned (the page shows what each will
test; the API answers 400 for a run on them).

## Verified (and how)

- pytest, 274 tests, all pass (`OMP_NUM_THREADS=1 .venv/bin/python -m
  pytest tests -q`, 25 s, 2026-10-08 session 23, close_fit included):
  vector maths, knobs, overrides and their checks, profile save/load and
  name guards, all four mechanisms on the light suit, a profile swapping a
  shoulder drive, per-part knobs, every bench on both suits with finite JSON,
  what power, stiffness, weight and strength knobs do to the results, game
  stats, every API route and error code, the page's files and that every JS
  import resolves (names and the import map). `tests/test_bad_input.py`
  covers the critic's findings: zero, negative and huge numbers, NaN and
  infinity, bad knobs, bad profile names, motion filters.
  `tests/test_suit_js.py` runs the page's real `suit.js` in node
  (`tests/js/suit_skin.mjs`, three from the shared vendor folder) on a
  fake VRM: the shorts band, the undersuit, the once-only rule, and the
  covers it refuses or warns about.
- `tests/check_ui.py` passed in headless Chrome (SwiftShader WebGL) against a
  sandboxed backend: home, ROM map, 3D load, editor with six tabs, knob edit
  -> live re-run -> Ctrl+Z, motions playback, hold pose mode, lift, a
  planned model, Save as, a typed 0 cuff width held at its limit, a failed
  run clearing the old verdict, a failed run or pose clearing the old
  numbers, a `&tab=` link opening the editor, the suits' skin (undersuit
  and shorts), the close-fit tables, the power knobs' help, the game's
  mass row, the cuff liner as a note, a J1 power knob dropped when J1
  swaps to a free bearing (on the open suit and on the other suit sharing
  the mechanism) so Save still works, and the spring's strength help: 48
  checks, all pass (session 23).
- black on every Python file; pyright with the app's venv: 0 errors.
- Baseline numbers: `~/Forge/docs/library/exolab/2026-10-08-baselines.md`.

## Not verified

- Never seen inside Emerson's real Forge window (WebKitGTK); only headless
  Chrome. Forge has to be restarted to discover the app.
- The physics is checked for direction and plausibility (more power lowers
  motor load, softer beams sag more, a fixed gimbal misaligns ~47 mm where
  the girdle tracker stays ~5 mm), not against a real exoskeleton.
- Frame rate on the Iris Xe with the VRM, suit and mechanism together.

## Known issues

- The suit's stirrups dip about 5 mm under the floor (y = 0); cosmetic.
- `exo_full` fails the overarm throw (elbow 8.7 vs 4.5 rad/s, J1 9.6 vs
  8 rad/s): real limit of the chosen drives, not a bug. Power does not buy
  it cheaply: x2 on every actuator still fails, x4 reaches warn with a
  48 kg suit, x20 fails again with a 194 kg suit (baselines doc, session
  20 addendum).
- `exo_lite` fails the 10 kg carry and the 12 kg lift on strap pressure: its
  cuffs carry the load into the skin. Also expected; it is the light suit.
- Shell strength reaches only the game's armour (`derive`). On the hip and
  knee drives, weight changes the suit's mass (and so the game stats),
  strength the game stats, stiffness only the drive's own figure. No bench
  loads the shells or the legs yet (critic M8; the legs get tests in a
  later chunk). A spring type's strength acts only where an arm joint uses
  it (the shipped suits use the spring only at exo_lite's knee); its help
  text says so.

## Fixed after the critic (session 13)

Each fix has a test in `tests/test_bad_input.py` or `tests/test_core.py`.

- Zero, negative or huge numbers (cuff width 0, a frame rate of 0, a motor
  speed of 0, a 1e300 kg payload) crashed a run with a 500 and the page kept
  the old verdict. Now `data/limits.json` bounds every typed number, numbers
  that still break the maths give a 400 with the reason, the editor holds a
  typed number at its limit, and the page clears the verdict on an error.
- The power knob did not raise a drive's torque limit; now it does.
- Hand sag was never judged, so the stiffness knob changed no verdict; it now
  warns past 15 mm and fails past 40 mm.
- Test settings that set the frame count are bounded: range steps of at
  least 5 degrees and at most 3000 cells a sweep, at most 1000 frames and at
  least 0.1 s a motion (the second critic showed steps of 2 took 17-33 s).
  Re-timed 2026-10-08, one run per process, laptop load ~10-13: the worst
  range sweep allowed (steps of 5, human range widened to every plane,
  2701 cells) takes 18.7 s (17.1 s CPU) on `exo_full`, 13.5 s on
  `exo_lite`, 0.3 MB of JSON; the worst motions run (120 fps, every motion
  stretched to 1000 frames, 6000 frames) takes 10.7 s on `exo_full`, 9.1 s
  on `exo_lite`, 2.6 MB of JSON (every 8th frame goes to the page). Each
  needs under 125 MB of memory. The default settings run in under a second.
- A missing profile name quietly ran the baseline (now 404); a motion filter
  naming no motion passed with nothing run (now 404); a gimbal's
  misalignment card never failed (now fails past 30 mm); the light suit on
  the cable drive got the girdle tracker's motor swaps (part overrides are
  now keyed by mechanism, so it gets `cable_bowden`); pose numbers took NaN
  and infinity (now 422); knobs that were not an object crashed (now
  refused).
- Small ones: profile names with a trailing newline, space or dot, or
  'Baseline' in any case, are refused; negative list positions are refused
  in Python and JS alike; a failing range card lifts the headline to at
  least warn; unknown knob kinds, items and knobs are refused on save; error
  texts keep their quotes; an inline profile that differs from its saved
  namesake is named '<name> (unsaved edits)'.

## Second critic (session 14)

Report: `docs/2026-10-08-critic-2.md` (probes on commit 953b375). Fixed, with
tests in `tests/test_bad_input.py` that fail on the old code: N1 (motion edits
in the Tests tab were saved but ignored by the motions bench), N2 (bounds
above), N5 (lift key times squeezed to ~0 gave NaN cards; now a 400 saying a
motion must last 0.1 s). Fixed in session 15 (commit 8068e9c), each with a
test that fails on the old code: N3 (huge JSON integers gave a 500), N4 (text
in the auto length fields skipped the limits), N6 (a hand-edited profile file
that is not an object gave a 500), N7 (a gearbox limit of exactly 0 meant no
limit; now the drive stops), L-a (text fields: an id of the right kind, one
of a fixed set of choices, or fixed, per the `text` block in
`data/limits.json`; only unknown models, tests, motions and profiles give
404), L-b (part knobs must name a real part), L-c (character edits are
checked; both ready models name their own character, so the human's
character choice changes nothing until a model leaves it out), L-d (`constructor` is no model id), L-e (the editor
checks the name pattern and 'baseline'; the server also refuses look-alikes
such as 'Ba5eline'), L-f (a failed run or pose clears
the old numbers). L-g kept by design: the range headline is the share of
directions followed; a failing card pulls a pass down to warn, a warning
card (for example "closest to gimbal lock 0.10") does not. The README
claims the report flagged are corrected.

## Reviews and the third critic (sessions 16-20)

Reviews: `docs/2026-10-08-creative.md` (15 ideas ranked by wow per effort)
and `docs/2026-10-08-emerson-view.md` (the app through Emerson's eyes, with
a ranked fix list). Built from them:

- Power costs mass. Power x k multiplies a drive's rated power, mass, remote
  mass and rotor inertia by k and its torque, torque limit and top speed by
  the square root of k (`data/knobs.json`); drives without a motor take no
  power knob; the battery's power is more cells (energy and mass together).
  On `exo_full` x4 is the sweet spot (hold passes at 82 % motor load,
  motions warn, a 48 kg suit); x20 is a 194 kg suit that fails again
  (baselines doc, session 17 and 20 addenda).
- Skin on the light suit. The sidecar's `skin` field: the full suit tints
  all skin as an undersuit; the light suit turns a band round the hips
  (0.26 m below to 0.075 m above the hips bone) into dark shorts whose hem
  tucks inside the thigh cuffs, and leaves arms and legs bare. The game
  uses the same code (`static/js/suit.js` `tintUndersuit`). Seen in
  headless Chrome shots, front, back and side (session 20).
- The page's Game links open the game with the tester's model and saved
  profile; their hover text says when unsaved edits are not in it.
- The game's stats panel lists the 9 kg kit in the mass line (55 + 11 + 9
  = 75 kg on the light suit).

Third critic: `docs/2026-10-08-critic-3.md`. Fixed, each with a test in
`tests/test_third_critic.py` that fails on the old code: M1 (battery power
gave free energy), M2 (power gave k squared the drive power for k the mass;
now the square-root rule above), M3 (a part's name field changed the
physics; only an item's own name is free), M4 (motion keys squeezed
together passed; keys must be 0.05 s apart), L1 (an unreadable or directory
profile file gave a 500; now 400), L2 (part knobs a part never reads were
saved; `part_knobs` in `knobs.json` now lists what each kind reads), L3 (a
text field became a pick when its shipped value happened to be an id;
`limits.json` `text.fixed` keeps an actuator's `kind` and the girdle's
unread `joint` fixed, server and editor alike), L4 (free text is capped at
200 characters), L5 (`tintUndersuit` runs once per model and warns in the
console when it cannot cut the shorts; its test, `tests/test_suit_js.py`,
came with the fourth critic), L6 (a human range whose planes do
not rise, or an empty sweep, is refused), L8 (digit look-alikes such as
"b4seline" are reserved), and the game's three divisors stay above zero.
Reported only: L7 (the game falls back to its offline stub, with a note,
when its profile was deleted after the page loaded; task 106's code). Its
doc-claim list is corrected in README, this file and the baselines doc.

Still open from the reviews:

- (The visual pass is built: see "Visual pass" below.)
- Material fatigue: `fatigue_safety` is computed (`exolab/arm.py`) but no
  rule judges it, so the strength knob's change to fatigue strength reaches
  no verdict (the yield-based beam safety does).
- One character only (hairsample_female); the plan's male VRoid sample is
  not in the shared assets.
- An `exo_combat` model (heavy drives, better than human), a shoulder
  shoot-out of all four mechanisms, click-to-edit in 3D, thumbnails on the
  home cards, golden test vectors and `docs/PORTING.md`.

## Fourth critic (sessions 21-23)

Report: `docs/2026-10-08-critic-4.md` (no High). Fixed, each with a test
that fails on the old code (`tests/test_fourth_critic.py`, 37 tests;
`tests/test_suit_js.py`; two `check_ui.py` checks):

- M1: motion keys exactly 0.05 s apart are allowed (float slack); the
  message prints the real gap. M2: the lift card times a lift by the
  motion's last key in time, not the last one typed.
- M3: the cuff liner is comfort only and nothing reads it, so it is fixed
  text (`limits.json` `text.fixed`); the editor shows it as a note, not a
  pick, and leaves it out of the materials in use.
- L1: a joint is powered when its actuator has a motor (the `motorless`
  list in `knobs.json`) and torque above zero; `parts.py` no longer keeps
  its own list. L2: `part_knobs` gives passive drives their own knobs (a
  free bearing: weight; a spring: strength and weight), on the actuator
  type as on a part; the editor shows only those.
- L3: rules between fields are checked on save (400): a human range whose
  planes do not rise, a motion a test plays with keys too close or too
  short at that test's frame rate (`benches.cross_errors`).
- L4: the range sweep's "Range tested" card warns when the sweep covers
  under half of what the unedited human reaches at the same steps, and
  that caps the headline at warn.
- L5: `/api/model` returns `part_knobs` (the knobs each part reads now);
  the editor drops a part knob its part no longer reads, with a note and no
  undo step of its own (J1 power, then J1 swapped for a free bearing: Save
  works; on the old code Save said "no motor, so no power knob").
- L6: 6 and 7 join the baseline look-alikes ("6aseline", "base7ine").
  L7: a failed save no longer leaves a stray `<name>.tmp`.
- L8: the light suit's skin cover refuses a band that is not two numbers
  in metres within 3 m of the bone (mm typed by mistake), warns when the
  band takes no face or more than half the skin, and counts each face once
  (MToon draws skin faces twice, skin and outline).
- Doc claims: the shell-strength line under Known issues and the
  third-critic L5 test claim are now true.

## Fifth critic (session 23)

Report: `docs/2026-10-08-critic-5.md` (no High, no 500 in any probe). It
checked the fourth critic's fixes and found two that did not hold on a
reachable path. Fixed, each with a test that fails on the code before it
(`tests/test_fifth_critic.py`, 7 tests; 2 more checks in
`tests/js/suit_skin.mjs`; 3 more in `check_ui.py`):

- M1: both suits share the girdle tracker, so a J1 swap made on the light
  suit stranded a J1 knob on the full suit and Save failed. `/api/model`
  now also returns `part_knobs_of` (every model's parts), and the editor
  drops a stale knob on any suit, naming it ("J1 power (Exo suit, full)").
  The critic showed the old editor code keeping the knob (its node probe);
  `check_ui.py` covers the new path.
- M2: the close fit test's own limits (300 frames in all, warn distances
  under `reach_mm`) and the motions it plays were not checked on save. Each
  bench module may now define `save_errors(test, reg, prof)`; `motions` and
  `close_fit` do, and `cross_errors` runs them all, so the rule lives
  beside the bench that enforces it. A range sweep's cell cap cannot be
  reached through `limits.json` (steps at least 5, planes within 180), so
  `shoulder_rom` needs none.
- L1: the "Range tested" card reads at most 100%; a wider range says it
  covers more than the usual one (`metrics.tested_pct` keeps the real share).
- L2: the spring type's strength knob says it acts only on an arm joint.
- L3: a mesh the shorts band cannot be tried on warns once, not twice.
- L4: `part_knobs` never offers power on a motorless kind.
- The light suit's `data-skin` now reads "shorts 812": each skin face once
  (MToon draws it twice, skin and outline; it read 1624 before).

## Close fit (Relay task 108, 2026-10-08)

`close_fit` (`exolab/body.py`, `exolab/benches/close_fit.py`,
`data/tests/close_fit.json`) measures each fitted shell against the posed VRM
skin and the moving shells against each other through the six shoulder
motions; README has the rules, the baseline doc
`~/Forge/docs/library/exolab/2026-10-08-close-fit.md` the numbers (both
suits fail: shells at the shoulder and chest go 10 mm or more into the skin,
the helmet meets the arm overhead).

Verified: `tests/test_close_fit.py`, 15 tests (rest gaps match the sidecar,
a cuff pushed 5 mm in fails, 40 mm in reads "10 mm or more", shells pushed
into each other fail in a frame and at rest, profile motion edits used, bad
reach/warn/fps refused, run time bounds); each new one fails on the code
before its fix. exo_full 4.6 s, exo_lite 1.6 s a run (laptop load about 4).
Three capped depths re-measured with a 50 mm search (10.4, 11.5, 12.6 mm).
An opus critic's findings are fixed (list in the baseline doc). check_ui
close-fit block: see the commit message for its last run.

Caveats: depths past `reach_mm` read as "N mm or more"; a shell overlap only
shows down to the thinner wall; at a seam between arm and torso skin a shell
point can switch label for a tiny pose change (0.7 mm once); the body
self-contact (forearm into the hips with the arm down) is the pose's and
excuses suit contacts within 30 mm of it.

## PS5 controller (Relay task 115, 2026-10-08)

The game takes a PS5 DualSense, or any pad the browser gives the standard
layout, through the browser Gamepad API.

- `static/game/controls.json` is the registry: the layouts (the standard
  mapping, and the raw Linux hid-playstation order for a browser with no
  mapping), the PS5 button names, the bindings (button -> action), the menu
  moves, deadzone, look speed, which stick moves and which looks
  (`sticks[].do`), the analog triggers (`pad.analog`), the trigger press and
  release lines, the menu's stick lines, how long the stick must rest to end
  sprint, how long the mouse stays quiet after pad input, and the rumble per
  sim event. Changing
  a binding is one line there.
- `static/game/pad.js` is the mapping with no DOM: `stepPad()` returns move
  and look, held sprint and walk, one action per press, the pause press and
  the menu moves and whether the pad is in use (`busy()`: a button, or a
  stick past the menu line, so a drifting stick does not count);
  `choosePad()` picks the pad in use (not just slot 0);
  `menuMove()` steps the menu focus (no wrap); `listPads()` turns a refused
  `getGamepads()` into a reason. `main.js` polls the chosen pad each frame
  (`pollPad`); the left stick reaches `readKeys` only when no movement key is
  down; the right stick turns the same camera as the mouse.
- Pause menu: a PS5 controller list built from the registry beside the
  keyboard list, and a line saying what the page sees (no pad yet, which
  pad, a pad with an unknown layout, or why the window refuses pads). The
  d-pad or stick moves a focus ring over Play, Restart and Back; ✕ picks,
  ○ or Options goes back.
- HUD: the mode boxes, the crate prompt and the broken-arms banner name the
  pad's buttons once the pad is used, and the keyboard's after a key or click.
- How to connect and the laptop check:
  `~/Forge/docs/library/exolab/2026-10-08-ps5-controller.md` (the pad has
  never been paired over Bluetooth, so that is needed once).
- In Forge (commits 5ef18e7, 472f0b7, then 7433529 and 77fd779 after the
  critic): `forge-pad.service` (`shared/pad`, the pad as mouse and keys while
  a Forge window has focus) would double every press (○ = Esc, L2 = Alt+Left
  back, d-pad = arrows, ✕ = click). The game posts `{forge: "pad", native}` to
  `window.parent`: true while it sees a pad, false when it loses it or on
  `pagehide`. In Forge's window the hub hears it and, while the game is in
  front, Forge writes 0 to the service's `pad-focus` flag; in a pop-out (the
  game is the top page and posts to itself) `forge_popout`'s injected script
  hears it and does the same for that window. The hub's app iframe also
  allows `gamepad` now (the spec's default is same-origin only and each app
  has its own port; a WebKitGTK 2.54.1 probe with no pad found `getGamepads()`
  answered with or without it, so the earlier note that the game would not
  have started in Forge was wrong). Behind another Forge app the game pauses
  and stops reading the pad (`{forge: "visible"}` from the hub). When
  Forge's window loses focus the game hears it too (`forge.py`
  `notify::is-active` -> hub `window.forgeWindowActive` -> `{forge: "focus"}`
  to every app frame; commit b538a50) and pad play pauses; getting focus
  back locks the pause menu until the stick is seen resting again
  (8509987). Forge must be
  closed and reopened once to load the hub and `forge.py` side.
- The press that makes a pad appear (a page sees a pad only after a press)
  is a wake-up, not an action; in Forge the pad-as-mouse service has already
  acted on it. A d-pad arrow is the harmless one on the pause menu.

Critic 1 (opus; full report
`~/.local/share/forge/relay/tasks/0115-critic-findings.md`), all fixed:

- F1 a popped-out game got every press twice: Forge 7433529
  (`forge_popout.relay_pad_native`), and the game posts even at the top level.
- F2 the pad went dead after a hub crash-reload with the game in front, F7
  after closing and reopening Exo Lab: Forge 7433529 (`forge.py` resets on
  hub load; the hub resets on close and sends on mount).
- F3 (high) pausing while running and then pressing ✕ restarted or left the
  game (the held stick moved the menu, which wrapped): a direction held from
  play moves nothing until let go, and the menu stops at its ends.
- F4 R2 resting on the line punched 30 times a second: let go only under 0.2.
- F5 L3 clicked just before the push never sprinted: sprint ends only after
  the stick has rested 0.25 s.
- F6 the first pad in the list won even when idle: `choosePad`.
- F8 Forge losing focus left the soldier running on the last stick: pad play
  pauses when the window loses focus.
- F9 the DualSense touchpad is also a desktop touchpad (a brush clicked):
  a click right after pad play only switches the hints back to the keyboard.
  The touchpad still moves the desktop pointer; a Hyprland per-device rule
  could turn that off (not done: his config was left alone).
- F10 the game told Forge it read the pad before seeing one: now only while
  it sees one.

Critic 2 (opus, on 77fd779; full report
`~/.local/share/forge/relay/tasks/0115-critic2-findings.md`), all fixed in
b538a50:

- G1 a direction held from play still moved the menu once it changed (F3
  was half fixed): the menu is locked (`st.menuLock`) after play, after the
  wake press and after focus loss until every direction is let go, and the
  stick keeps a direction down to `menu_stick_release` 0.4 (no flicker at
  the line).
- G2 a stick drifting just past the deadzone made every frame "pad in use",
  so mouse clicks never punched: in use now means a button or a stick past
  `menu_stick`.
- G3 the touchpad guard covered one click only: the mouse does nothing for
  `mouse_quiet_s` 2 after pad input (canvas click, locked pointer moves, real
  clicks on the pause menu; the pad's own menu presses still work).
- G4 a short stop then L3 turned sprint off, against the help text: L3
  turns it off only after `latch_rest_s` of running, else on (help text
  says so).
- G5 the blur pause needed the game's frame to hold focus: Forge's window
  focus now reaches the game through the hub (see above), and focus loss
  also locks the menu.
- G6 `latch_rest_s` 0 or missing cleared the latch the frame it was set: the
  latch clears only while standing, and the trigger release line is never
  above the press line.
- G7 which stick moves and which looks was in code: `sticks[].do` and
  `pad.analog` in the registry, read by `stepPad`.
- G8 text against the pad: the hint says press a d-pad arrow, and the repair
  prompt names the pad's or the keyboard's button from the labels.
- G9 a pad dropping out mid-run did not pause: it does in pad play.
- G10 a crash in the frame loop left Forge's pad-as-mouse service off: a
  window error tells Forge the game no longer reads the pad.

Critic 3 (opus, on b538a50; full report
`~/.local/share/forge/relay/tasks/0115-critic3-findings.md`, its harnesses
in `0115-critic3-harness/` beside it): three low findings, fixed in cdcaed9
with one more thing found while fixing:

- H1 gentle stick play (a slow walk, fine aim) stayed under the "in use"
  line, so touchpad taps mid-walk punched and Forge losing focus did not
  pause: while the pad is the device in use, its sticks moving keep the
  mouse quiet, and focus loss pauses when the pad is in use or its sticks
  move. (The mouse half was replaced in 8509987: see critic 4's I1.)
- H2 the pad in use dropping out did not pause while a second pad stayed
  connected: `choosePad` says `padLost` for the frame the pad read last
  time goes, and `pollPad` pauses on it. The first version of this fix was
  undone in a real browser: the `gamepaddisconnected` handler redrew the
  menu line through `choosePad` before the next frame and used the loss up.
  The menu line and rumble now only look (`peekPad()`); only `pollPad`
  moves the pad state on.
- H3 the menu lock opened on one frame inside the let-go line, so a dodge
  swinging the stick through the centre after Options walked the menu to
  Restart or Back: the lock now opens once the menu's buttons are let go
  and its stick has rested inside the line for `pad.menu_rest_s` 0.12 s
  (counted in play too, so Options pressed mid-swing locks as well). A
  d-pad let go is let go (the stick has been resting), and a pad just seen
  starts rested, so a quick second tap after the waking press moves.
- Also: Enter or Space on a pause menu item within `mouse_quiet_s` of pad
  input was swallowed with the touchpad's clicks; clicks the keyboard makes
  (`detail` 0) go through now.
- Kept by design (critic 3 noted them): a real mouse click within 2 s of
  pad input does nothing; a thumb resting on the stick at 0.4 or more keeps
  the menu locked; after a stick push, 0.1 s of let-go is not yet a rest.

Critic 4 (opus, on cdcaed9; full report
`~/.local/share/forge/relay/tasks/0115-critic4-findings.md`, its harnesses
in `0115-critic4-harness/` beside it): one medium and five low findings,
fixed in 8509987 apart from I2, which stays by design:

- I1 (medium) a stick drifting just past the deadzone after pad play kept
  the mouse dead for good: H1's fix took any stick movement while the pad
  was in use as pad input, and a drift looks just like a slow walk.
  Gentle stick play no longer keeps the mouse quiet. Instead, while the
  pad is the device in use, mouse moves do not turn the camera, and once
  `mouse_quiet_s` has passed since a pad button or firm stick the first
  click hands the controls back to the mouse (the rule the docs already
  gave; the next pad button or firm stick takes them back). Trade-off: a
  touchpad tap after 2 s of gentle-only stick play hands the controls to
  the mouse (no punch).
- I2 (by design) a keyboard player with a drifting pad lying by is paused
  when the window loses focus: a stick past the deadzone moves the
  soldier, so it counts. The registry's about line says to raise
  `pad.deadzone` for a worn pad.
- I3 the frame the stick came into the centre counted its whole length
  as rest, so one long frame could open the menu lock: the rest counts
  only between two frames that both found the stick resting
  (`st.menuIn`).
- I4 a slow walk under the let-go line counted as resting, so Options
  mid-walk with the thumb running on walked the menu: in play the stick
  rests only inside the deadzone (on the menu, inside the let-go line).
  A drifting stick holds the menu only until it has sat still.
- I5 getting focus back did not lock the menu again: a frozen, resting
  pad seen while away opened the lock, and a stick already held on the
  way back walked the menu at once. The window's focus event and the
  hub's `focused: true` now call `lockMenu(st, true)`, and the rest seen
  before does not count.
- I6 the tests let go of the stick in one frame longer than the game
  can produce, which hid I3: they let go over real 1/60 s frames now.

Verified:

- `tests/test_pad.py` (4 tests) runs `tests/js/pad_map.mjs` in node: 54
  checks on fake DualSense states read through the real `controls.json`
  (registry integrity, both layouts, deadzone, stick directions and look
  speed, one action per press, the R2 press and release lines, d-pad modes,
  L2 walk, the L3 latch and its rest time, Options pause and back with no
  double toggle, menu moves and repeat, a direction held from play not
  moving the menu, the menu's ends, a ✕ held from the menu not jumping, the
  wake press, the menu rest after a dodge and the d-pad let-go, no rest
  from one long frame or from a slow walk, `choosePad`
  with two pads and a drifting stick, unplugging and the pad-lost flag, HUD
  names, rumble, `listPads` on a navigator that throws), the page hooks
  `main.js` fills, and three fed into the real sim (✕ jumps, ▲ toggles
  Armour, L3 sprints at the suit's sprint speed, a half tilt moves slower).
  It also parses `main.js` with `node --check` and checks its wiring (pads
  only through `listPads` and `choosePad`, the native message, the blur
  pause, the click after pad play), and runs `tests/js/main_pad.mjs`: the
  real `main.js` in a node vm (fake page, fake clock, fake
  `getGamepads()`), 19 checks: the critic 2 cases (menu lock after play,
  wake and focus loss, a drifting stick, the mouse quiet time on the canvas,
  the locked pointer and the pause menu, Forge's focus message, the pad-lost
  pause, the error message to Forge, the hint text), the critic 3 cases
  (gentle stick play and the touchpad, focus loss mid-walk, the pad lost
  with a second pad, also when the disconnect event comes first, Enter on
  the menu), the critic 4 cases (a stick drifting after pad play: one
  click hands the mouse back; focus coming back locks the menu again)
  and that every name `main.js` imports from the game's own
  modules is exported there (the vm cannot see a broken import line, which
  would stop the game in a browser). 9 of the first 11 failed on the code
  before b538a50; run against b538a50's game files, the critic 3 checks
  fail there, 5 in each file; the 7 checks added or rewritten for critic 4
  fail on cdcaed9's.
- Forge side (`~/Forge/tests`, novelforge's venv): `test_forge_pad.py` and
  `test_forge_mic.py` 13 pass, 1 skip (no pad plugged in), including the
  hub's `forgeWindowActive` run in node on fake frames;
  `tests/browser/check_gamepad_webkit.py` and `check_popout_pad_relay.py`
  pass in an off-screen WebKitGTK 2.54 view (software only, no pad).
- The laptop's driver, Bluetooth, permissions and WebKit gamepad support, by
  command (the library doc lists what was run and found).

Not verified (Emerson asked for no browser runs tonight, 2026-10-08 21:36):

- Forge has not been restarted, so the hub and `forge.py` changes (the
  focus relay too) have not run in the real window.
- The game page has not run since the pad work: no headless Chrome, no
  Forge window. `main.js`, `hud.js`, `game.html` and `game.css` are checked
  only by `node --check` and the static checks. First thing to try: open the
  game, plug the pad in, press a d-pad arrow, then ✕ on Play.
- A real DualSense (none was connected), rumble on it, whether WebKit sends
  pad input to a window without focus (pad play pauses on blur either way),
  and the raw fallback layout (written from the hid-playstation evdev order;
  no browser seen using it).
- The feel numbers (deadzone 0.15, look 3.0 and 2.0 rad/s, curve 1.7,
  trigger 0.3 and 0.2, sprint rest 0.25 s, menu stick 0.6 and 0.4, menu
  rest 0.12 s, mouse quiet 2 s) are first guesses; tune them in
  `controls.json`.

## Visual pass (Relay task 116, 2026-10-08)

Built from creative A-C and Emerson-view items 3, 6, 7 and 9:

- Reach dome: the range test's map now carries each cell's arm direction
  (`dir`, body frame) plus `gh` and `reach_m`; the 3D view draws every
  reachable cell as a round dot at arm's length round the shoulder, coloured
  by its level (`View3D.showReach`, "Reach" layer). Other tests remove it.
- Gimbal-lock cones: `layout()` adds `lock` (warn and fail half-angles from
  the run's own rules, asin(0.15) = 8.63° and asin(0.05) = 2.87° by default,
  and the upper-arm length); the view draws two cones each way along axis 1
  from the exo centre ("Lock zones" layer); the fail cone brightens when the
  frame has a lock issue. Cable suits have no `lock`.
- What that edit did: after a live re-run caused by an edit, chips under
  the edited knob or field list up to four numbers it moved, before -> after
  (test numbers and game stats), or "no change in this test".
- Suit colours: mechanism parts keep their base colour (carbon pods, metal
  struts, a cyan twist ring) on a pass and glow amber or red on a warning or
  failure; the "Heat colours" layer brings back green, amber, red on every part.
- Cameras: Shoulder sits 0.6 m from the joint, in front and out to her
  right; Front is framed from her height (head bone).
- Planned models: the person, suit, mechanism, readout, pose box and dome
  are cleared and the model's plan text shows large over the empty stage.
- Plain words: the shoulder motors read lift, swing and twist (J1, J2, J3)
  in cards, tiles, issue lists, charts, the compare rows and the part table
  (core text is rewritten on the page by `plain()`); a motor's hover line
  names its drive and the drive's own note from the data. A passing test
  with an orange card reads "Pass, with warnings".

Only fields were added to the API; no number changed (277 pytest pass).

Verified: `tests/test_benches.py` `test_rom_cells_point_the_right_way` and
`test_lock_cones_agree_with_the_lock_check` (every cell of a lateral-gimbal
sweep at 5°: inside the fail cone exactly when the check fails on lock);
check_ui 61/61 in headless Chrome with new checks for the dome (363 dots,
0 on another test), 4 cones, the Shoulder camera distance (0.60 m), the
headline, no J1-J3 in cards, tiles and tables, a motor hover line, the lock
tile red at plane -30 elevation 140, the 7075 weight chips (suit mass 20.7
-> 22.7 kg, sprint 5.84 -> 5.70 m/s), and the planned screen and its way
back. Screenshots looked at: 2a shoulder camera, 2b dome from the front,
2c back, 2d lock pose, 4b chips, 6b planned.

Not done from those lists: the taller 3D panel, the ghost suit and hair
back with Suit off (Emerson-view 6), "J2 side" as a Left/Right pick and
hover lines on every editor field (9).

After the critic (all its findings fixed, 2026-10-08 night):

- The canvas's camera note is `data-view`, not `data-cam`: the canvas no
  longer matches the camera buttons' selector, so clicking the 3D view does
  not reset the camera.
- Chips come only from a real edit (`emit("profile", "edit")` from `edit()`;
  loading, undo and redo bring none), a reset button counts as an edit of
  its row, the row is the one edited when the run started (`delta-start`),
  a field row rebuilt by its own edit is found again by its title, and old
  chips elsewhere are cleared.
- The plan box hides on an error and whenever a built model loads; the Pose
  button is disabled on a planned model.
- "Pass, with warnings" only for a card at warn level (check_ui matches).
- The editor names the motors too: joint folds read "Lift motor ·
  flexion", drive tags read "lift swing twist". `MOTOR`, `motorName` and
  `plain` moved to `store.js`.
- Closed helmet for the pilot (Emerson: the default pilot must not be a
  girl): `exo_full.json` skin has `closed_helmet: true`; `suit.js`
  `closeHelmet()` hides the VRoid face and hair and puts a carbon helmet with
  a cyan visor on the head bone. The game loads exo_full too, so its pilot
  wears it. The body under the suit is still the only VRM on disk
  (HairSample_Female); a male or neutral VRM needs Emerson to pick one.

A second critic on those fixes found four more, all fixed: dropping
stale knobs after an edit re-runs with that edit's before-numbers (reason
"stale") instead of wiping the chips; Reset all and a model's Reset clear
the chip row (`touched(null)`) so their chips do not land on the last field;
the Pose button is enabled again as soon as a built model loads, even if its
run then fails; chips only compare runs of the same model and test
(`resultFor`). Its note, not fixed: the closed helmet is not one of the
view's suit parts, so with the Suit layer off the dark dome stays and the
face stays hidden, and it sits under the suit's own helmet part; decide
whether that is wanted when looking at it.

Verified: 277 pytest pass, `node tests/js/suit_skin.mjs` prints ok 15 (three
helmet checks), every changed module parses in node, black and pyright clean.
Not verified: none of these were seen in a browser (Emerson asked for no
Chrome runs tonight); check_ui was updated for `data-view` and the warn
headline but not run. Emerson to look tomorrow: run `tests/check_ui.py`, then
the helmet in Exo Lab and the game, chips after a field edit with rebuild
(Mechanism pick), and a planned model.

## Next (plan section 10)

1. Close fit follow-ons: the left arm (only the right arm moves now),
   legs and helmet through leg and head motions, and the reviewers' visual
   items in `tester.js`, `view3d.js` and `check_ui.py` (a follow-on task).
2. Cybernetic arm and leg: models, specs, tests (grip, lift, range, socket).
3. Bipedal and spider mechs: models, specs, tests (stability, leg loads,
   gait, drop).
4. Game depth, golden test vectors for porting, `PORTING.md`, performance.
