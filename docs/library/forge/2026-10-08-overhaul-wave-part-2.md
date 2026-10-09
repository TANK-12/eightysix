# Overhaul wave, part 2 (Relay task 63): what got done and what is left
date: 2026-10-08 · for: both

Part 2 of the Forge overhaul wave of 2026-10-07. The plan, briefs and lane
reports are in `sessions/2026-10-07-overhaul/` (HANDOFF.md first). This page
closes the items under "New asks" and "Next" in that HANDOFF.

## Item by item

**New asks (icons).** Done by Relay task 66: one shared drawn icon style
(`shared/forge_icons.js`), a new Mission Control icon built on the Claude logo
idea, Jan Tune and Power told apart (commits acc42c6, 7d13c63; before/after in
`sessions/2026-10-07-overhaul/reports/ICONS.md`). Task 70 added the New/Classic
icon style switch (a15cd03).

**Next 1, tests and a commit per lane.** Done: 35ef508, 994989b, be02b98,
b132a41, b84d33b.

**Glass freeze (Alt+Shift+M), found on the way.** Frosted and Liquid put a
live blur on every tile; WebKitGTK fell to 0 fps and hung. Fixed, plus a hub
hang watchdog in forge.py: a5788ee, fc1bc14. Full story and numbers:
`2026-10-07-glass-blur-freeze.md` in this folder.

**Browser checks.** `tests/browser/run.sh` had 6 FAILs. Fixed in b698e2f
(WebKit probes skip the DMA-BUF renderer that aborts offscreen on Wayland; the
visualiser harnesses step a frame's time). Now 1050 PASS, 0 FAIL.

**Next 2, final review swarm (Opus only).** Reports in
`sessions/2026-10-07-overhaul/critics/final-*.md`.
- Critic (looks and feel): 5 defects. Fixed in f4fcab0: the Claude header's
  settings (Normal/Ultracode, Limits, Can) were hidden in a sideways scroll
  below about 1900 px and now wrap; the avatar pane starts shut below 900 px;
  the Enjoy title gets an ellipsis; the hub's "Jump back in" names stay on one
  line. The Mission Control crew chip repeated per member: fixed by task 73
  (f4797a0).
- Analyst (power): a 13-item code audit. Item 1 fixed in e2770d4: the wall
  tint ran a 60 s colour fade restarted every 60 s, so it never stopped
  repainting the window; now a 2 s fade. Items 2-5 (particles and visualiser
  slower behind an open app, suspending the music audio graph, the Claude busy
  pulses) change what he sees or hears, and task 71 already left them as his
  call, so they are not applied.
- Breaker: BREAKER_RESULT

**Next 3, U1 every-app sweep.** Queued as its own Relay task 74 (Opus, xhigh;
request `sessions/2026-10-07-overhaul/U1-relay-request.txt`, brief
`U1-every-app-sweep-brief.md`), Forge Browser first. Not done by task 63: it is
a long multi-app job with its own critic and breaker per app.

**Next 4, the numbers table.** Plan written in
`docs/library/power/2026-10-07-overhaul-numbers.md`; no numbers taken yet.
Performance runs go last (Emerson, crew note 1054), so the plugged-in runs
belong at the end of the U1 sweep, whose request says so. The 10-minute
unplugged run needs Emerson at the laptop: blocked on him.

**Next 5, docs.** This page, PROGRESS.json `session_2026_10_08_overhaul_part2`,
HANDOFF.md "Update 2026-10-08", and `apps/claude/WIP.md`.

## Verified, and how

- Claude app: pytest 194 passed; `check_sizes_ui.py` 18/18 (it failed 1 at
  App 1.5 + Text 1.5 before, on the sidebar; fixed in f4fcab0);
  `check_run_controls_ui.py` and `check_enjoy_ui.py` all passed. Headless
  Chrome at 760/1100/1500: no header control outside the window.
- Hub: `tests/browser/run.sh` 1050 PASS; `tests/test_hub_transitions.py` failed
  on the old tint and passes now; in Chrome the old hub still had the tint
  transition running 3 s after a change, the new one had none.
- Not seen in the real Forge WebKit window: the checks use headless Chrome or
  a private headless GNOME.

## For Emerson

- Restart Forge once: the hang watchdog in forge.py needs it. The hub and app
  changes need only a reload.
- Your call: analyst items 2-5 (above), and the unplugged run for the table.
