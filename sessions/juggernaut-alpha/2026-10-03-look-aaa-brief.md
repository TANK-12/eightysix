# Brief: the picture looks washed out; push toward an AAA look
date: 2026-10-03 · for: Claude (next track-B session, hey, Opus high) · written by Tetsu

Start line: `Read ~/Forge/sessions/juggernaut-alpha/PLAN.md, results/V015.md and this brief, then do it.`

**Resume state (Tetsu, 2026-10-03):** part 1 is **done and committed** (f0f20b0, results/LOOK2.md). If you are Relay
task 37 restarting, do `2026-10-03-look-aaa-part2-brief.md` instead (town walls/masonry, props, far rock).
Work in `~/Games/eightysix`. Relay task 36 (forest and city maps, `2026-10-03-maps-brief.md`) may still be running:
check the forge crew board, claim your files with `crew claim`, and do not edit maps.json or the new map entries it owns.
Measure fps only when no other session's bot run or Blender job is using the GPU.

Emerson, 2026-10-03: "get me some more maps and better cities, I want actual AAA graphics, not this weird low poly
stuff. And it feels way too washed out."

1. **Washed out first.** Find out why, with numbers. Take the same six scoreboard camera shots and record a histogram
   for each: mean luminance, black and white points, saturation. Likely suspects (check them, do not assume): the
   tonemapper mode and white point (Godot 4.7 has AgX; Filmic/Linear flatten the range), exposure above 1.0 in
   `data/weather.json` (1.1-1.15 on some weathers), distance fog and height fog lifting the blacks, glow added on top,
   the sky's ambient light being too strong (no contrast in the shade), and no or weak SSAO. Fix it in weather.json and
   the environment code as data, per weather, so every map gets it. Before/after screenshots of the same views, side by side.
2. **Materials toward AAA, within the laptop.** Replace flat or low-detail surfaces with real PBR sets (Poly Haven,
   ambientCG: CC0, 2k where it shows, 1k elsewhere) with proper roughness and normal maps, decals for grime, and
   detail textures up close. Buildings in town: real facade textures (windows, trim, damage) instead of flat colours,
   plus mid-size detail models (rubble, cars, poles, fences, debris) from CC0 sources. Credit everything in
   assets/SOURCES.md. Nothing that cannot be traced to a named source and licence.
3. **The honest limit.** The Iris Xe targets stay (Low 60, Medium 45, High 30). The look must come from better lighting,
   tonemapping, textures and composition, which are cheap, rather than from effects the laptop cannot afford. Spend the
   heavy options (SSIL, volumetric fog, SDFGI, higher shadow resolution) on High and Ultra, where the MacBook Air M5
   will run them. Measure the cost of each one.
4. Scoreboard row, a "try this" note at the top of `results/LOOK2.md`, tests green, the PLAN.md status line, and a
   saved version only from a clean tree.

Done when: the washed-out cause is found and fixed with histogram numbers before and after, the town and ground
materials are visibly better in the same screenshots, fps per preset holds or improves, and results/LOOK2.md is written.
