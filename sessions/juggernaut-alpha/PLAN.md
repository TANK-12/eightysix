# Eighty Six 0.1 alpha: the 12-session plan

date: 2026-09-29 · for: both (Emerson and every Claude session in this wave) · written by Tetsu from Emerson's answers

**Plans after 0.1 (2026-10-08):** the spec to 1.0 (Relay 97) and its companion, the AAA plan and engine portability
(Relay 101), are in `~/Forge/docs/library/eightysix/` (`2026-10-08-spec-and-roadmap-to-complete.md` and
`2026-10-08-aaa-plan-and-engine-portability.md`). This file's targets stand unless those say otherwise.

**Start line for every session:** `Read ~/Forge/sessions/juggernaut-alpha/PLAN.md and do lane <ID>.`
Read this file and `2026-09-29-supplement-physics-combat.md` beside it (Emerson's physics and combat details; where they differ, the supplement wins), then your lane's section, then `results/` for the lanes you depend on. Nothing else unless your lane says so.

## The goal (Emerson, 2026-09-29)
A new game, **built from scratch**, that is stable and polished: a great-looking map where you walk the
Juggernaut around and fight basic Legion AI, with far better animation than anything so far. It is a base
to build on later, so spend the resources on a strong foundation. Emerson tests it himself around
session 8 (after window 4), so it must be **playable by then**; windows 5-6 add to it and fix his notes.

### Raising the bar (Emerson, 2026-09-30) — every session from now on
**The game should be fun first, and every bit of that fun must come from real physics.** The Juggernaut can
only do what motors, actuators, batteries and materials we have today could really do. Where the anime and
real engineering disagree, find the version that is both exciting and possible; never fake it with forces
that come from nowhere, teleporting, or motion nothing could produce. Masses are the realistic ones
(`~/Forge/docs/library/juggernaut/2026-09-30-juggernaut-realistic-mass.md`).

**Explore, don't just complete.** Each session tries ideas beyond its checklist (a new movement trick,
a better camera moment, a smarter way to build a map), keeps what makes the game better and writes down what
it tried and why it kept or dropped it. The target is that the game keeps getting better and better: each
session leaves it clearly better to play, to look at and to run than it found it, and shows how (numbers
before and after, and screenshots).

What "great" means, and where it falls short today (Emerson's own playtest):
- **Plays great:** fast, responsive and physical. Today it feels too slow, the slide is hard to find, the
  body scrapes the ground and gets stuck on things (A3 "Next" items 1-2).
- **Looks great:** today the lighting is the weakest part, along with a grainy, noisy filter over the image,
  and surfaces look too shiny. Fix these first: find where the grain comes from (post effect, dithering, low-res
  effects, TAA off) and remove or replace it; make materials read as worn, painted metal, concrete and dirt
  rather than plastic; give each map lighting that looks deliberate, like a film.
- **Runs great:** holds the preset fps targets on this laptop while looking better, not by looking worse.
- **Great menus:** clean, readable, quick to use with pad and mouse, in the anime's style.
- **Prove "better and better" with a scoreboard.** A fixed-route bot run (`tools/bot/`, same seed, same
  route across Ashen valley) every session records: top speed, 0-50 km/h time, slide distance and turn angle,
  stuck events, belly scrapes on flat ground, leg-swing turn rate in the air, fps per preset (no Blender job
  running), and the same six camera shots. Each session appends a row to
  `~/Forge/docs/library/juggernaut/<date>-eightysix-scoreboard.md`. No session makes a number worse without
  saying why in its results.
- **Emerson can find what's new.** He couldn't find the slide in version 5. Every session ends with a build and
  a 3-5 line "try this" note at the top of its results (what changed, which keys). Every new move appears in the
  controls tips, and the first time a move is possible a small hint shows (a setting turns hints off).
- **Idea to explore: power as gameplay.** The realistic mass includes a 350 kg power pack. Sprinting, reeling
  the wire, the autoloader and every actuator draw on one power bus with a real peak output and actuator heat.
  At the limit, choices matter (sprint or reel, fire or dodge). Game mode is generous, test bench strict. That's
  fun from real limits rather than from breaking physics. Try it, keep it if it plays well.
- **Runs great means no trade-off.** The small map already runs below target on Medium (36 fps, target 45)
  and High (23, target 30). The look pass must hold or raise fps: measure the cost of each effect and spend it
  where it shows.
- **Show off the Juggernaut (Emerson, 2026-09-30).** "The model looks cool; I want to be able to look at it,
  in the game and in the menus." A **Hangar** screen from the main menu: the Juggernaut in a well-lit hangar,
  orbit, zoom and pan with mouse or pad, light presets, the variants and loadouts, and parts you can point at
  with their name and realistic mass. The main menu itself shows the Juggernaut behind the buttons, slowly
  turning or idling. In the game, a **photo / inspect mode** (from pause or a key): time freezes, a free
  camera orbits your own mech (and anything near it), with the HUD hidden and a screenshot key.
- **Deadline: the game looks cool within the next 4 sessions** (by the end of A4/B4). Default owners: lane
  **B4 does the look pass first** (lighting, the grain, the shiny materials, a proper sky and atmosphere),
  then sound; lane **A4 builds the Hangar, the menu showcase and photo mode** alongside the Legion AI. If
  either runs out of room, the other picks it up; A3's next session may start them if it finishes early.
  Before/after screenshots of the same views prove it.
- **Great maps:** much better than what exists now: places with a shape and story (ruined towns,
  battlefields, forests), cover worth using, routes that suit the Juggernaut's speed, slide and wire.

- **Do not base anything on the old Godot games** (`~/Games/juggernaut`, `~/Games/juggernaut_walk`). They
  were a proof of concept. Leave them where they are (never delete them); do not copy code from them.
- **Engine:** Godot 4.7.2 (installed as `/usr/bin/godot`) with Jolt physics, unless a lane finds a concrete
  reason something else would work better (then post it on the board and write it in results before switching).
  Launch: a Linux export plus a Forge hub entry, and it runs from the editor too.
- **Graphics presets, four of them:** Ultra ("too hard" for this laptop, for future hardware), High,
  Medium, Low. Targets on the Iris Xe with no other GPU load: Low 60 fps, Medium 45, High 30, Ultra no
  target. **Only measure fps when no Blender job is running** (`pgrep -f "[b]lender -b"`): the old game's
  "slow" numbers came from renders running at the same time.
- **Physics:** two modes from the same data. *Game mode:* "magic motors" that feel right. *Test bench mode:*
  real actuator limits (torque, speed, power draw, heat), so Emerson can load his own Juggernaut designs and
  see if they could really walk. Every actuator is data (one registry entry per joint), never hardcoded.
- **Controls:** steep learning curve, rewarding, lots of controls. PS5 pad and keyboard/mouse both
  first-class through named input actions. Analog throttle, response curves and dead zones as settings.
  Controller rumble per event. Controller speaker sound and adaptive triggers: research only (Godot may not
  reach them on Linux); report what works, do not sink a session into it.
- **Animation:** procedural where it can be. Rocky terrain and constant movement, so feet place themselves
  (IK on the ground), the body sways and settles from physics, gaits come from a gait generator tuned against
  `~/Models/juggernaut/refs/anime-motion/ANALYSIS.md`. **The main gun stays locked to the body's heading**
  (no independent traverse: see the supplement) and rises at rest; the body turns to aim. Enemies animate procedurally too.
- **Cameras:** basic third person, a first-person cockpit view, and a **Handler command view** (the Para-RAID
  commander's view: a higher tactical camera to order the squad).
- **Friendlies:** allied Juggernauts with slight variants (sub-arms, blades, Model 1 as a variant). Variants are
  loadouts: one registry entry each.
- **Maps:** a smaller hand-made map that looks great (about 1 km), **and** a bigger map built on terrain tech
  whose collision works, because the old game's big map had broken terrain, building and collision. You must
  be able to **climb and grapple** (wire anchors) on both.
- **Models:** the Juggernaut (Model 2) looks good but slightly off: **one session** fixes that (lane B1).
  The Legion looks not bad but not great yet, mostly missing inferred detail where the references cannot
  show a part: **one session** for all three (lane B2). Where a part cannot be seen, build its most likely shape.
  Assume accuracy fixes do not break the animations. No STLs in this wave.
- **Textures:** the Undertaker logo on the side. Other textures only if there is usage to spare, because the
  model may still change; do not spend long on them.
- **Assets that will not change** (57 mm rounds, spent casings, shrubs, rocks, basic walls and buildings,
  debris, volumetric clouds and fog): make these look great, because they are used everywhere.
- **Sound:** realistic, 3D spatial (distance, occlusion, reverb zones). Download CC0 sounds or make them;
  collect every candidate in one review folder with a listening page so Emerson can pick. **Music:** the *86*
  soundtrack, English and Japanese versions (opening and ending themes, the score); if 1-hour loop uploads
  exist, fetch those and cut them as needed. Audio at 320 kbps, or the source's own rate when it is lower
  (re-encoding a lower-rate source up to 320 adds nothing). Personal use only: the music stays on this laptop,
  never in anything shared. Music is otherwise a later job.
- **Menus:** a great-looking first theme, with themes switchable (one registry entry each). Emerson loves
  settings and sub-menus; make them deep and neatly lined up. A tutorial only as a stub that is off by
  default; he decides after testing.

## How the sessions run
- **Two sessions side by side, one per account.** Track A on the default account, track B on `second`
  (`CLAUDE_CONFIG_DIR=~/.local/share/forge/claude/profiles/second claude`, or Relay picking the account).
  Each has its own 5-hour meter. Opus 5.5, high effort.
- **Pacing:** ignore the 70/92 rule for this wave. Work at full speed. At **95%** (Emerson, 2026-09-30; was 97%) of *your own account's*
  5-hour meter (`python3 ~/.claude/tools/usage.py`; the second account reads with `CLAUDE_CONFIG_DIR` set),
  write your handoff and stop. Stop by 99% of the weekly meter. Answer Emerson's questions in chat, every one.
- **Handoff:** `results/<lane>.md`, kept current as you go (so a crash loses nothing): what is done and
  **verified** (with the check), what is only reasoned, what is next, exact file paths. Update your line in
  the status table below.
- **Fresh session when the old one gets expensive** (about 150 tool calls, or context heavy): write the handoff,
  then start the continuation yourself with Relay on the same account (`relay` terminal command; guide in
  `~/Forge/apps/relay/README.md`), start line `... do lane <ID> (part N+1).` Then archive yourself: copy your
  brief to `archive/<date>-<lane>-partN.md` and your transcript (`~/.claude/projects/<dir>/<session>.jsonl`, the
  second account's under its profile) gzipped into `archive/transcripts/`. Lane A1 checks first that Relay can
  really start a session on each account; if it cannot, sessions skip self-handoff and just run to 97%.
- **Talking:** crew board `forge` (`python3 ~/.claude/skills/crew/crew.py`) for claims, "export ready", render
  slots; SendMessage to your partner session for direct questions. Claim your folders at start.
- **No subagents,** except one critic run in B1 and B2 if the session judges it worth it (a critic round
  costs about a quarter of a window).
- **One heavy Blender render at a time, machine-wide**; post on the board first. Final renders only at the end
  (lane B6), unattended. Keep every check image in numbered `images/` folders; never delete images or milestones.
- **Definition of done per lane:** tests (GUT for game logic, run headless), a scripted run with screenshots
  for anything visual, `black` and `pyright --pythonpath ./.venv/bin/python` on any Python touched, README and
  results updated. "Verified" only for what was run.

## Where things go
| What | Where |
|---|---|
| The new game | `~/Games/eightysix/` (Godot). `README.md` is its verified list; `data/*.json` are the registries |
| Juggernaut Model 2 | `~/Models/juggernaut/model2/` (latest `mk2_m22_canopy.blend`, fix list `CRITIC-A.md`) |
| Legion | `~/Models/legion/` (latest `blends/*_m11_hi_*.blend`) |
| Game exports | each model folder's `export/game/` (glb), copied into `~/Games/eightysix/assets/models/<name>/` by a tool script |
| Sound review | `~/Games/eightysix/assets/audio/review/` with `index.html` (play, keep/drop, writes `review.json`) |
| Music | `~/Music/86/` (personal, outside the game repo), listed in `data/music.json` by path |
| This wave | `~/Forge/sessions/juggernaut-alpha/` (`PLAN.md`, `results/`, `archive/`) |

## The game's skeleton (lane A1 builds it; everyone keeps to it)
Registries in `data/`: `mechs.json` (variants and loadouts), `parts.json` (armour, actuators with torque/speed/
power, health), `weapons.json`, `enemies.json`, `maps.json`, `graphics_presets.json`, `themes.json`,
`input.json` (actions and default bindings), `sounds.json`, `music.json`, `tuning.json` (every feel number).
A new mech, enemy, map, weapon, theme or sound is one file plus one registry entry. Code in `scripts/` by
system (`mech/`, `locomotion/`, `combat/`, `ai/`, `world/`, `audio/`, `ui/`, `camera/`), scenes in `scenes/`,
tests in `tests/`, tools (export, bot runs, fps logs) in `tools/`.

## The lanes (window = one A lane and one B lane side by side)
| Window | Track A (default account) | Track B (second account) |
|---|---|---|
| 1 | **A1** Foundation | **B1** Juggernaut model fix and game export |
| 2 | **A2** Locomotion, procedural animation, physics | **B2** Legion model pass and game exports |
| 3 | **A3** Combat, grapple, climbing, damage | **B3** Small map and the asset kit |
| 4 | **A4** Legion in game, AI, mission loop: **playable** | **B4** Sound, music, rumble |
| (Emerson tests here) | | |
| 5 | **A5** Friendlies, variants, Handler view, cockpit | **B5** Big map, buildings, destruction |
| 6 | **A6** Polish, Emerson's notes, performance, release | **B6** Test bench mode, textures if room, final renders |

If a lane overruns, it continues in the next free slot on its track and everything behind it slides; the two
spare sessions (11 and 12) exist for that. A lane that finishes early starts its track's next lane only if
that lane's inputs are ready, otherwise it deepens its own work from its list.

### A1 Foundation (~/Games/eightysix, new)
Project, folders and registries above; Jolt; the four graphics presets (resolution scale, shadows, SDFGI or
not, volumetric fog, draw distance, LOD bias) switchable live; input actions for pad and keyboard/mouse with
rebinding, dead zones and curves; rumble helper. Main menu, pause, settings with sub-menus (graphics, controls,
audio, gameplay, accessibility), theme registry and a first great theme. Loading screen. A throwaway test
level with a stand-in box mech so the loop runs end to end. Tools: headless GUT run, a bot run that plays a
scripted input file and saves screenshots, an fps logger per preset. Linux export preset and a Forge hub entry
(one registry entry in the hub). **Check Relay self-handoff on both accounts** and write the result at the top of
`results/A1.md`. Look up which Godot addons would help (terrain: Terrain3D by TokisanGames; tests: GUT) and
list them with source in results for Emerson; do not install until he picks (A1 can write its own tests
without GUT meanwhile).

### B1 Juggernaut model fix and game export (~/Models/juggernaut/model2)
One session to make Model 2 match the OneDrive set: work through `CRITIC-A.md`, the cockpit shell (canopy and
snout) first, then the slight angle and size mismatches part by part. Build the most likely shape where the
references cannot show a part. One critic run at the end if worth it. Then a **game export**: a lighter copy
(target triangle budgets per LOD, detail baked to normal maps), pivots at the real joint axes, sockets for the
gun, sub-arms, wire anchors, cockpit camera and the Undertaker logo decal, collision shapes per part, the
actuator list with plausible torque and power figures for `parts.json`. The full model is never altered for
the game. Save as the next milestone number. Post "Juggernaut export ready" on the board.

### A2 Locomotion, procedural animation, physics
The Juggernaut on rough rocky ground: gait generator (walk, run, sprint, turn on the spot, sidestep, skid,
jump with charge, landing that punishes a bad angle) tuned to `refs/anime-motion/ANALYSIS.md`, IK foot
placement, body sway and settle from a physics body, momentum and turning inertia, traction breaking into the
anime skid. Game-mode motors from `tuning.json`; actuator limits read from `parts.json` so test bench mode
(B6) only flips a switch. Third-person camera with weight. Uses B1's export, or m22 as a stand-in until then.
Tests: feet stay planted (slip under a set distance), no falling through ground over a 10-minute bot run.

### B2 Legion model pass and game exports (~/Models/legion)
One session for all three (Ameise, Grauwolf, Löwe): fill the missing inferred detail where references
cannot show a part, closer to the anime, more mechanical detail. Critic once if worth it. Game exports like
B1's (LODs, pivots, collision, weak points as named parts, muzzle sockets). Post "Legion exports ready".

### A3 Combat, grapple, climbing, damage
57 mm main gun: ammo count, reload, recoil into the body, ejected casings, projectile ballistics, impact
effects; gun locked to heading, raised at rest. Wire anchors: grapple to swing, pull and climb, plus a climb
on ledges and slopes that the legs can grip. Per-part damage from `parts.json` (armour, legs, actuators):
a hurt leg limps, lost armour exposes internals, damage decals and scorch on the textures, permanent-or-not
setting. HUD: ammo, damage diagram, heading.

### B3 Small map and the asset kit
The ~1 km hand-made map: rocky ground with real collision, ruins, roads, a lake or river, lighting and
weather that look great on each preset, volumetric clouds and fog. The asset kit, built to last: 57 mm
rounds and casings, rocks, shrubs and grass, basic walls and ruined buildings (modular, with break-apart
pieces ready for B5), debris, craters. CC0 sources (Poly Haven, ambientCG) or Blender-made, each listed in
`assets/SOURCES.md`. Climb and grapple points marked in the map data.

### A4 Legion in game, AI, mission loop (playable)
Enemies from B2's exports with procedural gaits. AI from `enemies.json`: Ameise scout and call others,
Grauwolf packs that flank and close in, one Löwe as the heavy fight; perception by sight and sound,
patrol, alert, attack, retreat. A mission: start, objective, waves, win and lose screens, restart. Everything
from windows 1-4 joined into a Linux build. **Write `~/Games/eightysix/PLAYTEST.md` for Emerson:** how to
launch, controls for pad and keyboard, what to try, where to write his notes. Post on the board that it is ready.

### B4 Sound, music, rumble
Sound library: footsteps per surface, servos and hydraulics, the gun, casings, impacts, Legion sounds, wind
and ambience, UI. 3D spatial audio: attenuation, occlusion, reverb zones per map area, a mixer with buses.
Everything in the review folder with the listening page. Music: *86* soundtrack in English and Japanese
versions, 1-hour loops where they exist, cut and tagged, into `~/Music/86/` and `data/music.json`. Rumble
patterns per event in data. Report on controller speaker and adaptive triggers.

### A5 Friendlies, variants, Handler view, cockpit
Allied Juggernauts with AI (follow, hold, attack target, regroup) and loadout variants from `mechs.json`
(Model 1, other sub-arms and blades). The Handler command view: tactical camera, orders to the squad, Para-RAID
style overlay. First-person cockpit view with instruments and HUD (a basic cockpit, the Star Citizen-level one
is later). Emerson's playtest notes come first if they have arrived.

### B5 Big map, buildings, destruction
The bigger map on terrain tech whose collision works (Terrain3D if Emerson approved it, otherwise chunked
height maps with Jolt height-field shapes), streaming so it stays within the presets' fps, towns from the
B3 kit, climbing and grappling everywhere it looks possible. Destruction: walls break into chunks, buildings
take damage in stages.

### A6 Polish, notes, performance, release
Emerson's playtest notes, then a bug bash through bot runs, fps on all four presets (logged in the README),
menu and theme polish, settings lined up, tutorial stub (off), final Linux build and hub entry. README and
`PLAYTEST.md` brought up to date.

### B6 Test bench mode, textures if room, final renders
Test bench mode: load a Juggernaut design (a Blender export plus its `parts.json` actuators), real motor
limits, power supply and heat, readouts of torque, power and failures; a flat test ground and a rough one.
Then textures if usage is left (Undertaker livery details, weathering). Finally one unattended render job
of game screenshots and model stills to `~/Desktop/Juggernaut/Renders/Alpha 0.1/`.

## Status (each session edits only its own line)
| Lane | Status |
|---|---|
| A1 | **done** 2026-09-30 (part 2, Yuna): tests 55/55, off-screen bot runs + screenshots, fps per preset (Low 96 / Med 54 / High 46 / Ultra 15), B1 v2 synced, export preset (templates wait on Emerson). results/A1.md |
| B1 | part 6 (2026-10-07, Nene relay-64): dome rear (critic fix 5): rolled rim on the blueprint arch, recessed grille of 14 slats on each dome flank, rear octagon plates now finned vents; m38, then critic fix m39 (grille plate was buried under the canopy), export v7 (mesh only, joints/sockets same) synced and committed in the game (2feb915); test_domerear (red then green, twice), game Juggernaut tests 78/78, bot images/640. Next: thigh ram, snout brow + hood pipe, gun-mount arch, smaller fixes, one per session (results/B1.md part 6) |
| A2 | **done** 2026-09-30 (parts 4-5, Hayato ejb-0a): hull colliders, sole-socket feet, real leg joints, gun fixed to the body, live stance/shine controls; part 5 from Emerson's playtest: springs over the feet (no more collapsing, sprint on 4 legs), game-mode jump (works while running, leap, heavier fall), anti-tip keel, knee rams stay on the legs. 79/79 tests. results/A2.md |
| B2 | part 1 (2026-09-30, Yui ejb-be): **game exports ready** for all three (export/game/, from m12: per-part hull colliders, masses, joints, legs, sockets, weak points; Godot load + socket/collider placement checked; 11 tests) and an inferred-detail pass (m12). Next: Grauwolf and Löwe turret reshape (results/B2.md) |
| A3 | parts 1-5 **done** (parts 4-5 2026-10-01, Tetsu ejb-d4): realistic mass, real recoil, physics-only air, crosshair wire with real winch/cable, 70 km/h gallop, analog slide, belly scraping fixed, sub-arm 12.7 mm guns, legs no longer straighten at speed (6-8% -> 0.23%). 145/145 tests; build 007. results/A3.md. Leftovers listed there; track A next: A4 |
| B3 | part 2 (2026-09-30, Chihiro ejb-73): Ashen valley + kit; ground holes fixed (3 overlapping detail rings), anchors on surviving blocks, town look, 10 viewpoints. Low 75 fps; Medium 31-45 (noisy, not verified at 45); High 23. Next: fps with the desktop idle, map-edge wall, outcrops (results/B3.md) |
| A4 | **part 7** (2026-10-02, Nagi relay-29): Hangar screen (5 light presets, orbit, part picking, photo) and the Juggernaut behind the main menu (setting to turn off), Legion sounds from an enemies.json block, Dyneema rope mass (game mech 5563.7 -> 5493.9 kg); test_hangar 17/17, test_legion_sounds 5/5, screenshots images/409, menu 81-87 fps vs 145 plain. Next: Hangar variant drives Deploy (A5), arc-dot and big-blast fps checks. results/A4.md "Part 7". **part 6** (2026-10-02, Sora ejb-ef): Emerson's ask, bigger shell hits and hit dust on two sliders (Graphics > World detail > Combat effects, default 1.6x, look only), the dart's dirt kick, HE fireball and clods; wire anchor arc as screen-sized dots; test_combat_fx 5/5, test_grapple 11/11 (7cde48e). Next (part 7): Hangar + menu Juggernaut, Legion sounds (signal from track B), Dyneema mass. results/A4.md "Part 6". Part 5 (Kaede relay-16): legs crossing, cockpit view, HUD, aim modes, hints. **part 4** (2026-10-02, Tetsu/Ren ejb-3e): Legion walk/run/cliffs/edge wall/legs fixed (0135a1b), 57 mm mark + sub-guns fixed by default with a setting (5f491b3); 229/229. Next (part 5): legs crossing, cockpit view, HUD, aim modes. results/A4.md. part 3 (2026-10-01, Ami/Tetsu ejb-a4): Emerson's notes: flips one turn every way (side was 7.7 rolls), feet out of the ground, park on P only (photo O), gun solid, walk/run answers the feet (squat 1.3 deg, was 0); flaky AI tests fixed, Kenji's part 2 committed; suite 205/205; version 010. Next: Legion sounds, Hangar, move hints. results/A4.md. Part 2 (Kenji): **playable** mission, Legion brains, honest HE blast |
| B4 | part 2 (2026-10-01, Kana ejb-60): Undertaker emblem decal (editable SVG, emblems.json), foot dust at a run, river gorge bends past the edge with water, slab across it fixed; builds.py: versions only via `save --note` from a clean tree (Emerson's 007/008 question). Part 1 (Tetsu ejb-f5): look pass and synth sound. Music and mix: audio session (Noa ejb-b9, B4-sound-music.md). Next: rumble with a pad. results/B4.md |
| B4 | sound part 2 (2026-10-01, Noa ejb-b9): real downloaded sounds (1,816 in ~/Forge/shared/sound_library) with a pick + level per sound in Settings > Audio > Sounds; music (23 tracks in ~/Music/86) with a menu/explore/combat player in Settings > Audio > Music; 57 mm shot -13.2 -> -7.6 dBFS (Godot 3D max_db ceiling lifted); servo hum off by default; shells bang instead of ding. 15/15 audio tests. results/B4.md "Part 2 (Noa)" |
| B4 | part 3 (2026-10-01, Tetsu ejb-21): Emerson's notes: sun calmer and bloom only above a threshold (facing the sun, top third 160 -> 108), the grain was the ground's pebble detail (31-38 % less), no synth sound defaults (BigSoundBank CC0), music = the 42-track OST in order by default + one original of each OP/ED, extras behind a switch, 1-hour loops gone; selector arrows both ways; test runs no longer overwrite his settings; far-cliff stripes gone (far ground normals, 621cb21). Same fps (A/B). 201/201 tests, fbf945c. Next: grime build-up, rumble, then B5. results/B4.md "Part 3" |
| B4 | part 4 (2026-10-02, Rika/Tetsu ejb-6f): dirt builds up on the Juggernaut over a sortie (ground covered, landings, skids; setting Dirt builds up), 0.23 per km at a gallop measured live, test_look 14/14, suite 210/210, bb47933. Rumble still waits on a pad. results/B4.md "Part 4" |
| A5 | parts 1-2 (2026-10-02, Minato/Tetsu ejb-42, hey): Spearhead squad as full physics Juggernauts driven by AI pilots through the same controls, orders 1-4 + Handler view (Tab, click to move or attack a marker, field HUD hidden), fires only when the real impact lands and no friendly is near the line, Legion hunt the nearest Juggernaut, way round walls + unstick, squad on the end screen; 2 wingmen cost no measurable fps on Medium (42.5 vs 42.2); test_squad 11/11. **Version 013 saved.** Open: scoreboard air turn ~80 deg/s (was 3.5-7.3) and 1-2 belly scrapes after the slide, repeatable with the squad off, cause not found (results/A5.md "Open"). Next: that bisect, Emerson's notes on 013, wingmen slide/jump/wire. results/A5.md |
| B5 | part 7 (2026-10-02, Relay 23, default): finale arrives twice in a row (images 388, 389, check_arrival exit 0); Ameise/Grauwolf stop rolling over in small-map shell craters (`ai.slope_margin_deg` 8, flips 9 -> 1 of 24 in the sweep, test), 351/351; NOT yet re-run: the finale with the margin (part 8 job 1). results/B5.md "Part 7". part 6 (2026-10-02, Tetsu ejb-ab): every preset native resolution, no upscaler or sharpening (Emerson; big map Low 64 / Medium 53 fps on open ground, towns 50 / 42); the Löwe climbs out of the finale hollow (step-up = slope + one ledge, bearing feet, tuck under the hip, look-ahead one ledge per body length; real-ground test 3/3); 295/295; **version 011 saved** (6d763b5). Next: finale arrival re-run x2, town fps. results/B5.md "Part 6". part 5 (2026-10-02, Relay 22, default account): the Legion looked at on 15/27 degree hills and a 24 degree traverse after the hip change (all three types lean with the slope, legs fine, `images/355-b5_hillside`, nothing to fix); real HE shells at the Ash bridge: a bearing took 5-6 shells, now `weak_hp_scale` 0.5 and one broke on the 6th fired shell (`images/367-b5_bridge_shell`). Arrival re-run (368): Grauwolf x2 and Ameise arrive, the Lowe stalls 80 s at x -160 z 1075 and does not (657 m): next. fps on a quiet GPU: Low 103, Medium 69, High 49, Ultra 15 (unchanged, the open item). Not done: Ultra work, rim rock. results/B5.md "Part 5". Part 4: **the Frontier sweep's last wave reaches the Juggernaut** (bot run 353; foothold retry, hips level to the hillside, crag-aware nav grid, `shake_free`; check `tools/check_arrival.py`). Parts 1-3: big map streamed 4 km + destruction, Frontier sweep + bridge, bridge beat, nav, keel (dc20068, ca436cc) |
| LOOK | 2026-10-02, Relay 26 (hey): world look pass: CC0 ground (dirt/turf/stones/gravel/rock) and masonry/steel shaders, a palette per map (big map overcast morning), Ultra is MSAA 4x with no TAA (sharpness 15.5 vs 4.5). Found the kit textures were uncompressed with no mipmaps (Low 22.7 -> 49 fps from the import fix alone); final big map fps Low 52 / Medium 44.5 / High 36.8 / Ultra 15 (vsync), town 47.5 / 40.4 / 37.1. Shots 392/393 before, 423/424 after. Not done: model upgrades, decals, baked AO. results/LOOK.md |
| V014 | **done** 2026-10-03 (Tetsu, hey): Emerson's notes after 012: 12.7 mm lag (Medium 18.8 -> 36.5 fps under fire), spawn-point sparks (effects in local coords), shot-off armour knocking the mech over, wingmen in the cockpit view, sub-gun muzzles, muzzle flashes, camera collision, Free roam + Keep exploring, wheel optics 1x-10x, HE dirt column + Shell tracers; 396/396; **version 014 saved**. Next: ricochet/near-miss, aim measured, first-person look (`2026-10-03-v015-brief.md`). results/V014.md |
| R2 | **done** 2026-10-03 (Relay 33, hey): rumble cannot stick or lag: every pad effect finite (dead-man), loops live only while refreshed + max_s, dropped on pause/focus loss, start on the same frame; test_rumble 18/18. Your saved settings have Rumble OFF: switch it on to try. results/R2.md |
| R3 | **done** 2026-10-03 (Relay 34, hey): first person draws the whole mech: only the pod shell around the eye (canopy, tub, side panels, lower side plates; `cockpit_hide`) is left out and casts no shadow while inside; hull, flanks, visor, sub-arms, barrel drawn and lit like third person; test_cockpit 9/9, neighbours green, before images/481-482, after 497/499/501. Not checked: shadow shimmer in motion. results/R3.md |
| R1 | **done** 2026-10-03 (Relay 32, hey): a ground that reads as real at 7 m on every map: patch-based no-tile sampling, metre-scale mottling, ragged road edges, dirt Ground105 and stones Ground112 at 2K; the test range and rough bench now use the shared ground shader, flat bench real concrete. Shots 483-487 before, 519-523 after; Low/Medium fps equal or better than before, High 10-20 % lower on the small map (GPU shared, see results). results/R1.md |
| V015 | **done** 2026-10-03 (Tetsu, hey): map list fits, L2/R2 pages, Winch size 1.4x, tracers from the muzzle, grapple line arcs, ricochet + near-miss crack (note 7), real-place maps (heightmap terrain + **Palouse grassland**, USGS lidar); with Relay R1 ground (new shader on every map), R2 rumble (+ Opus review fix), R3 first person whole mech; 427/427; **version 015 saved** (912acf5). Next: forest + city maps (`2026-10-03-maps-brief.md`). results/V015.md |
| After 015 | **done** 2026-10-03 (Tetsu ejb-cb, hey): grapple line stays on the launcher in flight, the dart rides on what it bit and pulls it, cockpit view from the front optical sensor (setting to switch back); 920c41e. results/AFTER015.md |
| LOOK2 | part 1 **done** 2026-10-03 (Koharu, Relay 37): washed-out cause = AgX white point never set, exposure 1.0, milky fog; now per weather in weather.json (white point 132-146 -> 171-185). Part 2 **done** 2026-10-06 (Mio, Relay 37): worn town walls (kit boxes carry open-edge data: bevel, grime, sill streaks, soot, mortar; block seams hidden), far rock at cliff scale with gullies and strata (no more grey plastic), backdrop rock relief. Tone held (white 170-211, nothing clipped); A/B cost 0.16 ms GPU; scoreboard Low 84 / Med 62 / High 42. test_kit_edges 4/4. Left: the ruined tower is a stack of cubes (geometry). results/LOOK2.md |
| CLIP | **done** 2026-10-06 (Koharu, Relay 38, hey): legs and camera no longer go through the floor. Camera sweep starts from open air at the mech (aiming down had buried the look point 1.8 m), legs fold about the hip against the ground like limp legs, spring rays ignore the ground's underside (Palouse shaking after a roll 53.6 -> 0.20). 18 moves x grounds: leg ticks under 528 -> 0, camera poses under 170/1200 -> 0; test_clip 20/20, test_flip 11/11, test_camera_collision 5/5; full suite 463/464 (the 1 is test_world_look: plaster/roof texture imports, not ours). Not done: getting up off its back by real leg pushes. results/CLIP.md |
| MAPS2 | **done** 2026-10-06 (Relay 36, hey: Sora, Nagi, Kaede): **Allegheny forest** (USGS 1 m, 4 km, ~100k firs as MultiMesh near mesh + billboard, trunk colliders, lanes 6.6 m+) and **Brilon** (real Sauerland town, DGM1 NRW + OpenStreetMap, roads 1.3x, 6018 houses with new PBR facade shader: windows, sills, soot, ruins; poles, wrecks, rubble props). test_real_maps 7/7, test_world_look 9/9, bots images 548-553; fps quiet GPU Low/Med/High: forest 49.5/37.3/25.8, town 77.8/61.7/42.3 (chase view). Next: forest High cost, breakable trunks, missions. results/MAPS2.md |
| LOOK3 | Half B **done** 2026-10-06 (Relay 39, 432c7d9): Allegheny misty morning (light shafts through the firs, mist in the hollows) and Brilon gold evening as their own weathers; firs with per-tree colour, crown AO, backlight; ragged scorch + wall crack decals capped per preset; every High/Ultra option measured, Ultra shadows 8192 -> 4096. Brilon High street 51 -> 34 fps, forest High in the trees 31 -> 30. Full suite 474/474. Open Allegheny views greyer than before (knobs named in LOOK3.md). Half A (mechs) **done** 2026-10-07 (Relay 40): real worn metal on both mechs (five CC0 ambientCG sets, triplanar since the exports have no UVs; AO cavities; dirt rising from the feet in height bands), the Legion's looks.py liveries in game (Settings > Gameplay > Legion livery: field worn, night, export), +0.75 ms GPU at Medium. Full suite 474/474. Version 016 saved. results/LOOK3.md |
| A6 | **done** 2026-10-07 (Asuka, Relay 51, hey): alpha 0.1. Tutorial stub off by default (data/tutorial.json, test_tutorial 4/4), settings lined up (lineup check, test_settings 9/9), menu subtitle + status line, bug bash 6 bots clean, fps test range Low 66.5 / Med 58.4 / High 35.2 / Ultra 15.1 in README, PLAYTEST.md current, hub tagline; full suite 479/479; **version 017 saved** (6bc599d), export boots. Open: Emerson's 3 questions (PLAYTEST.md end). results/A6.md |
| B6 | part 2 (2026-10-02, Relay 30, hey account): test bench mode **done**: part 1 physics + two grounds (`test_bench_flat`, `test_bench_rough`), HUD moved clear of the hull panel and checked by bot (`bench_check`, images/414), 29/29 bench tests, full suite 386/390 (4 failures not bench). Still open from B6: textures (Undertaker livery) and the final render job; optional re-size of parts.json actuators to 5.5 t. results/B6.md |

## Emerson's notes during the wave
- 2026-09-30 (during A2 part 4): **later sessions must make it look way cooler.** Every lane from A3 on treats
  how the Juggernaut and the game look in motion as a goal of its own (poses, gun, effects, camera, lighting),
  judged from screenshots, not only from tests.
- 2026-09-30, same session: **"make sure the game gets a lot, lot better."** Not only correct: each lane leaves the
  game clearly better to play and to look at than it found it, and says in its results what got better.
- 2026-09-30, same session: **the gun and chassis are fixed to the body; nothing follows the mouse up and down.**
  Body-tilt aiming and the parked gun raise are now settings (Gameplay: "Body tilts to aim", "Gun rests raised when
  parked"), both off by default. This answers the old vertical-aim question (A1 open question 2).
- 2026-09-30, same session: **mid-air movement "in the special way" and the slide** must not be forgotten: the
  recoil dodge (57 mm fired in the air = big reverse impulse) and the grapple are lane A3's; the skid/slide exists
  and A3 makes it feel great. He also wants stance and look adjustable for his own play-testing (done in A2 part 4).

- 2026-09-30 (during A3): **"movement in mid-air and basic shooting; aim up and down with the mouse by aiming the
  whole body."** Air control (steer and aim in flight) and body-tilt aim are now **on by default** (settings
  "Air control" and "Body tilts to aim"); off gives the supplement's pure ballistic jump and a level body. This
  supersedes supplement point 3's "zero air control" as the default and the earlier "nothing follows the mouse
  up and down" note.

- 2026-09-30 (after A3 part 3): **air movement physics only, and realistic mass.** "Only based on the movement of
  legs or whatever in real life would give the movement; small is fine; I want some mechanic of direction change;
  no teleportation or unphysical air movement." Supersedes the "Air control on by default" note above for air
  movement. Mass goes to the realistic aluminium-coffin figures (5.4 t loaded, not 12 t). Details for the next A3
  session: results/A3.md "Next" item 1.

- 2026-09-30, same day: **ground movement too.** "I don't like how slow it is; there is no sliding yet; it keeps
  scraping the bottom and getting stuck on stuff." Faster, a real slide, no belly scraping, no getting stuck,
  proven by a bot run. results/A3.md "Next" item 2.

- 2026-09-30 (late): **options and analog control over hand-holding.** "I just want options in this kind of stuff:
  control, hardcore; this will probably mostly be an analog stick game." Design every movement mechanic for
  the analog stick and triggers first, with how much of it happens set by how far you push, and expose the key
  figures as settings. Hardcore gives the most direct control. Don't pick a slow, safe default for him.

- 2026-10-01 (B4 part 3 / A4 part 3, one message to both tracks): sun far too bright and bloomy, the world too grainy
  and not good-looking, he hates the synth sounds (B); side flip far too fast, feet still clip the map, walking feels
  like an animation more than physics, the gun's recoil, Park only on P and not when standing still (A). **Music:** the
  official soundtrack is the standard and plays through in order; one original version of each song; **do not add
  tracks unless he asks**; everything else downloaded stays hidden unless switched on in settings. **Version 010:**
  whichever session has the most context left at the end saves it. **New sessions:** when a session gets heavy, start
  the next part as a fresh Relay session, not a subagent.

- 2026-10-01 (night, after playing version 010): **Legion AI and walking very broken** (they do shoot), their
  running broken (maybe the gait mode), they walk on cliffs and climb the map-edge wall to shoot him from above; **can't tell where the main gun aims** (only the sub-arm guns' crosshair,
  and those were put on the arms instead of fixed to the body as he wanted: make that a setting); **aiming modes
  as settings** with whole-body tilt, mid-air too if physically possible; **a little movement on the sub-arm guns** is welcome, **never on the 57 mm**, and **no recoil lessening** of any kind (no brake, buffer or scaling, not even as an option); **first-person view is broken**; **a better HUD**; **the Juggernaut's legs cross over and pass through each other** (new in 010?); **Legion legs as good as the Juggernaut's** (leg fold, knees, feet, hitboxes following).
  Track A part 4 does these first: results/A4.md "Emerson's notes after playing 010".

- 2026-10-02 (after B5 part 6): **graphics over frame rate.** "I don't care about fps, I want better graphics; I'll just
  copy this game to a better computer if I need to test at higher fps." Looks win outright: never trade looks for
  frames. Keep measuring fps per preset and report it, but the preset targets above are no longer limits. No upscaling
  or sharpening as the base (every preset native since B5 part 6). Share zips: only the newest version's are kept, each
  with an install script (`tools/builds.py share`, the hub's "Make share zips" / "Delete all share zips").

- 2026-10-02 (after playing 012): **aiming and shell effects.** Main gun aim bad in third person, the mark "locks onto
  the hills": he wants aim-at-the-mouse (crosshair = where it lands; the 57 mm stays fixed, the body turns and tilts to
  it); shells never land where aimed; sub-arm guns follow the body in first person but not really in third; the
  first-person model, its shadows and guns look bad; shell landings far too small to see: tracer option, big HE
  explosions, ricochets/skidding and near-miss blast physics; 12.7 mm ground-hit smoke causes huge lag spikes; the
  Legion hit almost every shot (fix options offered, his pick pending). Brief: `2026-10-02-emerson-notes-012-aim-brief.md`.

## Open questions for Emerson (sessions use the default until he answers)
1. Godot addons: Terrain3D (TokisanGames/Terrain3D, MIT) and GUT (bitwes/Gut, MIT). Default: not installed until he says yes.
2. Legion: one session for all three (default), or one session each?
3. Folder name `~/Games/eightysix`. Default: yes.
