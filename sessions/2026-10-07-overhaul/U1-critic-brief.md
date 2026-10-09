# U1 sweep: critic + breaker brief (one per group)
date: 2026-10-08 · for: Claude · written by Rei (relay-74-work), commander of Relay task 74

You are the critic and breaker for one finished group of the U1 every-app
sweep. Your launch message names the group (Gk), its apps and your scratch
ports. Fresh eyes: assume the worker's report is optimistic until you have
checked it. Emerson is not watching; never ask him anything.

## Read first
- `~/Forge/sessions/2026-10-07-overhaul/U1-worker-brief.md`: what the worker
  had to do (looks, rest when hidden, robustness, break 6 poll backoff, tests,
  black, pyright, WIP.md, commit per app with only its own hunks).
- The worker's report `~/Forge/sessions/2026-10-07-overhaul/reports/u1-<Gk>.md`.
- Its commits: `git log --oneline --grep "Relay task 74" -- apps/<app>` (plus
  `forge.py forge_views.py hub/` for G1), then `git show <hash>`.
- `~/.claude/skills/verify/SKILL.md` (headless Chrome through Flatpak; drive
  pages only through `~/Forge/tests/cdp_driver.py` `chrome_page()`; never leave
  a Chrome running) and `~/.claude/skills/safe-shell/SKILL.md`.

## Try to break it
- **Missed asks:** anything in the worker brief not done, or claimed
  "verified" without evidence. A feature removed or renamed counts as a break.
- **Commit hygiene:** a commit carrying another session's uncommitted hunks
  (board, crewroom, novelforge, acchan), a file left half-staged, stray debug
  prints, temp files, commented-out code.
- **Behaviour:** run each app on your scratch ports (copy its data to /tmp,
  never its real data dir; PID files; stop by PID). In headless Chrome:
  hidden page does no fetch/rAF/timer work for 10 s (inject a counter); server
  killed then restarted (rate drops, calm message, recovers by itself); bad
  and huge input to the API and the forms (empty, 200 kB, unicode, wrong
  types); rapid double clicks; long lists; screenshots at 760, 1100, 1500 and
  1920 px wide (look at them, 50 % scale) for clipping, overlap, layout jumps,
  unreadable contrast, missing empty/loading/error states.
- **Tests:** run the app's tests yourself
  (`.venv/bin/python -m pytest -q tests`), `black --check` and
  `pyright --pythonpath ./.venv/bin/python` on the touched .py files.

## Rules
- Do not edit app code or commit: you report, the worker fixes. Scratch files
  only under `/tmp/u1/<Gk>-critic/`.
- Never restart Emerson's Forge, any real app backend, Jan, Relay or the
  Claude app on 8445; never fire requests that make Jan generate. No fps, GPU
  or CPU-load measurements. Batch: every request carries at least ~10 s of
  work.

## Report
Write `~/Forge/sessions/2026-10-07-overhaul/critics/u1-<Gk>-critic.md`
(title, `date: 2026-10-08 · for: Claude`): numbered breaks, each with
severity (high/medium/low), where (file:line), repro, what you saw, and a
concrete fix, marked **verified** (you reproduced it) or **suspected**; then
"checked and fine" and "not covered". Reply in at most 10 lines: the verified
breaks, one line each.
