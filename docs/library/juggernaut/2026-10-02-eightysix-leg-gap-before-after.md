# Eighty Six: the Juggernaut's legs crossing, before and after

date: 2026-10-02 · for: both · measured by Kaede (relay-16), lane A4 part 5

What it measures: the closest approach between the bones (hip to knee to ankle) of any two of the Juggernaut's
four legs, in metres, from `tests/test_leg_gap.gd`. The leg meshes reach at most 0.21 m from their bone, so bones
0.42 m apart touch and 0.5 m leaves about 8 cm of daylight. Standing is 0.853 m (the hips).

| Scenario | Before (010 and 009 alike) | After |
|---|---|---|
| gallop straight | 0.002 | 0.849 |
| gallop, gentle turn | 0.001 | 0.843 |
| gallop, turn flat out | 0.180 | 0.850 |
| gallop backwards | 0.165 | 0.845 |
| gallop slalom (left/right every 1.2 s) | not measured | 0.791 |
| gallop sideways | 0.853 | 0.853 |
| walk | 0.555 | 0.853 |
| running jump | not measured | 0.623 |
| front flip | 0.009 | 0.601 |
| backflip | not measured | 0.597 |
| side flip | 0.849 | 0.853 |

The crossing was in version 009 too, so the 010 changes (flip tuck, the drive's moment at the feet) are cleared.
Cause and fix: results/A4.md "Part 5" in `~/Forge/sessions/juggernaut-alpha/`. Top speed unchanged (19.5 m/s).
