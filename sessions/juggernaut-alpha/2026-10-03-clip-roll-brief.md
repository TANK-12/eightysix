# Brief: camera and legs slip through the floor; rolling sideways or end over end breaks it
date: 2026-10-03 · for: Claude (next track-A session, hey, Opus high) · written by Tetsu

Start line: `Read ~/Forge/sessions/juggernaut-alpha/PLAN.md, results/V015.md and this brief, then do it.`

**Resume state (Tetsu, 2026-10-03, written when Relay task 38 stopped at the hey weekly limit; the session left no
results file):** uncommitted: tests/test_clip.gd (new; written first, 12 cases red on the last full suite: knees 0.35 m
under on flat/ramp half rolls and flips, the mech ends upside down; Palouse feet 0.05 m under), plus its edits in
scripts/camera/chase_camera.gd (27 lines on top of 920c41e), data/tuning.json and scripts/mech/standin_mech.gd
(check `git diff` on those; not verified which are 38's). Start from those numbers; write results/CLIP.md.
Work in `~/Games/eightysix` from version 015. Relay tasks 36 (maps) and 37 (look, weather.json) may be running at the
same time: check the forge crew board, `crew claim` your files, and do not touch maps.json, the map entries or weather.json.

Emerson, 2026-10-03: "camera and legs keep slipping through the floor, and when we roll over sideways or vertically it
messes it up and we get clipping also."

1. **Reproduce first, with a bot.** Bot scenarios on flat ground, a slope and the Palouse heightmap terrain:
   (a) a sideways roll and an end-over-end flip at speed, (b) landing from a jump, (c) a slide into a slope. Record each
   frame: lowest foot and knee point below the ground surface, camera height above the ground under it, and whether
   the body's colliders are inside the terrain. Screenshots at the worst frame. Check whether the heightmap terrain
   (new in 015) has the same collision as the old maps; that is a likely cause of "slipping through".
2. **Camera:** the chase camera has swept collision (`scripts/camera/chase_camera.gd`, `_swept`, `collision_radius_m`,
   `collision_mask = 1`). Find why it still goes under: wrong mask on the new terrain, the sweep starting from a point
   already inside the ground during a roll, the look target upside down, or the cockpit view (R3) skipping the check.
   The camera must never show the underside of the ground, upright or upside down.
3. **Legs:** IK feet and knees must stay above the ground (`tests/test_leg_gap.gd`, `scripts/locomotion/`). During a
   roll, the legs are dead weight on real joints: they collide with the ground like the hull and fold within the
   actuator limits, nothing invented. Where the leg meshes have no colliders, add simple ones if the cost is small.
4. **Rolls:** after a sideways or end-over-end roll the mech must not end inside the ground or jitter. Extend
   `tests/test_flip.gd` with the sideways and vertical cases; add `tests/test_camera_collision.gd` cases for a rolled body.
5. Real physics only (PLAN.md): no teleporting out of the ground, no forces from nowhere.

Done when: the bot shows zero frames with feet, knees or camera below the ground in all three scenarios on all
three grounds (numbers before and after), new tests pass, full suite green, results/CLIP.md with a "try this" note, the
PLAN.md status line written, committed from your own files only.
