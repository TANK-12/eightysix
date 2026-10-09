# Brief R2: rumble that sticks on and lags
date: 2026-10-03 · for: Claude (Relay, hey account) · written by Tetsu (v015 session)

Emerson, playing with his PS5 pad: **"rumble is a bit cooked: sometimes it will just stay on, and also lag."**

Rules for every brief in this wave: read ~/Forge/sessions/juggernaut-alpha/PLAN.md (top part and "Emerson's notes during the wave") first. Work in ~/Games/eightysix (Godot 4.7.2, git; commit your own files only, never `git add -A`: another session (Tetsu, hey) is editing scripts/combat/*, scripts/ui/main_menu.gd, scripts/ui/settings_screen.gd, data/weapons.json, data/settings.json and data/input.json at the same time; if you must add a setting, add only your one line to data/settings.json with a small script edit, then commit straight away). Real physics only, no faked forces (PLAN). Tests: `tools/run_tests.sh <file>` (check the log for SCRIPT ERROR too); screenshots with `tools/bot_run.sh <bot json>`; keep every image. At the end: results in ~/Forge/sessions/juggernaut-alpha/results/<your id>.md with a 3-line "try this" note at the top, what is verified (with the check) vs only reasoned, and your one line in PLAN.md's status table. Do not save a version (Tetsu saves 015). Stop and write the handoff at 95% of the hey 5-hour meter (python3 ~/.claude/tools/usage.py).

What to do:
1. Read `scripts/core/rumble.gd` and `data/rumble.json` and every Rumble.play / Rumble.stop call (grep). Find every way a rumble can stay on: a looping pattern (e.g. "grapple_tension", skids, servo) whose stop never comes (state changes, the mech freed, pause menu, scene change, death, the view switching), Input.start_joy_vibration with a long or zero duration, overlapping patterns where a later one keeps the motors on.
2. Find the lag: patterns queued behind each other, a per-frame restart of the same vibration (Godot restarts the motor on every start_joy_vibration call), work done in _process that waits, or vibration sent through a slow path. Measure if you can (time from the event to the start call).
3. Fix so a rumble always ends (a hard ceiling per pattern, stop on pause/scene change/free) and starts on the same frame as its event. Tests without a pad: wrap the motor calls so a test can read what would be sent (start/stop log with timestamps), then prove: no pattern outlives its length plus a frame; pausing, quitting to menu and freeing the mech stop everything; a loop stops when its cause ends; the same event fired 60 times a second does not restart the motor every frame.
4. Emerson tests on his pad: say exactly what to try in the "try this" note.

Results id: R2.
