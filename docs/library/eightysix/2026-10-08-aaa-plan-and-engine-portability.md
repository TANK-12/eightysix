# Eighty Six: the AAA plan and engine portability

date: 2026-10-08 · for: both (Emerson, and any Claude session with no history) · written by Mei (Relay 101)
from the measurements and research Umi (Relay 101) made the same day; checked by three rounds of critic
agents and fixed by Kenji (section 17).
Research and planning only: no game code, data, model or test was changed for this document.

## 0. How to read this

This is the companion to `2026-10-08-spec-and-roadmap-to-complete.md` (Relay 97, called **the spec** below).
Read the spec first: it holds the story M0 to M12, the seven tones, every feature with its gap and priority, the
phases 0.1.2 to 1.0 and decisions D1 to D13. Nothing here repeats it. This document adds:

1. **Engine portability** (sections 2 to 8): Emerson is building a new PC and may move from Godot to Unity or
   Unreal Engine. What of the work so far carries over, measured; what a move costs; what to do about it.
2. **A deeper story** (section 9): arcs, setups and payoffs, the first three missions minute by minute, the
   base room by room, the night talks, how much dialogue there is.
3. **The tone as a sensory grammar** (section 10), and the ways it can fail.
4. **AAA features** the spec lacks (section 11) and **polish targets** with a number and a check each
   (section 12); the gaps this adds to the spec's top 20 (section 13).
5. **The order of work** with the engine question in it (section 14), **decisions D14 to D20** (section 15),
   new **risks** (section 16).

It is a proposal. Emerson reorders, cuts or adds, and his word wins; each decision has a default so work can
start before he answers.

**Evidence tags.** The spec's tags hold: **[seen]** read in the game's code or data, **[handoff]** from the
2026-10-07 handoff, **[canon]** from the 86 sources, **[new]** a proposal. Three more:
- **[measured]**: counted by a script on 2026-10-08 in `~/Games/eightysix` or `~/Models`. Exact on that day.
- **[web]**: an engine fact read on a vendor or news page on 2026-10-08. Engines change fast: recheck before
  relying on it.
- **[estimate]**: a guess, with its reasoning beside it.

Nothing was built or run in Unity or Unreal, nothing was run on the new PC (its parts are not known yet), and the
game itself was not played for this document.

**Words used here.** A *port* is moving the game to another engine. An *engine-neutral* file or rule works the
same whatever the engine. *Coupling* is how much code calls one engine's own functions. A *bake-off* is building
the same small piece in two engines and judging them side by side. *Golden numbers* are the measured figures that
define how the game behaves (top speed, jump height, shell drop): a test checks them. *glTF* (`.glb`) is the open
3D model format every engine imports. *Telemetry* is a log the game writes about what happened in a run.

## 1. The short of it

- **Most of what exists is not Godot work.** The Blender sources (153 files), the game models (glTF plus a data
  sidecar; other engines' importers turn them 180 degrees, 3.4), textures, sounds, the maps' Python tools, 116
  bot timelines and all the design docs move to any engine as they are. The real-place maps need a one-time
  heightmap conversion, and the 27 data files a one-time clean-up: 339 Godot file paths become asset IDs, and the
  weather, graphics, sound and key settings split into a neutral part and an engine part [measured, sections 2.3
  and 3.2]. What is truly Godot is the code: 19,103 lines of
  GDScript, 11,500 lines of tests and 1,062 lines of shaders. Even there, **about three code lines in four call no Godot
  function**: they are maths and rules, re-typed in a new language, not redesigned [measured, section 2.2: 15 %
  of lines name a Godot class or idiom, 18 to 26 % once calls on engine objects are counted too].
- **A port's real cost is the feel, not the typing.** The Juggernaut's movement is tuned on the Jolt physics
  engine at 120 ticks a second. Unreal (Chaos) or Unity (PhysX) will move it differently, and getting "fun from
  real physics" back is the expensive part. The look is re-made by eye in the new renderer, not converted.
- **What a port costs:** about **28 to 44 sessions for Unity, 32 to 52 for Unreal**, only to get back to today's
  game [estimate, section 4]. The spec's road to 1.0 is 77 to 118 sessions; a port adds roughly a third to a half.
- **Recommendation: no switch on a hunch.** When the new PC is built, run a **bake-off of 7 to 9 sessions**: first
  measure and push Godot on it (two sessions; the laptop's integrated GPU is much of what limits the look today),
  then the same Brilon slice in Unreal 5.8, which must pass five gates fixed in advance (unlabelled screenshot
  picks, the movement numbers, how fast Claude can change and test it, frame rate, no blockers). Switch only if
  Unreal passes every gate and Emerson's own play does not veto it.
  **Unity is not recommended**: its high-end renderer is in maintenance only and its Linux editor targets Ubuntu
  on GNOME; Arch is unsupported [web].
- **Until then, build engine-neutral (N1, 3 to 5 sessions):** asset IDs instead of Godot paths in the data, the
  golden numbers, a dialogue database with the Act I script, a telemetry log, specs for the bot and save formats.
  The spec's 0.2 needs most of it anyway, and all of it survives any engine.
- **Story, deeper:** an arc per character, 18 setups and payoffs (Kujo's blackboard countdown stops at 128 days;
  Theo draws the Handlers and burns his drawings beyond the border, both canon), M0 to M2 minute by minute, a
  rule that makes each mission different, a base that empties as the names grow, about 2,100 lines of dialogue.
- **AAA bar:** 16 features to add (a radio that picks lines by context, a music state machine, a mark-and-call
  button, machines that act, telemetry, safe saves and more) and 32 polish targets, each with a number and the
  way to check it.
- **Seven new decisions (D14 to D20):** the engine, the new PC's system, how the Para-RAID sounds (canon says it
  ignores distance and interference, so the spec's radio static does not fit), C++ over Blueprints in Unreal,
  the dialogue format, sound middleware, and the polish bar.

## 2. What exists today, measured

### 2.1 Inventory

| What | Size [measured] | Where | Tied to Godot? |
|---|---|---|---|
| Blender sources | 153 `.blend` files: Juggernaut 47 (1.6 GB), Legion 56 (246 MB), arsenal 50 (109 MB); each built by Python scripts (`build_juggernaut.py`, `materials.py`, `animate.py`; Legion `build.py`, `export_game.py`, `gamedata.py`; arsenal `build.py`, `registry.py`) | `~/Models/` | no |
| Game models | 42 MB. The Juggernaut as glb (full 539k triangles, lite 130k) with a skeleton, sockets and 7 animation clips, plus a JSON sidecar of parts, joints, convex hulls, masses, sockets and actuators; copied in by `tools/sync_models.py`, turned into game data by `tools/build_juggernaut_data.py` | `assets/models/` | no: glTF and JSON are open formats |
| Textures | kit 84 MB, textures 6.2 MB, trees 0.4 MB | `assets/` | the files no; the shaders that use them yes |
| Audio | 285 MB, of which the 86 soundtrack is 246 MB (personal use only) | `assets/audio/` | no |
| Real-place maps | 46 MB: per map a heightmap (`.f32` floats), OpenStreetMap features (`osm.json`) and a woods mask (`woods.png`), all made by Python | `assets/maps/`, `tools/maps/` | no |
| Data | 27 JSON files, 11,264 lines | `data/` | mostly no (section 2.3) |
| Game code | 88 GDScript files, 24,417 lines (19,103 code, 2,190 comment) | `scripts/` | the language is; most lines are not (2.2) |
| Shaders | 11 files, 1,062 lines: ground 254, masonry 225, facade 134, sky 109, tree 100, menu backdrop 65, water 44, foliage 36, colour filter 34, terrain 33, grass 28 | `assets/` | yes: Godot's shading language |
| Scenes | 11 `.tscn` files, 2,088 bytes in all; no `.tres` resources. The game builds itself from data by code | `scenes/` | barely: there is almost nothing in them |
| Tests | 67 GDScript files, 11,500 lines; last full run 528 of 529 passing [handoff, Relay 95] | `tests/` | the code is; the numbers they expect are not |
| Bots | 116 JSON timelines (115 committed) and their runner | `tools/bot/`, `tools/bot_run.sh` | timelines no, runner yes |
| Python tools | 28 files, 4,731 lines: maps, audio, builds and share zips, fps logs, image checks (`histogram.py`, `sharpness.py`, `contact_sheet.py`), scoreboards | `tools/` | mostly no; `builds.py`, `export.sh`, `play.sh`, `run_tests.sh` drive Godot |
| History | 171 commits | `.git` | no |
| Engine set-up | Godot 4.7.2; Jolt physics at 120 ticks a second; seven named physics layers; no add-ons | `project.godot` | yes |

### 2.2 How tied the code is to Godot

**Method [measured].** Every non-blank, non-comment line in `scripts/**/*.gd` was checked against Godot's full
class list (taken from the installed engine with `godot --dump-extension-api`, 4.7.2) and against Godot idioms
(node paths, `add_child`, signals, `_process`, `preload`, `res://` and the like). A line naming any of them
"calls Godot". Lines that use only maths types (Vector3, Basis, Transform3D, Quaternion, Color, which exist one for
one in every engine) are counted apart. Umi's separate keyword scan the same morning found 14.5 % overall; this
one finds 14.6 %. The script was a scratch file in `/tmp`; the method above is enough to repeat it.

**A second pass [measured, after Critic A].** The scan above misses lines that only use methods or properties of
engine objects without naming a class. A strict list of engine-only names (`global_position`, `global_transform`,
`linear_velocity`, `apply_force`, `intersect_ray`, `direct_space_state`, `set_shader_parameter`, `draw_rect`,
`get_parent`, `is_action_pressed`, `add_theme_*`, `look_at` and the like) adds 3.5 % of lines; a broad list that
also counts shared names such as `position`, `visible` and `text` adds 8 % (the critic's own broad pass, 11.7 %).
So the true share tied to Godot is **about 18 to 26 %**, and the table's figures are the floor, not the answer.

| Folder | Files | Code lines | Calls Godot | Maths types only | What is in it [seen, file names] |
|---|---|---|---|---|---|
| world | 20 | 4,828 | 13.6 % | 12.2 % | the maps (small, big, test range, bench), terrain, scatter, sky, backdrop, destruction, film grade |
| ui | 15 | 3,234 | 23.2 % | 7.5 % | menus, settings and search, HUDs, Hangar, loading, mission end, the radio, tutorial |
| mech | 8 | 2,393 | 5.9 % | 11.7 % | the Juggernaut and stand-in, builder, mass, climbing, the test bench rig |
| combat | 10 | 2,282 | 13.6 % | 9.3 % | ballistics, shells, blast, damage model, hits, blade, wire, ammunition |
| core | 9 | 1,770 | 18.5 % | 1.5 % | boot, game, settings, controls, graphics, rumble, registry, bot hooks |
| ai | 7 | 1,309 | 7.5 % | 9.8 % | Legion brain and path grid, pack hunter, scout, heavy, squad and wingman pilot |
| legion | 1 | 899 | 7.7 % | 12.6 % | the Legion bodies |
| audio | 4 | 775 | 21.4 % | 1.5 % | the mix, music, effects, mech sounds |
| camera | 4 | 631 | 21.2 % | 11.3 % | chase camera, Handler view, kill cam, photo mode |
| look | 4 | 454 | 17.0 % | 5.7 % | emblems, finishes, foot dust, grime |
| mission | 3 | 426 | 12.9 % | 3.8 % | mission runner, sortie log |
| locomotion | 3 | 102 | 0.0 % | 13.7 % | charge jump, leg IK, leg rams |
| **all** | **88** | **19,103** | **14.6 %** | **9.1 %** | |

**What it says [reasoned].**
- About three code lines in four are plain logic (85 % by the class scan, 74 to 82 % by the second pass). They are re-typed into C# or C++ line for line, with the same names,
  and the same tests' numbers prove them right.
- The engine-heavy parts are where you would expect: menus and HUD (23 %), sound (21 %), cameras (21 %), start-up
  (19 %), the look (17 %). These are rebuilt on the new engine's own systems, not translated.
- **The Juggernaut is the least tied (6 %).** It is one rigid body pushed by forces from ray-cast spring legs
  [Umi, seen `standin_mech.gd`]: the most portable kind of physics controller there is, since every engine has
  rigid bodies, forces and ray casts. Its *numbers* are what do not carry: they were tuned on Jolt.
- 131 Godot classes are used. The ten most used: Node (174 lines), Node3D (147), Control (95), RigidBody3D (75),
  Label (73), MeshInstance3D (61), Button (57), StandardMaterial3D (55), FastNoiseLite (53),
  GeometryInstance3D (48). Section 3.3 maps the main ones to Unity and Unreal.

**Two hidden traps [reasoned].**
- **Random numbers.** 38 lines use Godot's RandomNumberGenerator, which is the PCG32 generator. Anything placed
  from a seed (grass, trees, kit-town layouts, spawn jitter) comes out different in another engine unless the same
  generator comes along. Port PCG32 itself (a few dozen lines) rather than using the new engine's random.
- **Noise.** 53 lines use FastNoiseLite. Godot wraps the open FastNoiseLite library, which also exists for C#, C++
  and HLSL under the MIT licence, so terrain and grass made from noise can come out the same if the settings carry
  over. Check it with a golden image (the same seed rendered top-down in both engines, compared pixel by pixel).

### 2.3 What the data still knows about Godot

- **339 `res://` paths** (Godot's own file paths) in six files: `sounds.json` 306, `maps.json` 15, `themes.json`
  12, `enemies.json` 3 (the Legion models), `mechs.json` 2 (the Juggernaut model and its sidecar), `emblems.json` 1
  [measured]. They become asset IDs (rule 7.1).
- **`weather.json`** uses Godot's environment settings (the AgX tone mapper, glow, volumetric fog) [measured].
  Split each preset into an engine-neutral part (sun height and direction, sun colour temperature, fog density in
  metres, cloud cover, wind) and an engine block (Godot environment fields; Unreal post-process volume, height fog,
  sky atmosphere, volumetric clouds; Unity volume profile).
- **`graphics_presets.json`** maps to Godot settings; Unreal would use its scalability groups, Unity its quality
  levels. **`input.json`** action names are neutral; its key codes are Godot's.
- **`sounds.json`** carries Godot's 3D-sound fields `unit_size` and `attenuation`; only `max_distance_m` is in
  metres [measured]. They give way to a reference distance and a rolloff in metres (rule 7.9).
- Everything else (missions, squad, enemies, weapons, mechs, parts, radio lines, music list, settings pages,
  tuning) is plain game data with SI units and carries over as is [seen in the spec's reads; units not audited
  file by file].

## 3. What transfers

### 3.1 Five verdicts

- **Keep**: works as it is in any engine.
- **Convert**: a script changes its format once.
- **Re-type**: the same design and numbers, written again in C# or C++.
- **Replace**: use the new engine's own system instead of carrying ours over.
- **Rebuild**: made again by hand and tuned again by eye or by feel. The costly kind.

### 3.2 Category by category

| Category | Verdict | Unity | Unreal | Notes |
|---|---|---|---|---|
| Blender sources and their Python build scripts | keep | keep | keep | untouched by any engine change |
| glb models, skeleton, 7 clips | keep | glTFast importer | Interchange glTF importer | axes and units differ (3.4); the clips import as animations |
| JSON sidecars: parts, joints, hulls, masses, actuators | keep | read by our code | read by our code | the hulls feed the engine's convex shapes |
| Textures | keep | keep | flip normal maps' green channel | Blender, Godot and Unity use OpenGL-style normal maps (green up); Unreal uses DirectX style (green down) and has an import option to flip |
| Sound files | keep | keep | keep, converting any format it will not import | |
| Map sources and Python map tools | keep | convert heightmap to 16-bit RAW for Terrain | convert to 16-bit PNG or RAW for Landscape | note the height scale; house building from OSM footprints is our code, re-typed (or Unreal's procedural tools) |
| Data JSON | convert | asset IDs; engine blocks | asset IDs; engine blocks | section 2.3 |
| Game logic: mech maths, ballistics, armour, damage, AI decisions, missions, sortie log, settings model, radio picker | re-type | C#: close to GDScript (both managed, garbage collected) | C++: heavier (headers, engine macros, compile times) | the golden numbers prove the copy (7.6) |
| Physics set-up: body, ray-cast legs, actuators, layers | re-type, then rebuild the tuning | PhysX; a community Jolt plugin exists [web] | Chaos; a community Jolt plugin, UnrealJolt, runs beside it [web] | the forces port; every tuning value is re-fit until the golden movement numbers pass |
| The 120 Hz fixed tick | re-type | `FixedUpdate` at 1/120 s: the same model as Godot | physics normally steps with the frame; a fixed step needs sub-stepping or the async physics tick, which changes how code reads and pushes bodies | [reasoned from the engines' documented models; check in E1] |
| Menus, settings, HUD, Hangar | replace | UI Toolkit (or uGUI) | UMG and CommonUI | the settings pages are data (`settings.json`), so pages come back from data |
| Cameras | replace the components, re-type the maths | Cinemachine | camera components, camera manager | offsets and smoothing values carry over |
| Sound playback and mix | replace, re-type our logic | AudioSource, AudioMixer | MetaSounds, submixes, attenuation | the speed-of-sound delay and radio logic are ours; FMOD is an option (D19) |
| 11 shaders | rebuild | Shader Graph or HLSL | material graphs | ground, masonry and facade (613 lines) are the big ones; Unreal's landscape layers, decals and virtual textures cover much of them |
| Grass, trees, terrain look | replace and rebuild | Terrain details or GPU-instanced grass | Landscape grass, procedural foliage (PCG), Nanite where it helps | today grass ends at 60 m [handoff] |
| Sky and weather | replace | custom or bought sky and clouds in URP [reasoned] | sky atmosphere, volumetric clouds, height fog | the neutral half of `weather.json` drives either |
| Particles (smoke, dust, sparks) | replace and rebuild | the built-in Particle System (CPU, like today's) or VFX Graph (GPU) | Niagara | the smoke's GPU budget work (Relay 56) is redone |
| Streaming of the 4 km maps | replace or re-type | scene streaming, Addressables | World Partition | or keep our own cell streaming, re-typed |
| Destruction (towns break, bridges drop spans) | re-type | rigid pieces as today | rigid pieces as today, or Chaos destruction | ours is simple rigid pieces; keep that model |
| Tests | re-type | Unity Test Framework (batch mode) | Automation tests | the expected values come from the golden file |
| Bot runner and timelines | re-type the runner, keep the timelines | | | a written format spec (7.7) makes this mechanical |
| Builds and share zips | replace the build step, keep the packing | BuildPipeline in batch mode | RunUAT BuildCookRun | `HOW-TO-RUN.txt`, credits and zips stay |
| The look (0.1.1's sky, grass, Hangar light) | rebuild | by eye | by eye | today's screenshots are the reference |
| Movement feel | rebuild | to the golden numbers, then Emerson's hands | same | the scariest line in this table |

### 3.3 The Godot classes this game leans on, and their counterparts

| Godot | Unity | Unreal |
|---|---|---|
| Node, Node3D (the scene tree) | GameObject and Transform | Actor and SceneComponent |
| RigidBody3D, PhysicsDirectBodyState3D | Rigidbody, `FixedUpdate` | a primitive component simulating physics (Chaos body instance) |
| PhysicsRayQueryParameters3D (ray casts) | `Physics.Raycast` | line traces by channel |
| CollisionShape3D, BoxShape3D, convex shapes | colliders (box, convex mesh) | collision primitives and convex elements |
| the seven physics layers | layers and the collision matrix | collision channels and profiles |
| MeshInstance3D, ArrayMesh, SurfaceTool | MeshRenderer, the Mesh API | static mesh components, dynamic or procedural meshes |
| StandardMaterial3D, ShaderMaterial | URP Lit material, Shader Graph | materials and material instances |
| Control, Label, Button, containers | UI Toolkit | UMG widgets |
| Camera3D | Camera with Cinemachine | camera component, player camera manager |
| AudioStreamPlayer3D, AudioServer buses | AudioSource, AudioMixer | audio components, MetaSounds, submixes |
| CPUParticles3D | Particle System (VFX Graph is GPU only) | Niagara |
| Input, InputEvent | Input System | Enhanced Input |
| FastNoiseLite | FastNoiseLite for C# (same library) | FastNoiseLite for C++ (same library) |
| RandomNumberGenerator (PCG32) | our own PCG32 | our own PCG32 |
| ResourceLoader, `res://` | Addressables | soft object paths, asset manager |
| Environment, WorldEnvironment | volume profile | post-process volume, sky atmosphere, fog |
| signals | C# events | delegates |

### 3.4 Units and axes

| | Up | Forward | Handedness | Unit of length |
|---|---|---|---|---|
| Blender | +Z | -Y (a model's front faces -Y) | right | metre |
| glTF | +Y | +Z (an asset's front faces +Z) | right | metre |
| Godot | +Y | -Z | right | metre |
| Unity | +Y | +Z | left | metre |
| Unreal | +Z | +X | left | centimetre |
| **Our models** | +Z in Blender, +Y in the glb | **+Y in Blender, so -Z in the glb** (Godot's forward): the opposite of both conventions above [measured: `~/Models/juggernaut/build_juggernaut.py` lines 4-5, `~/Models/legion/export_game.py` line 233] | right | metre |

Consequences [reasoned]: into Unreal every length, speed and force is multiplied by 100 (its forces are in
kilogram-centimetres per second squared, so a newton is 100 of its units; gravity is -980), axes swap, and each
change of handedness flips the sign of one axis and of every rotation and cross product built on it. Into Unity
only the handedness changes. Our models break the formats' own conventions (last row): an importer that trusts
glTF's +Z front will bring every mech and Legion in turned 180 degrees, so the turn is fixed once in the
conversion step, never per model. **Rule:** our data stays in metres and SI units with one written convention, one
small conversion module per engine does every crossing, and the first test of any port imports an **axis totem**
(a 1 m cube with labelled +X, +Y and +Z arrows and a notch on one side) plus one real mech, the Juggernaut, and
checks where everything landed and which way it faces.

## 4. Port size, area by area

Sessions as in the spec: one session is one Relay task. Guesses from how fast the alpha was built (171 commits,
about 36,000 lines of game and test code in ten days) and from how long tuning took (the stand-up alone took
several sessions [handoff]). Not promises.

| Area (lines today) | Unity | Unreal | Why it costs that |
|---|---|---|---|
| Foundation: project, input, settings, data loading, asset IDs, units, start-up (core 1,770, mission 426) | 3 to 4 | 4 to 6 | Unreal: C++ module set-up, build times, the Linux tool chain |
| The Juggernaut: body, legs, actuators, damage, gait, and re-fitting its feel (mech 2,393, locomotion 102) | 5 to 8 | 6 to 10 | the re-tune; Unreal's frame-tied physics step (3.2) |
| The fight: guns, shells, armour, blade, wire (combat 2,282) | 2 to 3 | 2 to 4 | mostly maths |
| Legion and wingmen: bodies, brains, path grids (legion 899, ai 1,309) | 2 to 3 | 3 to 4 | perception and grids rebuilt on the engine's queries |
| The world: five maps, terrain, streaming, kit towns, destruction, weather (world 4,828) | 5 to 8 | 5 to 8 | Unreal gives more for free (landscape, procedural foliage, streaming), each a new system to learn and tune |
| The look: materials, 11 shaders, light, post, grass, trees (look 454, shaders 1,062) | 3 to 5 | 2 to 4 | rebuilt by eye; Unreal starts from a higher default |
| Menus, HUD, settings, Hangar, photo mode (ui 3,234, camera 631) | 3 to 5 | 4 to 7 | the most Godot-tied code; Unreal's UI is slower to build as text (D17) |
| Sound and music (audio 775) | 1 to 2 | 1 to 2 | playback replaced, logic re-typed |
| Tests, bots, builds, share zips (11,500 test lines, the bot runner, `builds.py`) | 4 to 6 | 5 to 7 | Unreal's automation and packaging are heavier |
| **Total** | **28 to 44** | **32 to 52** | |

These buy back today's game (0.1.1 plus the 0.1.2 clean-up) and nothing new. The Unreal half of the bake-off
(section 6) counts as about 3 to 4 sessions of it. Work done in Godot before a port makes the port bigger: if the
switch came after the spec's 0.2, the new campaign systems and screens would add roughly 5 to 8 sessions
[estimate].

After a port, some later work gets cheaper in Unreal (the look strand, the story places, foliage, camera moments
with its sequencer) and some dearer (every campaign screen, every test). Taken together the port cost is close to
a straight addition [estimate].

**Rule of thumb while the engine is undecided [estimate]:** a session of Godot-only work (UI, shaders, Godot look
tuning) adds about half a session to a later port; a session of game logic adds about a third (re-typing is
quicker than first writing); data, assets, writing and design add almost nothing.

## 5. The three engines, for this game

| | Godot 4.7 (today) | Unreal 5.8 | Unity 6.3 LTS |
|---|---|---|---|
| **Look ceiling** for wide outdoor scenes, grass and forest | good, not the top: Forward+ renderer, real-time global illumination (SDFGI) and volumetric fog; 4.7 adds HDR output and area lights [web]; no virtualised geometry | the highest: Lumen (dynamic global illumination), Nanite (virtualised geometry), virtual shadow maps; MegaLights production-ready in 5.8, Mesh Terrain, a lighter Lumen [web] | URP is Unity's focus; HDRP, its high-end renderer, gets maintenance only from 2026; the old built-in renderer is deprecated from 6.5 [web] |
| **Physics** | Jolt, the default since 4.6 [web]; every number in the game was tuned on it | Chaos; a community Jolt plugin, UnrealJolt (MIT, 169 stars, built for 5.8.1), bolts on beside Chaos rather than replacing it [web] | PhysX built in; a community Jolt plugin, JoltPhysicsUnity [web] |
| **How Claude works in it** | all text: GDScript, JSON, 2 KB of scenes [measured]; 528 headless tests and 116 bots run unattended today [handoff] | C++ is text but compiles slowly; Blueprints, levels and most assets are binary files (`.uasset`, `.umap`) Claude cannot read, compare or edit as text; an official MCP plugin (experimental) lets an agent drive the editor [web] | C# text; scenes and prefabs are YAML text linked by IDs (readable, fragile to edit by hand); Unity's MCP is an open beta needing a Unity AI subscription [web] |
| **Headless tests** | done | automation tests and command-line runs without a GPU; slower to start [reasoned] | batch mode and the Unity Test Framework [reasoned] |
| **Linux** | first-class; the game is made on it | a precompiled Linux editor on Vulkan; Epic's 5.8 requirements: Ubuntu 22.04 or Rocky Linux 8, 32 GB of memory, a GeForce 2080-class card with 8 GB or more, NVIDIA drivers 570 or newer or AMD's RADV 24.2.8 or newer [web, read by a critic]; whether Live Coding (patching C++ while the editor runs) works on Linux is not confirmed: Epic's 5.8 page names no desktop system | official only for Ubuntu 22.04 and 24.04 on GNOME, on X11 or Wayland (Wayland with AMD, or with NVIDIA 550 or newer on 24.04, and still called experimental) [web]; Arch unsupported |
| **Change-to-result loop** | seconds | a C++ change compiles, often with an editor restart; shader compiles [reasoned] | a C# reload, seconds to tens of seconds [reasoned] |
| **On the laptop (Iris Xe)** | runs, measured: test range Low 66.5 to Ultra 15.1 fps [handoff] | Lumen and Nanite want a real graphics card; expect the laptop to struggle [reasoned] | URP runs on weak graphics [reasoned] |
| **Friends' copies** | small zips for three systems [handoff] | builds of several GB [reasoned] | in between [reasoned] |
| **Licence** | MIT, free | free for a non-commercial game | the free tier covers it |
| **What comes next** | steady 4.x releases | Unreal Engine 6 announced: early access late 2027, a new scripting language (Verse) and Scene Graph [web]; an Unreal 5 port may face another move | its renderers are being merged [web] |

**Unity's case is weak here.** Its strongest look path is frozen, its Linux editor does not target this setup,
and a port would cost about as much as Unreal's for a lower look ceiling. What Unity does well (C#, a quick loop,
light builds) Godot already gives.

**Unreal's case is the look.** Lumen light, Nanite detail and virtual shadows on gold grass fields, fir forests
and real-town streets are the biggest single lever toward an AAA look, and Emerson's standing rule is that
graphics win over frame rate. Its costs: Claude loses text access to most assets, C++ iteration is slow, Linux is
less travelled, friends' copies get heavy, and the laptop cannot show it.

## 6. The recommendation and the bake-off (E1)

1. **Do not switch now, and never on a hunch.** Much of what limits the look today is the laptop's integrated GPU
   (Ultra at 15 fps everywhere [handoff]). The new PC lifts that for Godot too. Measure Godot there first.
2. **Run the bake-off (E1) once the new PC is built**, before any port: 7 to 9 sessions.
   - **Step G, Godot on the new PC (2 sessions):** first give `tools/fps_log.py` a `--map` option (it measures
     the test range only today) and run the fps table on every map and preset. Then one look session: make the
     grass range a preset field (today a constant, 60 m, in `scripts/world/small_map_scatter.gd`) and push it to
     150 m or more, try what lies beyond Ultra (real-time GI, 4096 shadows and fog volume 160 are Ultra's values
     already [seen `graphics_presets.json`]), and take six fixed shots.
   - **Steps U, Unreal 5.8 (5 to 7 sessions):** a C++ project with only what the slice needs. The Juggernaut (glb
     plus sidecar into a body with ray-cast legs and actuators: walk, gallop, slide, jump); Brilon (heightmap to
     landscape, OSM houses as instanced meshes, forest from the woods mask with procedural foliage); the golden
     afternoon light; one 57 mm shell with drag and penetration against a standing Löwe 400 m away; a chase
     camera; no menus. Plus what the gates below need: automation tests that read `golden.json`, a bot that
     measures the movement figures, and a packaged Linux build. If the feel numbers miss on Chaos, try the body
     on UnrealJolt (section 5) before calling it.
   - **Five gates, fixed before anything is built.** Unreal must pass every one; there are no weights or points.
     1. **Look:** six matched shots (same place, sun and lens), shown to Emerson in unlabelled pairs in random
        order; Unreal wins at least 5 of the 6 picks.
     2. **Feel:** every golden movement number within tolerance (top speed 70 km/h within 3 %; stop distance,
        jump height, slide length and turn rate within 10 %), measured by the bot.
     3. **Claude's loop:** a ten-line logic change reaches a passing test unattended in under 5 minutes, and a
        full headless test run and a packaged build need no step from Emerson's hands. (Godot's loop takes
        seconds, so a "no more than three times slower" bar would decide for Godot in advance.)
     4. **Frame rate:** 1 % low at least 30 fps at the chosen look on the new PC. Whether it runs on the laptop
        at all is noted, not gated.
     5. **Trouble:** no unsolved crash and no Linux blocker.
   - **Emerson's play is a veto, not a score.** He plays each for ten minutes. That cannot be blind (the two
     renderers look different), so it is not a pick; but if Unreal's feel is wrong to him, Godot stays.
   - **Default rule:** switch only if Unreal passes all five gates and Emerson does not veto it. Otherwise stay,
     and spend what the port would have cost on Godot look work and content.
3. **If Unreal wins, port at once** (section 8), before the spec's 0.3: every Godot session after that makes the
   port bigger.
4. **Unity stays out of the bake-off** unless Emerson has a reason of his own (D14).
5. **Until E1, build engine-neutral** (section 7 and N1 in section 14).

## 7. Engine-neutral rules: start now, whatever the engine

Cheap now, sessions saved later; most are good practice even if the game never leaves Godot.

1. **Asset IDs, not engine paths.** Data names assets by ID (`sfx.gun.57mm.fire`); one table per engine maps IDs
   to files. Today 339 `res://` paths sit in six data files, the model paths among them [measured].
2. **One unit convention.** Metres, kilograms, seconds, newtons; degrees in data, radians in code; written once
   (3.4), crossed only by the conversion module.
3. **Models stay Blender-first.** The Python build scripts are the source; export glb plus the JSON sidecar
   (as `sync_models.py` and `build_juggernaut_data.py` do today [seen]); never author game data inside an engine
   scene. Make LODs (lower-detail copies for distance) and collision hulls in Blender by script, so every engine
   imports the same ones.
4. **Textures as a neutral set:** base colour, OpenGL-style normal, and one packed occlusion-roughness-metal map,
   at power-of-two sizes. Engines convert at import.
5. **Logic without engine calls where it is cheap:** ballistics, armour and damage maths, AI decisions, the
   mission beat runner, the campaign runner, the save format, the radio line picker. Pure functions, engine calls
   at the edges in a thin adapter. Then a port re-types the pure part mechanically.
6. **The golden file.** One engine-neutral file (`data/golden.json` [new]) holding input and expected output for
   every pure rule (57 mm penetration at set ranges and angles, ricochet limits, shell drop at 1 km, damage per
   part, grade thresholds) and the measured movement figures with tolerances (top speed, stop distance, jump
   height, slide length, turn radius, the fall a leg survives). Today's tests read it; any new engine's tests read
   the same file. "It feels the same" becomes checkable.
7. **Bot timelines stay JSON** (116 today), with a short written spec of their actions, timing and checks.
8. **Dialogue in a database** (D18): every line with an ID, speaker, text, mission, beat, conditions, priority and
   voice file; one file per act.
9. **Keep each sound's best original:** today 107 WAV (106 at 48 kHz), 198 OGG (the downloaded library in
   `assets/audio/lib/`) and 56 MP3 (53 of them the soundtrack) [measured]. Never re-encode a lossy file; fetch
   WAV where a source offers it. `sounds.json` becomes the neutral list (IDs, variations, volume, pitch range,
   speed-of-sound flag) once its Godot fields `unit_size` and `attenuation` give way to a reference distance and
   a rolloff in metres (only `max_distance_m` is in metres today); each engine compresses at build time.
10. **Saves as versioned JSON** with a chain of migrations, so an old save always loads; settings and key
    bindings the same way. Engine-neutral by construction.
11. **Telemetry as JSON lines** (section 11, feature 8): the same log from bots and from Emerson's play, read by
    Python. It also becomes the bake-off's measuring tape.
12. **What not to make neutral:** rendering (materials, light, post), UI widgets, particle effects and terrain are
    engine-native. Do not build layers to abstract them: they get rebuilt per engine, and an abstraction would
    cost more than the rebuild.

## 8. If E1 says switch: the migration order

Each step ends with tests passing and a short note of what changed; the Godot game stays runnable beside it as
the reference until parity.

| Step | What | Done when |
|---|---|---|
| P0 Freeze | save the last Godot version with `builds.py`; record its golden numbers, fps table and six shots | the reference set is in the docs library |
| P1 Foundation | project, input, settings, data loading through asset IDs, units module, the axis totem, the golden-file test harness, the telemetry log | the totem and the pure-rule golden numbers pass |
| P2 The Juggernaut | body, ray-cast legs, actuators, stand-up, climbing; re-fit tuning | every golden movement number within tolerance, then **Emerson plays it: the feel gate** |
| P3 The fight | 57 mm ballistics, damage per part, blade, wire; the three Legion types and their brains; wingmen | combat golden numbers pass; the combat bots play |
| P4 The world | the five maps, kit towns, destruction, weather presets, streaming | each map loads, streams and passes a 10-minute walk bot |
| P5 The look | materials, light, post, grass and trees, the Hangar | Emerson picks the new shots over the P0 shots |
| P6 Menus and HUD | every screen and settings page from data; photo mode; accessibility settings | the smoke bot plays every menu |
| P7 Sound and music | the mix, 3D sound at the speed of sound, music, radio | a captured bot run passes the loudness targets (12) |
| P8 Tests, bots, builds | the full suite re-typed, the bot runner, share zips on three systems | **parity:** the suite and bots pass, and Emerson plays both side by side |

The roadmap continues at the spec's 0.3 (or wherever the game strand stood) once P8 is done.

## 9. The story, deeper

The spec's section 4 is the story: the arc, mission by mission, the roll of the fallen. This section deepens it.
Anything marked [new] is invention; anything marked [canon] was read on the 86 wiki or in the spec's canon reads.
Watch the episode before scripting any scene, as the spec says.

### 9.1 What each act asks

| Part | The question the player feels | Answered by |
|---|---|---|
| Prologue (M0) | Does anyone on the other side of the wall see the 86 as people? | a new voice on the Para-RAID that night |
| Act I (M1 to M4) | Can Lena earn their trust? | the switch from callsigns to real names (M4) |
| Act II (M5 to M7) | What does it cost to hear the dead? | Lena hears them and stays; eleven more names |
| Act III (M8, M9) | What do you owe the dead? | Shin frees his brother; the five choose to go on |
| Act IV (M10 to M12) | What is freedom worth when it lasts days? | the school night, then the last stand |
| Epilogue | Who remembers? | Lena does: Lev tells her about them; their list of names, photograph and messages, and Shin's wish that she leave flowers, are hers now [canon, Volume 1]; she keeps fighting |

### 9.2 Arcs, and how each is shown without faces

Pillar 3 (the spec, D1) keeps people off screen, so every arc lives in voice, objects and machines.

| Who | Starts | Turns | Ends | Shown through |
|---|---|---|---|---|
| **Shin** | a calm executioner carrying everyone's names, hunting his brother's ghost [canon] | tells Lena of the names (M4); frees Shourei (M9) | lighter beyond the border, then chooses to be the decoy (M12) [canon] | the fewest words of the squad; Undertaker's machine (the headless skeleton mark, the box of name markers in his bay [new]) |
| **Lena** | formal, idealistic, inside the Republic's lie [canon] | learns her own prejudice (episode 4); hears the dead and stays (M5); breaks the rules for the guns (C2) [canon] | alone in the empty base, resolved to fight on [canon] | her voice changing from script-reading to plain speech [new direction]; her console |
| **Raiden** | the vice-captain who argues with Shin and holds the squad together [canon] | argues against Shin's hunt for his brother [new framing of M8] | follows him anyway (M12) [canon] | the bluntest lines; the first to joke after a loss, but only at the base [new] |
| **Theo** | sharp tongue, quick temper; draws, and drew the portraits of the squadron's Handlers at the First Ward base [canon] | his rant at Lena (episode 3), his apology (episode 4) [canon] | throws his drawings into the fire beyond the border; to Fido: "I'm amazed I've made it this far. I wonder if I'll be next. This time, I'll die for sure, right?" [canon, episode 10] | the sketchbook at the base; its pages seen as machines and places, the Handler portraits never turned to the camera (pillar 3) [new staging] |
| **Kurena** | the sharpshooter; hates the Alba, whose soldiers executed her parents [canon] | jealous of how close Lena gets to Shin [canon] | goes where Shin goes [canon] | calls her shots by range and wind [new]; the coldest voice toward Lena, warming late [new] |
| **Anju** | soft-spoken and kind, close to Daiya [canon] | Daiya's death (M6) [canon] | the one who grieves longest [canon] | the quietest radio voice; her corner of the barracks keeps Daiya's things [new] |
| **Kujo** | counting down the days to the end of his service on the hangar's blackboard, to Lev's disapproval [canon] | | dies in M0; the board stops at 128 [canon] | the blackboard |
| **Kaie** | open, curious about Lena [canon] | warns her not to get attached [canon] | dies in the marsh (M3) [canon] | the night talk before M3 |
| **Fido** | the Scavenger that has followed Shin since before the story [canon] | carries more each act (the spec's D9) | left behind, crippled (M11) [canon] | beeps, servo whine, how it trails Shin; its memory camera (M11) |
| **Annette** | sardonic; her father died over the Para-RAID's experiments [canon] | her guilt over the neighbours taken away, who were Shin and Shourei [canon] | hacks the Republic's artillery for Lena (C2) [canon] | console messages, then her voice in C2 |
| **Shourei** | a Shepherd's voice: rage and grief [canon] | | apologises when freed (M9) [canon] | voice only, placed in 3D |
| **Lev Aldrecht** | the squad's chief mechanic, an Alba in his fifties; married to a Colorata, he dyed his hair to follow his wife and daughter into the Sector, too late to save them, and stayed [canon, Volume 1] | the machines come back fewer each act; he keeps mending the ones that do [new] | the last voice left at the base: in the epilogue he tells Lena about them [canon, Volume 1] | a grumbling voice at the base; the machines' state after a mission as his lines [new]; an Alba on the 86's side, Lena's mirror [new framing] |

### 9.3 Setups and payoffs

A setup is something the player meets early that pays off later. The list keeps the writing honest: every
setup needs its payoff scripted in the same act file, and every payoff its setup.

| # | Setup | Where | Payoff | Where | Source |
|---|---|---|---|---|---|
| 1 | Kujo updates his countdown on the hangar blackboard | M0 morning | the board stays at 128; nobody wipes it | every base visit; Lena finds it in the epilogue | countdown and 128 [canon]; staging [new] |
| 2 | Shin cuts a piece of aluminium from a fallen comrade's Juggernaut and writes the name | M0 | the box of 576 names set down beside crippled Fido and the broken Juggernauts: a grave the player makes | M11 | [canon: the box of dog tags left with Fido, episode 11; the 576 fragments enshrined with Fido, Volume 1]; the player doing it [new] |
| 3 | Theo's sketchbook; the Handler portraits | the base, Act I | burnt in the fire beyond the border | M10 or M11 | [canon] |
| 4 | Shin calls the Legion before anyone sees them ("They're coming. North-east.") | M0 to M4 | the player hears them too | M5 | the spec 5.10 |
| 5 | Lena asks: "Do you know a Shourei Nouzen?" | M4 | the story of the pilot who saved her; the Shepherd | M5, M9 | [canon] |
| 6 | Shin tells Lena to cut the link because of the Black Sheep | M5 | she keeps it open, and later keeps faith through the guns | M5, C2 | [canon] |
| 7 | The radio uses callsigns | M0 to M3 | real names from then on | M4 | the spec |
| 8 | HQ's cheerful line: "no human casualties" | Act I briefings | the same line read over M7's seven deaths | M7 debrief | line [new], irony from the canon premise |
| 9 | Lena promises fireworks for the Revolution Festival | a night talk in Act II [new] | the festival night | M7 | fireworks [canon] |
| 10 | The festival's fireworks: crackle and thump in a night sky | M7, base | the same sky full of long-range shells | M7, the attack | [new]: a deliberate sound rhyme |
| 11 | Daiya's cat in the hangar; each of them calls it by a different name (Blackie, Whitey, Calico, Kitty) | M0 | after M6 it sleeps on Daiya's stripped bunk [new]; Kurena and Anju's note asks Lena to adopt it | M6, epilogue | [canon: TP, adopted by Daiya; the note, Volume 1] |
| 12 | Fido picks up after every fight | M0 onward | Fido left behind, keeping the names (setup 2); its memories | M11 | [canon] |
| 13 | The mercy shot (Kujo) | M0 | Daiya (M6); then Shin frees his brother | M6, M9 | [canon] |
| 14 | Annette's guilt in her messages | M8 | she hacks the artillery | C2 | [canon] |
| 15 | Raiden argues with Shin | M8 | follows him anyway | M12 | [canon] |
| 16 | The base full but for two bare bunks (Matthew's and Mina's, 9.9): mugs, jackets, voices from other rooms | Act I | the base emptying, object by object | Acts II and III, epilogue | [new] (9.6) |
| 17 | Lena's voice reads from a script | M1 | she speaks plainly, without the script | from M5 on | [new direction] |
| 18 | Shin's dream | | meeting Shourei; a stranger says "welcome" | coda | [canon] |

### 9.4 The vertical slice, minute by minute

The spec's 0.2 builds M0 to M2 first. These are their beat sheets: times are targets, every line is new writing,
and each mission's needs are listed in the spec's 4.3.

**M0 "The 86th Sector"** (about 25 minutes; Ashen valley; late afternoon at the base, `dusk_haze` on the march,
then the new night preset for the rescue, moved up from the spec's M4; night at the base)
- **0:00 Base, late afternoon.** Black screen, the hangar's sounds: a compressor, a radio low, Daiya's cat. Fade up on
  Undertaker's bay. Chalk on a blackboard: Kujo, cheerful, "One hundred and twenty-eight." Lev grumbles at him
  [the countdown and Lev's disapproval are canon; the scene is new]. The player walks the Juggernaut out of the
  bay: walking and looking, taught by the squad's voices, not by boxes on screen.
- **3:00 The march out, the sun going down.** The old Handler reads a checklist in a bored voice; only Shin answers. Gallop on the
  road; the skid stop. Banter that introduces each voice.
- **7:00 Scouts, at dusk.** Shin: "Contact. North-east. Six." before anything is in sight (setup 4). Ameise scouts: aim,
  fire, reload, one ammunition type.
- **10:00 The Handler signs off mid-fight** [new]: "I'm logging off. Don't call." The squad carries on without a
  word of complaint: the first sign of who they are.
- **11:00 The pack, in the last light.** Grauwolves: the slide and the jump to dodge; the wire, as it stands today.
- **14:00 Nightfall: the rescue** [canon: Kujo's last fight was a night battle, a mission to rescue another unit,
  Volume 1 Chapter 2]. Another squadron calls for help, then goes quiet; Shin turns them toward it. The night
  preset; the squad fights by sound and by Shin's calls.
- **16:00 Kujo.** A person-sized shape on the ground ahead, moving like someone hurt: Kujo takes it for a wounded
  soldier and goes to it. A self-propelled mine [canon, Volume 1 Chapter 2]. His Juggernaut down, legs gone,
  Legion closing. His voice stays light, then quiet. The mercy
  shot (D4): the player's gun, one shot. No hit marker, no kill cam, the music drops out, ten seconds of radio
  silence.
- **18:00 After.** The fight ends without a win screen. Shin cuts a piece of aluminium from the wreck (setup 2);
  Fido collects what is left.
- **20:00 Night.** The blackboard still says 128. The names screen, first use: 559 names, then Kujo's.
- **22:00 The Para-RAID chimes.** A new voice: the squad's new Handler introduces herself [canon, episode 1]. The
  squad's silence. Shin: "Undertaker. Acknowledged." Title card.
- *The player learns:* walk, gallop, skid, aim and fire, reload, slide, jump, the wire, and fighting in the dark
  by sound. *The curve:* warm, then routine, competence, shock, stillness, and a flicker of something new.
- *What this adds to the spec's 0.2:* a night lighting preset (the spec's first night is M4) and the
  **self-propelled mine** as a P0 for M0 (the spec has it as a P2 riding with any act that has room): a person-sized shape that moves like
  someone hurt, then latches on [canon].

**M1 "First contact"** (about 20 minutes; Ashen valley; `golden_afternoon`)
- **0:00 Briefing** on Lena's console, her first: earnest, formal, reading her script [new direction].
- **2:00 Wave 1.** Lena orders a textbook formation; Shin says "Understood" and does otherwise; it works.
- **8:00 Wave 2. The ignored order** (the spec's beat): she orders a hold; Shin flanks; Lena, after a pause:
  "Noted." The squad's teasing on the open link; she does not hang up.
- **14:00 Wave 3, the Löwe.** Lena's first useful call: she reads the map right about the Löwe's approach, and
  Shin uses it [new]. A small win for her, unacknowledged.
- **19:00 Debrief.** The grade, and Lena: "Thank you, everyone." Theo, off the link: "She thanked us." Night talk
  N1.

**M2 "Spearhead"** (about 30 minutes; the Sector 86 frontier; `overcast_morning`)
- **0:00** A big attack wave hits the squad's position [canon, episode 2]. Waves as Frontier sweep has them.
- **The bridge** as the optional objective (it exists), played with real shells (the spec's 0.1.2).
- **The finale:** the heaviest units, Shin alone against them; Lena watching the markers [canon]. After a long
  silence: "How did you do that?" [new line].
- **After:** her console shows the history class she takes over: the Republic's lie in its own words [canon].
  Night talk N2.

### 9.5 The rule that makes each mission different

Every mission has one rule the others do not, so no two play as the same wave fight [new].

| # | Length | The rule | The moment it is remembered for | The curve |
|---|---|---|---|---|
| C1 | 8 min | you are Lena: no body, only the map | placing the marks the squad will fight from | quiet, careful |
| M3 | 25 min | the ground pulls: the marsh sinks and drags the legs | Kaie's machine going down, the voice steady until it is not | confident, then the ambush works, then the loss, then Theo's rant |
| M4 | 20 min | night: your own lamps and flares are the only light | callsigns become names; "Shourei Nouzen?" | quiet, close |
| M5 | 25 min | the Handler goes silent for two minutes; you hear the dead | the first time the voices are the player's | dread, chaos, numbness |
| M6 | 30 min | the Legion learns: your ambushes get flanked | the second mercy shot | grim competence, then loss |
| M7 | 35 min | fireworks, then shells: a retreat under guns you cannot reach | the festival sky, then the same sky full of shells | warmth, horror, seven names |
| M8 | 25 min | the last night, then the march | the farewell | tender, resolute |
| M9 | 35 min (C2 inside) | the boss is your brother; you go down, and Lena's guns carry it | Shourei's apology | rage, helplessness, release |
| M10 | 30 min | no Handler, no map but Fido's: hide, do not fight | the river they cannot cross | fragile freedom |
| M11 | 30 min | a town to wander and a damaged Black Sheep to free | Fido's memories | lightness, then a loss |
| M12 | 25 min | hold as long as you can; it ends by script | the others following Shin anyway | warmth, then the last stand |
| E | 10 min | you are Lena at the base: Lev's voice, then the empty rooms | the list of names, the photograph (never turned to the camera), their messages, the cat, Shin's wish that she leave flowers [canon, Volume 1]; "welcome" | grief, resolve, a door opening |

Mission time adds to about 6 hours 15 minutes; with about 5 minutes at the base between missions, about 7 hours
20 minutes, inside the spec's 6 to 8 [estimate].

### 9.6 The base, room by room

The First Ward base [canon, from the wiki's account of Theo's portraits] as the hub. Rule: **the base empties as
the names grow** [new]. Nobody is seen (pillar 3); people are heard from the next room, and what they leave
behind changes between visits.

| Place | What is there | What you do | How it changes |
|---|---|---|---|
| The hangar | the squad's Juggernauts in their bays with personal marks; Lev's bench; the cat's box (Daiya's cat) | loadout, inspect your machine (the Hangar showroom's tools), hear Lev on the last mission's damage | bays go dark one by one; marks painted over; replacement machines never come [new] |
| Undertaker's bay | the box of aluminium markers | carve a new name (the names screen as a short quiet scene) | the box fills |
| The blackboard | Kujo's countdown at 128, the squad's notes, a duty rota | read it | names leave the rota; nobody touches the 128 [new] |
| The barracks | bunks, each corner with its owner's things (Theo's sketchbook, Daiya's jacket) | look; each thing has a line from its owner, or about them once they are gone | bunks stripped; Anju keeps Daiya's things on hers; the cat sleeps on Daiya's bare bunk [new] |
| The mess and kitchen | a long table, a cooking rota | the evening banter scenes | fewer plates set each act [new] |
| The roof | the sky over the wall | the night talks with Lena; the festival fireworks | the epilogue: Lena on the same roof [new] |
| Fido's corner | scrap it has collected | Fido follows you in | empty after M8, when Fido goes with the five |

**Absent presence** (the technique of Gone Home and What Remains of Edith Finch, telling people through their
rooms and things) carries pillar 3 here: a door closing, a radio switched off in the next room, a mug still warm.

### 9.7 The night talks

Para-RAID conversations, mostly after a mission. Replies to pick are flavour only (D3).

| After | Who | What it does | Source |
|---|---|---|---|
| M0 | Lena, Shin, the squad listening | her introduction; their silence | [canon, episode 1] |
| M1 | Lena, Theo, Kaie | she asks about their day; they test her; she does not hang up | [new], the week the anime skips |
| M2 | Lena, Kaie | the history class; Kaie gets curious | [new] |
| before M3 | Kaie, Lena | why she cares; the pilot who saved her; the warning | [canon, episode 3] |
| M3 | Lena, then only Shin (the others will not link) | after Theo's rant she calls anyway; she apologises to Shin alone and asks for their real names; the custom of carrying the names, 561 by now | [canon, episode 4] |
| M4 | the squad, on the night patrol | Shin links her to the others: names given both ways; they accept her, but never as an equal while she stays behind the wall; later, alone, Shin's own name and Shourei | [canon, episode 4] |
| before M5 | Lena, Shin | how Shourei saved her life in the ambush that killed her father | [canon, episode 5] |
| M5 | Shin, Lena | what he hears: the Legion's voices | [canon, episode 5] |
| M6 | Shin, Lena | more of Shourei, and her feelings for Shin, unspoken; the order to attack the Legion base (M7), which Shin takes knowing it is a trap | [canon, episode 6] |
| M7, before the festival | Anju and Kurena, Lena not linked | Daiya's death and Anju; whether to tell Lena the squadron's secret | [canon, episode 7] |
| M7, before the attack | everyone | the festival | [canon, episode 7] |
| M7, after | Shin, Raiden, Lena | the truth about Spearhead; Raiden on why they still fight: to keep their pride by going down fighting | [canon, episode 7] |
| M8 | Shin and Raiden; then Lena | Shourei's voice; the farewell | [canon, episode 8] |
| after M9 | nobody | Lena is gone; the silence is the scene | [new] |
| M10, M11 | the five, at night fires | Shin's plan to find a country the Legion has not taken; Theo's drawings in the fire; the rest talk freely | [canon, episode 10]; the rest [new] |
| M12 | the five | the school night | [canon, episode 11] |

Episode 4's night is split in two here: the apology to Shin and his custom of carrying the names go to the
talk after M3, the squad's names and Shourei to M4. The spec's M4 paragraph puts the custom and the 561 in M4;
this table moves them to M3. Where canon has a talk, the table uses it; [new] fills only what the anime skips
(the spec's rule).

### 9.8 How much there is to write

| Kind | Lines (about) | Notes |
|---|---|---|
| Mission story lines | 720 | 13 missions and 2 console chapters, about 50 each |
| Combat calls | 480 | 8 main speakers, about 60 each, so nothing repeats within minutes (11, feature 1) |
| Night talks and the fires | 350 | 16 scenes of about 22 lines |
| The base: things and rooms, per act | 250 | each owner's line, and the line about them after |
| Lena's console: briefings, HQ, the news, her uncle, Annette | 150 | the Republic's clean voice |
| The voices of the dead | 80 | Black Sheep and the two Shepherds |
| M0's teaching lines, Lev, the old Handler | 70 | |
| **All** | **about 2,100** | about 25,000 words: a short novel's worth [estimate] |

The spec's order holds: Act I is written in 0.2 and read by Emerson before anything is voiced; each act's script
comes before its phase. With D2's default (Piper for the fight calls, dry over the Para-RAID by D16), the 480 combat calls are the first to get
voices.

### 9.9 The 559 names

Shin carries 559 names into M0 (the spec, 4.4). They need writing once, with care [new]:
- in the canon roll's mix of origins (Kujo Nico, Kaie Taniya, Daiya Irma, Lecca Lin, Hariz Senya...), since the 86
  are the Colorata: every Republic citizen without the Alba's silver hair and eyes, of every origin [canon,
  episode 2];
- ending with Spearhead's own first two dead, the spec's two light-novel names (it spells them as the Japanese
  reads them, Mashu Nanaki and Mina Shiroka): **Matthew Nanaki** (Walpurgis, Raiden's platoon, the quiet one, the
  first to fall) and **Mina Siroca** (Artemis, Theo's platoon, killed in an infantry-type charge, Kujo's
  little-sister figure) [canon, light novel Volume 10, "Triage Black Tag"]. At M0 their bunks are already bare
  (setup 16), and Kujo's moon watch after Mina's death can be one of his M0 lines;
- no famous real people; no repeats; a callsign and a former squadron each, for the names screen;
- shown quietly: the screen scrolls, no sorting or statistics.

## 10. The tone as a sensory grammar

The spec's 3.2 says which tone lives where. This says what each one is made of, so every session builds it the
same way [new; the light figures are colour temperatures in kelvin, lower is warmer. They are targets: today's presets
run from `dusk_haze`, about 2,430 K, to `clear_noon`, about 5,820 K (McCamy's formula on each preset's sun colour
[measured]), and a preset is retuned only after Emerson looks].

| Tone | Light and colour | Camera | Sound bed | Voices | HUD | Pace |
|---|---|---|---|---|---|---|
| **The grind** | the act's light (the spec's 3.3: the light carries the calendar); in Act I a low warm sun, about 4,000 to 4,800 K, long shadows, gold grass, poppy-red accents | steady, slow; no shake | wind, insects, grass on the legs, servo hum; music sparse | clipped callsigns, routine checks, dry jokes | minimal: compass, ammunition | a contact every 3 to 5 minutes |
| **The fight** | the map's light plus muzzle flash, tracer, smoke and fire | shake only from real forces (hits, landings, recoil), never added for drama | shots, cracks, ricochets, the Legion's machinery; music driving | short, overlapping, cut off; Lena steady | full | a contact every 20 to 40 seconds; 10 to 20 seconds of breath after each wave |
| **The base** | warm work lamps, 2,700 to 3,200 K: a new `hangar.json` preset, since `work_lights` and `floodlit_night` are cool white (`dawn_door` is the nearest warm start); dark corners | walking pace, free | the hangar's hum, tools, the cat, a radio low | relaxed, teasing, real names | none | the player's own |
| **The voices** | shadows a little colder and thinner, never grey overall; dust in the air | tighter framing | the world thins (quieter, less bass) while the dead speak; a low drone | whispers placed in 3D: the dead's last words | the hearing ring | dread, then a rush |
| **The names** | low sun or dusk (2,400 to 3,500 K) | still; no cuts | near silence: wind, metal ticking as it cools | at most one line; nobody fills the silence | none | 10 to 30 seconds of nothing |
| **The wall** | Lena's console: cool white-blue screen light, clean type | none: the console is the screen | office quiet, the console's tones | polite, bureaucratic, cheerful | the `handler_console` theme | measured |
| **Beyond the border** | open noon, mist, gold evenings, wider views | a wider view when cresting a hill | birds, wind in firs, water; music open | the five talk freely, no Handler | minimal; Fido's map | open, wandering |

**Moving between tones.** The radio is the bridge: a line can start in one tone and end in the next. A death cuts
the music within a beat. Humour comes back only after a base scene. Nothing ever fades to grey.

**How the tone fails, and the guard against each:**

| Failure | What it looks like | The guard |
|---|---|---|
| Melodrama | characters naming their feelings; music swelling over a death | no music on a death (the spec's 3.5); a critic flags any line that states a feeling outright |
| Misery as spectacle | deaths staged for shock; bodies | only the canon deaths at their beats (D5); nothing shown (pillar 3) |
| Grey grief | the world drained of colour for sadness | colour stays (the spec's 3.5); the exposure and colour check (12) flags a saturation drop |
| Power-fantasy drift | streaks, per-kill pop-ups, slow motion, an announcer | no streaks, per-kill pop-ups or score; the HUD's "Legion destroyed" count stays as wave progress and the debrief keeps grade and kills, as today (`mission_hud.gd`, `mission_end.gd`); the kill cam for the Legion only |
| A cartoon Republic | sneering villains | polite and banal; the cruelty only in calm words |
| Whiplash | a joke straight after a death | humour waits for a base scene |
| Over-explaining | Shin explaining himself; tutorials breaking a scene | Shin speaks least; teaching comes in the squad's lines |
| Quoting the anime | lines lifted word for word | every line is new writing on a canon beat |
| Sameness | every mission one more wave fight | each mission's own rule (9.5) |

## 11. AAA features to add

Features the spec does not have, each from games that do this well. Priorities as in the spec (P0 to P2).

| # | Feature | What it is | Learned from | Neutral? | Priority | Phase |
|---|---|---|---|---|---|---|
| 1 | **A radio that picks lines by context** | grows the event priorities and cool-downs `radio.json` already has: each line gets conditions (who is alive, what just happened, range, damage, act), a priority (story over danger over orders over banter), a cool-down, and a rule that nothing repeats within minutes; a story line can interrupt a call, never the other way round | Valve's rule-based dialogue (Left 4 Dead 2; Elan Ruskin's GDC 2012 talk) | yes: data and a small matcher | P0, as the way to build the spec's many-speaker radio | 0.2 |
| 2 | **A music state machine** | states (explore, tension, fight, after, story) that change on phrase boundaries using cue points kept in `music.json`; short stings for events. The 86 soundtrack is finished stereo tracks, so crossfades rather than layered stems | the adaptive scores of most AAA action games | the logic yes | P1 | 0.4 to 0.7 |
| 3 | **Mark and call** | one button marks what the crosshair is on (a Legion, a place, a wreck); the squad says it aloud and acts on it | Apex Legends' ping | the logic yes | P1 | 0.3 |
| 4 | **Callouts by the clock** | wingmen call threats by clock direction and range band, and acknowledge orders aloud (the Handler's wave lines already give a bearing and distance) | Ace Combat's wingmen | yes | P1 | 0.3 to 0.4 |
| 5 | **Machines that act** | in story moments the Juggernauts perform: a sensor turning toward a voice, a hatch opening, a slump when hit, a leg dragged; framed like actors | Armored Core VI (a story told through machines and voices), Titanfall 2 (BT's body language) | clips from Blender, yes | P1 | 0.2 onward |
| 6 | **Absent presence at the base** | 9.6: objects that change between visits, voices from other rooms | Gone Home, What Remains of Edith Finch | yes | P0 (the base is P0) | 0.2 |
| 7 | **Readable damage** | dents, scorch, holes, missing panels and leaks per part, kept for the mission (and between missions in Act IV, the spec's P2) | MechWarrior 5 | partly | P1 | 0.3 and 0.8 |
| 8 | **Telemetry** | grows the bots' `report.json` samples into a JSON-lines log per run (time, position, event, health, frame time), the same from bots and from Emerson; a Python report: where he died, where he struggled, time per beat, frame-time spikes | standard practice in big studios' playtest labs | yes | P0 for building the game | N1 |
| 9 | **Safe saves** | three rotating autosaves, writes that cannot leave half a file (write, then rename), a version and migrations, a fallback when a save is damaged | standard | yes | P0 (extends the spec's save) | 0.2 |
| 10 | **Dynamic resolution** | keep the frame target on weaker graphics: FSR 1 and FSR 2 are settings already (`settings.json`); add a scale that adjusts itself to hold the frame target. Unreal has its own upscaler and plugins | standard | no | P1 | 0.9 |
| 11 | **No hitches when an effect first appears** | shaders compiled ahead (at load or at build) so the first explosion, first smoke and first muzzle flash do not stall a frame | standard | no | P1 | 0.9 |
| 12 | **Input buffering, without cheating physics** | a jump or shot pressed shortly before it becomes possible still happens when it does. The game-mode jump already has a 0.2 s coyote window (a jump just after leaving the ground: `jump.coyote_s` in `tuning.json`, from Emerson's playtest notes of 2026-09-30); keep it, keep bench mode strict, and add no other grace that pushes without a leg on the ground | standard, filtered through the physics rule | yes | P1 | 0.3 |
| 13 | **A Legion field manual** | entries unlocked on meeting each type, in the Republic's clean voice; the Black Sheep entry rewritten after M5 | Halo's and Mass Effect's codex | yes | P2 | 0.4 onward |
| 14 | **Accessibility to the Xbox guidelines' level** | targets in section 12 | Xbox Accessibility Guidelines | mostly | P1 | 1.0 (the spec) |
| 15 | **Text ready for other languages** | every string in tables with IDs; a pseudo-translation pass (longer strings, accents) that shows clipped text | standard | yes | P2 (English only at 1.0) | 0.9 |
| 16 | **Shot list per mission** | the camera moments (the spec's P1) planned as a short list of framed shots per mission, set before building | film practice | yes | P1 | 0.5 and 0.7 |

## 12. Polish targets, with numbers and checks

What "AAA" means for 1.0, as things that can be measured [new targets]. **The reference machine** is the new PC
(D15); the laptop keeps `PLAN.md`'s Iris Xe targets. "Today" says what is known.

| Area | Target | How it is checked | Today |
|---|---|---|---|
| **Frame and feel** | | | |
| Frame pacing | 1 % low at least 70 % of the average; no frame over 50 ms after a mission's first 10 seconds | `tools/fps_log.py` on bot runs, once it has a `--map` option (it measures the test range only today) | the 1 % low, worst frame and hitches over 50 ms are logged already (`frame_stats()` in `scripts/core/bot.gd`), test range only; Ultra on the laptop: 1 % low 13.3 of 15.1 average [measured, `logs/fps/`] |
| First-effect hitches | no frame over 100 ms when an effect first appears | a bot run that fires every weapon and effect once, logging frame times | not measured |
| Input to motion | an input reaches the physics in the first tick after the frame that reads it: at most one rendered frame plus one tick (25 ms at 60 fps, 42 ms at 30 fps). Godot reads input once per rendered frame on desktops; per-tick flushing is Android-only [web, Godot docs] | a run at `--fixed-fps 30` (four ticks per frame) that injects input between frames and counts ticks; the normal suite runs one tick per frame (`--fixed-fps 120`), so it cannot see the gap. Button-to-screen time needs a high-speed camera; no tool for it | not measured |
| Load time | mission start within 20 s on the reference machine, 45 s on the laptop | bot timer from Deploy to the first frame you control | not measured |
| Stability | no crash and no script error in 30-minute soaks on every map and in the campaign bot | the engine log's error count is zero | the bot stalls now and then [handoff bug 6] |
| Frame rate | the spec's 1.0 item 9, per mission and preset, on both machines | fps log per mission | per map, before 0.1.1's grass [handoff] |
| **Look** | | | |
| Texture detail | at least 10.24 pixels per cm on the Juggernaut and Legion up close; 5.12 on the world | a script over `data/mech_surfaces.json` and the world shaders' tiling: texture width in pixels times repeats per metre, divided by 100. The models carry no UVs; their surfaces are projected (triplanar, `scripts/look/finish.gd`), so the data sets the density | mechs 8.2 to 16.4 px/cm from 1024 px sets: rusted paint (8.2) and chipped paint (9.2) fall short [measured]; world not measured. A UV-and-bake texture pipeline instead would be a new feature with its own price |
| Detail with distance | every mesh over 10,000 triangles has 3 or more LODs (or Nanite); no visible pop at 1080p | a model check script; a camera dolly bot that flags sudden frame-to-frame changes | Juggernaut full 539k, lite 130k [measured] |
| Draw distance | grass to 150 m or more with a fade; trees to the horizon | fixed-camera shots | grass ends at 60 m [handoff] |
| Exposure and colour | sky clipped in under 1 % of a daylight frame; the names and voices shots keep their mean saturation within 20 % of the same map's grind shot | `tools/histogram.py` (it reports clipping and mean saturation) on the six fixed shots per map, and on paired shots | Allegheny's sun blows out [handoff]; saturation not measured |
| Sharpness | no fixed shot softer than the 0.1.1 reference | `tools/sharpness.py` | a tool exists |
| Grounding | feet within 2 cm of the ground when planted; nothing floats or sinks | a bot logs foot height while planted | not measured |
| Foot slide | a planted foot drifts under 3 cm per step at a walk | the same log | not measured |
| Silhouettes | each Legion type named right at 300 m in a greyscale shot | a blind test (Emerson or a critic agent) | the shapes are boxy [handoff] |
| **Sound** | | | |
| Loudness | whole mix about -24 LUFS (within 2), true peak at most -1 dBTP, loudness range up to 20 LU (PlayStation's guidance) [web] | Godot's movie maker (`--write-movie`) records a bot run; `ffmpeg`'s loudness filter measures it | not measured |
| Speech over noise | music and effects duck 6 to 9 dB under every spoken line | the mixer's data, then by ear | text only today |
| No repeats | the same call not twice within 2 minutes; the same footstep sound not twice in a row | the radio's log; a test | random picks [seen `scripts/ui/radio.gd`, line 91] |
| Sound and sight together | at the player, shot sound and flash in the same frame; far sounds late by distance at 343 m/s | a test | the delay exists [handoff] |
| **Text, menus, access** | | | |
| Text size | body text at least 28 px at 1080p (Xbox guideline 101) [web]; subtitles larger by default | a script over the themes; screenshots | not measured |
| Subtitles | at most 2 lines of about 40 characters; on screen for at least 1.5 s and no faster than about 17 characters a second; speaker named | a lint over the dialogue database | subtitles exist [seen `settings.json`] |
| Contrast | text at least 4.5 to 1 against what is behind it | a script over theme colours | not measured |
| Controls | every action rebindable and reachable on a pad | a test comparing `input.json` with the pad map | the blade has no pad button [handoff] |
| Not colour alone | every colour-coded mark also differs in shape | a list check | the filter recolours only [the spec] |
| Menus | every screen works with keys alone and with a pad alone; feedback within 100 ms | the smoke bot | the smoke bot plays menus [handoff] |
| **Story and content** | | | |
| Lines | every line has an ID and speaker and passes the tone lint (no capitals shouting, no banned words) and a critic read | a lint script, a critic agent | no lines yet |
| Missions | a bot reaches the end of every mission | the campaign bot | 2 missions |
| Beat actions | each has a unit test | the suite | none yet |
| Pacing | no stretch over 3 minutes without a story or fight beat | telemetry: time between beats | not measured |
| Difficulty | on Normal a fixed-skill bot wins every mission; on Story a bot with added aim error still wins | campaign bot runs per difficulty | no presets yet |
| **Robustness** | | | |
| Saves | 100 random save-and-load round trips come back equal; every older save version loads | tests | no saves yet |
| Friends' copies | installs and runs on a real Windows PC and a Mac without help | a real run | Linux only verified [handoff] |
| Credits | every shipped asset licensed and credited | a script comparing assets with `SOURCES.md` | OSM and some sounds uncredited [handoff bug 11] |

## 13. Gaps added to the spec's list

The spec's section 6 ranks 20 gaps. This pass adds these, in order of importance:

21. **The feel figures are Godot-bound and scattered.** Some are pinned as GDScript bounds (`tests/test_slide.gd`:
    gallop 66 to 74 km/h, 0 to 50 km/h in 0.8 to 1.8 s; `tests/test_feel.gd`: squat, nose dip, lean, landing tilt),
    but not in one engine-neutral file a port's tests could read (`golden.json`, rule 7.6).
22. **Godot paths and settings in the data** (339 paths, the weather presets).
23. **Telemetry is bot-only and point-in-time.** Bots write the mech's `telemetry()` and every Legion unit's
    position, health and brain state to `report.json` at scripted moments (`scripts/core/bot.gd`,
    `scripts/mission/mission.gd`); Emerson's own runs log nothing, and there is no event stream or report.
24. **The radio is per event, not per situation.** Events have a priority and a cool-down (`radio.json`,
    `scripts/ui/radio.gd`), but the line within an event is random, and nothing checks who is alive, the act or
    what was said before (11, feature 1).
25. **The Para-RAID sound contradicts canon** (D16): the spec plans static and a range fade for a link that
    ignores distance.
26. **No dialogue database or tone lint** for the 2,100 lines.
27. **No music states.** Tracks play per use (menu, explore, fight), not per moment.
28. **No mark-and-call or clock callouts** for directing the squad by voice.
29. **No hitch, loudness or texture-density checks, and LOD checks only for the Legion** (`tests/test_legion.gd`:
    the full model to 150 m): the look and sound have no measured bar.
30. **No input buffering**, and no written rule on which grace is allowed (the coyote window stays: Emerson asked
    for it, and removing it would be his call).
31. **The spec's sizes have no AAA allowance:** about 12 to 18 more sessions (section 14).
32. **The machine targets predate the new PC.** `PLAN.md` sets Iris Xe targets (Low 60 fps, Medium 45, High 30,
    Ultra none), and the roadmap to beta names a MacBook Air M5 for testing the share copies; nothing places the
    new PC in that scheme (D15).

## 14. The order of work, revised

The spec's phases stand. This inserts the engine question and the AAA work.

| Step | What | Sessions | When |
|---|---|---|---|
| 0.1.2 | Clean slate, as the spec says | 1 to 2 | now |
| **N1** | **Engine-neutral groundwork:** asset IDs in place of `res://` (a Godot adapter, the data converted, tests); `golden.json` and the bot that measures the movement figures into it; the units note and the axis totem; telemetry log and report (grown from the bots' `report.json`); the bot timeline spec; the save format spec; the dialogue database format and lint | 3 to 5 | right after 0.1.2 |
| 0.2 | The story spine, as the spec says, plus the context radio (1), the base's absent presence (6), safe saves (9), machines that act in the slice (5), and M0's night preset and self-propelled mine (9.4). Build its engine-neutral half first: the Act I script, the beat and campaign data, the save format, the names, new models | 11 to 17 (the spec's 9 to 14, plus 2 to 3) | after N1 |
| **E1** | **The bake-off** (section 6). It may interrupt 0.2 | 7 to 9 | as soon as the new PC is built |
| D14 | Emerson decides the engine | | after E1 |
| Port | only if Unreal: P1 to P8 (section 8) | 28 to 48 (its 32 to 52, less the 4 sessions of E1's Unreal work it reuses), plus 5 to 8 if 0.2 is done by then | at once after D14 |
| 0.3 to 1.0 | the spec's phases with the AAA features and polish checks folded in | the spec's 67 to 102, plus 10 to 15 | after 0.2 (or the port) |

**Totals [estimate]:** staying in Godot, about **99 to 150 sessions** to 1.0 (the spec's 77 to 118, plus N1,
E1 and the AAA work). Moving to Unreal after 0.2, about **132 to 206**.

**While the engine is undecided:** do N1 and the neutral half of 0.2 first. If the new PC is not ready when they
are done, carry on with 0.2 in Godot rather than stall, knowing the rule of thumb's price (section 4). Hold off on
big Godot-only investments (new shaders, a custom grass or terrain system, a UI rewrite) until E1.

## 15. Decisions for Emerson

Each with the default a session uses until he answers. They continue the spec's D1 to D13.

- **D14. The engine.** Default: Godot, until the bake-off (E1) on the new PC; Unreal only if it wins by the
  default rule in section 6, and then a port at once, before 0.3. Unity is not tested unless he wants it.
- **D15. The new PC's system, and the reference machine.** Default: Arch Linux, like the laptop; the new PC is the
  reference machine for High, Ultra and every polish target; the laptop keeps `PLAN.md`'s targets (Low 60 fps,
  Medium 45, High 30) unless Emerson relaxes them (he put graphics over frame rate on 2026-10-02, `PLAN.md`); the
  MacBook Air M5 stays a test machine for the share copies. If the new PC will run Windows, say so: Unreal and Unity are both smoother there, and the bake-off
  should run on Windows.
- **D16. How the Para-RAID sounds.** Canon: it "ignored all interference by distance, weather, and terrain" (light
  novel volume 1, chapter 1), and its synchronisation rate sets which senses it shares, sound being the lowest
  [canon, wiki]. The spec's radio filter, static and range fade do not fit, and its M9 "range" wording sits
  oddly with its own note that the link works across any distance. Default: Para-RAID voices sound close and dry,
  as if the speaker were beside you; HQ's broadcasts and recorded messages get the radio treatment; how the link
  ends in M9 is staged the way episode 9 stages it (watch it first), not as a fade into static. This changes, in the
  spec: D2 (no radio filter on Para-RAID calls; HQ's broadcasts keep one), the 5.2 and 5.9 radio rows, phase 0.7's
  list ("the radio filter and static" becomes "the HQ broadcast filter") and the M9 beat.
- **D17. If Unreal: C++ over Blueprints.** Default: all game logic in C++, UI built from C++ and data, and
  Blueprints only as thin wiring of assets. Claude can read, compare, test and review text; a Blueprint graph is a
  binary file it cannot. The official MCP plugin (experimental) may soften this; the bake-off measures it.
- **D18. The dialogue format.** Default: one JSON file per act in the game (ID, speaker, text, mission, beat,
  conditions, priority, cool-down, voice file), and a readable script generated from it for Emerson to read and
  mark up. Alternative: a spreadsheet he edits directly.
- **D19. Sound middleware.** Default: none; the engine's own sound. FMOD Studio (a sound tool used by many games)
  only if the music state machine outgrows it: FMOD has official Unity and Unreal plugins and a community-kept
  Godot one (utopia-rise's fmod-gdextension) [web]. Its licence terms need reading before use, and nothing is
  installed without review.
- **D20. The polish bar.** Default: every target in section 12 is part of 1.0, measured on the reference machine, and
  each laptop figure (load time, frame rate) on the laptop. He trims or raises any of them.

## 16. Risks

The spec's eleven risks stand. New ones:

1. **The feel does not come back after a port.** The most serious. Guard: E1's feel gate (the golden numbers) and
   Emerson's veto after playing, before any commitment; UnrealJolt is the fallback for the body.
2. **Claude's unattended loop slows in Unreal**: binary assets, compile times, steps that need the editor's
   hands. Relay's strength is unattended work. Guard: E1's loop gate (a ten-line change to a passing test, unattended, in under 5 minutes); D17; the MCP plugin is experimental.
3. **Months without new content during a port** (32 to 52 sessions). Guard: decide early; keep writing the
   script and building models in Blender during a port, since both are engine-neutral.
4. **Unreal Engine 6** (early access late 2027) [web] may mean another move for an Unreal 5 port. Guard: re-read
   Epic's plans at E1.
5. **The new PC's date is unknown**, and each Godot-only session adds to a later port. Guard: N1 and the neutral
   half of 0.2 first; the rule of thumb prices the rest.
6. **AAA scope creep.** Sections 11 and 12 add 12 to 18 sessions. Guard: the P2 items go first (the spec's risk
   1), then the P1 polish targets.
7. **Friends' copies on weaker PCs.** Unreal's look wants strong graphics. Guard: the laptop as the minimum
   (D15), measured.
8. **Linux under Unreal or Unity** is less travelled than Godot's [web]: if the new PC has an AMD graphics card,
   check Unreal on it in E1.
9. **Canon drift in the deeper story.** Section 9 invents staging (marked [new]). Guard: watch each episode
   before scripting it; a critic checks lines against the canon and the tone rules.

## 17. Sources and what was checked

**Measured on 2026-10-08** (by Umi in the morning, and by Mei for the per-folder table and the Godot class count):
line and file counts in `~/Games/eightysix` (scripts, tests, tools, shaders, data, bots, scenes), folder sizes
in `assets/`, `.blend` counts and sizes in `~/Models`, `project.godot` (physics engine, tick rate, layers),
`godot --version` (4.7.2), the API scan in 2.2 (Godot's class list from `godot --dump-extension-api`), the
`res://` counts, `git log` (171 commits).

**Read in the game:** `tools/sync_models.py`, `tools/model_sources.json`, `tools/build_juggernaut_data.py` (heads),
the `scripts/` file list, `README.md` (Start here), `data/weather.json` (Umi); `scripts/mech/standin_mech.gd`,
`scripts/ui/radio.gd` (the random pick, line 91), `data/settings.json` (subtitles).

**Docs:** the spec (`2026-10-08-spec-and-roadmap-to-complete.md`), `2026-10-07-handoff.md`,
`~/Forge/sessions/juggernaut-alpha/PLAN.md` (Umi).

**Web, 2026-10-08 (Umi; addresses not kept):** Unreal Engine 5.8's release (2026-06-18: MegaLights
production-ready, Lumen lite, Mesh Terrain, the experimental MCP plugin); Unreal Engine 6's announcement
(2026-06-17: early access late 2027, Verse, Scene Graph); Epic's Linux requirements; Unity 6.3 LTS (December
2025); Unity's 2026 plans (URP the focus, HDRP maintenance only, the built-in renderer deprecated from 6.5);
Unity's MCP open beta (2026-05-11, needs a Unity AI subscription); Unity's Linux editor requirements; Godot 4.6
(Jolt by default) and 4.7 (2026-06-19: HDR output, area lights; a new GI system not confirmed shipped);
JoltPhysicsUnity (community); a Jolt plugin for Unreal was missed here and found by a critic (UnrealJolt); PlayStation's loudness guidance; Xbox Accessibility
Guideline 101.
**Web, 2026-10-08 (Mei):** Epic's Live Coding page for 5.8 (names no desktop system);
github.com/utopia-rise/fmod-gdextension (a Godot 4 FMOD extension, maintained). **Canon, the 86 fandom wiki
through its API:** "Kujo Nico" (the countdown on the hangar's blackboard until his death, stopping at 128 days;
Lev's disapproval), "Theoto Rikka" (the sketchbook; the Handler portraits at the First Ward base; the drawings
thrown into the fire in episode 10, with the quoted line), "Lev Aldrecht" (mechanic), "Para-RAID" (the volume 1
quote; the synchronisation rate).

**Not checked:** anything on the new PC; Unreal or Unity themselves (nothing installed or run); Live Coding on
Linux; Unreal on AMD graphics under Linux; FMOD's licence terms; whether Godot's FastNoiseLite matches the C# and
C++ library bit for bit; the episodes themselves (wiki summaries only); the units inside every data file; the
handoff's test results (taken as written); any sizes or session counts beyond their stated reasoning; Epic's Linux requirements page (read by a critic only:
it needs a browser).

**Web addresses, for rechecking** (the pages behind the [web] tags, 2026-10-08): Epic's "Linux Development
Requirements" and the Unreal Engine 5.8 release notes (dev.epicgames.com/documentation);
docs.unity3d.com/6000.3/Documentation/Manual/system-requirements.html; unity.com/topics/render-pipelines-strategy-for-2026;
godotengine.org/releases/4.6/ and godotengine.org/releases/4.7/; Godot's `input_devices/buffering/agile_event_flushing`
setting in the class reference; devdocs.xbox.com/gaming/accessibility/xbox-accessibility-guidelines/101;
github.com/seep/JoltPhysicsUnity; github.com/Yadhu-S/UnrealJolt; github.com/utopia-rise/fmod-gdextension. Canon:
86-eighty-six.fandom.com, read through its API (`api.php?action=parse&page=<page>&prop=wikitext`), pages Episode 1
to 11, Kujo Nico, Theoto Rikka, Lev Aldrecht, Para-RAID, Matthew Nanaki, Mina Siroca, Light Novel Volume 1.

**Checked by critics (2026-10-08).** Three rounds of fresh critic agents (Opus) read this doc against the request,
the game repo, the spec and the wiki: critic A on facts, numbers and engines (13 findings), critic B on request
coverage, canon, story, tone and the README entry (21 findings). 33 are fixed here and one (F2) was correct as
written. Every repo fact a fix rests on was re-checked by grep or a script, and the canon fixes on the wiki's API.
- A1 the coupling share is "three lines in four", with the second pass (18 to 26 %) in 2.2; A2 116 bot timelines;
  A3 339 `res://` paths in six files; A4 our models' axes (+Y front in Blender, -Z in the glb).
- A5 the 1 % low is logged already, on the test range only (`fps_log.py` needs `--map`); A6 the models have no
  UVs, so texture density comes from `mech_surfaces.json` (8.2 to 16.4 px/cm); A7 Godot reads input once per
  rendered frame, so the latency test runs at `--fixed-fps 30`; A8 E1 has five pass-or-fail gates instead of a
  weighted scoreboard, Step G 2 sessions, Steps U 5 to 7 with tests and a packaged build, and Emerson's play is a
  veto (E1 is 7 to 9 sessions, so the totals rose by 2); A9 UnrealJolt exists; A10 Unity's Linux editor allows
  Wayland in part, and Epic lists AMD and memory figures; A11 the sounds are kept as they are (WAV, OGG, MP3) and
  `sounds.json`'s Godot fields are named; A12 this section; A13 Unity's CPU particles, and the port reuses 4
  sessions of E1.
- F1 M0 at dusk and night, with the rescue and the self-propelled mine; F3 Theo's quote; F4 Lev's arc; F5 the 576
  names left with Fido at M11; F6 Daiya's cat; F7 the canon epilogue; F2 (the countdown) stood as written.
- F8 and F9 the night talks follow canon order: episode 4's night split between M3 and M4, Shourei's rescue before
  M5, episode 6's talk, Anju and Kurena before the festival, Raiden's "pride", Shin's plan and Theo's drawings at
  the fires. One change from the critic's fix: the [new] Anju and Lena talk after M6 was dropped, as canon's Anju
  and Kurena talk covers it. F10 Matthew Nanaki and Mina Siroca, and the Colorata; F11 section 1 now says the maps
  and data need a one-time conversion.
- F12 the coyote window stays (Emerson asked for it); F13 the radio already has priorities and cool-downs; F14 D16
  names every spec line it changes; F15 the feel figures and bot telemetry that exist; F16 kelvin targets follow
  the act, and the base needs a warm preset; F17 FSR and the Legion's LOD exist; F18 the saturation check, folded
  into the Exposure row (still 32 targets); F19 the Iris Xe targets and the MacBook Air M5 (gap 32, D15, D20); F20
  the README entry; F21 the kill count stays as progress, with no streaks.
