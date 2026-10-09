# PulseForge: two new visualisers and particle effects

Emerson (2026-09-27): "make 2 new visualisers and particke effects". Written by
ejb-34, which stopped at 90% (5-hour) / 95% (7-day) usage on account "hey", so
this runs as a fresh session, on the account "second" once it is signed in to
the Claude app (profile ~/.local/share/forge/claude/profiles/second).
Standing directions: don't stop to ask questions, do what is best and coolest;
batch tool calls; add, never redesign (PulseForge memory: keep the tabs and the
schema-driven scene forms; `drift` is the one he rated good).

## Read first (small)
- apps/pulseforge/pulseforge/scenes/registry.py docstring: a scene is one file
  defining `SCENE` (metadata + param schema) and `frames(ctx)` yielding
  (H, W, 3) uint8 frames, plus one line in `_MODULES`. Nothing else changes.
- One existing visualiser for the ctx/feature-track shape: aurora.py (278
  lines) or bars.py (196). living.py already draws particles: reuse its code
  instead of writing a second particle system.
- tests/test_scenes.py for how scenes are tested.

## The job
1. Visualiser "tunnel": the spectrum as rings rushing toward the viewer in
   polar space; bass sets the ring radius, beats fire a bright ring, loudness
   sets speed, palette param. Family "visualizer".
2. Visualiser "scope": a glowing oscilloscope / Lissajous trace of the audio
   with phosphor afterglow trails, colour shifting with brightness, a flash on
   kicks. Family "visualizer".
3. Particle effects as a layer any frame-based scene can use: presets in one
   declarative table (embers, snow, sparks that burst on beats, dust motes,
   petals), each preset one dict (count, speed, size, colour, how the music
   drives it). Exposed as scene params (effect + amount), applied after a
   scene's frames, so the existing scenes gain it with no per-scene edits.
   If the renderer has one place frames pass through, put it there.

## Done means (CLAUDE.md definition of done)
- Tests first in tests/ (scene loads, frames right shape/dtype, music moves
  them, each particle preset renders, old scenes unchanged with effect off).
- A real 10-20 s render with a real song for each new visualiser and for two
  particle presets on `drift`; look at extracted frames, not just exit codes.
- UI check: the scene picker shows both new scenes and the particle params
  (headless Chrome through ~/Forge/tests/cdp_driver.py; 0 headless Chromes left).
- black + pyright (with the app's .venv) on touched files; WIP.md + MANIFEST.md
  updated with verified vs not verified; commit in ~/Forge.

## State
- Tunnel + Scope: done and committed (a170938). Tests pass; real-song frames
  (Alto's Odyssey OST, first 12 s, 23 beats) looked at: tunnel good; scope
  re-centred and fitted to the frame, grows with loudness.
- Particles: committed (ae36179, then a brightness fix). pulseforge/particles.py
  has 5 presets in one table (embers, snow, sparks on beats, dust, petals); the
  registry adds `particles` + `particle_amount` (group "particles") to every
  visualizer/scenery/sprites scene; render.py `_feed` wraps every scene's frames;
  "particles" added to LOOK_GROUPS in static/scenery.js and KNOWN_GROUPS in
  tests/test_ui.py. Full suite 335 passed, 1 skipped.
- Real frames of drift at 640x360: embers rise from the bottom, a spark burst
  hangs after a beat. Both read as small, faint dots at 360p. Dot radius scales
  from 720p (`size * h / 720`), so judge them at the real render size; if still
  faint, raise `size` in PRESETS or the halo weight in Layer.step.
- Not done: a full MP4 render with particles on, the UI check (scene picker
  shows Tunnel, Scope and the Particles group; the living scene's look panel
  has a new Particles section), and PulseForge WIP.md + MANIFEST.md entries.
- Owner now: Kenji (ejb-eb) claimed apps/pulseforge on the board (#250) to finish
  this. ejb-cf handed over and is not touching it.
- Kenji (ejb-eb), 2026-09-27 afternoon: DONE. Full 1080p 15 s renders of drift
  + embers and drift + sparks looked at; sparks got `streak` tails (they read
  as dust before); UI check tests/check_scene_picker.py 9/9; WIP.md and
  MANIFEST.md updated. Left: Emerson sees it live after a PulseForge restart.
