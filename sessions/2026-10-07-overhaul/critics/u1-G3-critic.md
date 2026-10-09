# U1 critic: group G3 (Files, Comix)
date: 2026-10-08 · for: Claude

Critic for commits e1207cc (Files) and 7e495db (Comix). Scratch copies on
8935 (files) / 8936 (comix) with copied sandbox data in `/tmp/u1/G3-critic/`
(`srv.sh`, `fuzz.py`, `critic.py`, `stale.py`, outputs `files.out`,
`comix.out`, shots in `shots/`). Both servers were stopped by PID; no Chrome left.

## Breaks

1. **Files: thumbnails and previews stay broken after a backend restart** (medium, **verified**).
   `apps/files/static/app.js:95`: `go()` sets `online = true` directly, so the
   drive poll's `setOnline(true)` (`:954` area) never calls `refresh()`. The token
   is only renewed by that poll. Repro (`stale.py`): open Pictures, SIGKILL the
   server, wait 25 s, restart, open a folder of 7 PNGs that has not been visited.
   Result: `{"imgs":7,"fallback":7}` (every thumbnail is the fallback icon, because
   `?t=` is stale). After the poll ran 32 s later the token had changed but the
   result was still `{"imgs":7,"fallback":7}`, and `rawUrl` previews are hit the same way.
   It was worse before the sweep, but the "refreshes by itself" claim only holds
   if no folder is clicked first.
   Fix: on the first successful `go()` after being offline, call `startSession()`
   to get the new token before `render()`. Or make the poll re-render when
   `S.token` changes.
2. **Files: a vanished job takes 61 s to be reported lost** (low, **verified**).
   `app.js:563`: a 404 from `/api/jobs/<id>` is counted as silence. Repro: stub
   `api('/api/transfer')` to return a running job id "ghost" against a live server.
   Saw "Lost track…" only after 61.1 s, with a frozen progress bar the whole time.
   Fix: treat a 404 as lost at once, and keep backoff only for network errors.
3. **Files and Comix: job watchers poll while hidden** (low, **verified** for Files).
   With the ghost job running and the hub hidden for 10 s, Files made 2 fetches.
   Comix `track()` (`apps/comix/static/app.js:99`) wraps the shared `pollJob`. That
   keeps a fixed 1.5 s / 3 s `setInterval` while hidden and while the server is
   down, so the WIP line "a job that vanishes is reported as lost instead of
   polling forever" only holds once the server answers again (that part is
   **suspected**, from reading the code). The worker already flagged that the fix belongs in shared.
4. **Comix: raw browser error text** (low, **verified**). Clicking a series card
   with the server down gives the toast "Could not open that series: Failed to
   fetch". `api()` at `apps/comix/static/app.js:15` doesn't wrap fetch errors the
   way Files does. Fix: catch them and throw "Comix isn't answering…".
5. **Comix: 500 on oversized ids** (low, **verified**). `GET /api/series/99999999999999999999999`,
   `POST /api/series/<huge>/choice`, `POST /api/chapters/<huge>/want` and
   `GET /api/read/<huge>` all return 500 (`OverflowError: Python int too large to
   convert to SQLite INTEGER` in the log). The new 404 guards don't cover this.
   Fix: give the path params `Path(ge=1, le=2**63-1)`, or catch OverflowError in store lookups.
6. **Comix: a second "Check for new chapters" can start** (low, **suspected**).
   `app.js:271` disables only the button that was clicked. Get/Skip calls
   `showSeries()`, which redraws the detail with a fresh, enabled Check button
   while the first check is still running. Fix: keep a per-series "checking" flag.
7. **Comix: settings take any text as a folder** (low, **verified**, pre-existing).
   `download_dir` accepts `"\u0000bad"` and `{"a":1}` (saved as `"{'a': 1}"`), and
   `library_url` accepts 200 kB, all with 200 (`comix/settings.py`, the else branch).
   Fix: reject NUL and non-strings, and cap the length.
8. **Comix: `DELETE /api/series/999999` returns 200 `{"ok":true}`** (low, **verified**).
   This doesn't match the new 404s on choice and want.

## Checked and fine
- Both pytest suites: comix 36 passed, files 40 passed. black --check and
  pyright are clean (0 errors) on the touched .py files, and `node --check` is ok on both app.js.
- Commit hygiene: the commits contain only `apps/files` and `apps/comix` paths, and
  there are no debug prints or commented-out code. The only untracked file is
  `apps/files/tests/last_ui.png` (noted by the worker).
- Rest when hidden: with the hub hidden while the server was down, both apps made 0 fetches, timers and rAF in 10 s.
- Break 6: Files made 1 fetch in 0-10 s and 1 in 10-30 s, and the chip showed.
  Comix made 2 then 1, and the bar showed. Comix recovered 3.7 s after the restart with 6 cards.
- Comix: the filter matches unicode (日本), "zzz" gives the empty state, three
  quick `readChapter` calls end on the last one, and a blank number field in settings
  saves without error. There were no page errors in either app.
- Files: a 2501-item folder (with a 200-byte unicode name) drew in 0.3 s. API
  fuzzing (NUL, unicode, 20 kB query, wrong types, paths outside the roots) gave
  only 4xx and no tracebacks.
- Screenshots at 760/1100/1500/1920 (50 % scale) of the Files picture and long-list
  views and the Comix library, detail, settings and read views: no clipping or
  overlap. At 760 the headers wrap to a second row cleanly.
- Note on the worker's evidence: "loaded: False" in `g3check.out` comes from the
  harness, not the app. `p.wait` on a DOM node returns `{}`, which is falsy in Python.

## Not covered
- Real Forge window (WebKitGTK), real comix.to downloads, running `check_ui.py` (it picks a random port).
