# U1 sweep critic: group G5 (Settings, Code, Logins)
date: 2026-10-08 · for: Claude

Critic for Relay task 80 (worker commits 3dcd150 settings, f2866b2 code,
ecd27cf logins). Scratch servers on 8955 (settings), 8956 (code), 8957
(logins) from `/tmp/u1/G5-critic/srv.sh` against sandbox copies in
`/tmp/u1/G5-critic/` (settings with `XDG_CURRENT_DESKTOP=Hyprland` so the
desktop picture comes from the sandbox `path.txt`, not GNOME). Check script
`/tmp/u1/G5-critic/crit.py`, output `crit-settings-code-logins.out`,
`many.py`; screenshots `/tmp/u1/G5-critic/shots/` (50 % copies in
`shots/half/`, contact sheets `sheet-*.png`). All servers and Chrome stopped
by PID; the worker's 8950-8952 servers were not touched.

## Breaks

1. **Settings: unticking "Follow my desktop wallpaper" refuses with a false
   message when the desktop picture is in a sub-folder of the wallpaper
   folder.** Severity low (all 236 real wallpapers sit at the top level today,
   but sub-folders are a supported layout: `list_wallpapers` names them
   `anime/moon.png`). **Verified.**
   Where: `apps/settings/static/app.js:251` (new gate) compares against
   `state.theme.wallpaper_name`, which is only the basename
   (`shared/forge_theme.py:2301` `source.name`; same for
   `apps/settings/web_app.py:66` `desktop_wallpaper`).
   Repro: sandbox walls hold `anime/moon.jpg`, `path.txt` points at it; untick.
   Saw: still ticked, note "Your desktop's picture is not in the wallpaper
   folder: pick one below…", nothing stored. Same root cause (pre-existing):
   picking `anime/moon.jpg` from the grid stores it, but no tile is
   highlighted and the current preview is the empty placeholder
   (`settings-subfolder-picked.png`). The reverse also slips through: an
   outside desktop picture whose basename matches a top-level wallpaper passes
   the gate and selects that other file.
   Fix: have the backend expose the picture's name relative to
   `WALLPAPER_DIR` when it lies inside it (e.g. a `wallpaper_key` next to
   `wallpaper_name` in `forge_theme.theme()`, "" when outside), and use that
   for the gate, the tile highlight and the thumbnail. Needs a shared/ change,
   so recommend rather than do in the app.

2. **Settings: a save answer that arrives after Reset puts the old value back
   on screen and says "Saved", while the file holds the defaults.** Severity
   low-medium (a save that renders a new wallpaper can take seconds, which is
   the window). **Verified** with a fake 1.5 s delay on the POST answer
   (server itself handled both in order).
   Where: `apps/settings/static/app.js:795-797` (Reset clears the timer and
   pending but not a save in flight) and `:103` `accept()`.
   Repro: `change('tint', 0.21)`, 0.4 s later press Reset twice.
   Saw: page tint 0.21, status "Saved"; `GET /api/settings` tint 0.5.
   Fix: give each request a sequence number (`state.gen++` on Reset and on
   each flush) and drop any `accept()` from an older generation; or make
   Reset wait for `state.saving` to clear (await the in-flight flush) before
   it posts.

3. **Settings: Reset pressed while the backend is down silently throws away a
   change waiting to be saved.** Severity low. **Verified.**
   Where: `apps/settings/static/app.js:795-797` (`stopRetry(); state.pending = {}`
   before the request is known to work).
   Repro: kill the server, `change('tint', 0.33)`, press Reset twice.
   Saw: `pending={}`, status "Not reset: the Settings backend is not
   answering", the slider still shows 0.33 but nothing will ever save it; the
   server keeps the old value after restart.
   Fix: only clear `state.pending` and stop the retry after the reset request
   succeeded (on failure keep pending and the retry running).

4. **Code: the "remembered folder is gone" fallback still shows a red error
   toast.** Severity low. **Verified.** The report says it "opens home instead
   of an error".
   Where: `apps/code/static/index.html:123` (openPath always toasts) with the
   fallback at `:139`.
   Repro: `localStorage['code.folder']='/tmp/u1/G5-critic/gone'`, reload.
   Saw: editor opens `/home/ejb`, toast "toast err | /tmp/u1/G5-critic/gone
   doesn't exist" (`code-gone-folder.png`; the toast also sits over the
   hub's "Close app / Full screen" corner).
   Fix: pass a `quiet` flag to openPath for the remembered-folder attempt (and
   clear the stale `code.folder`), or replace the error with a calm
   "Your last folder has gone, opened home" toast.

5. **Logins: one account's Bring login in locks the button for every account
   for up to 20 s, with no reason shown.** Severity low. **Verified**
   (simulated hub parent, faked cookies answer).
   Where: `apps/logins/static/app.js:107-128` (`state.waiting`/`bringTimer`
   are global, the button is one).
   Repro: Bring on claude-one, switch to the gemini tab, press Bring.
   Saw: `disabled=true`, 0 cookie reads, status still "Sending 1 cookies…"
   (about claude-one) while gemini is on screen.
   Fix: keep the waiting state per account (`state.waiting` as a Set or a map
   id -> timer) and set `$("bring").disabled` from the active account in
   `select()`.

6. **Logins: with more tabs than fit, the tab strip can no longer be scrolled
   with a mouse in the hub.** Severity low (5 real accounts fit down to about
   650 px of app width). **Verified** in Chrome; WebKitGTK reasoned.
   Where: `apps/logins/static/app.css:36` `.tabs::-webkit-scrollbar { display: none; }`
   (new) on top of the old `scrollbar-width: none` (`:9`).
   Repro: 30 accounts (with `port`), 760 px window (`logins-many30-760.png`).
   Saw: strip `scrollWidth 3732 / clientWidth 760`; a vertical wheel over it
   leaves `scrollLeft` at 0; only keyboard focus (tabs are buttons now, which
   scrolls them in) or shift-wheel/touchpad reach the hidden ones. Before
   this commit WebKitGTK still showed a bar there.
   Fix: either keep a thin styled bar (`height: 6px` thumb instead of
   `display: none`), or map vertical wheel to horizontal on `.tabs`
   (`wheel` listener: `tabs.scrollLeft += e.deltaY` when `deltaX` is 0).

7. **Code: if `/api/url` fails right after `/api/session` said ready, the
   start screen spins forever with no Try again.** Severity low. **Suspected**
   (reproduced only with a faked 503 on `/api/url`; the real window is the
   editor dying between the two calls). Pre-existing shape, but this commit
   reworked exactly this path.
   Where: `apps/code/static/index.html:139` (both openPath calls fail, boot
   returns, nothing shows the retry).
   Saw: no requests in the next 15 s, title "Starting the editor…", spinner
   on, retry hidden (on a fresh load the wait card stays up as is).
   Fix: if the fallback openPath also fails, `waitScreen("The editor didn't
   open", e.message, true)` so Try again appears.

8. **Settings backend stores any string for `wallpaper` unchecked (200 kB
   accepted into `settings.json`).** Severity low, pre-existing, backend not
   touched by the sweep. **Verified**: POST `{"wallpaper": "x"*200000}` ->
   200, file grew to 203 kB (restored afterwards); every backend that loads
   settings reads it. `"ünï/../../etc/passwd\0"` is stored too (harmless, the
   lookup goes through the listing). Where: `shared/forge_theme.py:1481`
   (the plain-string branch of `_clean`). Fix: for `wallpaper`, keep the
   value only if `wallpaper_path()` finds it (else ""); cap plain strings at
   e.g. 1 kB. Shared change: recommend only.

Cosmetic, verified, low: the retry cards glue the error to the next sentence
without a full stop: "accounts.json: Expecting value: line 1 column 16 (char
15) Trying again by itself…" (`apps/logins/static/app.js:169`; Settings has
the same join at `apps/settings/static/app.js:847` but adds the full stop).
Fix: end the message with ". " when it has no closing punctuation.

## Checked and fine
- Tests: settings 34, code 14, logins 7 passed (each app's venv). `black
  --check` and `pyright --pythonpath ./.venv/bin/python` on
  `apps/code/web_app.py tests/test_code.py`: clean, 0 errors. `node --check`
  on both app.js files and the Code inline script: ok.
- Commit hygiene: each commit touches only its own app (`git show --stat`),
  no debug prints or commented-out code in the added lines, the three app
  trees are clean in `git status`.
- Rest when hidden (document hidden, 10 s): 0 fetch / rAF / timer /
  interval in Settings, Logins and the Code wrapper.
- Backoff and recovery: Logins with a broken `accounts.json` asked 2 times in
  0-10 s and 2 in 10-30 s, said what is wrong, and recovered by itself; the
  empty registry shows "No accounts yet" and stops polling. Settings boot card
  and Code wait card show while down and both pages came back by themselves
  after a restart. Logins inside a simulated hub: down card shows, hides again
  on recovery.
- API bad input: Settings non-dict / bad JSON -> 422; NaN, 1e999, wrong types
  clamp or fall back; thumb traversal and 5 kB names -> 404. Code `/api/url`
  NUL -> 400, 20 kB name -> 404, unicode -> 404, no header -> 403. Logins
  unknown / huge / NUL ids -> 400, no header -> 403. No 500 anywhere.
- Screenshots at 760/1100/1500/1920 (Settings, Logins), 760/1920 (Code and
  down cards): no clipping or overlap from the sweep; cards readable at 760.

## Not covered
- Inside the real Forge window (WebKitGTK): scrollbars, the hidden tab-strip
  bar, the hub's `forge-visible` path beyond the simulated message.
- Code-server inside the iframe keeps its own timers while Code is hidden (the
  counters only see the wrapper page); the worker's "measure this" item.
- Real Sign in in Firefox and real cookie hand-off (faked on purpose).
- The 422-with-array detail formatting in Settings was read, not run.
