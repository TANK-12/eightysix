# Brief: AAA look, part 2 (materials and town)
date: 2026-10-03 · for: Claude (next look session, hey, Opus high) · written by Koharu (Relay 37)

Start line: `Read ~/Forge/sessions/juggernaut-alpha/PLAN.md, results/LOOK2.md and this brief, then do it.`
Work in `~/Games/eightysix`. Part 1 (`results/LOOK2.md`) fixed the washed-out tone. It stopped early because the
hey weekly meter hit 97 %. What is left is item 2 of `2026-10-03-look-aaa-brief.md`, the materials:

1. **Town walls (the biggest gap).** On the big map's `l_street` view (`tools/bot_run.sh look_big`, shot 03) the
   ruined houses read as flat salmon-tan blocks, and the ruined tower is a stack of cubes. Relay 36 (maps) owns
   `assets/kit/shaders/masonry.gdshader` and `data/kit.json` until it posts on the forge board that they are
   committed. It is putting real facade textures (windows, trim) in a new `assets/kit/shaders/facade.gdshader` for
   its batched BigCity. Check the board first. Then either reuse facade.gdshader on the kit towns (small map,
   Ashen valley / Frontier) or give masonry stronger brick relief, darker mortar, grime at the base, and soot
   and damage at the broken edges. Measure each change with the same shots.
2. **Mid-size detail.** Rubble piles, burnt cars, poles and fences from CC0 sources (Poly Haven models,
   ambientCG), credited in `assets/SOURCES.md`. Relay 36 was told to do these for its city. Agree on the board
   who does them so the work is not done twice.
3. **Far rock.** The big map's mountains read as smooth grey plastic in `look_big` shots 03 and 07. Ground rock
   is in `assets/kit/shaders/ground.gdshader` (R1, committed). It needs a larger-scale normal and
   colour breakup at distance.
4. Keep the tone from part 1: compare with `tools/histogram.py` (the white point should stay 170-225, blacks
   under 15 on near views, nothing clipping). fps per preset with `tools/scoreboard.py` on a quiet GPU.

Done when: the town and ground are visibly better in the same shots (before = part 1's after folders named in
LOOK2.md), fps per preset holds, sources credited, `results/LOOK2.md` has a part-2 section, and the PLAN.md
LOOK2 line is updated.
