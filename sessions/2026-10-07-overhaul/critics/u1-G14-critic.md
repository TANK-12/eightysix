# U1 sweep critic, group G14: PanelForge and PrintForge
date: 2026-10-08 · for: Claude · written by the G14 critic (launched by relay-88-work)

Commits checked: 08649f9 (PrintForge as found), 0d16caa (PrintForge sweep),
a81eda5 (PanelForge sweep). Scratch copies ran on 9045 (PanelForge, data
copied to `/tmp/u1/G14-critic/pfdata`) and 9046 (PrintForge, temp config and
cache under `/tmp/u1/G14-critic/pf/`). Both are stopped by process group.
No job routes were sent `null`/`{}` or any valid body, no job was started,
and Jan was not touched. Scripts and shots: `/tmp/u1/G14-critic/`.

## Breaks

### 1. PanelForge: Infinity or NaN inside a body is stored, then the document is a 500 for good (medium, verified)
- Where: `apps/panelforge/panelforge/store.py:38` (`json.dump` writes
  `Infinity`/`NaN` because `allow_nan` defaults to true). It is reached from every
  free-form `dict` body: `put_script` (`panelforge/api/audio.py:181`),
  `put_cast` (`panelforge/api/scene.py:252`), and likewise `put_panels`, `put_bubbles` and `put_timeline`.
  The sweep's `RequestValidationError` handler (`web_app.py:38`) only catches a
  *top-level* `1e999`, because a nested one is valid for `doc: dict`.
- Repro (scratch copy, chapter bad-born-blood/0001):
  `PUT /api/chapters/bad-born-blood/0001/script` body `{"lines":[],"x":1e999}` → **500**;
  then `GET .../script` → **500**, and it stays 500 until the file is edited by hand.
  The same happens with `NaN`. `PUT /api/series/bad-born-blood/cast` body
  `{"cast":[],"z":1e999}` → 500, then `GET /api/series/bad-born-blood/cast` → 500.
  (Scratch files were restored afterwards.)
- The report says "a body of 1e999 on any body route was a 500 ... now 422".
  That holds only when the whole body is the number.
- Fix: refuse non-finite numbers before anything is stored. Do it either in
  `store.write` (`json.dump(..., allow_nan=False)`, raising a `ValueError` that a
  handler maps to 422), or with one body check in `web_app.py`: a middleware or
  dependency that parses JSON bodies with
  `json.loads(raw, parse_constant=reject)` and answers 422. Add tests for nested
  `1e999` and `NaN` on script and cast, and for the GET after.

### 2. PrintForge: the 1e999/NaN 500 that was fixed in PanelForge is still there (medium, verified)
- Where: `apps/printforge/web_app.py:30` has no `RequestValidationError`
  handler. Affected routes: `post_settings` (:55) and `open_folder` (:92).
- Repro: `POST /api/settings` with body `1e999`, `{"values":1e999}` or
  `{"values":NaN}` → **500**. `POST /api/open-folder` with `1e999`,
  `{"path":1e999}` or `{"path":NaN}` → **500** (FastAPI cannot echo the
  non-finite input as JSON). Nested `{"values":{"light":1e999}}` is correctly a 422.
- Fix: the same handler as PanelForge's `_bad_request`. That also fits the
  report's own `shared/forge_errors.install(app)` recommendation. Add a test.

### 3. PrintForge: one symlink in a root turns the whole library into a 500 (medium, verified)
- Where: `apps/printforge/library.py:185-190` (`scan`). `(d / name).resolve()`
  follows the link, and then `p.relative_to(root)` raises `ValueError` when the
  target is outside the root. A dangling link fails the same way, and one whose
  target is inside the root but missing would fail at `p.stat()`. Nothing is
  caught.
- Repro: `ln -s /tmp/u1/G14-critic/outside/out.stl pf/roots/demo/link_out.stl`
  then `GET /api/library` → **500**
  (`ValueError: '/tmp/u1/G14-critic/outside/out.stl' is not in the subpath of
  '/tmp/u1/G14-critic/pf/roots'`). A dangling `broken.stl -> nothere.stl` gave the same 500.
  The page then shows "Could not read the library: Internal Server Error" and retries forever (see 5).
  `~/Downloads` is a likely place for such links.
- Fix: in `scan`, wrap the per-file block in `try/except (OSError, ValueError): continue`.
  Either skip links that resolve outside the root (`allowed()` would refuse them
  anyway), or list them using `d / name` without resolving. Add a test with one
  outside link and one dangling link.

### 4. PrintForge: a root like `~someone/models` is accepted, then every library and info call is a 500 (medium, verified)
- Where: the `roots` check `library.py:69` accepts any string, and
  `roots()` `library.py:142` calls `Path(r).expanduser()`, which raises
  `RuntimeError("Could not determine home directory.")` for an unknown user.
  The bad value then passes the same check on load, so it sticks.
- Repro: `POST /api/settings {"values":{"roots":["~nosuchuserxyz/models"]}}` →
  200 (saved). Then `GET /api/library` → **500** and `GET /api/info?path=<valid stl>` → **500**.
  In the page, typing that in Roots and pressing Save and rescan gives
  "Could not read the library: Internal Server Error. Trying again in 4 s."
- Fix: in the `roots` check, try `Path(r).expanduser()` and refuse the value
  ("roots must be a list of folder paths") on `RuntimeError`. Also have
  `roots()` skip an entry that cannot expand, so an old stored value cannot
  break the app. Add a test.

### 5. PrintForge: the library retry never stops, runs while hidden, and leaves "Save and rescan" disabled (medium, verified)
- Where: `apps/printforge/static/app.js:239-249` (`loadLibraryUntilItWorks`
  recurses on a plain `setTimeout`, with no visibility gate and no end) and
  `:301-306` (`once(rootsSave, ...)` awaits that loop, so the button stays
  disabled until the library loads).
- Repro (headless Chrome, `/tmp/u1/G14-critic/pf_check.py`): type
  `~nosuchuserxyz/models` in Roots and click Save and rescan. After 4 s the
  button is `disabled = true`. With the page then hidden by the hub signal for
  32 s, `/api/library` was still fetched at **2.0, 10.0, 26.0 s**, and the button was still disabled.
  A permanent 500 (breaks 3 and 4) is retried forever, and the user cannot fix
  the roots without reloading the page. A second loop also starts beside the
  first-load loop.
- Fix: run the retry through `ForgeIdle.poll(fn, 2000, {backoff: 2, maxMs: 30000})`
  and stop it on success. Make Save and rescan start (or `now()`) that one
  poller instead of awaiting it, so the button frees as soon as the save
  returns. Optionally, stop retrying on a 4xx/5xx that is not a network failure
  and say "check the folders in Settings".

### 6. PanelForge: an id of `..` reads and writes one level up, in the data root (low, verified, existed before the sweep)
- Where: `apps/panelforge/panelforge/paths.py:44-49` (`series_dir`,
  `chapter_dir` join raw path params); for example `put_series_words`,
  `panelforge/api/detect.py:212`.
- Repro: raw `PUT /api/series/%2e%2e/words` body `{"words":[]}` → 200, and it
  wrote `pfdata/glossary.json` (the data root, outside `series/`).
  `GET /api/series/%2e%2e/words` → 200. It cannot climb above the data root,
  because a slash does not match a path segment. The worker's fuzz sent `..`
  only to GETs.
- Fix: one id check, used by `series_dir`/`chapter_dir`, that refuses `.`,
  `..`, empty, NUL and over-long ids, raising a 404. That also removes the need
  for the ENAMETOOLONG special case.

### 7. PanelForge report and WIP: the lost-job timing and its reason are wrong (low, verified)
- Where: report "Assumptions", `apps/panelforge/WIP.md`, and `static/js/core.js:180`.
- What I saw: `PF.watchJob('nope-job')` fetched at **0.0, 1.6, 4.8 s** and
  gave up at 4812 ms ("the server no longer knows this job"), not "about
  2.4 s". The backoff doubles 800 → 1600 → 3200.
- The reason given ("the job files survive it") is not true. `jobs.get()`
  (`panelforge/jobs.py:118`) reads only the in-memory `_jobs` dict, so after a
  backend restart every job is a 404 at once. The behaviour (give up) is right;
  only the stated reason is wrong.
- Fix: correct the two sentences.

### 8. PrintForge at 760 px: the standalone Close app and Full screen buttons cover the bed badges (low, verified, shared chrome)
- Where: the floating buttons from the shared chrome, over the check panel at
  the bottom right; screenshot `/tmp/u1/G14-critic/shots/pf_760.png`. They sit
  on top of the "standing" badges of the last two beds.
- Only standalone (the hub hides them). Fix: give the check panel
  `padding-bottom` of about 48 px at the narrow breakpoint, or note it under shared/.

### 9. PanelForge: a job thread dies in `_save` with `TypeError: Object of type Job is not JSON serializable` (low, verified in the test run, existed before the sweep)
- Where: `panelforge/jobs.py:75-79`. `_save` catches only `OSError`, and some
  job's `result` holds a `Job` (`dict item 'result'`, tuple item 5).
- Seen as `PytestUnhandledThreadExceptionWarning` in the full pytest run, credited to
  `tests/test_detect_normalize.py::test_balloon_edge_strokes_are_removed` (it
  comes from an earlier test's job thread). The state is already set in
  memory, so the UI is fine; the job's JSON file is not written.
- Fix: catch `(OSError, TypeError, ValueError)` in `_save`, and find the job
  whose result returns a `Job` (look for a work function that returns
  `jobs.start(...)`).

## Checked and fine
- Tests: PanelForge 584 passed. PrintForge 25 passed. `black --check` was clean
  and `pyright --pythonpath ./.venv/bin/python` gave 0 errors on the touched
  .py files of both apps.
- Commit hygiene: the three commits touch only their own app paths. There are
  no caches or temp files in 08649f9, no stray debug output (the `print`s are in
  `tests/check_ui.py`'s own output), and `git status` is clean for both apps.
- PrintForge, hidden with the turntable spinning: 0 rAF, 0 timers, 0 fetches
  in 10 s; frames resume when shown (60 in 1 s headless).
- PrintForge, custom bed typed far above its max (1e5, 1e7): the range input
  clamps to 500 before `setBed`, so there is no runaway grid build.
- PrintForge API: 5000-character and NUL paths → 404, `..` escape → 404
  "outside the PrintForge folders", `/etc/passwd` → 404, a damaged STL → 422,
  an empty STL → 200 with 0 triangles, a 200 kB `roots` string → 422, bad colour
  → 422, a unicode bed name → falls back to the first bed.
- PrintForge widths 760/1100/1500/1920: no sideways scroll and no page
  errors. At 760 the check panel sits under the view (shots looked at).
- PanelForge, hidden with the jobs drawer open: 0 fetches, 0 timers, 0 rAF in 10 s.
- PanelForge, server killed: the note "The PanelForge server is not
  answering..." shows, reads well at 760 and 1920, and cleared by itself after
  restart. There were no page errors, and other tabs still render their forms.
- PanelForge, lost job: it stops after three 404s and calls `onError`.
  `watchJob` callers (render, cast, library) ignore the return value, so the
  change from a timer id to a poller breaks no caller.
- `ForgeIdle.poll` with `immediate: true`: `poller` is assigned before
  `tick` first touches it (it does so after an `await`).

## Not covered
- Any PanelForge job route with a valid body, by the safety rule. So watchJob
  was not seen on a real running job, and nested Infinity on job routes was not
  tried.
- `/api/jan/settings` (shared Jan config) and `/api/open-folder` with a valid path
  (it would open a window on Emerson's screen).
- Inside the running Forge window (WebKitGTK); real 36 MB STLs; a FIFO named
  `*.stl` in a root (suspected: `triangle_count` would block the library scan).
- PanelForge screenshots at 1100 and 1500, and rapid double clicks on its buttons.
