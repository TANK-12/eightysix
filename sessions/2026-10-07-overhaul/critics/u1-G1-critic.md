# U1 sweep critic: G1 (Browser + forge.py views fix)

date: 2026-10-08 · for: Claude

Critic of the Relay task 75 worker: commits 97bfd48 (forge.py + tests/test_views.py)
and b777562 (apps/browser). Scratch ports 8915-8917; scratch files in /tmp/u1/G1-critic/
(break.py + break.out, fuzz.py, oldhandler.py, check_ui.out, shots/, shots2/).
Every backend and Chrome I started was stopped. The 6 headless Chromes still running
at the end belong to G4 (`/tmp/u1/G4/cdp-term`) and were left alone.

**Summary.** The root-cause fix is right: I reproduced the bug with the old handler
logic and saw it go away with the new one. The Browser sweep holds up under fuzzing
and the hidden-page check. Two medium breaks are in the new offline handling: the
saved tabs can be wiped, and the "server away" strip stays up 25 s after the server
is back.

## Breaks

1. **Medium, verified: after a boot with the server away, the saved tabs get overwritten.**
   Where: apps/browser/static/app.js:702 `boot()`, :483 `saveSessionSoon()`, :558 `setOffline()`.
   Repro: /tmp/u1/G1-critic/break.py, scenario B. A saved session of 3 web tabs
   (a/b/c.example.com, active 1). The page boots while its /api/ fetches fail: a shim
   rejects them with `TypeError('Failed to fetch')`, which is what the page sees from a
   dead server. Then the server answers again.
   Seen: boot opens one blank tab. The 0.8 s session timer runs while `offline` is set,
   so it sets `sessionDirty`. On recovery `loadState(false)` does not restore the tabs,
   and the dirty session is saved. Saved session before: 3 tabs. After recovery:
   `{'tabs': [{'url': 'about:blank', 'title': 'New tab'}], 'active': 0}`. The user's
   tabs are gone and nothing on screen says so.
   The trigger is narrow, because the page itself comes from the same server: it needs
   the server to die between serving the page and `/api/state`. The loss is silent, so
   it rates medium. The same loss already happened before this commit when only
   `/api/state` failed (the boot tab's save went through). The dirty flag adds the
   offline path.
   Fix: never save the session before `state.loaded` is true (in the save timer:
   `if (!state.loaded) return;`). On recovery, if the tabs are still just the boot's
   untouched blank tab, close it and run `loadState(true)` instead of `loadState(false)`.
   Add the scenario to check_ui.py.

2. **Medium, verified: the offline strip stays up for 25 s after the server is back.**
   Where: app.js:568. `setOffline(false)` runs only when `/api/agent/next?wait=25`
   returns, and the server holds that request for up to 25 s when there is no command.
   Seen: 25.1 s from the server answering to the strip clearing (scenario B). With a
   real kill and restart (scenario C) the strip cleared 28.9 s after the backend was
   back: backoff wait plus the 25 s hold. Bookmarks and history do not reload during
   that time either. check_ui.py's recovery check allows 40 s, so it hides this.
   Fix: while offline, probe with `wait=0` (`api(\`/api/agent/next?wait=${offline ? 0 : 25}\`)`),
   or call `setOffline(false)` from any successful `api()` call. Tighten check_ui's
   limit to about the backoff step plus 2 s.

3. **Low, verified: the strip's text promises more than the page does.**
   Where: static/index.html:36. The strip says "bookmarks, history and saved tabs catch
   up by themselves when it is back". Only the tabs do.
   - A bookmark made while away is refused. Scenario E, the star while away gives the
     note "Could not save the bookmark: Failed to fetch".
   - Visits made while away are dropped. app.js:240 sends `/api/visit` with
     `.catch(() => {})`, read in the code, not run.
   Fix: change the text, for example "Bookmarks and history wait until it is back;
   open tabs are saved then". Or keep a small queue of visits and send it on recovery.

4. **Low, verified: notes show the raw "Failed to fetch".**
   Where: app.js `toggleBookmark`, `savePrefs`, clear-history and bookmark-remove
   catches. Seen in scenario E: "Could not save the bookmark: Failed to fetch". The
   worker brief asks for a calm error. Fix: when `offline` is set, or the error is a
   TypeError, say "...: Browser's server is not answering just now".

5. **Low, verified on screen (the wheel part is suspected): with many tabs, the open
   tab and the + button scroll off the strip.**
   Where: app.js:181 `renderTabs()`, app.css `.tabs` (overflow-x auto, scrollbar
   hidden in both engines).
   Seen in /tmp/u1/G1-critic/shots2/offline-tabs-note-760.png: 13 tabs, about 3.5
   showing, and the open tab (the last one) and + are not visible. Nothing scrolls the
   open tab into view. As far as I know a vertical wheel does not scroll a strip that
   only overflows sideways (not tested).
   Mostly older than this commit: `scrollbar-width: none` was already there. This
   commit's `::-webkit-scrollbar { display: none }` takes away the last scrollbar in
   WebKitGTK.
   Fix: in `renderTabs()` add
   `strip.querySelector('.tab.active')?.scrollIntoView({inline: 'nearest'})`, and a
   wheel handler that turns deltaY into scrollLeft.

6. **Low, verified on screen: at narrow widths the note covers the right of the tab strip.**
   Where: app.css:113. At 760 px the 45vw note hides about 2 tabs and their close
   buttons for 3.5 s (shots2/offline-tabs-note-760.png). Clicks pass through
   (`pointer-events: none`), but the user cannot see what they would click.
   Fix: `max-width: min(420px, 30vw)`, or put it in the toolbar row's free space.

7. **Low, suspected: Ctrl+Shift+T works only while the Browser's own bar has focus.**
   Where: forge.py `on_key` (about line 1580) passes no keys to the Browser, and
   forge_views.py has no key handling at all. While a native page has focus, Ctrl+T,
   W, L, D and the new Ctrl+Shift+T never reach app.js's keydown. The other shortcuts
   already had this gap; the new one inherits it. Not run: the worker's rig had no
   working input.
   Fix (hub-side, needs an exception): when a Browser view has focus, forge.py sends
   those combos to the owner page as a view-event `{event: "key", combo}`, and app.js
   maps them.

8. **Low, verified: one ask missed.** The worker brief's G1 note says: if runs cannot
   show what Emerson sees, put one short question for him at the top of the report.
   Real input in a shown window was not checked, and the fix reaches him only after a
   Forge restart, yet reports/u1-G1.md has no question. Suggested question: "After
   your next Forge restart, does the Browser show a page at once and take typing and
   clicks?"

9. **Low, verified, older than the sweep: the API accepts some odd values.**
   - `POST /api/prefs {"restore_tabs": "no"}` turns restore on, because store.py:198
     uses `bool("no")`.
   - Addresses with spaces, NUL or U+202E count as web addresses and are kept in
     sessions and bookmarks (store.py:79 `web()`).
   - A bookmark `folder` given as a dict is kept as the text "{'a': 1}".
   No 500s. Fix: in `prefs()` keep `restore_tabs` only if it is a real bool. Have
   `web()` refuse `[\x00-\x20\x7f‪-‮]`. Have `add_bookmark` keep `folder`
   only if it is a str.

## Checked and fine

- **forge.py root cause (97bfd48).** Reproduced and fixed
  (/tmp/u1/G1-critic/oldhandler.py, real offscreen WebKit). With the old
  `handle_view` logic, `owner` then `inset` then `create` gives
  `first page visible = False, host.owner = None`. With `forge.view_handler`:
  `True, 'browser'`. `tests/test_views.py`: 9/9 pass (system python, as its docstring
  says). The hub really does send `owner` from `applyChrome()` (hub/index.html:3351)
  before the frame asks for a view.
- **Worker's rig.** `/tmp/u1/G1/h/rig_noinput.txt` exists and reports 9/9.
- **Tests and tools.**
  - apps/browser `pytest -q tests`: 35 passed.
  - `black --check` clean on web_app.py, store.py, tests/test_browser.py,
    tests/check_ui.py, forge.py and tests/test_views.py.
  - pyright 0 errors on the 4 browser files. forge.py and test_views.py show 8 errors,
    all gi "unknown import symbol" or forge.py:256, which was there before. None are
    in the new code.
  - `tests/check_ui.py --port 8915`: 17/17 in my run.
- **Rest when hidden.** Hidden for 35 s, longer than the 30 s start-page clock:
  fetch 1 (the `/api/agent/next` long-poll), raf 0, interval 0, timeout 0.
- **Server killed.** The strip shows at once. Backoff confirmed (check_ui 0-10 s vs
  10-30 s). The native page view's rect moves when the strip shows (y 92 to 122.4,
  height 625 to 594.6), so the page cannot cover the strip. A typed address opens
  while the server is away. One command loop after recovery.
- **API fuzz** (28 cases on 8917, temp data): no 500s and no tracebacks in the server
  log.
  - 200 kB titles are cut to 300 characters; 5000 tabs are capped at 100.
  - Wrong-typed tabs and active values are dropped quietly.
  - An overlong URL gets a 400 as a bookmark and is not kept as a visit.
  - A bad timeout gets a 400.
  - A 200 kB query string gets uvicorn's 400, not a 500.
  - `javascript:` and `file:` addresses resolve to a search.
- **Double clicks.** A double click on the star sends one POST. Two quick "Reopen
  closed tab" clicks reopen the two tabs closed before (correct, not a double submit).
- **Clear-history confirm.** It hides the page view (view op `hide`), and the dialog
  shows (shots2/confirm-1100.png).
- **Screenshots looked at (50 % scale):**
  - shots2/offline-tabs-note-760 and -1500 (strip readable, it wraps cleanly at 760)
  - shots/menu-760 ("Reopen closed tab Ctrl+Shift+T" fits)
  - shots/start-1920
  - shots2/confirm-1100

  No clipping or overlap beyond breaks 5 and 6.
- **Commit hygiene.**
  - 97bfd48 has only the view_handler hunks in forge.py and the new test.
  - b777562 touches only apps/browser.
  - No debug prints; the prints are check_ui.py's own output. No commented-out code.
  - `git status` is clean for apps/browser.
  - check_ui.py's `tests/.ui-<pid>` sandbox is removed in a `finally` (it is left
    behind only after a SIGKILL).
- **Ctrl+Shift+T clashes.** None with the hub's key table or forge.py's workspace
  keys.
- **WIP.md.** It has the U1 section, and it says what is verified and what is not.

## Not covered

- Real pointer and keyboard input into a page in a shown window, and Emerson's own
  window. The worker could not do it either: the rig's input never reached the window.
- Rendering in WebKitGTK. All my screenshots are from Chrome.
- `/api/firefox/import` and `/api/firefox/cookies`: they would read Emerson's real
  Firefox profile.
- `/api/agent/do` with real ops driving a page. Only an unknown op and bad timeouts
  were sent.
- Power: a video in a hidden or background view. This is the worker's "measure this"
  item.
