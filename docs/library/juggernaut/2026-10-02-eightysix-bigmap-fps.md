# Eighty Six: frame rates on the big map (Sector 86 frontier)

date: 2026-10-02 · for: both · lane B5 part 2 (Minato, Relay task 17)

Measured with `tools/bot_run.sh b5_fps --preset=<p>` (off screen, 1920x1080, a bot walking the big map from the
spawn): 8 s standing, two 10 s walks over ground that is being built as it goes, 8 s in front of Kreuzberg's
buildings. Quiet GPU (track A held its bot runs, announced on the crew board); no Blender job. Readings on this
laptop swing about 10 % between identical runs.

| Preset | standing | walk (second 10 s) | town (Kreuzberg) | worst frame, walk | GPU ms (walk) |
|---|---|---|---|---|---|
| Low | 103 | 105 | 86 | 30 fps (cold start), 65 | 9.1 |
| Medium (warm run) | 67 | 64 | 53 | 24 (cold start), 36-45 warm | 15.2 |
| High | 48 | 48 | 42 | 29, 35 | 20.4 |
| Ultra | 15 | 15 | 15 | 13 | 103-111 |

Notes
- The very first Medium run after an idle spell read 42 standing / 56 / 70 walking: the GPU was slow for the first
  ~20 s. The repeat run a few minutes later (the "warm" row) had no such slope. Count the warm one.
- The worst frames in the first 10 s of walking (24-30 fps) were from the cold first run. A later check (`b5_hitch`,
  Medium, two runs) walking from the spawn and then over never-built tiles: 68.7 / 68.5 fps average, worst frame
  36-40 fps (25-28 ms against 14 ms typical), the same in both walks: no first-time shader stutter, only the small
  dips of tile builds (3 ms each on the main thread, the rest on a worker).
- Against the presets' targets (Medium 45, High 30): both pass on the big map. Ultra is GPU-bound at 92-111 ms a
  frame (same as the small map: 15 fps), unchanged since A1.
- The bridge and the buildings being Destructibles add no measurable cost standing still (pieces are only
  rebuilt when something breaks).
