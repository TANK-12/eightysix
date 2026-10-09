# Eighty Six: the golden file (data/golden.json)

date: 2026-10-08 · for: both

## What it is

The AAA plan's rule 7.6 (gap 21, part of N1): one engine-neutral file holding input and expected output for
the game's pure rules and the measured movement figures, so "it still behaves and feels the same" is a test,
in this engine or any other.

- `data/golden.json`: 30 entries (29 at first; the fix round added one). Each has `group` (`rule` = pure maths; `movement` = the physics body driven
  by its inputs), `rule` (the measuring recipe), `about`, `input`, `expect`, `tolerance`. SI units, angles in
  degrees, speeds in m/s unless a name says `_kmh`. Inputs name entries of `weapons.json`, `mechs.json`,
  `enemies.json` and `tuning.json` (a port reads those same files).
- `tests/test_golden.gd`: runs every entry against today's game. Pure rules call the code (`Ballistics`,
  `Projectile.skip_velocity`, real `Projectile` flights against test plates and ground, `DamageModel`,
  `LegionMech.take_hit`, the sortie log's `score` and `grade_of`). Movement drives a fresh Juggernaut Model 2
  headlessly on flat ground, 120 ticks a second, default settings except the ones each entry's `input.settings`
  names (sprint as a hold; bench mode and its stance for the fall), let go from `input.spawn_height_m`. It writes everything it
  measured to `logs/golden-last.json`.
- `tools/golden_measure.py`: runs the test and lists each entry as ok, off or not measured (`-v` lists every
  differing figure, `--no-run` reads the last run). `--write` fills entries whose `expect` is still null;
  `--write <id> ...` re-measures those entries on purpose.

Tolerances: top speed 3 %, every other movement figure 10 % (the AAA plan's E1 gate 2). Pure rules 0.1 %
(0.2 % for the real shell flights); booleans, strings and counts must match exactly.

## Today's numbers (all measured 2026-10-08, Godot 4.7.2, CPU, headless)

| Figure | Value |
|---|---|
| Gallop top speed | 70.2 km/h |
| 0 to 50 km/h | 1.33 s |
| Stop from a gallop, stick let go | 16.4 m in 1.76 s |
| Full slide from a gallop (to 1.5 m/s) | 53.6 m in 5.1 s |
| Standing full-charge jump | body rises 8.20 m, 2.6 s with no foot down |
| Turn rate standing | 95.0 deg/s (the tuning cap `turn.rate_deg_s`) |
| Turn at a gallop | 69.9 deg/s at 48.5 km/h: an 11.0 m radius |
| The fall a leg survives (bench mode) | edge 9.0 m; share of drops that broke an actuator: 4-6 m 0.0, 6-8 m 0.2, 8-10 m 0.5, 10-12 m 0.8 (fix round; was "first break 7.25 m") |
| 57 mm drop at 1 km | APFSDS 2.06 m, heavy AP 4.13 m, HEAT 6.44 m, HE 8.37 m |
| 57 mm APFSDS speed at the target | 1548 m/s at 100 m, 1530 at 1 km, 1510 at 2 km |
| 57 mm penetration | APFSDS 180 mm, heavy 140, HEAT 220, at every range and angle |
| Ricochet limit, APFSDS at 1550 m/s | dirt 8.0 deg, rock 17.0, metal 20.0 |
| A dart at 4 deg over dirt | skips twice (max_skips), then stops in the ground |
| Recoil per 57 mm shot | APFSDS 5580 N s, heavy 8360, HEAT 4050, HE 3480 |
| What destroys the Juggernaut | 2 legs lost, or the canopy or the pod tub lost |
| Grades | S from 90, A 75, B 60, C 40, D below |

Plus the full damage tables: all 59 Juggernaut damage parts (health, armour, kind) with the first-hit damage
and hits-to-lose for the Löwe 120 mm APFSDS and HE, the Ameise MG and the 57 mm; and every zone of the Löwe,
Grauwolf and Ameise with what one 57 mm APFSDS, heavy AP or 12.7 mm round deals there, hull pass-through included.

## How to use it

- Check: `cd ~/Games/eightysix && tools/run_tests.sh test_golden.gd` (about 60 to 80 s since the fix round), or
  `tools/golden_measure.py` for the table.
- A tuning change that moves a figure turns the test red. That is the point. If Emerson has played the
  change and keeps it, re-measure just those entries: `tools/golden_measure.py --write move_gallop`, and say so
  in the commit. Never re-measure to make red go green without that.
- A new figure for a rule that exists: add one entry with `"expect": null`, run
  `tools/golden_measure.py --write`, read the value, commit.
- A new rule: one `_m_<name>(input)` method in `tests/test_golden.gd` (it may `await` physics) and one line in
  its `RULES` table, then an entry as above.
- A port (E1 or after): its tests read this same file and measure each `rule` the way the doc and the GDScript
  recipe describe; the `about` lines say what each one does.

## Verified

- `tools/run_tests.sh test_golden.gd`: 3 passed, 0 failed, run three times; the same values each run
  (physics at a fixed 120 Hz is repeatable here).
- The test catches change: with the gallop's expected top speed set to 73 km/h it failed ("expected 73.0
  within 2.19, got 70.195"); at 72 km/h it passed (inside 3 %); with the APFSDS drop set to 2.07 m it failed
  (0.1 %). The file was put back after.
- Every value in the file came from `tools/golden_measure.py --write` after a run, none typed in.
- `test_registry` (11 passed, the new data file loads), `test_scripts` and a filtered run leave nothing behind.
- `black` and `pyright` on `tools/golden_measure.py`: 0 errors.

## Reasoned, not verified, and things Emerson may want to decide

- **Penetration ignores range and angle.** The game's rule is penetration_mm against armour_mm and nothing
  else, so the golden file says 180 mm at 100 m and 2 km, square on and at 60 degrees. A fuller model (falling
  with impact speed, line-of-sight thickness at an angle) would be a design change; the golden numbers then
  change on purpose.
- **No 57 mm round goes through a Löwe's hull front** (240 mm against 180, 140 and 220): a hull hit deals
  ricochet_fraction (15 %). Its weak points and legs are the way in. Recorded, not judged.
- **The fall a leg survives has a ragged edge.** Measured in test bench mode (game mode has no fall damage):
  in a 0.5 m scan every drop to 8.5 m survived, 9 broke, 9.5 to 10.5 survived, and from 11 m almost all broke
  (14.5 and 16.3 survived); with 0.25 m steps 7.25 m broke. How the body lands decides it, so the file records
  the first break of an upward 0.25 m scan from 4 m. A tuning change can move it more than the 10 % suggests.
  (Superseded in the fix round below: the file now holds an edge and per-band break shares over 40 drops.)
- Movement figures are flat ground, default settings (except each entry's `input.settings`), CPU physics. The game's own `tests/test_slide.gd` and
  `test_feel.gd` keep their own bounds; the golden file does not replace them.
- Damage figures are at the damage-model level, before the difficulty's enemy damage scale.
- The order of measurements shifts the 0 to 50 km/h time by one tick (1.317 s alone, 1.325 s in the full
  file): well inside 10 %.

## Fix round (2026-10-08)

An independent critic reviewed the first version. Every finding was fixed; none was rejected. Each
behaviour fix had a failing test first (seen red, then green).

1. **The fall figure hung on one landing** (major). The first-break scan gave 7.25 m, but the critic showed
   single drops flip centimetres apart (7.20 broke, 7.22 survived, 7.24 broke), so a tiny tuning change
   could move it past 10 %. `move.fall` now drops at every 0.2 m from 4.0 up to (not including) 12.0 m
   (40 drops, 10 per 2 m band) and stores two steadier figures: `edge_m` = 4.0 + 0.2 x (drops survived),
   where one clean edge would sit, so one flipped drop moves it by one step; and `break_share` per band.
   Measured: edge 9.0 m; broke 0.0 / 0.2 / 0.5 / 0.8 in the 4-6, 6-8, 8-10 and 10-12 m bands. Tolerance:
   edge 10 %, shares 0.25 (2.5 drops of 10). Test: `test_fall_summary_is_steady` (flipping any one drop moves
   the edge by exactly one step). The old wrong comment ("every drop from 4 to 8.5 m survived") is gone.
2. **Hidden settings** (major). The fall's bench stance (leg_length 1.0, foot_spread 1.0, ride_lift 0, bench
   mode) and 2.4 m base, and the movement entries' sprint-as-hold and 3.0 m spawn, lived only in GDScript.
   Every movement entry now carries `input.settings` and `input.spawn_height_m`; the test applies them in a
   loop and hardcodes none. Test: `test_movement_inputs_are_explicit` (and every named setting exists).
3. **A killing round zeroed later Legion zones** (major). `damage.legion` reset hp but not
   `is_destroyed`. Each one-hit trial is now a freshly built unit. Test: `test_legion_trials_start_undamaged`
   (an Ameise hit by the Löwe's 120 mm dart, which kills it with one 1500-point hull hit, then the 57 mm),
   plus a new golden entry `damage_legion_ameise_one_hit_kill`. The three old Legion entries came out
   unchanged, so their stored numbers were right.
4. **"Pure maths, no clock" was wrong for three rules** (minor). The `_about` now says shot.impact,
   ricochet.flight and damage.legion step a shell or unit through the 120 Hz tick; the two shell entries'
   `about` lines spell out `Ballistics.step` so a port can match within 0.2 %.
5. **The tool could show or write a stale run** (minor). `tools/golden_measure.py` now notes the time
   before the run and refuses (exit 1, a plain message, nothing written) when `logs/golden-last.json` was
   not rewritten by that run. A non-zero exit code alone is not refused, because a failing test (an
   entry off) still writes its figures and showing those is the tool's job. `--no-run` still reads the
   last run on purpose. Tests: `tools/tests/test_golden_measure.py` (4).
6. **from_kmh was held to 10 %** (minor). `move_stop` and `move_slide` now hold `from_kmh` to 3 %, the same
   as the gallop top speed (E1 gate 2). Test: `test_top_speed_is_held_to_gate_2`.

Verified in this round:

- Red first: the four new GDScript tests failed for the reasons above before the fixes; the tool tests
  failed 2 of 4 (a stale run was accepted and written).
- `tools/run_tests.sh test_golden.gd`: all 7 golden tests pass, run three times with identical figures (60
  to 83 s, the machine was shared). The only failures in those runs were other helpers' test files that do
  not compile right now (test_legs_realmesh, test_textures, test_world_look), not this item.
- `move_fall_limit` and the new kill entry were written by `tools/golden_measure.py --write` (unmeasured
  only); nothing typed in. Every other entry still reads ok (`--no-run`).
- It catches change: with edge 10.5 m, the 8-10 m share at 0.8 and move_stop's from_kmh at 73 km/h (4 %
  off, which passed before) the movement test failed on all three; the file was put back after.
- `python3 -m unittest tests.test_golden_measure` (from tools/): 4 OK. `black` and `pyright` (0 errors) on
  `tools/golden_measure.py` and the new test. The project has no `.venv`; pyright ran against system
  Python, fine for stdlib-only code.

Reasoned, not verified, and for Emerson:

- The fall is still measured in bench mode with the bench's modelled stance, not the game's default stance:
  the bench's actuators are sized for that pose (tests/test_bench.gd uses it too). Now that the stance is in
  the entry, switching to the default stance is a data change plus a deliberate re-measure.
- The fall scan costs about 40 drops of 3 s simulated each, so test_golden.gd takes roughly twice as long.
  A coarser step (0.25 m) would halve that at the cost of noisier band shares.
- Band shares from 10 drops can only move in steps of 0.1; the 0.25 tolerance lets a port that behaves
  the same statistically pass, but is a judgement, not a measured spread.

