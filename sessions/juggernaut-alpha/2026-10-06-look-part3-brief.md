# Brief: AAA look, part 3 (two halves, side by side)
date: 2026-10-06 · for: Claude (Tetsu in the main session + one Relay helper, hey, Opus high) · written by Tetsu (Kaito ejb-b1)

Emerson, 2026-10-06: "make it look so much better." Context: `2026-10-03-look-aaa-brief.md` (the AAA ask),
`results/LOOK2.md` (part 1 tone fix; part 2 by Relay 37 = town walls / masonry, props, far rock).
Work in `~/Games/eightysix`. Results go in `results/LOOK3.md`, one section per half; each half edits only its own section.

## Ground rules for both halves
- Relay 37 (look part 2) may still be finishing: it owns `assets/kit/shaders/masonry.gdshader`,
  `assets/kit/shaders/ground.gdshader`, `scripts/world/kit/kit.gd`, `scripts/world/backdrop.gd` until it posts
  on the forge board that it has committed. Do not edit those files before then; read them freely.
- Claim files with `crew claim` on board `forge`. Post GPU slots before bot runs or fps runs; one at a time.
- Graphics over frame rate (Emerson, 2026-10-02): looks win; still measure and report fps per preset.
- Tone stays in range: `tools/histogram.py` white point 170-225, near-view blacks under 15, nothing clipped.
- Every texture or model from a named CC0 source (Poly Haven, ambientCG), credited in `assets/SOURCES.md`.
- Before/after shots of the same views, side by side, in numbered `images/` folders (never delete images).
- Tests headless and green; full suite once at the end; commit your own files only.

## Half A: the mechs (Tetsu, main session)
The Juggernaut and the Legion read as clean grey/white plastic (images/561 shot 06). Make them read as worn,
painted military metal: real PBR detail (painted-metal / scratches normal + roughness breakup), edge wear and
cavity darkening, dirt and grime rising from the feet, the Legion's own scheme. Works through `data/finishes.json`
and `scripts/look/finish.gd` (as data, per finish), so the hangar, the menu showcase and the game all get it.
Files: `scripts/look/finish.gd`, `data/finishes.json`, `scripts/mech/juggernaut_mech.gd` (material copy only),
Legion material setup in `scripts/legion/`, new textures under `assets/textures/mech/`.

## Half B: light and air (Relay helper)
1. **High and Ultra spend their budget.** Measure each heavy option on High and Ultra on a quiet GPU (SDFGI,
   SSIL, volumetric fog quality, shadow atlas / directional shadow size and splits, contact shadows): cost in ms
   and what it adds (histogram + shots). Keep what shows, as data in `data/graphics_presets.json`.
2. **The new maps look deliberate.** Allegheny forest and Brilon (Relay 36, `results/MAPS2.md`) got geometry and
   a facade shader but not a look pass: give each its own weather/light (light through the firs, mist in the
   valleys; a town under a grey or golden sky), foliage that is not flat (translucency / backlight in
   `foliage.gdshader`, colour variation), fog that sits in the low ground. Owner of `maps.json` / map scripts for
   these two maps during this task: you (Relay 36 is done).
3. **Decals** if room: scorch and cracks where shells land and on kit walls (Godot Decal nodes, CC0 textures),
   capped per preset.
Files: `data/weather.json`, `data/graphics_presets.json`, `scripts/world/small_map_sky.gd` and the environment
code, `assets/kit/shaders/foliage.gdshader`, `sky.gdshader`, the forest/Brilon map scripts, decal code.
Not yours: masonry/ground (Relay 37), `scripts/look/` and mech materials (half A).

Done when: same-view before/after shots show a clear step up on the forest, Brilon and the High/Ultra presets,
fps per preset recorded, tests green, `results/LOOK3.md` "Half B" written with a 3-5 line "try this" note, the
PLAN.md status line for LOOK3 updated (add one if missing), and your work committed.
