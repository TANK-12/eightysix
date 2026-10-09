# Eighty Six small map (Ashen valley): frame rates

date: 2026-09-30 · for: both

Iris Xe, 1920x1080, start view, no Blender running, first clean reading per preset (lane B3 part 1).

| Preset | Target | Measured | GPU ms |
|---|---|---|---|
| Low | 60 | 75.4 | 12.9 |
| Medium | 45 | 35.7 | 27.5 |
| High | 30 | 23.2 | 40.6 |

Medium before the ground-shader and scatter cuts: 22.2 fps. Biggest measured costs on Medium: volumetric fog
about 5-7 ms, SSAO up to 13 ms, shrubs about 5 ms. Source runs: `~/Games/eightysix/images/082-095`.

## Part 2 readings (same day)
Medium, walked view: 31.8 / 35.5 / 31.2 fps before the three ground detail rings, 44.8 once after (images 103-105, 115). Identical runs swing up to 30 %, so 45 is not proven. Probes: ground shader about 1 ms, shrubs about 2 ms, two shadow cascades about 7 ms.
