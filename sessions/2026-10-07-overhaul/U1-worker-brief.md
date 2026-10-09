# U1 sweep: worker brief (every app group)
date: 2026-10-08 · for: Claude · written by Chihiro (relay-74-work), commander of Relay task 74

You are one worker of the U1 every-app sweep. Your launch message names your
group (Gk), its apps and your scratch ports. Emerson is not watching: work
unattended, never ask him anything, decide sensibly and write each assumption
down in your report.

## Relay workers (from 2026-10-08 01:20, Kiko, session 5 of task 74)
Each group now runs as its own Relay task, queued one at a time by the U1
sequencer (`sessions/2026-10-07-overhaul/u1_sequencer.py`, paced by the
usage meter), because in-session subagent workers died every time the
commander session handed over. For your group's Relay session:
- The Relay rules apply on top of this brief: keep your task file's
  `## State` current (which app, which step, which commits) so a fresh
  session can carry on after a hand-over, and end with `status: done`.
- Claims: claim your app folders on crew board "forge" at the start
  (`python3 ~/.claude/skills/crew/crew.py claim forge <your name> ~/Forge/apps/<app>`)
  and release them at the end. If another live session (not relay-74-work)
  holds a claim inside one of your apps, skip that app and say so.
- Order: sweep and commit each app, draft the report, then the critic, then
  fixes, then the final report.
- Critic: launch one fresh critic yourself when your sweep commits are in:
  Agent tool, model opus, `run_in_background: false`, prompt "You are the U1
  critic for group Gk (<apps>), scratch ports <upper five of yours>. Read
  ~/Forge/sessions/2026-10-07-overhaul/U1-critic-brief.md and do what it
  says." Fix its verified breaks (and the suspected ones you can confirm),
  re-run the checks, commit a follow-up per app, and list every finding,
  fixed or not, in your report.
- Scratch ports: 8900+10*k to +9 for group Gk (G1 8910-8919, G12 9020-9029).
- `/tmp/u1/done/<group>` is no longer needed (the sequencer watches the Relay
  task status). Final phone message: at most 4 short lines; a question for
  Emerson goes at the top of your report and into that message.

## Read first (only what you need, grep big files)
- `~/Forge/CLAUDE.md`, `~/.claude/skills/forge-session/SKILL.md`,
  `~/.claude/skills/verify/SKILL.md` (headless Chrome through Flatpak; drive
  pages only through `~/Forge/tests/cdp_driver.py` `chrome_page()`; never leave
  a Chrome running), `~/.claude/skills/safe-shell/SKILL.md`.
- `~/Forge/sessions/2026-10-07-overhaul/U1-every-app-sweep-brief.md` (the goal)
  and `~/Forge/docs/library/power/2026-10-07-power-best-practice.md` (the power
  checklist). Lane H4 already wired `shared/forge_idle.js` into many apps:
  `~/Forge/docs/library/power/2026-10-07-app-power-sweep.md` says which, and
  what it left.
- Per app: README / MANIFEST, `forge_app.json`, the newest `WIP.md` section,
  then the code you need.

## What a sweep is (per app)
Emerson: "i want everything to look nice, great, pretty and smooth"; "use less
power ... i dont want to lower the looks of anything too much"; "please dont
remove features i like what i have"; "if something works fine, do not change
it".
1. **Looks.** Uses the shared theme (`/shared/forge.css` tokens, no hardcoded
   colours fighting it); smooth 150-250 ms transitions on transform/opacity
   only; no layout jumps when data arrives; polished empty, loading and error
   states (never a blank pane or a raw stack trace); thin styled scrollbars
   (incl. `::-webkit-scrollbar`, the hub runs WebKitGTK); crisp at 760, 1100,
   1500 and 1920 px wide. Look at a headless screenshot at each width (keep
   the images small, e.g. 50% scale) before and after.
2. **Rest when hidden.** No polling, rAF, timers, infinite CSS animation or
   audio analyser running while hidden (`shared/forge_idle.js` ForgeIdle.poll,
   `visibilitychange` / `forge-visible`), and the shared power tier from
   `shared/forge_power.js` honoured where the app draws anything animated.
   Check it: in headless Chrome, inject a tiny counter for fetch / rAF /
   setInterval callbacks, hide the page (dispatch the hub's hidden signal or
   emulate visibility hidden), and count for 10 s: expect 0 (or the documented
   slow tick). This is a functional check, not a power measurement.
3. **Robustness.** Bad input (empty, huge, unicode, wrong types to the API),
   the server going down and coming back (the page shows a calm error and
   recovers by itself, no request storm), rapid double clicks (no double
   submit, no stacked timers), long lists.
4. **One useful missing feature**, only where the app clearly lacks one and it
   is small and safe. Optional. Never remove or rename a feature.

Do not change what already works well just to change it. Do not touch
`shared/`, `hub/`, `forge.py`, other apps, `apps/claude`, `apps/mission`,
`apps/wallpapers`, `apps/relay` (your launch message may grant an exception).
If the right fix belongs in `shared/`, write it in your report instead.

## Hard rules
- No fps, GPU or CPU-load measurements (Emerson, crew note 1054: performance
  runs go last). Instead list "measure this" items in your report (what to
  measure, how, expected effect).
- Never restart Emerson's Forge, any app backend on its real port, the Claude
  app on 8445, Relay or Jan. Never touch CPU power caps. Test copies run on
  your scratch ports only (check the port is free with `ss -ltn` first), with
  a PID file; stop them by PID when done. Static file changes reach Emerson's
  Forge on the next page reload; backend (.py) changes only on his next Forge
  restart: say so in WIP.md.
- Games: never lose or overwrite game state or saves; test with a temp data
  dir or a copy.
- Backup every file before you edit it to
  `~/Forge/backups/2026-10-07-overhaul/sweep/<app>/` (keep the relative path).
- Batch hard (Emerson): each request carries at least ~10 s of work: many
  independent tool calls in one message, related shell steps in one Bash call,
  several edits to one file in one script. Never `git stash`, never
  `git add -A`, never `git checkout` a file someone else changed.
- No ALL-CAPS in UI strings or logs. Never delete anything Emerson made; trash
  (`gio trash`) instead of `rm` for anything not created by you in /tmp.

## Definition of done per app
- App tests green: `cd ~/Forge/apps/<app> && .venv/bin/python -m pytest -q tests`
  (install pytest into that venv if missing). Add a test for each behaviour
  you add or fix where there is a test surface; JS-only changes get a headless
  check script or at least `node --check`. If the app touches something the
  hub-level runner covers, run that block of `~/Forge/tests/browser/run.sh`.
- `black` on every .py you touched; `pyright --pythonpath ./.venv/bin/python
  <files>` from the app folder shows no new errors.
- No leftover debug prints, temp files or commented-out code.
- `apps/<app>/WIP.md` gets a new top section `## U1 sweep (2026-10-08, Relay
  task 74)`: what changed, what is **verified** (and how), what is not.
- **Commit per app**, only your own changes, message
  `<App>: <what changed> (U1 sweep, Relay task 74)` and the trailer line
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
  `git add <your paths>` only. Some apps hold other sessions' old uncommitted
  work (board, crewroom, novelforge, acchan; check `git status --porcelain
  apps/<app>` before you start and save `git diff apps/<app>` to your backup
  folder). Never commit that work and never revert it. For a file that mixes
  theirs and yours, stage only your change onto the HEAD version:
  `git show HEAD:<f> > /tmp/u1/head; cp <backup-of-f-before-you-edited> /tmp/u1/base;`
  `git merge-file -p /tmp/u1/head /tmp/u1/base <f> > /tmp/u1/mine` (resolve
  any conflict by hand), then
  `git update-index --cacheinfo 100644,$(git hash-object -w /tmp/u1/mine),<f>`
  and check `git diff --cached <f>` shows only your change.

## Report
Write `~/Forge/sessions/2026-10-07-overhaul/reports/u1-<group>.md` (title,
`date: 2026-10-08 · for: both`): per app what changed, commits, tests (counts),
screenshots looked at (paths under /tmp/u1/<group>/), verified versus not,
"measure this" items, shared/ changes you recommend, assumptions. Then
`touch /tmp/u1/done/<group>` and end with a reply of at most 15 lines (the
commander reads only that): per app one line (commit hash, tests, the main
change), then anything blocked.

If a critic's findings are sent back to you later, fix the confirmed ones,
re-run the checks, commit a follow-up per app, update WIP.md and the report,
`touch /tmp/u1/done/<group>-fix`, and reply in at most 10 lines.

## Group notes (read the one for your group)
- **Breaker items for every group:** `sessions/2026-10-07-overhaul/critics/final-breaker.md`
  break 6: no `ForgeIdle.poll` caller backs off while its server is down. In
  your apps, make each poll job `return false` on failure and pass
  `{ backoff: 2, maxMs: 30000 }` (keep `hiddenMs` where set); check it with
  the server killed (count fetches 0-10 s and 10-30 s: the rate must drop) and
  restarted (the page recovers by itself).
- **G1 browser** (Emerson: "the forge app browser lowkey never works for me";
  fix this first and best). Its pages are native WebKit views laid over the
  hub by `forge.py` + `forge_views.py`; WIP.md says that path was never checked
  in a real Forge window. Exception for G1 only: a minimal, tested fix in
  `forge_views.py`, `forge.py` or `hub/index.html` is allowed if the bug lives
  there (backup first, separate commit `Forge views: ...`); it reaches Emerson
  on his next Forge restart (never restart it yourself). Look first at
  `journalctl --user -b | grep -i -E "webkit|forge"`, `outputs/browser.log`,
  `outputs/forge*.log`. Offscreen GTK windows need
  `WEBKIT_DISABLE_DMABUF_RENDERER=1` on this machine (see tests/page_probe.py).
  A shown-window rig exists: `tests/browser/headless_gnome.sh` (headless
  gnome-shell; stop it by PID when done). An earlier, stopped G1 worker left
  `/tmp/u1/G1/rig_explore.py` (real hub + Browser + native views in the rig)
  and its output `/tmp/u1/G1/explore2.txt`: after opening the Browser and a
  page, the tab's view reported `visible: False, alloc (-1,-1,1,1)` until the
  hub called `selectWorkspace('browser')`; reuse it. If logs and runs cannot
  show what Emerson sees, put one short question for him at the top of your
  report (the commander posts it) and carry on.
  **State left by the 2nd stopped G1 worker (00:51):** `forge.py` already
  holds an uncommitted fix, `view_handler()`: the hub's `owner` and `inset`
  messages sent before the first view used to be dropped, so the Browser's
  first page stayed hidden until another app was opened; they are now kept and
  replayed when the ViewHost is made. Test added in `tests/test_views.py`
  (`test_the_first_view_shows_for_the_app_the_hub_already_put_in_front`,
  all 9 pass, `/tmp/u1/G1/test_views.out`). **Committed by the 3rd run as
  97bfd48** (`Forge views: keep the hub's owner and inset ...`, confirmed in
  the GNOME rig per its message). The 3rd stopped G1 worker (01:07) also left
  `apps/browser/tests/check_ui.py` (untracked, unreviewed): finish or drop it.
  Carry on with the rest of the Browser sweep: does a page actually show,
  take input, navigate and come back after switching apps in a shown window?
- **G2 board, calendar.** Board holds another session's uncommitted 09-30 work
  (saved at `backups/2026-10-07-overhaul/sweep/board/preexisting-uncommitted.diff`):
  never commit or revert it; stage your hunks with the merge-file recipe.
  The backups in `backups/2026-10-07-overhaul/sweep/{board,calendar}/` and the
  before-shots in `/tmp/u1/G2/shots/` were taken by an earlier stopped worker
  and are still the untouched originals: keep them, do not overwrite.
  **State left by the 2nd stopped G2 worker (00:53):** sweep edits already
  in the tree, not yet tested or committed: board `web_app.py` (post/ack pass
  options as `--opt=value` and the words after `--`), `tests/test_board.py`,
  `static/index.html`; calendar `collector.py`, `store.py`, `web_app.py`,
  `tests/test_calendar.py`. Diff each against its backup, keep what is right,
  finish, test, commit. The 3rd stopped G2 worker (01:03-01:05) also edited
  calendar `static/app.css`, `static/app.js`, `static/index.html`. All
  calendar backups equal HEAD (checked 01:15).
- **G12 dossier, foresight.** Both can call the shared Jan: never restart
  Jan, and do not hit routes that ask Jan for an answer during robustness
  tests (stub or skip them). Before-shots from an earlier stopped worker are
  in `/tmp/u1/G12/`.
  A 2nd stopped worker also took `before2-*` shots there (00:55). The 3rd
  stopped worker (01:07) left untested edits in dossier `dossier.py`,
  `store.py`, `web_app.py` (its backups equal HEAD, checked 01:15) and
  drafts `tests/test_u1_robustness.py` in both dossier and foresight (no
  foresight code edits). Review, keep what is right, finish, test, commit.
- **G3 files, comix / G5 settings, code, logins.** Break 6 applies (Calendar,
  Comix, Files, Settings named in final-breaker.md as the same wrapper
  pattern). Logins holds secrets: never print or copy real credentials; test
  with a temp data dir only.
- **G4 crewroom, terminal.** Crewroom holds another session's uncommitted
  10-07 work (WIP.md, context.py, launch.py, sources/sessions.py,
  static/app.js, tests/test_sources.py, tests/test_where.py): save
  `git diff apps/crewroom` to your backup folder first, never commit or revert
  it, stage only your hunks with the merge-file recipe. Terminal: break 6 names
  `refreshInfo` (static/app.js); never kill or write into Emerson's real
  terminal sessions.
- **Games (G6 emberfield, G7 arcade + driftpeaks, G8 janhollow, G9 cosmos +
  eightysix).** Never lose or overwrite saves or game state: point the scratch
  copy at a temp data dir. No GPU runs and no fps numbers; "measure this"
  items only. Eightysix: `~/Games/eightysix` files are claimed by
  relay-65-work; touch only `apps/eightysix/`.
- **G10 acchan, jan-tune.** `apps/acchan/qwen.py` is another session's
  untracked file: never commit it. Acchan and Jan-tune talk to Jan: never
  restart Jan, never start a tune or eval, and do not fire routes that make
  Jan generate.
- **G13 novelforge, inkforge.** Novelforge holds another session's large
  uncommitted 09-28 work (many modified and untracked files, see
  `git status --porcelain apps/novelforge`): save the diff to your backup
  folder, never commit or revert it, and keep your novelforge changes small
  and in files you can stage by hunk. NovelForge talks to Jan: no generation
  calls in tests.
- **G14 panelforge, printforge.** `apps/printforge/` is wholly untracked but
  finished (crew/ejb-fc-print.json says done, 09-28): first commit it as found
  (`PrintForge: app as built on 2026-09-28 by ejb-fc (U1 sweep, Relay task
  74)`, only `apps/printforge/` paths, no caches), then sweep it in a second
  commit.
- **G18 codec-lab, codec-player.** The code lives in `~/anime-codec-lab`,
  a git repo with no commits at all: do not make its first commit (that is
  Emerson's call). Back up, sweep, test with its own venv, and record in the
  report which files you changed; skip the commit step for that repo and say
  so. Exclude `winbuild/wineprefix/` from every search, lint and test run.
