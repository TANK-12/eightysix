# LOOK2: the washed-out picture, found and fixed (part 1 of the AAA look)
date: 2026-10-03 · for: both · Koharu (Relay 37, hey account), working on ~/Games/eightysix after version 015

## Try this (Emerson)
- Start any map: the picture has real contrast now. Sunlit ground is bright, shade is dark, and colour is richer.
  Nothing is blown out. The golden afternoon on the small map shows the change most.
- Settings > Graphics > High now has ambient occlusion on (soft contact shadows in creases and under walls).
  It still runs at 42-44 fps on this laptop (target 30).
- Every weather has its own tone in `data/weather.json` (`exposure`, `agx_white`, `agx_contrast`). Try
  `set_weather` through all five on the small map.
- Not done yet: town walls and props (part 2 brief: `../2026-10-03-look-aaa-part2-brief.md`).

## The cause (verified with numbers)
1. **The tonemapper's white point was never set.** Every map uses AgX (the tonemapper, which turns the scene's light
   values into screen colours). In Godot 4.7, AgX reads its own `tonemap_agx_white` (default 16.29) and ignores
   `tonemap_white`, the field our weather "white" set. A white of 16.29 suits scenes with very bright light, many
   times brighter than ours. Sunlit ground (about 0.3-1 in linear light) landed at 132-146 of 255 on the small map,
   with the HUD left out. Nothing in the frame was ever bright.
2. **Exposure 1.0 was too dark for our albedos.** Lowering the AgX white alone only moved the white point 140 -> 151
   (try 1, images/526). Exposure 1.3-1.6 per weather (1.25-1.5 in the end) brought it to 170-185 (try 2, images/529). The blacks rose
   with it.
3. **Flat tone curve and a milky fog.** AgX contrast 1.25 (the default) kept the range narrow, so it is now 1.55-1.85
   per weather. The volumetric fog took 0.4 of the sky light into every metre of air (`volumetric_fog_ambient_inject`).
   That lifted the blacks of anything 50 m or more away, so it is now 0.15-0.25 per weather. Volumetric and height-fog
   densities are cut by a third to a half, and the sky's ambient light is 25-35 % lower, so shade keeps its contrast.
   Ruled out: glow (it only blooms above 1.4, which does not reach the ground) and the brightness setting (1.0).
   SSAO was off on Low, Medium and High. It now costs 3.7 ms on Medium (see below), so it is only turned on for High.

## Before / after (Medium, same views; tools/histogram.py, 0-255 on screen, HUD corners left out)
Small map (golden afternoon): before images/524-look2_before_small, after images/539-look2_after_medium.
Big map: before images/525-look2_before_big, after images/537-look2_after_big.
Side by side: images/541-look2_side_by_side/small_before_after.png and big_before_after.png (before | after).

| shot | mean | black point | white point | saturation | clipped % after |
|---|---|---|---|---|---|
| 01-score-start | 87.7 -> 109.6 | 10.6 -> 3.5 | 146.0 -> 184.8 | 0.305 -> 0.403 | 0.0 |
| 02-score-town | 81.0 -> 96.7 | 32.8 -> 25.7 | 138.0 -> 177.8 | 0.33 -> 0.442 | 0.0 |
| 03-score-river | 70.8 -> 83.1 | 21.1 -> 10.3 | 132.0 -> 170.8 | 0.4 -> 0.547 | 0.0 |
| 04-score-bridge | 72.3 -> 85.2 | 11.1 -> 1.4 | 133.6 -> 172.8 | 0.266 -> 0.409 | 0.0 |
| 05-score-mast | 84.5 -> 104.3 | 25.7 -> 19.5 | 140.0 -> 180.0 | 0.33 -> 0.425 | 0.0 |
| 06-score-mech | 79.1 -> 95.9 | 1.3 -> 0.5 | 143.2 -> 180.3 | 0.389 -> 0.518 | 0.0 |
| *big map (Frontier morning)* | | | | | |
| 01-jg_spawn | 65.9 -> 66.7 | 7.1 -> 2.7 | 179.1 -> 205.4 | 0.285 -> 0.434 | 0.0 |
| 02-l_ground | 77.8 -> 83.6 | 4.4 -> 2.7 | 181.6 -> 208.0 | 0.311 -> 0.466 | 0.0 |
| 03-l_street | 110.5 -> 124.8 | 21.1 -> 8.7 | 184.4 -> 210.8 | 0.238 -> 0.299 | 0.0 |
| 07-depot | 90.2 -> 93.8 | 35.4 -> 20.4 | 173.3 -> 200.1 | 0.254 -> 0.398 | 0.0 |
| 09-ford | 85.8 -> 90.2 | 23.8 -> 11.1 | 178.3 -> 204.6 | 0.313 -> 0.469 | 0.0 |
| 12-river_valley | 136.6 -> 153.5 | 60.6 -> 48.8 | 197.9 -> 222.0 | 0.159 -> 0.214 | 0.17 |
| 14-overview | 117.7 -> 132.1 | 44.8 -> 28.5 | 182.5 -> 208.6 | 0.169 -> 0.228 | 0.0 |
| 15-jg_kreuzberg_a | 77.9 -> 79.8 | 9.8 -> 2.7 | 177.1 -> 203.0 | 0.3 -> 0.445 | 0.01 |

Far views on the big map keep some lifted black (river_valley 49, overview 28). That is the 2 km aerial haze,
kept on purpose. The other weathers (images/536, the b4_weathers views): golden 3.5 / 185, overcast 32 / 209,
clear noon 25 / 186, dusk 3 / 157 (saturation 0.73, a deliberate orange dusk), storm 22 / 157.
They have not been compared with a before run.

## fps per preset (score_look, view / walk, 1920x1080)
| preset (target) | v014 row (images/473) | after (images/538-540) |
|---|---|---|
| Low (60) | 60.2 / 59.3 | 87.0 / 78.3 |
| Medium (45) | 48.2 / 44.6 | 65.1 / 59.3 |
| High (30) | 40.7 / 39.0 | 43.8 / 41.9 (SSAO now on) |
The tone settings do not change the render work, because the same passes run with other numbers. Most of the gain
since v014 is R1's ground work. Headless test runs from other Relay sessions were using the CPU during these
runs, and `tools/scoreboard.py` refused for that reason. The numbers were taken with bot_run directly and are
not a clean measurement. The A/B pair was taken back to back under the same load.
**SSAO cost, Medium:** 64.0 / 58.9 fps without it (images/533) and 51.7 / 47.9 with it (images/534), +3.7 ms GPU.
It stays off on Low and Medium and is on for High. Not measured: SSIL, volumetric fog quality and SDFGI on High/Ultra
(part 2).

## Checks
- tests/test_tone.gd 2/2 (every weather drives AgX white and contrast, under 8, fog ambient pickup at most 0.3, and
  a live weather switch moves the tone). It fails on the old data, which had no agx_white. test_look 15/15.
  The full suite was not run (another session's tests were running).
- black + pyright on tools/histogram.py: 0 errors.

## Files
data/weather.json, scripts/world/small_map_sky.gd, data/graphics_presets.json (High ssao), tests/test_tone.gd,
tools/histogram.py, tools/bot/look2_ssao.json. The test range and the hangar have their own environments and
were left alone.

---

# LOOK2 part 2: worn town walls and real far rock
date: 2026-10-06 · for: both · Mio (Relay 37, hey account), working on ~/Games/eightysix

## Try this (Emerson)
- Big map, look along the street at Kreuzberg or stand the Juggernaut next to the depot. The walls now have rounded
  edges that catch the sun, grime along the real edges (window openings, broken tops, outer corners), rain streaks
  running down from the sills and the broken courses, and soot under the tops of some buildings. The seams between
  the blocks a wall is built from no longer show.
- Look at any mountain: it reads as rock now (cliff faces, ledges, dark gullies, strata) where it was smooth grey
  plastic. The small map's rim cliffs got the same treatment.
- Still not fixed: the ruined tower on the l_street view is a stack of cubes. That is its shape (kit geometry), not
  its material; it needs a new building builder, not a shader.

## What changed (verified with screenshots, see below)
1. **Kit boxes know their edges** (`scripts/world/kit/kit.gd`, `Parts.box` + `Parts._open_edges`). Each box face now
   carries its size (UV = metres from the face centre, UV2 = half size), its edge direction (TANGENT), and, in COLOR,
   which of its four edges are open. An edge is closed when the wall carries on in another box, or another wall meets
   it at a corner. The first try (images/544) wore every edge and showed each block of a wall as a grid of cubes,
   which is why this pass exists. Small rubble blocks and the undersides skip the test.
   Build cost: the biggest ruin (`ruin_block`, 357 boxes) builds in 13.5 ms instead of 8.3 ms. It is paid at map load
   and when a damaged building rebuilds.
2. **Masonry shader** (`assets/kit/shaders/masonry.gdshader`): a 3.5 cm bevel on open edges (at least 1.5 pixels wide
   so far edges still read), plaster chipped off and grime along the open edges, soot below broken tops on some
   buildings, rain streaks below every open top (sills), dust on top faces, mortar joints darkened by the texture's AO
   (sunlit brick showed no joints before), relief x1.7, and a per-building warm/grey shift with a slow tonal drift
   over each wall. All of these are uniforms with defaults, so `data/kit.json` was not touched.
3. **Far rock** (`assets/kit/shaders/ground.gdshader`): beyond 40-260 m the rock no longer fades to its mean colour
   with a flattened normal. It switches to the same rock texture at a cliff-sized scale (about 90 m a tile) in both
   colour and normal, with gullies (dark vertical streaks) and strata from the noise (`far_rock_detail`,
   `far_rock_breakup`).
4. **Backdrop hills** (`scripts/world/backdrop.gd`): the far ring gets the rock's normal map at its 60 m scale
   (`relief`, default 1.6). It is a small change, hard to see at that distance.

Props (rubble, burnt cars, poles) were left to relay 36, which built them for its OSM city (results/MAPS2.md). No new
assets in this part, so there is nothing new to credit in assets/SOURCES.md.

## Before / after (Medium, same views)
Before = part 1's after: images/537-look2_after_big, images/539-look2_after_medium. After: images/557-look2b_after_big,
images/558-look2b_after_small. Side by side (before left): images/559-look2b_side_by_side/. Wall close-ups were
iterated with the new short bot `tools/bot/look2_walls.json` (images/556).

Tone kept (tools/histogram.py; white point should stay 170-225, blacks under 15 on near views, nothing clipping):

| shot | mean | black point | white point | saturation | clipped % after |
|---|---|---|---|---|---|
| big 03-l_street | 124.8 -> 121.6 | 8.7 -> 4.2 | 210.8 -> 210.8 | 0.299 -> 0.310 | 0.0 |
| big 07-depot | 93.8 -> 93.2 | 20.4 -> 19.9 | 200.1 -> 200.1 | 0.398 -> 0.399 | 0.0 |
| big 15-jg_kreuzberg_a | 79.8 -> 77.8 | 2.7 -> 2.7 | 203.0 -> 203.1 | 0.445 -> 0.461 | 0.01 |
| big 17-jg_depot | 87.8 -> 82.1 | 2.7 -> 2.7 | 193.4 -> 193.0 | 0.407 -> 0.428 | 0.0 |
| small 01-score-start | 109.6 -> 108.9 | 3.5 -> 1.4 | 184.8 -> 185.8 | 0.403 -> 0.400 | 0.0 |
| small 02-score-town | 96.7 -> 96.0 | 25.7 -> 23.1 | 177.8 -> 177.5 | 0.442 -> 0.445 | 0.0 |
| small 03-score-river | 83.1 -> 81.8 | 10.3 -> 7.9 | 170.8 -> 170.8 | 0.547 -> 0.549 | 0.0 |
| small 06-score-mech | 95.9 -> 95.8 | 0.5 -> 0.5 | 180.3 -> 182.5 | 0.518 -> 0.512 | 0.0 |

The walls are darker and more varied (the depot close-up's mean drops 5.7), and the tone stays the same.

## fps per preset (score_look, view / walk, 1920x1080)
| preset (target) | part 1 (images/538-540, busy CPU) | part 2 scoreboard (images/561 Medium, quiet) |
|---|---|---|
| Low (60) | 87.0 / 78.3 | 84.3 / 76.7 |
| Medium (45) | 65.1 / 59.3 | 62.2 / 58.0 |
| High (30) | 43.8 / 41.9 | 41.7 / 40.5 |
Part 1's runs had a different tree and load, so a clean A/B was run back to back at Medium (quiet GPU):
committed shaders 63.4 / 58.4 fps (GPU 15.34 / 16.61 ms, images/564) and these shaders 62.7 / 57.6 (GPU 15.50 /
16.78 ms, images/566). **The cost is about 0.16 ms of GPU time.** The first run after the change (images/565, walk 51.4) was the
shader compile stutter of a fresh pipeline cache; the rerun is the number.

## Checks
- tests/test_kit_edges.gd 4/4 (lone box: all edges open and its half size; the seam between two blocks is closed and
  the outer ends open; a block under another has its top edge closed; a real ruin has closed seams), test_kit 6/6.
- The test runner prints "ok" for a test whose script errored partway (a parse error in kit.gd showed as 4 "ok"):
  read the SCRIPT ERROR lines, not just the summary.
- Bot runs on 2026-10-06 needed `LD_LIBRARY_PATH=/tmp/llvm22/usr/lib`: llvm-libs 23 was upgraded at 16:09 while mesa
  is held at 26.2.2 (IgnorePkg), so the off-screen compositor could not load libLLVM.so.22.1. The old lib was taken
  out of the pacman cache into /tmp, and no system files were changed.

## Files
scripts/world/kit/kit.gd, assets/kit/shaders/masonry.gdshader, assets/kit/shaders/ground.gdshader,
scripts/world/backdrop.gd, tests/test_kit_edges.gd, tools/bot/look2_walls.json.
