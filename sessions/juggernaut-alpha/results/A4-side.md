# Lane A4 side jobs (for Koharu's A4 part 1)

date: 2026-10-01 · for: both · session: Haru/Tetsu (ejb-ca, track A, hey account)

## Try this
Nothing new to play. This part made the test suite trustworthy: `tools/run_tests.sh` now frees whatever each
test leaves in the world and releases any held input before the next test, and prints a `LEFT` line for any
file that leaves state behind. Run it and the full-run-only failures in `test_grapple` / `test_legion` are gone.

## Done and verified
1. **Full-run-only failures (job 1).** Cause: test files left live nodes under the scene root after their own
   `after_each`, including **RigidBody3D** debris, spent casings and Legion parts (`test_ai`, `test_combat`), plus
   decals and particles (`test_damage`, `test_flip`, `test_juggernaut`, `test_slide`). When a test freed its
   ground, a sleeping body stayed where it was, near the origin where the next suite builds its mech and its
   ledge, so `test_grapple:test_climbs_a_ledge_in_reach` and `test_legion` failed only when debris happened
   to settle there. Fix, in `tests/runner.gd`: `_sweep()` after every test frees root children that weren't
   there before its `before_each`, and releases held input actions; `_state()` / `_left_behind()` print
   `LEFT <file> left behind: ...` per file (time scale and physics rate too). A file that does not compile now
   prints a `FAIL` line (it used to count silently).
   **Verified:** the leak report before the fix listed the files above (run 2 output, `/tmp/haru_full2.log`).
   Full suite after the fix: **192 passed**, 0 failing among committed and in-progress tests. The 1 failure is
   `test_zz_bench.gd` "does not compile", another session's new untracked file, not this part's.
   `test_grapple` alone: 9/9.
   Honest caveat: the failure was intermittent (both tests also passed in a full run *before* the fix, 190/1,
   the 1 in `test_ai`), so "fixed" rests on the mechanism plus the leak report. It is not a reproduced
   fail-then-pass. Watch the next few full runs.
2. **Crew board names (Emerson's ask, outside the game).** `~/.claude/skills/crew`: a new session reusing a
   derived name (ejb-ca) inherited the old session's persona ("Suzu") while its Claude-app tab said "Haru";
   notes from Emerson read "Shun (Emerson)". Fixed: `crew.touch` asks the app for the tab name when the session
   behind a name changes; the fallback pick is seeded by session id, not the reused name; `PEOPLE = ("Emerson",)`
   never get a persona; `notes_hook.rename()` refreshes on a session change and once per prompt (tab renames).
   **Verified:** `test_crew.py` 28/28, `test_notes_hook.py` 12/12 (3 new tests), black and pyright clean; the
   live board's "Shun" on Emerson removed.

## Not done (stopped at the 5-hour meter, about 90%)
In order, for the next session:
2. Move hints: `data/hints.json` (one entry per hint: flip, slide, wire anchor, sprint any direction, Heavy AP),
   `scripts/ui/move_hints.gd`, shown the first time the move is possible, setting to turn them off (there is a
   stub `gameplay.tutorial` in `data/settings.json`; a new `interface.move_hints` toggle fits better). Tests and
   a verify-skill screenshot.
3. Wire anchor arc dots on screen (`scripts/combat/wire_anchor.gd` `_draw_arc`): off-screen bot run, ask for a GPU slot.
4. Realistic mass for 20 mm Dyneema (0.22 kg/m) in `~/Models/juggernaut/model2/realistic_mass` and
   `tools/build_juggernaut_data.py`, rerun the tests, scoreboard row.
5. Hangar screen and main-menu Juggernaut (tell Kenji on the board first).
The claims for these files on the forge board were released at the stop.

## 2026-10-02 · Kaede (relay-16)
Job 2 (move hints) done in A4 part 5: see A4.md "Move hints". Jobs 3-5 still open.
