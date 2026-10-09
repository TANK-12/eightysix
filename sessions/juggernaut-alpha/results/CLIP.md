# CLIP: legs and camera through the floor, and rolls that shake
date: 2026-10-06 · for: both · Koharu (Relay 38, hey account), working on ~/Games/eightysix after version 015

Emerson, 2026-10-03: "camera and legs keep slipping through the floor, and when we roll over sideways or vertically
it messes it up and we get clipping also."

## Try this (Emerson)
- Small map or Palouse: aim all the way down (mouse) and hold free look down. The camera stays above the ground.
  Before, it went 1.8 m under it on flat ground.
- Do a half side roll (crouch + jump, half stick left) so it lands on its side or back. The legs fold against the
  ground like limp legs instead of poking through it, and it lies there without shaking. On Palouse it used to
  shake hard (53 rad/s of back-and-forth spin per second); now 0.2.
- Do full flips and rolls at speed on flat, the 25 degree ramp test and Palouse. No foot or knee goes under.
- Not changed: a mech that lands on its back still needs the balance assist's slow righting (Settings >
  Gameplay > Balance assist), as before. It often can't turn itself over from flat on its back. See "Next".

## Causes (verified)
1. **Camera.** Aiming down drops the camera's look point by sin(pitch) x 12 m, about 1.8 m into flat ground at
   -30 degrees with free look down. The swept camera (`_swept`) started its sweep from that point, already inside
   the ground, so it never found the surface. Fix (`scripts/camera/chase_camera.gd`, `_anchor`): the sweep starts
   from a point at the mech in open air (above the hull centre, or the first free spot straight up from it). The
   camera still looks at the real look point.
2. **Legs.** The leg pose (IK, the code that places knees from the hip and foot) never checked the ground,
   except for the soles while planted. Lying on its side, hanging in a roll, or swinging through a bump, knees went
   0.35 m under and feet up to 1.56 m under on the ramp. Fix (`scripts/mech/standin_mech.gd`, `_fold_on_ground`):
   a leg whose knee, ankle or sole would end more than `feet.fold_touch_m` (0.01 m) inside the ground swings as
   one about its hip, like a limp leg, until all three are `fold_clear_m` (0.05 m) clear. It is checked against
   where the body will be after this tick's physics step. It is drawn pose only: no force comes from it (the legs'
   mass is in the body already).
3. **Shaking on Palouse after a roll.** The leg spring rays (one per leg, cast down the body's own axis) started
   under the heightmap surface when the mech lay on its back, and hit the ground's underside (normal pointing
   down). Two legs then flickered loaded / not loaded every few ticks, so drive, turning and steadying switched
   on and off. Fix: `query.hit_back_faces = false` on the spring ray.
4. **Heightmap collision is not a cause.** The Palouse collider matches the drawn ground to 0.000 m
   (`test_palouse_collider_matches_the_drawn_ground`).

## Numbers, before -> after (tests/test_clip.gd, headless, 120 ticks/s)
Six moves (side roll, flip at speed, jump landing, slide into the slope, half roll, half flip) on three grounds
(flat, 25 degree ramp, Palouse heightmap tiles with their real colliders) = 18 cases, 1000 ticks each.
- Ticks with a foot, ankle or knee more than 0.03 m under the drawn ground: up to 528 per case (knees 0.35 m
  under lying on the side or back, feet 1.56 m under on the ramp, 0.05 m on Palouse landings) -> **0 in all 18**.
  Deepest bone point now 0.01-0.02 m.
- Chase camera under the ground (or within 0.1 m of it), 1200 frozen poses (upright, side, back, nose down,
  tail down x 4 headings x 4 aim pitches x 5 free-look angles x 3 grounds): **170 bad (worst -1.84 m) -> 0**.
- Cockpit eye below the ground: 0 before and after. Chase camera in the 18 moving cases: 0 frames low, lowest
  3.56 m above the ground.
- Hull inside the ground: at most 0.07 m (ramp side roll), the physics engine's normal contact depth.
- Shaking over the last second (back-and-forth spin, see the note below): Palouse half roll 53.6 -> 0.20 rad/s,
  all others 0.00-0.20 (limit 1.0).

**Note on the shaking measure (changed this session, on purpose).** The first version of the test added up every
change of spin over the last second. On flat ground and the ramp it failed (1.1-2.4) for a mech that was slowly
tipping off its side onto its back. A per-tick dump showed the spin growing smoothly, 0.016 rad/s every tick
(`tests/test_clip.gd` now prints that sum as "all spin change"). Switching off the balance assist, the
unstick shove and air control did not change it, so it was the body tipping over, not shaking. The test now
counts only the back-and-forth part: the spin's change reversing direction from one tick to the next. The
Palouse case was real shaking under either measure (53.6 before the fix).

## Tests (all headless, tools/run_tests.sh)
- `tests/test_clip.gd` (new): the 18 cases, the collider check, the 1200 camera poses. 20/20.
- `tests/test_flip.gd`: + `test_half_roll_sideways_lands_on_its_side_and_lies_still` and
  `test_half_flip_end_over_end_lands_and_lies_still` (hull above ground, no leg under, no shaking). 11/11.
- `tests/test_camera_collision.gd`: + `test_mech_on_its_side_aiming_down`, `test_mech_on_its_back_aiming_down`. 5/5.
- Full suite: see the PLAN.md status line for the count.

## Tried and dropped
- Legs carry no load when the body is more than 60 degrees off the ground's normal: it did not change the
  Palouse shaking (the underside hits passed it at 46 degrees) and was not needed after the back-face fix. Removed.
- Righting torque at full strength once past 90 degrees (it fades to nothing on the back as sin(lean)): no
  measurable change in the half roll and half flip tests. Reverted.

## Not done / next
- No on-screen bot run or worst-frame screenshots. The headless probe stands in for the bot: same physics, same
  inputs, it reads the bones every tick. The off-screen bot runner also fails today on this laptop
  (llvm-libs upgrade; Relay 37's crew note 770 has a workaround). There was no UI change.
- Getting up off its back with real physics: the legs pushing on the ground to roll the body over, the way
  real legged robots right themselves. That would replace the balance assist's torque from nowhere. Worth its own
  session.
- The leg hitboxes follow the folded pose, but legs still don't collide with the world (unchanged; the hull does).
