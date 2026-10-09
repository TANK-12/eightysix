# Brief: review R2 (rumble) before Emerson tests it
date: 2026-10-03 · for: Claude (Relay, hey, Opus medium) · written by Tetsu

Relay 33 fixed rumble that stuck on and lagged (results/R2.md, its commits in ~/Games/eightysix: `git log --oneline -15`, the ones touching scripts/core/rumble.gd, data/rumble.json, tests/test_rumble.gd and callers). Review it, do not redo it:
1. Read the diff (`git log -p` on those commits). Check every path that can leave the motors on: pause, scene change, mech death or free, anchor freed, setting off mid-loop, window focus loss, the pad unplugged and plugged back, two pads. Check the new refresh scheme (a 0.25-0.4 s effect re-sent about every 0.2 s) cannot pile up, restart the motor every frame or leave a gap that feels pulsed.
2. Check the "a frame late" fix does not double-fire an event.
3. Run tests/test_rumble.gd and the full suite (`tools/run_tests.sh`); check each log for SCRIPT ERROR. Other sessions are working in the tree: commit only files you change, never `git add -A`, never `git stash`.
4. Fix real bugs you find (with a test that fails before the fix); leave style alone.
5. Append a "Review (Opus, <date>)" section to results/R2.md: what you checked, what you found, what you fixed, what is still only reasoned. Keep it short.
