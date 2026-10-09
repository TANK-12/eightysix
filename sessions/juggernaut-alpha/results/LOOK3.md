# LOOK3: AAA look, part 3
date: 2026-10-06 · for: both · brief: `../2026-10-06-look-part3-brief.md`. Each half edits only its own section.

## Half A: the mechs (Tetsu, Kaito ejb-b1, then Relay 40 Hikari) — done 2026-10-06

### Try this
- Settings > Gameplay > Legion livery: "Field worn" (default) vs "Night" vs "Model export"; switches live.
- Settings > Gameplay > Mech finish: "Undertaker, field worn" vs "Model export (no paint)" in the Hangar (Q/E lights).
- Look at the Juggernaut's feet and shins next to its hull: the dirt rises from the ground up.
- Sheets: `images/588-look3-mechs-before-after/` (left before, right after, same view, High).

### Cause (verified by reading the glb JSON)
The Juggernaut and Legion game exports have no UV maps (POSITION and NORMAL only), so their `blue_metal_plate`
maps sampled one texel: flat plastic. The Legion's liveries (`~/Models/legion/looks.py`) never reached the game:
base colour white.

### What changed (committed)
- `data/mech_surfaces.json` + `tools/make_mech_textures.py`: five ambientCG CC0 sets (PaintedMetal012 chipped_paint,
  PaintedMetal002 scratched_metal, Metal027 powder_coat, Metal016 rough_steel, PaintedMetal014 rusted_paint) built
  into `assets/textures/mech/<id>/` (albedo, normal GL, ORM; roughness mean 0.75). Credited in `assets/SOURCES.md`.
  Measured metal share of each map: chipped_paint 10 % (chips), scratched_metal 7 %, powder_coat 100 %, rough_steel 89 %.
- `scripts/look/finish.gd`: a finish material may name a `surface` (object-space triplanar, rides with the part);
  occlusion from the ORM red channel (cavity darkening); `emission` recolours a glow; `band_copies` gives each part a
  material copy per height band and a finish's `grime_rise` adds grime per band, so dirt rises from the feet
  (`tuning.json` `mech_grime_bands` heights [0.14, 0.32] of the model's rest height). `apply_to(..., registry)`.
- `data/finishes.json`: JG2 paint chipped_paint (metallic 1.0: metal only in the chips), metal and steel rough_steel,
  frame powder_coat; grime_rise [0.35, 0.15] on field worn, [0.12, 0.04] on fresh paint.
- `data/legion_finishes.json` (new): `legion_field` (looks.py field: cream chipped to dark metal, red eyes; colours
  converted linear to sRGB, cream raised by the map's 0.86 mean), `legion_night` (silver-blue liquid metal),
  `legion_export`. `scripts/legion/legion_mech.gd` `_wire_livery` on the full and lite model; every Legion of a kind
  shares one set of copies, so the setting repaints all at once. `data/settings.json` `legion.livery`.
- `scripts/mech/juggernaut_mech.gd` `_wire_shine` makes its per-mech copies through `band_copies`.
- Bots `look3_mech_hangar`, `look3_legion`, `look3_mech_cost`.
- Assumption (not asked): the bands are per part, not a per-pixel gradient (StandardMaterial3D kept so Metal shine,
  GrimeBuildup and the tests keep working); part seams are plate seams, so it reads as dirtier lower plates.

### Before / after (verified: images 575/576 before, 585/586 after, both on High; sheets in 588)
Plastic white/grey to worn painted metal: the Legion's cream shell is chipped to dark metal with grime, the
Juggernaut's hull and legs show chipped paint, scratched steel and dirt on the feet. A first after pass (581/582,
Medium) had the field shell too dark and the "scratched metal" set turning blades to paint; the data was fixed
(cream raised, bare metal on rough_steel) before 585/586.

### Tone (verified: tools/histogram.py)
Outdoors (look3_legion shots 2-5): white 178-207 after (173-211 before), blacks 0.5-0.7, clip 0.01-0.10 %. In range.
Hangar views are dim by design: white 115-156 after, 145-164 before (the white plastic was the brightest thing in
the frame); not in the 170-225 range before or after.

### Cost (verified: images/587-look3_mech_cost, Medium, 1920x1080, camera trailing a Legion unit)
Worn looks 20.45 ms GPU (46.4 fps) vs bare exports 19.7 ms (48.1 fps): about +0.75 ms. The third measure (worn
again, 25.97 ms) is not comparable: the unit walked into a different view. Read it as under 1 ms, not exact.

### Checks
`tests/test_mech_look.gd` 4/4 (surfaces have their maps; a surface lays maps and factory takes them off; grime rises
by band; the Legion wear the livery, share copies, lite twin too, switch live). `test_look` 21/21 (roughness
assertions follow the surface mean), `test_juggernaut` 27/27, `test_ai` 25/25, `test_cockpit` 9/9. Full suite: **474 passed, 0 failed** (2026-10-07, `tools/run_tests.sh` with both halves in the tree, 0 SCRIPT ERROR lines; the one `Parse JSON failed` line is test_bot feeding bad JSON on purpose).
Bot logs: 0 SCRIPT ERROR lines. black + pyright clean on `tools/make_mech_textures.py`.

### Left
- The field eye glow reads pink-white at emission strength 12.5 (export value); a deeper red needs a lower energy.
- A real per-pixel dirt gradient and edge wear from curvature would need a mech shader (the exports have no UVs
  or vertex colours to bake into).

## Half B: light and air (Relay 39: Hikari, then Sakura) — done 2026-10-06, commit 432c7d9

### Try this
1. Play **Allegheny** (Medium or High), walk into the trees and look east-south-east: low morning sun through the firs,
   light shafts in the mist, far firs fading into haze.
2. Play **Brilon**: a gold evening sun from the west-south-west down the streets, big lit cloud deck, warm haze over town.
3. Fire shells at the ground and at a wall: ragged scorch with soot rays, and cracks on walls. Settings > Graphics >
   World > "Scorch marks kept" caps them (Low 24, Medium 48, High 64, Ultra 128).
4. Ultra now uses 4096 shadows instead of 8192 (looks the same, about 29 ms faster among the trees).

### What changed (all committed with this section)
- `data/weather.json`: two new weathers. `allegheny_mist`: sun 22 deg from the east-south-east, volumetric fog 0.0035
  over 220 m with forward scatter 0.5 for light shafts, mist pooled below 90 m in the hollows (spawn road 64 m, ridges
  170-220 m), exposure 1.85. `sauerland_evening`: gold sun 15 deg from the WSW, broken cloud deck lit gold, warm haze
  toward the sun, haze pooled below 34 m. New optional fields: `fog_unscaled` (the weather's fog is already right for
  its map, so the map's fog_scale is skipped), `cloud_scale`, `volumetric_length_m`.
- `data/maps.json`: allegheny -> allegheny_mist, brilon -> sauerland_evening; allegheny ground palette darker and
  cooler (the needle litter read orange); a forest `look` block per map (variation, crown_ao, translucency) that
  `scripts/world/big/big_forest.gd` passes to the tree shader.
- `scripts/world/small_map_sky.gd` (fog_unscaled, cloud_scale, volumetric length), `assets/kit/shaders/sky.gdshader`
  (cloud_scale uniform).
- `assets/trees/tree.gdshader` (the firs use this, not foliage.gdshader): per-tree green (cool blue-grey to warm
  yellow-green), crown AO inside the crown and on the low whorls, sun through the needles (BACKLIGHT), cone-shaped
  normals on the far billboards (a sunny and a shaded side), alpha sharpened with the mip level.
  `foliage.gdshader` was not changed (the grass already had backlight).
- `assets/trees/fir/branch.png.import`, `far.png.import`: mipmaps on and VRAM compressed (far firs sparkled).
- Decals (`scripts/combat/combat_fx.gd`): ragged noisy-edged scorch with soot rays and a crater normal map (was a
  smooth radial gradient); a shell hit on a wall (normal steeper than 60 deg) leaves a crack decal; new preset field
  `decal_limit` in `data/graphics_presets.json` + a Settings row in `data/settings.json`; bullet holes keep three
  quarters as many. Textures are procedural (128 px, built once), so nothing new to credit.
- `data/graphics_presets.json`: Ultra `shadow_size` 8192 -> 4096; the measured costs and the decisions are written
  into the High and Ultra notes.
- `tests/test_look3.gd` (6 tests), bots `tools/bot/look3_cost.json` (Brilon street) and `look3_cost_forest.json`.

### Cost of each heavy option (verified: images/567-look3_cost, 568-look3_cost_forest; quiet GPU, Iris Xe, 1920x1080)
fps is the bot's uncapped estimate; ms is GPU time against the base.

| from High: change | Brilon street fps (GPU ms vs base) | Allegheny in the trees fps (GPU ms vs base) |
|---|---|---|
| base (High as shipped) | 38.8 (GPU 25.75 ms) | 25.0 (GPU 39.83 ms) |
| sdfgi | 29.6 (+8.1) | 18.1 (+15.5) |
| ssil | 39.4 (-0.4) | 22.5 (+4.6) |
| ssr | 42.2 (-2.0) | 24.1 (+1.6) |
| fog off | 51.1 (-6.2) | 24.8 (+0.5) |
| fog 128x96 | 36.5 (+1.6) | 21.7 (+6.2) |
| fog 160x128 | 33.2 (+4.4) | 16.4 (+20.7) |
| shadows 4096 | 35.4 (+2.5) | 21.6 (+6.5) |
| shadows 8192 | 24.3 (+15.4) | 13.1 (+36.3) |
| shadow filter 4 | 28.7 (+9.1) | 22.6 (+4.3) |
| shadow distance 260 m | 30.6 (+6.9) | 25.5 (-0.7) |
| SSAO high | 26.0 (+12.8) | 21.2 (+7.3) |
| SSAO off | 45.2 (-3.6) | 30.4 (-6.9) |
| MSAA 4x | 24.4 (+15.2) | 18.8 (+13.2) |

From Ultra (GPU ms only: every Ultra state shows 15.0 fps in this bot, the frame pacing floors there, so only the GPU
timer separates them; single 4 s samples, noise about +-10 ms): Ultra base Brilon 91.9 / forest 151.6 ms.
Without SDFGI -16 / -23, without SSIL +5 / -5, without SSR -4 / -2, FXAA instead of MSAA 4x -6 / -22,
shadows 4096 instead of 8192 0 / -29, fog 64x64 -2 / -21, SSAO low +12 / -8 (both noise).
Godot 4.7 has **no contact shadows** (checked ClassDB), so that line of the brief cannot be done.

**What shows (same-view crops at 100 %, histogram):** no single option moved the histogram by more than about 1 %
(white point within 3) except volumetric fog off, which removes the haze both weathers are built on.
Shadows 8192 vs 4096: no visible difference on either map. SSAO off vs on in the forest: no visible difference at this
view. SDFGI: a little bounce light on shaded facades and the forest floor. Fog 160x128 vs 64x64: more depth layers
between far firs. SSIL, SSR: nothing visible on these two dry maps.

**Decision (data, `data/graphics_presets.json`):** High unchanged (the forest already runs 25-30 fps on it, target 30;
SSAO stays, LOOK2 put it there). Ultra: shadows 8192 -> 4096; SDFGI, fog 160x128, MSAA 4x, SSIL, SSR kept.

### Before / after (verified: images/580-look3-before-after, 16 side-by-side sheets)
Before = images/549, 550 (Allegheny Medium/High), 552, 553 (Brilon); after = 571, 572 (Brilon), 578, 579 (Allegheny,
final weather). Tuning runs on the way: 569, 570, 573, 574, 577 (forest too milky, then too dark, then the sun halo
clipped 17 % of the ridge view).

Tone (tools/histogram.py, High; white point / black point / saturation / clipped %):
- Brilon chase 219/6/0.29/0 -> 202/13/0.39/0; start 220/5/0.28 -> 206/1/0.41; over town 220/15/0.22 -> 203/34/0.34
  (far view, aerial haze); street 221/1/0.24 -> 204/10/0.35. Medium the same within 6.
- Allegheny chase 144/1/0.51 -> 151/7/0.39; start 220/1/0.40 -> 170/3/0.27; ridge (into the sun) 222/17/0.17/0.01 ->
  239/60/0.23/1.6 (the sun disc and its halo); in the trees 221/1/0.54 -> 223/2/0.51.

Reading (looked at, my judgement): **Brilon is a clear step up**: a gold evening with depth over the town instead of a
flat grey noon, saturation up about a third, whites in range. **Allegheny in the trees and the ridge are a clear step
up** (light shafts through the firs, haze between the trunks, sunlit and shaded sides on far firs). **The open Allegheny
views (chase, start) are moodier but greyer than before**: the blue sky and white clouds of overcast_morning gave
way to a hazy morning sky. If Emerson wants more colour there, the knobs are `allegheny_mist` sky_top / fog_sky_affect.

### fps per preset (verified: bot measures in the folders above, uncapped estimate)
| map, view | Medium before -> after | High before -> after |
|---|---|---|
| Brilon chase | 63.4 -> 55.5 | 43.0 -> 38.1 |
| Brilon street | 75.1 -> 63.9 | 50.9 -> 33.8 |
| Allegheny chase | 37.8 -> 35.5 | 26.0 -> 24.5 |
| Allegheny in the trees | 43.6 -> 37.9 | 31.0 -> 29.8 |
Brilon pays most (reasoned, not measured per cause: the low sun lengthens shadows across the whole street, so more
casters land in the shadow cascades). Brilon stays above its targets (Medium 45, High 30); Allegheny High in the trees
is 0.2 fps under 30, chase was under target before too. Graphics over frame rate (Emerson, 2026-10-02).

### Checks
- `tools/run_tests.sh test_look3`: 6/6 passed, no SCRIPT ERROR (2026-10-06).
- Full suite: **474 passed, 0 failed** (2026-10-06, `tools/run_tests.sh`, no SCRIPT ERROR lines; Half A's uncommitted work was in the tree too).
- No Python touched, so black/pyright do not apply.
