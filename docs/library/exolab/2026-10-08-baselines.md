# Exo Lab: baseline bench numbers

date: 2026-10-08 · for: both · from Relay task 102

The untouched data (profile `baseline`), measured with the app's core
(`exolab.benches.run`, `exolab.derive.derive`). Use these to see what an edit
changed. Re-measure after a data change; this sheet is not updated by itself.

## exo_full (full suit)

Suit 20.7 kg, arm hardware 3.86 kg per arm. Mechanism girdle_tracking: J1 and
J2 harmonic_m, J3 qdd_planetary; elbow harmonic_s; load-bearing gauntlets.

- Shoulder range: pass. Follows 98% of reachable arm directions; worst
  misalignment 5 mm; worst strap pressure 1.3 kPa; closest to gimbal lock 0.10
  (warn).
- Motions: fail on the overarm throw only (327 W peak; elbow 8.7 vs 4.5 rad/s
  top speed, J1 9.6 vs 8). Overhead reach 44 W, side raise 34 W, reach across
  21 W, behind the back 6 W, rifle aim 80 W, all within 5 mm.
- Hold: warn. Motor load 86% (arm forward, 5 kg), 96% (side, 5 kg), 16%
  (overhead, 5 kg), 164% (10 kg carry at the side, warn), 46% (3 kg tool).
  The wearer carries 0.9 to 2.7 N·m.
- Lift (12 kg box): warn. 410 J per lift, 2527 lifts per charge.
- Game stats: lift 12.5 kg, Strength mode 25 kg, hold out 11.7 kg, break
  151 kg; sprint 5.84 m/s; jump 0.38 m, boost jump 1.51 m; armour 190 HP;
  battery 360 Wh.

## exo_lite (light partial suit)

Suit 11.0 kg, arm hardware 1.75 kg per arm. Mechanism girdle_tracking: J1 and
J2 qdd_planetary, J3 free bearing; elbow qdd_planetary; assist share 0.4.

- Shoulder range: pass. 98% followed; 5 mm; 1.5 kPa; gimbal lock 0.10 (warn).
- Motions: warn (rifle aim 42 W and throw 97 W warn; the rest pass).
- Hold: fail on the 10 kg carry (wearer 20.7 N·m). Motor load 125%, 141%,
  24%, 134%, 47%; the wearer carries 4.1 to 20.7 N·m.
- Lift (12 kg box): fail (strap pressure). 355 J per lift, 1460 per charge.
- Game stats: lift 11.9 kg (Strength mode the same: no load-bearing
  gauntlets), hold out 7.3 kg, break 153.8 kg; sprint 5.86 m/s; jump 0.37 m,
  boost jump 1.82 m; armour 108 HP; battery 180 Wh.

## Shoulder mechanisms on exo_lite (range sweep)

| Mechanism | Followed | Clean | Worst misalignment | Worst strap | Verdict |
|---|---|---|---|---|---|
| girdle_tracking | 98.1% | 97.5% | 5.3 mm | 1.49 kPa | pass |
| soft_cable | 100% | 81.5% | 0 mm | 1.79 kPa | pass |
| lateral_gimbal | 75.2% | 42.7% | 47.0 mm | 18.8 kPa | fail |
| tilted_gimbal | 74.9% | 40.2% | 47.0 mm | 18.8 kPa | fail |

## Knob effects (shoulder hold, worst pose)

- Power x2 on every actuator: motor load 164% -> 82% (full), 141% -> 70% (lite).
- Stiffness x0.2 on every material: hand sag 8.8 -> 35.4 mm (full), 13.1 -> 42.6 mm (lite).
- Weight x2 on al_7075_t6: suit 20.66 -> 21.67 kg (full), 10.97 -> 11.72 kg (lite).
- Strength x2 on every material: break load 151 -> 305 kg (full), 154 -> 309 kg (lite).

## Addendum, 2026-10-08 15:00 (after the critic fixes)

Re-measured with the same calls (`benches.run` on profile `baseline` and on
inline knob profiles).

- Every baseline verdict and number above is unchanged: exo_full range pass
  (98%, 5 mm, 1.3 kPa), motions fail (overarm throw), hold warn (10 kg carry
  at the side, motor 164%), lift warn (12 kg box); exo_lite range pass,
  motions warn, hold fail (10 kg carry), lift fail (12 kg box). Suits 20.66
  and 10.97 kg.
- Mechanisms on exo_lite: same numbers. Both gimbals now fail all three
  range cards (47 mm misalignment is past the new 30 mm fail line).
  soft_cable now gets its own drive (`cable_bowden`), not the girdle
  tracker's motor swaps; its range numbers are the same.
- What the knobs now do to verdicts:
  - Power x2 on every actuator: exo_full hold warn -> pass (motor 164% ->
    82%), motions fail -> warn (overarm throw; the upper-arm cuff then
    presses 5.0 kPa). exo_lite hold stays fail on strap pressure (motor
    141% -> 70%), motions stay warn.
  - Stiffness x0.2 on every material: hand sag 8.8 -> 35.4 mm on exo_full
    (arm forward and arm out to the side turn warn; verdict stays warn) and
    13.1 -> 42.6 mm on exo_lite (arm out to the side turns fail). Sag is
    judged from now on: warn past 15 mm, fail past 40 mm.
  - Strength x2 on every material: no hold verdict changes (break load not
    re-measured). Weight x2 on al_7075_t6: suits 20.66 -> 21.67 kg and
    10.97 -> 11.72 kg, as before.

## Addendum, session 16: worst-case run times

Measured 2026-10-08 ~15:58, one run per process (`/tmp/exolab-s16-time/one.py`,
`web_app._run` directly), laptop load average 10-13 from other sessions.

- Range sweep at the most the limits allow (plane and elevation steps 5,
  human range widened to every plane and 180 degrees, 2701 cells, twist
  checked): exo_full 18.7 s wall, 17.1 s CPU; exo_lite 13.5 s wall,
  12.7 s CPU. 0.3 MB of JSON, about 90 MB of memory.
- Motions at the most the limits allow (120 fps, every one of the six
  motions stretched to 1000 frames, 6000 frames): exo_full 10.7 s wall,
  10.5 s CPU; exo_lite 9.1 s. 2.6 MB of JSON (756 frames sent to the page,
  every 8th), about 120 MB of memory.
- Default settings (steps 10, 30 fps): under a second each (0.74 s range,
  0.42 s motions, session 10).
- pytest: 181 tests in 17 s on the committed app.

## Session 17 addendum: the power knob now costs mass

Power is "a bigger motor all round", so it now scales a drive's mass and
remote mass with its torque, speed and rated power (`data/knobs.json`,
`exolab/parts.py` joint). Measured with the core on a clean copy (power set
on every actuator; suit kg / total kg with the 64 kg person / game stats
from `/api/derive`):

| suit, power | suit kg | total kg | sprint m/s | jump m | boost jump m | lift kg | Strength lift kg |
|---|---|---|---|---|---|---|---|
| exo_full x1 | 20.7 | 84.7 | 5.84 | 0.38 | 1.51 | 12.5 | 25.0 |
| exo_full x2 | 29.8 | 93.8 | 6.43 | 0.42 | 1.34 | 25.8 | 50.8 |
| exo_full x20 | 194.3 | 258.3 | 9.94 | 0.65 | 0.77 | 125.9 | 125.9 |
| exo_lite x1 | 11.0 | 75.0 | 5.86 | 0.37 | 1.82 | 11.9 | 11.9 |
| exo_lite x2 | 15.8 | 79.8 | 6.19 | 0.39 | 1.67 | 11.9 | 11.9 |
| exo_lite x20 | 102.5 | 166.5 | 8.86 | 0.52 | 0.82 | 11.9 | 11.9 |

Before this change power x20 left exo_full at 20.7 kg with sprint at its
14 m/s cap, jump 1.99 m and lift 151 kg (the Emerson-view review,
`apps/exolab/docs/2026-10-08-emerson-view.md`). exo_lite's lift stays
11.9 kg at any power: its cuffs carry the load into the skin, so strap
pressure, not motor torque, sets the limit. Baseline (x1) numbers are
unchanged by this session.

## Session 20 addendum: power under the square-root rule

Since session 19, power x k on a drive multiplies its torque, torque limit
and top speed by the square root of k and its rated power, mass, remote
mass and rotor inertia by k (the third critic's M2: torque x k at speed x k
was k squared the power for k the mass). The battery's power knob is more
cells, energy and mass together (M1), and drives without a motor take no
power knob. Measured 2026-10-08 ~18:10 with `/tmp/exolab-s20-measure/power.py`
(`derive` and `benches.run`, power on every actuator; the knob on a
motorless one is dropped with a warning). Total = 55 kg body + 9 kg kit
(6 kg gear, 3 kg boost pack) + suit: the session-17 table's "64 kg person"
meant body and kit together.

| suit, power | suit kg | total kg | sprint m/s | jump m | boost jump m | lift kg | Strength lift kg | hold motor | hold | motions |
|---|---|---|---|---|---|---|---|---|---|---|
| exo_full x1 | 20.7 | 84.7 | 5.84 | 0.38 | 1.51 | 12.5 | 25.0 | 164% | warn | fail |
| exo_full x2 | 29.8 | 93.8 | 6.43 | 0.37 | 1.3 | 18.0 | 35.7 | 116% | warn | fail |
| exo_full x4 | 48.1 | 112.1 | 7.33 | 0.35 | 1.0 | 25.8 | 50.8 | 82% | pass | warn |
| exo_full x20 | 194.3 | 258.3 | 9.94 | 0.22 | 0.34 | 58.6 | 114.6 | 49% | warn | fail |
| exo_lite x1 | 11.0 | 75.0 | 5.86 | 0.37 | 1.82 | 11.9 | 11.9 | 141% | fail | warn |
| exo_lite x2 | 14.9 | 78.9 | 6.26 | 0.37 | 1.68 | 11.9 | 11.9 | 107% | fail | warn |
| exo_lite x4 | 22.7 | 86.7 | 6.95 | 0.36 | 1.44 | 11.9 | 11.9 | 86% | fail | warn |
| exo_lite x20 | 85.4 | 149.4 | 9.88 | 0.26 | 0.62 | 11.9 | 11.9 | 77% | fail | fail |

- This replaces the earlier power lines: "Power x2 ... 164% -> 82% (full),
  141% -> 70% (lite)" (sessions 13-14) and the session-17 table. Under this
  rule x2 gives 116% (full) and 107% (lite); the full suit's hold first
  passes at x4, and its motions go warn at x4 and back to fail at x20.
- Jump height falls as power rises (the suit gets heavier faster than the
  legs get stronger); sprint still rises.
- exo_lite lift stays 11.9 kg at any power: strap pressure, not motor
  torque, sets it.
- Baseline (x1) numbers are unchanged.
