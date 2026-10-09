# U1 critic: group G16 (Media, MediaForge)
date: 2026-10-08 · for: Claude · critic for Relay task 90 (commits 2fc302e, b6b51ba)

Scratch servers: Media on 9065 (`FORGE_MEDIA_DATA=/tmp/u1/G16-critic/data/media`),
MediaForge on 9066 (`HOME=/tmp/u1/G16-critic/home`), started by
`/tmp/u1/G16-critic/srv.sh`, both stopped by PID at the end. Browser checks:
`/tmp/u1/G16-critic/check.py` and `down.py` (cdp_driver `chrome_page()`),
outputs in `m.out` / `mf.out`, screenshots in `/tmp/u1/G16-critic/shots/`.
The worker's servers on 9060/9061 were left alone.

## Breaks

### 1. Duplicate Slayer thumbnails are a 500 once a Storage duplicate scan has run (medium-high, **verified**)
- Where: `apps/mediaforge/web_app.py:1033-1038` (`dedupe_thumbnail`, new in b6b51ba).
- Cause: the check walks every job and calls `(job.result or {}).get(...)`.
  `/api/storage/duplicates` stores a **list** of groups in `job.result`
  (`web_app.py:402-412`). Once that list is non-empty, `.get` raises
  `AttributeError: 'list' object has no attribute 'get'` for every thumbnail
  request until the server restarts, so the Duplicate Slayer review shows
  no page images at all. Before the commit the route did not look at jobs.
- Repro (scratch HOME, two identical 1.5 MB files in `/tmp/u1/G16-critic/dup`):
  ```
  POST /api/storage/scan {"root":"/tmp/u1/G16-critic/dup"}    -> job done
  POST /api/storage/duplicates?min_bytes=1000                 -> job done
  GET  /api/storage/duplicates/<id>/result -> 200 {"groups":[[".../a.bin",".../b.bin"]]}
  GET  /api/dedupe/thumbnail?path=/etc/passwd                 -> 500 Internal Server Error
  GET  /api/dedupe/thumbnail?path=/tmp/u1/G16-critic/dup/a.bin -> 500
  ```
  Log: `web_app.py, line 1036, in <genexpr> ... AttributeError: 'list' object has no attribute 'get'`.
- Fix: only look at dict results, e.g.
  `r = getattr(job, "result", None); if isinstance(r, dict) and r.get("needs_review"): ...`
  and add a test that puts a job with `result=[["a","b"]]` in `state.jobs`
  next to a pending review and expects the review page to still be served.
  The same `.get` on a list sits in `dedupe_finish` (`web_app.py:1051`,
  pre-existing; a storage-duplicates job id there gives a 500).

### 2. Validation errors show as "[object Object]" (low-medium, **verified**)
- Where: Media `apps/media/static/app.js:18` (`api()` throws `new Error(detail)`);
  MediaForge through the shared `errText()` (`shared/forge.js:40-47`), which
  returns pydantic's `detail` array as is.
- Repro A (Media, Settings tab): put 51 lines in Library folders, press Save
  -> note reads `Not saved: [object Object]` (the backend's new
  `max_length=50` gives a pydantic 422 list).
- Repro B (MediaForge, Storage Tools): clear Min MB, press Search -> toast
  `[object Object]` (`min_mb=` is a pydantic float_parsing 422). Any form that
  sends NaN/empty numbers (Upscale scale, etc.) does the same.
- Fix: in Media's `api()`, `if (Array.isArray(d)) d = d.map((x) => x.msg).join("; ")`.
  For MediaForge, the same in `errText()`; that is `shared/`, so either a
  local wrapper in `index.html` or a shared/ recommendation in the report.

### 3. Media refuses more than 50 library folders (low, **verified**)
- Where: `apps/media/web_app.py` `Settings.folders = Field(None, max_length=50)`.
- A save that worked before the sweep is now refused (and with break 2, the
  reason is unreadable). Repro: POST `/api/settings` with 51 folders -> 422
  `List should have at most 50 items`. A cap is fine, 50 is low for a user
  with many drives; suggest 500, and a readable message.

### 4. Probe still invents tracks for a file that is not a video (low, **verified**, pre-existing)
- Where: `apps/mediaforge/web_app.py:521-530`.
- `GET /api/subtitles/probe?path=/etc/passwd` -> 200
  `{"duration":0.0,"audio":[{"index":0,"label":"0 -- (none)"}],"subtitle":[...]}`.
  The sweep fixed this for a missing file only; the UI still toasts
  "1 audio / 1 subtitle tracks, 0s" for a non-media file. Fix: when ffprobe
  finds no streams, answer 422 "no audio or subtitle tracks in that file".

### 5. Start-up banner blames the network for any failed boot step (low, **suspected**)
- Where: `apps/mediaforge/static/index.html` `boot()` (end of file).
- Any of the four steps (settings, encoders, history, models) failing with an
  HTTP error, with the server up, shows "Can't reach the MediaForge server"
  and keeps retrying every 30 s while visible. I found no route that fails
  that way today (`list_manifests` skips bad files), so this is only a
  wording/robustness note: show the step's own error when `res.status` is set.

### 6. A test leaves a job in the live state (low, **suspected**)
- Where: `apps/mediaforge/tests/test_u1_robustness.py`
  `test_dedupe_thumbnail_serves_a_page_of_a_pending_review` adds to
  `web_app.state.jobs` without removing it; later tests in the same process
  see it. Use `monkeypatch.setitem(web_app.state.jobs, job.id, job)`.

## Checked and fine
- Tests: Media `pytest -q tests` 34 passed; MediaForge 19 passed. `black --check`
  clean on the touched .py files of both. pyright: Media 0 errors; MediaForge
  40 errors now vs 54 on `b6b51ba^` (same files exported with `git archive`),
  so none new. Real `~/MediaForgeData/settings.json` untouched by the tests
  (mtime 2026-09-06) and all its value types pass the new `value_problem`, so
  none of Emerson's saved settings would be dropped on load.
- Commit hygiene: both commits touch only their own app; `git status` shows
  nothing left in `apps/media` or `apps/mediaforge`; no stray prints, temp
  files or commented-out code seen in the diffs.
- Media in headless Chrome: 0 fetch/rAF/timer/interval in 5 s visible, 10 s
  hub-hidden and 10 s document-hidden. Five Rescan clicks -> one `/api/library`.
  Search for `<img src=x onerror=...>` renders as text in the no-match note.
  Server killed after load: Rescan -> toast "Could not read the library: the
  Media server is not answering", list kept (31 rows), 0 fetches while idle.
  API down at start: calm note with Try again, 2 fetches in 0-10 s, 2 in
  10-30 s, 0 while hidden, filled itself after the restart.
- MediaForge: 0 work in 5 s visible and 10 s hub-hidden; three Save clicks ->
  one POST; three Name check clicks -> one job; 200 kB `jan_base` -> toast
  "jan_base is too long"; `{"values":{"jan_base":null}}`, `"crf":"22"`,
  `min_mb=nan/inf` all 4xx; `/api/subtitles/probe` of a missing or NUL path
  -> 404; `/api/dedupe/thumbnail?path=/etc/passwd` -> 404 (until break 1).
  API failing at start (fetch to /api rejected in the page): banner shown,
  retries stretch (2 timer ticks in 0-10 s and 2 in 10-30 s), banner clears
  by itself once the API answers.
- Media API: volume 50.5 / folders "abc" / 51 folders / blank or NUL
  download folder / `limit` 0 / `kind` "exe" / `urls` as a string all 4xx;
  `/api/file` with NUL, `/etc/passwd` or `lib/../../etc/passwd` -> 404;
  `open-firefox` with `file://` -> 400.
- Screenshots (50 % scale) at 760, 1100, 1500, 1920: Media library, download,
  settings; MediaForge all ten tabs (`shots/sheet-mf-*.png`, `sheet-media.png`).
  No sideways overflow (scrollWidth == innerWidth at every width), tabs wrap
  to their own row at 760, Media's panel scrollbar sits at the window edge,
  no contrast problems seen.

## Not covered
- The real Forge window (WebKitGTK), Media's YouTube/Crunchyroll views,
  playback, any yt-dlp run, a real Duplicate Slayer review with a PDF/CBZ in
  the browser (break 1 shown through the API only), Jan routes (not fired).
- MediaForge with its server killed after load was not re-run (the worker's
  report covers it); my "down at start" check rejected `/api` fetches in the
  page, since the page itself cannot load from a stopped server.
