# S4: Blender + Godot tooling, and Acchan

Part of the 2026-09-25 wave; read `~/Forge/sessions/README.md` first.
Suggested model: **Opus at medium or low effort** (Emerson asked for that
for the Blender/mech/Godot work).

## Owns
- `apps/acchan/` (the MCP server that provides `blender_*`, `godot_*`,
  `assets_*` and the app tools)
- `~/.claude/skills/mech-forge/`, `~/.claude/skills/godot-forge/`
- `~/Forge/docs/DESKTOP-REACH.md`, `~/Forge/docs/plans/PLAN-blender-godot-upgrade.md`
- Not `apps/claude/runner.py`: S1 fixes the missing Acchan tools there
  (A39); wait for S1's board note if you need that.

## Ledger

- **A1** "for the blender mech godot thing, [do] all of the tasks" -> finish
  `~/Forge/docs/plans/PLAN-blender-godot-upgrade.md` ("State at handoff" and "NOT DONE /
  BROKEN"): [core]
  - Upgrade 3: rewrite the `mech-forge` skill.
  - Upgrade 4: finish the interrupted checks (the node_paths fix, the
    tests).
  - Update the `godot-forge` skill (new "no errors" message, the `template`
    argument, the add-ons), `~/Forge/docs/DESKTOP-REACH.md`, `PROGRESS.json`.
  - Delete the scratch in `/tmp` listed in the plan.
- **A31** "we saw an example of the godot render last session and it looked
  trash, it was just cubes with a pill capsule walking around; I want
  polish" -> demos and templates use real assets, not primitives: a proper
  character (the VRM path already started), textured terrain, props from
  the CC0 packs the assets tools find, lighting and a sky. No code-built
  characters (they came out uncanny before). The end-to-end demo gets done
  at this standard. [core]
- **A30** "don't run renders or tests" -> do not run Blender renders,
  Godot play recordings or viewport shots yourself; use `godot_check` and
  script-level checks, and leave Emerson one exact command or button per
  thing to look at. Ask on the board if a single screenshot is truly
  needed. Unit tests (pytest) are fine. [constraint]
- **A22a** "none of the apps open except terminal when I ask the acchan
  thing" -> Acchan's launch_app (or the fast path that calls it) only works
  for the terminal. Find why (app names not matched? `.desktop` lookup?
  Flatpak apps? Forge apps?), fix, and add tests for several real app names
  on this laptop (Firefox, Files, QBZ, a Forge app). [core]
- **A22b** "any model, and 4b with think, takes an ungodly time to respond
  to hey" -> a plain greeting is slow on every model. Look for the cause
  without running evals: is the full tool list and memory sent for "hey"?
  thinking on for small talk? model reload each turn? Add a fast path for
  small talk (no tools, no thinking, short context). Give Emerson a one-line
  command to time "hey" before and after. Claim `jan:<model>` on the `jan`
  board if you do make a single live call. [core]
- "acchan is fine" otherwise: no other Acchan changes beyond the eval
  notes already in its WIP. [constraint]

## Order
A22a -> A22b -> A1 skill and doc updates -> A31 polished demo/templates ->
A1 cleanup.

## Checks
pytest in `apps/acchan` (its venv); `godot_check` on projects; black and
pyright on touched Python. Emerson looks at the visuals himself.

## State (session ejb-e1, updated as items finish)

Chunks: 1) A22a  2) A22b  3) A1 skills/docs + interrupted checks
4) A31 polished template/demo  5) A1 cleanup + handoff.

- **A22a done + checked.** Cause: `acchan.service` (systemd user unit) starts
  at login before GNOME passes WAYLAND_DISPLAY/DISPLAY to the user manager, so
  the backend had no display variables. Qt apps (Dolphin) crashed and
  Firefox/Chrome said "no DISPLAY"; GTK apps and the terminal (D-Bus
  activated) still opened. Fix: `desktop.adopt_session_env()` fills them in
  from `systemctl --user show-environment` on every desktop re-check.
  Also: "browser" now means Firefox, not the first fuzzy match (Chrome);
  Forge apps are launchable by name ("open cosmos") and open inside the
  running Forge through `shared/forge_open.py` (a socket) +
  `forge.py --app <name>`. Checked: `tests/test_apps.py` 22 passed (real
  names: firefox, browser, files, file explorer, qobuz, qbz, steam, terminal,
  text editor, blender, cosmos, novelforge, drift peaks); `~/Forge/tests/test_forge_open.py`
  5 passed; Acchan suite 140 passed; `tests/test_app_discovery.py` ALL PASS;
  live: from the service's exact stripped env, raw `dolphin` dumps core and
  `firefox` says "no DISPLAY", while `launch_app('file explorer')` opened
  Dolphin and it stayed up (closed again). acchan.service restarted, 200 OK.
  **Not checked live:** the forge.py socket (needs a Forge restart; Emerson's
  Forge was not restarted). Check after the next restart:
  `python3 ~/Forge/forge.py --app cosmos` should switch the open Forge to Cosmos.
- **A22b done + unit-checked; not timed live** (no model calls, per A30).
  Causes found by reading the code and the real chat log (no evals): (1) the
  Think setting applied to "hey" (+2000 token budget); (2) a greeting took the
  full loop: whole history with tool results, a history summary call first
  when over budget, and after an empty/failed reply a step up to a bigger
  model (another model load); (3) the chat-vs-tools prompt switch throws away
  llama.cpp's prompt cache; (4) **bug**: a client that dropped its stream (quit
  terminal client, reloaded page) never stopped its run, so Jan kept
  generating for nobody and the next message queued behind it (the real chat
  shows three unanswered "hey"s in a row). Also a model is unloaded after 5
  idle minutes (Emerson's RAM rule, unchanged), so the first message after a
  break pays a load. Fix: `router.is_small_talk` + `Agent._small_talk` (the
  chat's own model, no tools, thinking off, last 6 plain turns, 200 tokens,
  no summary, no escalation); `web_app._sse` and the /v1 stream stop the run
  when the client leaves; a run whose client left while queued never starts.
  Checked: `tests/test_small_talk.py` 19 passed; suite 159 passed; black,
  pyright 0 errors. acchan.service restarted, 200 OK.
  **Emerson's timing command** (after = small_talk true, before = false, same
  4B with Think on; the first line pays any model load, so the gain is if
  anything understated; each run adds a "timing" chat to the list):
  `for st in true false; do curl -sN localhost:8451/api/chat -H 'Content-Type: application/json' -d "{\"text\":\"hey\",\"tier\":\"medium\",\"thinking\":true,\"small_talk\":$st,\"source\":\"timing\"}" | grep -o '"seconds": [0-9.]*' | sed "s/^/small_talk=$st /"; done`
- **A1 (skills/docs/checks) done.** mech-forge rewritten as the general
  Blender skill (backup: backups/2026-09-25-S4-skills/); godot-forge updated
  (template arg, add-ons, new clean message, no primitive stand-ins, no-render
  rule); interrupted checks: black on test_godot.py, `test_godot.py` 7 passed,
  pyright 0; the node_paths/pitch edits load cleanly in the headless template
  check. The follow-camera look was not re-recorded (A30). /tmp scratch was
  already gone. ~/Forge/docs/DESKTOP-REACH.md, PLAN header, PROGRESS.json session_61_work
  updated. S1 says A39 is done (Claude app gets the acchan MCP tools).
- **A31 done + checked headless by Kiln (S11), 2026-09-27**: Emerson picked "3 Both"; VRoid HairSample_Female (CC0) + Quaternius UAL clips, retargeted by shared/bridges/godot/humanoid.py. Details and what is left: docs/plans/PLAN-blender-godot-upgrade.md "State 2026-09-27". Earlier note: **A31 was blocked on Emerson's character pick** (board note to
  Emerson: 1 Quaternius UBC+UAL (CC0, recommended) / 2 VRoid beta CC0 VRM /
  3 both / 4 Mixamo by him). Next session: read his board reply, fetch
  the pick (say size on the board), then in
  `shared/bridges/godot/templates/third_person/`: replace the capsule with the
  character + its idle/run clips in the AnimationTree, Poly Haven ground
  texture (assets_get), rock/tree props instead of crates, an HDRI or
  ProceduralSky, check with godot_check + a headless position probe; leave
  Emerson the godot_play command. Then the end-to-end demo (Blender HDRI
  scene -> export_godot -> template) and the A1 wrap-up.
- Stopped at 69% of the 5-hour window (5 sessions sharing it).
