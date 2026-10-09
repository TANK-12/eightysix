# Brief R1: a ground Emerson likes, on every map
date: 2026-10-03 · for: Claude (Relay, hey account) · written by Tetsu (v015 session)

Emerson, playing 013/014: **"I hate the ground texture ... in all [maps]."** Also asked whether nicer maps could be downloaded and imported (Tetsu answers that part separately; do not download whole maps).

Rules for every brief in this wave: read ~/Forge/sessions/juggernaut-alpha/PLAN.md (top part and "Emerson's notes during the wave") first. Work in ~/Games/eightysix (Godot 4.7.2, git; commit your own files only, never `git add -A`: another session (Tetsu, hey) is editing scripts/combat/*, scripts/ui/main_menu.gd, scripts/ui/settings_screen.gd, data/weapons.json, data/settings.json and data/input.json at the same time; if you must add a setting, add only your one line to data/settings.json with a small script edit, then commit straight away). Real physics only, no faked forces (PLAN). Tests: `tools/run_tests.sh <file>` (check the log for SCRIPT ERROR too); screenshots with `tools/bot_run.sh <bot json>`; keep every image. At the end: results in ~/Forge/sessions/juggernaut-alpha/results/<your id>.md with a 3-line "try this" note at the top, what is verified (with the check) vs only reasoned, and your one line in PLAN.md's status table. Do not save a version (Tetsu saves 015). Stop and write the handoff at 95% of the hey 5-hour meter (python3 ~/.claude/tools/usage.py).

What to do:
1. Screenshot the ground as it is on every map (small map, big map, test range, both test benches) from the chase camera at walking height and from 30 m up: bot runs in tools/bot (see b4_look_quick.json, look_*.json). These are the "before".
2. Find what makes it look bad: the ground shader is `assets/kit/shaders/ground.gdshader` with `scripts/world/ground_look.gd` (lane LOOK, results/LOOK.md: ambientCG dirt/turf/stones/gravel/rock, a palette per map in data/maps.json). Likely suspects: visible tiling/repetition, texture scale wrong for a 7 m mech, muddy colours, flat lighting response (roughness/normal strength), blotchy blend masks.
3. Make it look like real ground at this scale: better CC0 sets if needed (ambientCG / Poly Haven, 2K, listed in assets/SOURCES.md; disk is short, keep only what is used, compressed with mipmaps as LOOK found), macro variation to kill tiling, sensible blends by slope and height, and the per-map palettes kept. Graphics win over fps (PLAN, 2026-10-02), but report fps per preset before/after.
4. Same views after, a side-by-side contact sheet (tools/contact_sheet.py), tests green (tools/run_tests.sh test_look and the full suite at the end).

Results id: R1.
