# U1 sweep, group G12 critic: Dossier and Foresight
date: 2026-10-08 · for: Claude · critic for Rei (relay-77-work), commits 4416aa7 (Dossier) and 6f78d95 (Foresight)

Rig: `/tmp/u1/G12-critic/` (`serve.sh` = the worker's serve.sh moved to Dossier
9025, Foresight 9026, Jan pointed at dead port 9028; own copies of the library
`dossier-data/` and of Foresight's data as `ForesightData/` *beside* the library,
so the new "beside Dossier" root was exercised live; `probe.py`/`probe2.py` API
breakers with output in `probe.out`; `c.py` shots/idle; `down.py`; `back.py`;
shots in `shots/`). Both servers stopped by PID at the end, no Chrome left.

## Breaks

1. **Dossier "Get new info" still polls every 1.5 s while hidden** (medium,
   **verified**). `apps/dossier/static/app.js:516-519`: the
   `do { await sleep(1500); api("/api/history") } while (h.running)` loop after
   "Get new info" never goes through ForgeIdle, and a five-year news fetch runs
   for minutes. Repro: `c.py idle dos "<open #/subject/germany, click Get new info>" fake-newinfo.js`
   (fetch faked so nothing real runs): hidden 10 s = **6 timer callbacks**, each
   followed by an `/api/history` read. Also, if the server drops mid-loop, the
   `catch` shows a raw "Failed to fetch" alert and the loop ends for good
   (suspected, from the code). Fix: run it through the same `watch("historyWatch", ...)`
   / `ForgeIdle.poll(..., { backoff: 2, maxMs: 30000 })` the history card now
   uses, finishing (flash + `openSubject`) when `running` goes false; on a
   failed read return false instead of alerting.

2. **Foresight: a failed /api/status at boot leaves the page dead, and Sweep
   then shows a JS error** (medium, **verified**). `apps/foresight/static/app.js:69-102`:
   `boot()` returns early on a status error, so `state.sweepPoll` is never made
   (no poll, no recovery; the pill stays "backend unreachable"); the new
   `state.sweepPoll.now()` at :346 and :360 then throws. Repro: `c.py js
   "http://127.0.0.1:9026/#/watch" <click #sweep-go> fake-statusdown.js` (first
   `/api/status` rejected, sweep POST faked): result `poll: "null"`, dialog
   **"Cannot read properties of null (reading 'now')"** although the sweep
   started. Before the commit the same click called `pollSweep()` and worked.
   Fix: create the poll at the top of `boot()` (or before the status read), use
   `state.sweepPoll?.now()`, and retry `boot()` with a ForgeIdle poll (backoff)
   until status answers. Dossier's `boot()` (app.js:84-91) has the same
   no-retry shape, pre-existing (suspected impact: an app opened while its
   backend restarts stays "backend unreachable" until reload).

3. **Foresight tests write into the real data folder** (medium, **verified**).
   With the new `dossier_link.chosen()` reading the real
   `~/.config/forge-dossier/location.json`, `store.data_root()` in the test
   process now resolves to `~/AN3-backup/ForesightData` and `_usable()` creates
   and deletes a `.write-probe-*` file there on every `pytest` run (before, it
   probed `~/ForesightData-local`). Repro: point `DOSSIER_LOCATION_FILE` at a
   temp library with a `ForesightData/` beside it, `touch -d 2020-01-01` that
   folder, run `pytest -q tests`: its mtime becomes now; per file, the culprits
   are `tests/test_economic_signals.py` and `tests/test_u1_robustness.py`.
   (`~/AN3-backup/ForesightData` mtime is 01:35:20 today, after the commit; my
   first plain test run did this too.) Only a probe file, nothing else written.
   Fix: an autouse fixture in `tests/conftest.py` that points
   `dossier_link.DOSSIER_CHOICE`, `store.USB_ROOT`, `store.LOCAL_ROOT` at
   `tmp_path` and resets `store._resolved`.

4. **Foresight: no length cap on slugs; a long unbroken log line pushes the
   Signals view sideways at 760/1100** (low, **verified**). `store.check_slug`
   (`apps/foresight/store.py:164`) accepts any length: `POST /api/sweep
   {"subjects":[{"slug":"x"*200000}]}` answered `200 started`, sent that title
   to the pageviews source, and filled the sweep log so `GET /api/sweep` became
   1 MB (re-read every 8 s while shown); `POST /api/plans {"slug": <200 kB>,
   "tier":"rules"}` is a **500** (`OSError: File name too long` in
   `plans.learn`, foresight.log). With that log, `#view-watch` scrolls
   sideways (scrollWidth 1,384,782 at 760 and 1100), because the
   `@media (max-width:1100px)` rule (`app.css:66`) resets `.split` to `1fr`
   (min-content) and `.joblog` (`app.css:141`) has no `overflow-wrap`. A long
   URL in a real error line would do the same on a smaller scale. Fix:
   `check_slug` rejects `len(slug) > 200` (Dossier's `subject_dir` too);
   `grid-template-columns: minmax(0,1fr)` in the media query and
   `overflow-wrap: anywhere` on `.joblog`.

5. **Rapid clicks send repeated POSTs** (low, **verified** on the page side,
   backend effect reasoned). Triple-click with all POSTs faked (600 ms
   latency, `dbl.js` + `fake-post.js`): Dossier `#q-deepen` 3x
   `/api/queue/deepen`, `#history-start` 3x, `#q-start`/`#q-pause` 3x;
   Foresight `#plan-score` 3x. The one that matters: `add_deep_for_held`
   skips jobs already queued and keeps going, so three clicks queue **75 deep
   dives instead of 25** (`apps/dossier/static/app.js:1195`, `jobqueue.py:361`).
   History-start is safe (backend 409). Fix: disable the button while its
   request is in flight (the pattern `#sweep-go` already uses).

6. **The worker's per-view screenshot evidence is not what it says** (low,
   **verified**). `/tmp/u1/G12/after-dos-{home,jobs,library,links}-*.png` are
   byte-identical (md5 `0b36e6ec…` at 1100), and all five
   `after-fs-*-1100.png` are identical too: `h.py` set `location.hash` to
   names that did not switch views, so only the first view was shot. I re-shot
   every view properly (below) and the "no horizontal overflow" claim holds on
   normal data, but the report should cite the new shots, not the old ones.

## Checked and fine

- Tests: Dossier 318 passed, Foresight 123 passed; `black --check` and
  `pyright --pythonpath ./.venv/bin/python` (0 errors) on all 8 touched .py
  files; `node --check` both app.js. No debug prints, no commented-out code;
  `git status` shows nothing left in either app; each commit carries only its
  own app's files.
- Path safety (scratch servers): Dossier GET/DELETE `/api/subject/%2E%2E`,
  `%2E`, `..%5C..`, `a%00b`, unicode, 5 kB slug, `/image/`, `/tour`, `/notes`,
  `/new-info` on `..` all 404; library intact (56 subject folders, delete of
  `Germany` refused). `slugify` is idempotent on all 2,450 real folder names
  (read-only listing) and on odd names. Foresight `/api/subject`, `/api/plans`,
  `/api/plans/learn` with `..`, `a/b`, `..\x`, NUL: 404; `DELETE /api/plans/%2E%2E` 404.
- Wrong types: Dossier recipe/deepen `limit`, briefing `days`/`kind`, watch
  `every_hours`/`per_sweep`, history `limit` with "abc", [], {}, true, "1e400",
  "nan": all 400; huge numbers clamp (168, 1). Foresight sweep `sources` as a
  string or ints, `limit`/`days` bad, `subjects` as a string, strings, `{}`,
  `{"slug":5}`, `..`, `a/b`: all 400 with nothing started; non-object bodies
  422. 200 kB + unicode notes save and reload.
- Foresight reads the chosen library: on the rig, status said "Beside the
  Dossier library you chose: …/ForesightData" and "Dossier · 2450 subjects".
  Real data check (read-only): `~/ForesightData-local` holds only `trump` and
  `gaza-war`, `~/AN3-backup/ForesightData` the 486 signal folders + plans; the
  worker's assumption holds.
- Rest when hidden: Dossier with the queue faked running, hidden 10 s = 0
  fetch/0 timer, resumes when shown; Foresight idle hidden 0/0; Foresight with
  a sweep faked running, hidden = 1 leftover timer, no fetch. (The "back 0
  fetches" in both my and the worker's Foresight idle run is a counter-reset
  artifact: `back.py` shows the poll fires at the instant of showing, 13.1 s,
  then every 8 s.)
- Server down: Foresight 1 fetch in 0-10 s, 1 in 10-30 s, recovered 21.1 s
  after restart; Dossier (queue faked) 1 and 2, recovered 26.1 s; the summary
  line says the server is not answering; no page errors.
- Looks: every view (Dossier world, library, subject/germany, links, watch,
  jobs; Foresight ask, findings, plans, signals, sources) at 760/1100/1500/1920:
  no document overflow and no unclipped element past the edge on normal data;
  looked at the 760 and 1500 contact sheets: top bar wraps cleanly, no overlap,
  empty states present ("Name a subject to see what it connects to").

## Not covered

- Inside the real Forge window (WebKitGTK); scrollbar styling only seen in Chrome.
- Any route that makes Jan generate (ask, ask-aloud, tour, model tiers) and real
  sweeps/queue runs (network); valid-limit queue/deepen/history starts.
- The worker's queue-watcher end-of-job path with a real job finishing.
