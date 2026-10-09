> **2026-09-25:** the remaining work here now lives in `sessions/2026-09-25-S4-blender-godot-acchan.md`. Work from that brief.

# Plan: Blender + Godot tooling upgrade

> **S4 (2026-09-25 evening):** Upgrade 3 done (mech-forge rewritten),
> godot-forge updated, interrupted checks run (test_godot 7 passed, black and
> pyright clean), /tmp scratch already gone. Left: A31 polish (real character,
> terrain, props, sky) and the end-to-end demo. Current state lives in the S4
> brief's State section.

Written 2026-09-25. **Partly built**: see "State 2026-09-27" and "State at handoff" right below.
Follow the `forge-session` and `verify` skills.

## State 2026-09-27 (Kiln, S11): A31 character done; what is left
VERIFIED:
- A31 (Emerson: "3 Both"): the third_person template's capsule is now the
  VRoid **HairSample_Female.vrm** (CC0 per VRoid's FAQ; 17 MB, in
  `shared/assets/characters/hairsample_female/` with manifest.json) playing
  Quaternius's **Universal Animation Library** free edition (CC0; 46 clips,
  4 MB, `shared/assets/animations/universal_animation_library/`, from the
  github.com/J-Ponzo/gltf-universal-animation-library mirror of itch.io).
- New `shared/bridges/godot/humanoid.py`: BoneMap + minimal `.import` onto
  Godot's SkeletonProfileHumanoid, from a VRM's own humanoid table (0.x and
  1.0) or a Rigify DEF- rig; both become `%GeneralSkeleton`. template.json
  gained `assets` (copied from shared/assets) and `retarget`;
  `godot_new_project` does both (acchan godot.py `template_assets`).
- Checks: `tests/test_godot_humanoid.py` 5 passed; acchan `test_godot.py` 9
  passed, incl. a real headless walk (FORGE_DEMO_WALK, 150 frames: moved
  5.5 m, blend 1.0, thigh swing 1.66 rad, no track errors); acchan suite 161
  passed; `godot_check` clean on a fresh project; the VRM imports in
  headless Blender (1 armature, 119 bones, 3 meshes, 1.63 m).
- godot-forge skill updated (character, `ual/<clip>`, humanoid.py).
NOT CHECKED: how it looks on screen (no GPU runs from Claude, Emerson's
rule). His check: `godot_new_project('~/Games/tp', template='third_person')`
then `godot_play('~/Games/tp', seconds=8)` with FORGE_DEMO_WALK=1, or open
it in the editor and press F5.
LEFT: textured ground and rock/tree props instead of the grey ground and
crates in main.tscn (Poly Haven via assets_get); the end-to-end demo (Blender
HDRI scene -> export_godot -> template); a new project is 46 MB after import.

## State at handoff (2026-09-25; session 1 stopped at 94% usage, session 2 stopped at 17:58 by Emerson)

VERIFIED (tests run, output seen):
- Upgrade 1 done: `shared/forge_assets.py` (Poly Haven search/get/local, md5
  check, path-escape guard, cache) + Acchan toolset `apps/acchan/acchan/tools/assets.py`
  (`assets_search`, `assets_get`, `assets_local`). `tests/test_forge_assets.py`
  7 passed (fake network). Real download worked: `abandoned_bakery` HDRI in
  `shared/assets/polyhaven/` (1.7 MB).
- Upgrade 2 done: `shared/bridges/blender/forge_studio.py` (use_hdri,
  import_asset incl. .vrm, texture, frame_camera, look studio/toon/hdri,
  rig_human (Rigify), keyframe, render_animation -> mp4, export_godot -> glb),
  exposed as `forge.*` via `forge_studio.HELPERS` in `forge_bridge.py`.
  `tests/test_blender_studio.py` 1 passed (every helper in headless Blender).
  Blender bridge tests still pass. Backups in `backups/2026-09-25-blender-studio/`.
- VRM add-on v4.7.2 installed in Blender 5.2 user extensions (sha256 checked
  against extensions.blender.org); `bpy.ops.import_scene.vrm` exists.
  Not yet checked on a real .vrm file.
- Godot add-ons in `shared/godot_addons/`: phantom_camera (v0.11.0.3),
  vrm (godot-vrm v2.1.0), Godot-MToon-Shader (main, MIT; godot-vrm needs it).
  `godot_new_project` now copies every add-on there, enables their plugin.cfg,
  and writes `[autoload]` lines from each add-on's `.forge-autoload` file.
  A new project opens headless with 0 errors; `godot_check` clean.
  Acchan suite 111 passed.

- (session 2, 17:52) godot-vrm fixed for Godot 4.7.2 by a local patch: four
  GLTF hook overrides got a trailing `return OK` (details and file list in
  `shared/godot_addons/vrm/FORGE-PATCH.md`; unpatched copy in
  `backups/2026-09-25-blender-studio/godot-vrm-before-4.7-patch/`). Both
  `.forge-disabled` files deleted. A fresh `godot_new_project` enables
  forge_bridge, phantom_camera, vrm and Godot-MToon-Shader; `godot --headless
  --editor --quit` prints 0 error lines; `godot_check` says clean.
  Not yet checked: importing a real .vrm file in Godot (no sample on disk).

- (session 2, 17:56) Upgrade 4, template part: starter templates are
  discovered folders in `shared/bridges/godot/templates/<name>/` (files copied
  over a new project, plus `template.json` holding a one-line `summary`).
  `third_person/` has `main.tscn` (sky, sun, ground, crates, Player instance,
  PhantomCamera3D `PlayerCamera` in follow_mode 6 (third person) and a
  Camera3D with a PhantomCameraHost), `player.tscn` (CharacterBody3D, capsule
  body, AnimationPlayer with idle/run clips, AnimationTree BlendSpace1D on
  speed) and `player.gd` (WASD relative to the camera, mouse orbit, Space jumps,
  Esc frees the mouse; env `FORGE_DEMO_WALK=1` walks in a circle with no
  input, for recorded checks).
  `apps/acchan/acchan/tools/godot.py` (backup `godot.py.before-upgrade4`):
  `templates()`, `godot_new_project(..., template="")` (an unknown name is
  refused before anything is written), `import_problems()` (.glb/.gltf/.vrm
  outside `addons/` and `.godot/`: no .import file, `valid=false`, imported
  file missing, WARNING log lines naming the file), and `godot_check` now adds
  those; its clean message is now "No script, scene or model import errors."
  New `apps/acchan/tests/test_godot.py`: 7 passed, including a real headless
  Godot check of the template. Full acchan suite 118 passed. black and pyright
  (0 errors) done on godot.py and the test.
  Bug found and fixed: the first template left out
  `node_paths=PackedStringArray("follow_target")` on the PlayerCamera node,
  so Godot never set follow_target and the camera stayed put while the player
  walked off screen (seen in recorded frames). With it, a headless probe showed
  the camera trailing the player: frame 90 player (4.94, 0, 4.60), camera
  (4.87, 1.50, 8.15).

INTERRUPTED at 17:58 (Emerson stopped the command; nothing half-written):
- Two edits landed but are NOT verified: `player.gd` `_ready` now pitches the
  camera down with `pcam.set_third_person_rotation.call_deferred(Vector3(-0.35, 0, 0))`,
  and `test_godot.py` got an assert for the `node_paths` line.
  Still to run: `black apps/acchan/tests/test_godot.py` (the new assert line is
  over 88 chars), then the tests, then re-record with
  `FORGE_DEMO_WALK=1` + `godot_play('/tmp/x', seconds=3)` and look at frames
  5/45/89 to confirm the camera follows on screen. The only recording
  looked at so far is from before the node_paths fix.
- Scratch left in /tmp (safe to delete): /tmp/vrmtest, /tmp/fp1, /tmp/tp,
  /tmp/tpdemo (has a dbg.gd probe autoload), /tmp/vrm_patch.py,
  /tmp/tpdemo_strip.png.

NOT DONE / BROKEN:
- Upgrade 3 (skill rewrite of `~/.claude/skills/mech-forge`) not started.
- Upgrade 4 is built (see above); only the interrupted checks remain.
- godot-forge skill still says "No script or scene errors."; update it to the
  new message, the `template` argument and the add-ons.
- `godot-forge` skill, `~/Forge/docs/DESKTOP-REACH.md`, `PROGRESS.json` not yet updated.
- End-to-end demo not done.
- **Forge Claude app accounts lack the Acchan MCP tools** (found 2026-09-25):
  the `second` profile's `.claude.json` has no `mcpServers`, and
  `apps/claude/runner.py::mcp_config()` writes only `forge-browser` into
  `~/.local/share/forge/claude/mcp.json` on every start. So sessions run from
  the Forge Claude app have no `blender_*` / `godot_*` / `assets_*` tools.
  Fix: have `mcp_config()` also include the user-level `mcpServers` from
  `~/.claude.json` (the acchan entry), add `mcp__acchan` to what auto mode may
  use if needed, test it in `apps/claude/tests`, and restart the Claude app
  only when no conversation is busy (restarting it ends running sessions).
  Everything else is shared by symlinks (CLAUDE.md, skills, memory, settings).

## Background (why this exists)

- Emerson asked for an "AA-graphics" anime character in Blender. Claude built one
  purely from code (metaballs + numpy face texture). It came out uncanny; he had
  it deleted (`~/Desktop/anime_girl` is gone, on purpose) and asked instead to
  "fix your blender set up and mcp and tools and stuff to make it better",
  with "the best animation and making abilities and assets you can set up".
- **Verified cause of the missing tools:** that session had no `blender_*` /
  `godot_*` tools because it was attached to an older Acchan MCP server
  process. The current `mcp_server.py` offers 93 tools including all 12
  Blender/Godot ones (checked with a raw `initialize` + `tools/list` over stdio).
  A Claude Code restart fixes it; no code bug.
- Lesson recorded in memory `no-code-built-characters`: organic models come
  from assets / character creators; Claude's effort goes into shading,
  lighting, posing, scenes.

## Emerson's answers (verbatim choices, 2026-09-25)

- Installs: "VRM add-on for Blender, godot-vrm, Phantom Camera (Godot)"
- Upgrades: "Yes, all four (Recommended)"

## Installs (approved; sources checked 2026-09-25)

| What | Source | Licence / status |
|---|---|---|
| VRM add-on for Blender | extensions.blender.org/add-ons/vrm/ (repo saturday06/VRM-Addon-for-Blender) | MIT, pushed 2026-09-23 |
| godot-vrm | github.com/V-Sekai/godot-vrm | mixed licence file (mostly MIT), pushed 2026-07-08 |
| Phantom Camera | github.com/ramokz/phantom-camera (also Godot Asset Library) | MIT, pushed 2026-09-21 |

Godot add-ons go into a **shared addons folder** (e.g.
`~/Forge/shared/bridges/godot/addons/` or a new `shared/godot_addons/`) and are
copied into projects by `godot_new_project`, not installed per project by hand.
Blender extension: install into Blender 5.2's user extensions
(`blender --command extension install-file` or the online repo) and enable it
from the bridge. Verify by importing a sample `.vrm`.

## The four upgrades

1. **Asset fetcher** (new Acchan toolset `acchan/tools/assets.py`, discovered by
   the registry like the others). Tools: `assets_search(kind, query)` and
   `assets_get(id, resolution)` over the public Poly Haven API
   (`https://api.polyhaven.com`, CC0: HDRIs, textures, models; checked, it answers 200).
   Downloads **on demand only** (disk is tight) into `~/Forge/shared/assets/<kind>/<id>/`
   with a `manifest.json` holding source URL, licence and author. Cache: never
   download twice. Tests with a mocked HTTP layer in `~/Forge/tests/`.
2. **Blender bridge helpers** (`shared/bridges/blender/forge_bridge.py`, the
   `forge` namespace): `forge.look(preset)` for `studio` / `hdri:<id>` /
   `toon` (cel shader + inverted-hull outline + Standard view transform);
   `forge.import_asset(id)`; `forge.rigify(obj)` (built-in Rigify);
   keyframe helpers; `forge.render_animation(path, frames, res)` to MP4 at low
   res for checking; `forge.export_godot(path)` (glTF `.glb`). Each helper gets a
   test in `tests/test_blender_bridge.py` (headless `blender -b` where needed).
3. **Skill rewrite:** `~/.claude/skills/mech-forge` becomes a general Blender
   skill (mechs, props, characters, environments, animation). Add: a
   "tools missing -> tell Emerson to restart Claude Code; meanwhile use
   `blender -b -P script.py`" fallback; "organic models from assets/VRM, not
   metaballs"; the look presets; the Godot hand-off. Keep it short.
4. **Godot side:** `godot_check` also reports imported `.glb` / `.vrm` problems;
   a third-person character-controller template (AnimationTree + Phantom Camera)
   in the `godot_new_project` template; update the `godot-forge` skill.

## Done when

- All three add-ons installed and each checked on a sample (a VRM loads in
  Blender and in Godot; a Phantom Camera follows a player in `godot_play` frames).
- New tests pass; black + pyright clean on touched files.
- One end-to-end demo, looked at: HDRI-lit Blender render of a Poly Haven model,
  exported to Godot, played with `godot_play`.
- `~/Forge/docs/DESKTOP-REACH.md` and `PROGRESS.json` updated; this plan marked done.
