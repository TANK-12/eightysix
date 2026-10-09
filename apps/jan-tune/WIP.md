## U1 sweep (2026-10-08, Relay task 74; Koharu, Relay task 85)

Changed:
- Page: the Advanced panel was always shown, whatever the toggle said (its
  `display: grid` beat the `hidden` attribute); now `[hidden]` always hides.
- Page rests and backs off: the status poll returns false while the server is
  away and while nothing is running anywhere, so `ForgeIdle.poll` stretches
  3 s up to 30 s (`{ backoff: 2, maxMs: 30000 }`); Run, Stop and coming back
  into view poll at once. A calm "server is not answering" line shows while
  it is down and goes away by itself; models load again if the first load failed.
- Page robustness: Run, Stop and Apply send one request at a time (a double
  click no longer posts twice); network errors and 422 lists read as plain
  text ("repeats: too big", not `[object Object]`); repeats and pause are
  clamped before sending; no models gives a plain message and a disabled Run;
  a model with no results gets a "Not tuned yet" hint.
- Looks: thin themed scrollbars (incl. `::-webkit-scrollbar`), the progress
  bar moves by transform (250 ms) instead of width, sections fade in, reduced
  motion honoured.
- API (`web_app.py`): `/api/run` checks repeats 1-10, pause 0-600 s, model id
  length; knob names and values must be this model's own (they become
  llama-server flags), else 400; model ids with `/` or a leading dot get 404
  and `/api/status` never reads outside `data/results`.
- New `tests/test_web_app.py` (18 cases, a fake Tuner: no real run starts).

### Critic follow-up (same day)
- The "Written to model.yml" note after Apply was wiped by the next status
  poll; it is kept per model now (browser check, Apply stubbed, poll forced).
- `/api/run` with a knob named with an empty list again means "that knob, all
  its values" (the sweep had turned it into "every knob"); test added, 32 pass.

Verified: pytest 31 passed. black + pyright 0 errors on web_app.py and the new
test. Headless Chrome on a scratch copy (port 9001, temp data dir): shots at
760/1100/1500/1920 looked at (`/tmp/u1/G10/shots/after-jt-*`); Advanced
hidden until ticked; hidden 10 s = 0 fetches/timers/rAF, 1 fetch on coming
back; server killed: 3 fetches in 0-10 s, 1 in 10-30 s (was 3 and 7), the
offline line shows and clears by itself after restart; triple click on Run
(fetch stubbed) = 1 request.
Not verified: a real tuning run (not allowed in this sweep). Page changes
reach Forge on the next reload; `web_app.py` on the next Forge restart.

## 2026-09-27 (session S12): fixed "jan tune app is broken"

Real cause: `apps/jan-tune/forge_app.json` and `apps/calendar/forge_app.json`
both claimed port 8453. forge.py treats a port that's already answering as an
always-on backend it shouldn't start its own server for (see its docstring
around `port_open`), so whichever of the two loaded second in the sidebar got
its window pointed at the *other* app's backend. `outputs/calendar.log` shows
this happening live: repeated `GET /api/status?model=...` (jan-tune's own
polling call) hitting calendar's backend and 404ing, because calendar has no
such route. From the user's side, opening Jan Tune would show Calendar's page
or garbage API errors depending on load order.

Fix: moved jan-tune to port 8461 (first free port after the highest
registered app port, 8460). Updated `forge_app.json` and the port mentioned in
`README.md`. Did not touch calendar's port — its code, tests and forge-log all
reference 8453 as its own identity in several places, so moving jan-tune was
the smaller, safer change. Did not touch forge.py (out of scope for this
session; it behaved as designed, the manifests were wrong).

Added `tests/test_manifest.py` (2 new tests) that fail if jan-tune's port ever
collides with another app's, or if any two apps in `apps/*/forge_app.json`
share a port — this is the regression guard for the exact bug found here.

### Verified
- `.venv/bin/python -m pytest -q tests`: **13 passed** (11 existing + 2 new).
- Test copy started standalone on a scratch port (not 8453/8461, a random
  free port via safe-shell): `/api/models` and `/api/status` returned real
  JSON (model list, `{"running": false, "running_model": null}`), no errors
  in the uvicorn log.
- Headless Chrome screenshot of the running page: renders correctly, model
  dropdown populated, controls visible, no console-visible breakage.
- black: `tests/test_manifest.py` unchanged (already clean).
- pyright (`--pythonpath .venv/bin/python`): 0 errors on `tests/test_manifest.py`.
- Caution for future sessions: do not run `black` on `forge_app.json` — it is
  JSON, not Python, and black corrupted it (added a trailing comma, invalid
  JSON) when run against it here; it was caught and fixed before this session
  ended, but only run black on `.py` files.
- Scratch server stopped by saved PID; its port confirmed free afterward.

# Jan Tune: current state (2026-09-24, session 54)

Asked by Emerson: "a series of automated tests I can launch from Forge. I can
choose the model, it auto-scans, tries different common settings at set
intervals, runs many tests and finds the right settings for each model for
the fastest token generation. Do the same yourself for the 4B now. Don't mess
with the KV cache (at least 8, better answers); context limits are mine or
the apps' to set." Plan: ~/.claude/plans/optimized-squishing-feigenbaum.md.

Reading of "set intervals": both the stepped values tried for each setting
and a cool-down pause between tests (default 10 s). Scheduled repeat runs
were not built; ask Emerson if he meant that.

## Verified
- tests/test_tune.py: 11 passed with fake timings: model scan, GGUF layer
  and expert read, the search and its tie-break, KV cache and ctx never varied,
  apply keeps comments and other keys, waiting while Jan is busy, resume after
  a stop, board claim released and note posted.
- black and pyright clean (tune.py, web_app.py, tests).
- Real 4B run: see "4B result" below.

## Not verified
- The page inside the Forge window (appears after a Forge restart).
- The page's buttons were not clicked; the API behind them has no
  test file of its own (the logic lives in tune.py, which is tested).

## 4B result (real run, 2026-09-24, Q4_K_M file, q8_0 KV, ctx 20000)
| setup | gen tok/s | prompt tok/s |
|---|---|---|
| baseline: 16 iGPU layers, batch 1024, ubatch 512, 4 threads | 3.53 | 45.1 |
| 0 layers | 5.05 | 43.7 |
| 8 layers | 5.78 | 80.0 |
| 24 layers | 7.13 | 83.3 |
| 32 layers (all) | **7.21** | 82.3 |
| 24, batch 512 | 7.07 | 83.5 |
| 24, batch 2048 | 7.03 | 83.5 |
| 24, b512, ubatch 128 / 256 | 7.13 / 7.17 | 75.4 / 80.7 |
| threads 6 / 8 (Jan-wide, report only) | 7.20 / 7.19 | 83.6 |

Applied 2026-09-25 by hand at Emerson's word ("just change the settings"): n_gpu_layers 32 (batch 1024, ubatch 512 unchanged), Jan restarted, preset shows n-gpu-layers = 32. Backup of the old model.yml in data/backups/.

**Bug found by this run (fix first):** the 3% tie-break chains. 32 layers
(7.21) lost to 24 (7.13) on prompt speed, then batch 512 (7.07) beat 7.13 the
same way, so the reported "best" (24 / b512, 7.07) is slower than 32 layers.
Fix: compare a challenger against the best *generation* seen so far, not just
the current holder, or drop the tie-break to 1%. Add a test for the chain.
**Suspect:** the baseline (16 layers, 3.53) is slower than 8 layers (5.78),
which makes no sense; it was the first test, likely skewed while Jan unloaded
its own 4B. Re-measure the baseline last, or add a warm-up test.
**Recommendation for Emerson:** all 32 layers on the iGPU (7.21 gen, twice
the current 16-layer setting's 3.53), batch/ubatch 512. Apply via
`tune.apply` or the page after the fix, then restart Jan when it is idle.

## Improve next
1. Test the web API (run/stop/apply) with TestClient and a fake Tuner.
2. A second pass around the winner (e.g. layers 12, 14, 18, 20 if 16 won).
3. Tune all models in one queue, overnight, respecting the usage of Jan.
