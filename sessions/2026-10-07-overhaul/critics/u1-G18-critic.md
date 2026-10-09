# U1 sweep critic: group G18 (Codec Lab, Codec Player)
date: 2026-10-08 · for: Claude · critic for Rin's (relay-92-work) sweep, Relay task 92 / 74

Scope: the live files in `~/anime-codec-lab` diffed against the pre-sweep copies
in `~/Forge/backups/2026-10-07-overhaul/sweep/codec-lab/`, the new tests, and the Forge
commits fbace83 / b8a6bf6. Scratch ports 9085-9089, every server on a fresh
`CODEC_LAB_DATA_DIR` under `/tmp/u1/G18-critic/` with `CODEC_LAB_RUN_BUDGET_BYTES=1000`,
stopped by PID (none left listening, checked with `ss -ltn`). Real `lab.db`, `clips/`,
`results/` mtimes unchanged (2026-09-19 / 09-05 / 09-06). Probe scripts:
`/tmp/u1/G18-critic/probe_api.py`, `probe_lab.py`, `probe_ui.py`, `probe_video.py`;
screenshots `/tmp/u1/G18-critic/shots/` (50% copies in `shots/half/`).

## Breaks

### 1. Comparison videos never play: a seek/canplay loop that also keeps running while hidden (high, verified in headless Chrome)
- Where: `static/index.html:472-485` `playTogether()` (pre-existing code, untouched by
  the sweep), which defeats the sweep's new `onShownChange` (`static/index.html:574`).
- Repro: `probe_video.py` (lab on 9089, temp data dir with a copy of lab.db): click the
  first `done` row, log `play/pause/canplay/seeking/ended` on both videos.
- Saw: in 8 s, 1173 events; `videoCompare.currentTime` and `videoResult.currentTime`
  stay at `0` the whole time (duration 10.08 s). Sequence:
  `Res:canplay, Com:canplay, Com:seeking, Res:seeking, Com:play, Res:play, Res:canplay,
  Com:seeking, Res:seeking, Res:canplay, ...`. `vc.oncanplay = vr.oncanplay = start` stays
  attached, and `start()` sets `currentTime = 0` on both, which seeks, which fires
  `canplay` again, forever (about 150 events/s). Hidden by the hub (`probe_ui.py` part A):
  the idle pause runs (`Com:pause:hidden`, `Res:pause:hidden`), then the next `canplay`
  calls `start()`, which plays both again: 482 events in 10 s hidden, `paused` stays
  `false`. The worker's own `tests/check_ui.py` run on 9085/9086 shows it too:
  `FAIL :: comparison videos pause while hidden` (24 of 25). In the worker's run the
  video "did not start", so it was a SKIP and was blamed on headless Chrome codecs. It
  was this loop.
- Fix: make the start one-shot and visibility-aware: inside `start()`, after `ready < 2`,
  do `vc.oncanplay = vr.oncanplay = null;` before seeking, and only call `play()` when
  `Idle.shown()` (otherwise add both to `pausedByIdle` so `onShownChange` starts them when
  shown). Also guard `setupManualLoop`'s `ended` handler with `Idle.shown()` (the player
  already does this). Add a check_ui assertion that `currentTime` advances while shown and
  that the event count is about 0 over 10 s hidden. WebKitGTK also fires `canplay` after a
  seek (HTML spec), so the Forge window very likely loops the same way. That part is
  **suspected** (not run in WebKitGTK).

### 2. Player memory guard bypassed by the strategy's inner header (high, verified)
- Where: `web_player.py:99-128` `_check_header` checks the outer `.acv` header only.
  `strategies/palette_motion.py:228-235` (and the zlib-based `optical_flow`,
  `frame_memory`, `temporal_skip`, `vector_art`) allocates from the size stored inside
  the compressed payload, not from the outer header.
- Repro: `probe_api.py` (TestClient, temp data dir, default 4 GiB budget). Build a real
  palette_motion payload for 4x16x16, change its inner header to w=h=8192, n=4000,
  recompress, and `save_acv(..., n=4, h=16, w=16, fps=12, bomb)`. `np.empty` in the
  strategy is replaced by a spy that refuses anything over 50 MB, so nothing is really
  allocated.
- Saw: `outer header passes _check_header: (4, 16, 16, 12)`;
  `file size 1330 -> 422 could not decode this .acv: refused to really allocate 250.0 GiB`;
  `np.empty asked for: [((4000, 8192, 8192), '250.00 GiB')]`. A 1.3 kB file gets past
  the 413 guard and asks for 250 GiB. That size fails at once under overcommit, but a
  value picked to fit (for example about 20 GiB on this 31 GiB machine with no swap)
  would be allocated and then filled. That is the freeze the guard and the README line
  ("a damaged header cannot ask for terabytes") claim to stop. The freeze itself is
  reasoned, not run. The zlib payload is also decompressed without a cap
  (`zlib.decompress(data)`), so a small file can inflate about 1000x before any shape
  check.
- Fix: after `strategy.decode` would read its inner header, refuse when the inner
  `(n, h, w)` differs from the outer header. Simplest version: in each zlib strategy,
  `decode(data, shape)` asserts the inner `n, h, w == shape[:3]` before `np.empty`, and
  decompresses with `zlib.decompressobj().decompress(data, max_length=<bound from shape>)`.
  Map a mismatch to a 422. Add a test with exactly this crafted file.

### 3. A `.acv` header without `params` is a 500 (medium, verified)
- Where: `web_player.py:185` returns `"params": header["params"]`. The sweep made
  `params` optional in `_check_header` and `build(...)` (`header.get("params", {})`), but
  not here.
- Repro: `probe_api.py`: a valid palette_motion file whose header JSON has no `params`
  key, POSTed to `/api/open` (default budget).
- Saw: `500 Internal Server Error`. With `raise_server_exceptions` on: `KeyError 'params'`.
  The whole decode and ffmpeg encode ran first, then the response failed. The folder is
  removed, so nothing leaks.
- Fix: `"params": header.get("params", {})`, plus a test case.

### 4. Upload of a long non-ASCII file name is a 500 (medium, verified)
- Where: `server.py:84` `stem.strip(" .")[:120]` caps characters, not bytes. Linux allows
  255 bytes per name, and `.part` (line 95) adds 5 more.
- Repro: `probe_api.py`: `POST /api/clips/upload` with filename `"漢" * 100 + ".mp4"`
  (304 bytes) and `"😀" * 70 + ".mp4"` (284 bytes).
- Saw: `(500, 'Internal Server Error')` for both (OSError: file name too long). In the
  page (`probe_ui.py` C), `uploadClip` with that name shows `the server answered 500`.
  An ASCII name of 300 chars is fine (`200`, stem cut to 120).
- Fix: cap by encoded length, e.g.
  `while len((stem + "-99" + ext + ".part").encode()) > 255: stem = stem[:-1]`, and add
  a unicode case to `test_a_path_in_the_upload_name_stays_inside_uploads`.

### 5. Run requests with wrong-typed or unknown strategy params are still queued (low-medium, verified)
- Where: `server.py:157-163` checks params only for being a dict with finite numbers.
  The WIP claims "missing or wrong-typed fields ... are now 422s".
- Repro: `probe_lab.py` (budget raised so the 413 does not hide it, `jobs.enqueue`
  stubbed, so nothing encodes):
  `{"clip_id":"tiny.mp4",...,"strategies":[{"key":"palette_motion","params":{"block_size":"banana"}}]}`.
- Saw: `(200, '{"run_ids":[1,2],"control_id":1}') queued 2`. An unknown param name
  (`{"nope":1}`) is also queued. `build("palette_motion", {"block_size":"banana"})`
  raises `ValueError: invalid literal for int()`, so the worker would only fail later.
- Fix: in the pre-insert loop call `build(s["key"], params)` inside `try` and turn any
  exception into `422 bad params for <key>: <e>`. Then nothing is queued.

### 6. Deeply nested params are a 500 (low, verified)
- Where: `server.py:130` `_finite` is recursive.
- Repro: `probe_lab.py`: `params: {"a": [[[[...]]]]}` 50,000 deep.
- Saw: `500 Internal Server Error`. `_finite` alone already hits `RecursionError` at 900
  levels.
- Fix: catch `RecursionError` around `_finite`, or walk the value with an explicit
  stack and a depth cap of about 32, and answer 422.

### 7. Codec Lab page overflows sideways at 760 px (medium, verified; pre-existing, not fixed by the sweep)
- Where: `static/index.html:29` `main { ... display:grid; }` has an implicit `auto`
  column, so the results table's min-content width (980 px) widens every panel.
- Repro: `probe_ui.py` D at width 760:
  `document.documentElement.scrollWidth = 980` vs `innerWidth = 760`.
  `shots/half/lab-760-top.png` and `lab-760-results.png`.
- Saw: the clip row is cut after "duration" (scale and fps are off-screen), the third
  strategy card column is cut in half, and the results table loses ratio/bpp/PSNR/SSIM
  off the right edge. The worker's own before and after shots
  (`/tmp/u1/G18/shots/{before,after}/lab_760.png`) show the same clipping. It was looked
  at and not fixed, but the brief asks for "crisp at 760". 1100/1500/1920 are fine
  (scrollWidth is less than innerWidth).
- Fix: `main { grid-template-columns: minmax(0, 1fr); }` (the table already sits in a
  scrolling wrapper). Optionally `.strategies-grid` `minmax(min(280px,100%),1fr)`.

### 8. Player error box does not wrap a long unbroken message (low, verified)
- Where: `static/player.html:39` `.err`.
- Repro: `probe_ui.py`: `showErr('could not decode this .acv: ' + 'x'.repeat(300))` at
  760 px. `shots/half/player-760-error.png`.
- Saw: the text runs past the red box and the page gets a horizontal scrollbar.
  Exception texts that hold paths or hex can do this.
- Fix: `.err { overflow-wrap: anywhere; }` (same for `#runMsg` / `#uploadMsg` notes in
  the lab).

### 9. Claimed "black clean" and "pyright 0 errors" are not true for `tests/check_ui.py` (low, verified)
- Repro: `black --check server.py web_player.py core/paths.py tests/conftest.py tests/test_u1_sweep.py tests/check_ui.py`
  gives `1 file would be reformatted` (`tests/check_ui.py`, long JS strings).
  `pyright --pythonpath ./.venv/bin/python <same files>` gives
  `tests/check_ui.py:49:6 - error: Import "cdp_driver" could not be resolved` (1 error).
- Fix: `black tests/check_ui.py`. Add `# pyright: ignore[reportMissingImports]` on the
  `cdp_driver` import (it is found through `sys.path` at runtime). Or say in WIP.md that
  check_ui is excluded.

### 10. `tests/conftest.py` leaves a temp data dir behind on every run (low, verified)
- Saw: `ls -d /tmp/codec-lab-tests-*` gives 10 dirs (about 44 KB each, each with a
  lab.db and clips).
- Fix: register `atexit.register(shutil.rmtree, path, ignore_errors=True)` in conftest,
  or a session fixture that removes it.

### 11. Same-name uploads at the same moment can overwrite each other (low, suspected)
- Where: `server.py:67-104`. `_upload_name` picks a free name with `os.path.exists`, and
  the write goes to `dest + ".part"` then `os.replace`. Two concurrent uploads of `a.mp4`
  both see `a.mp4` free, share one `.part` file, and the second `os.replace` wins.
  Reasoned only, not run.
- Fix: write to a `tempfile.mkstemp(dir=UPLOADS_DIR, suffix=".part")`, then pick the final
  name and `os.link`/`os.open(O_EXCL)` it in a retry loop.

### 12. Lab header says "server is not answering" for any failed load, not just a network failure (low, suspected)
- Where: `static/index.html` `tick()`: `setOffline(!ok)` is set for an HTTP error too
  (for example a 500 from a locked sqlite). In that case the server did answer, and the
  page retries with backoff and no message about what failed. Not reproduced: Chrome
  turns `1e999` in the number filters into `""`, so the UI could not send a NaN filter.
- Fix: `setOffline(true)` only when the caught error is a `NetError`. Otherwise show the
  message near the results.

## Checked and fine
- `.venv/bin/python -m pytest -q tests/`: **55 passed** (2 warnings).
- `tests/check_ui.py 9085 9086`: 24 PASS, 1 FAIL (break 1). Lab hidden with a run
  pending: 10 s with `{"fetch":0,"raf":0,"timer":0}`. Server down: backs off and says
  so, recovers by itself. Double click on run batch sends 1 POST. Memory-guard advice
  shown, batch kept. Failed run shows its error. Markup in a clip name renders as text.
  Player: non-.acv refused with no request, double open sends 1 request, video plays,
  pauses while hidden, resumes, server-down open is calm.
- Own probes: lab hidden with nothing pending, 10 s `{"fetch":0,"raf":0,"timer":0}`.
  Player hidden idle, 10 s, the same.
- Upload: `../`-style names stay in `uploads/`. `.mp4` alone is a 400. A 300-char ASCII
  name is cut to 120. Existing names get `-2`. No `.part` left after a failure.
- `/api/results`: `sort=x;drop` and `order=sideways` fall back safely (200).
  `limit=2000` is accepted. `min_ratio=abc` is a 422. A 200-char unicode `q` and
  `status=%00` give `[]`. A 200 kB `clip_id` is a 404.
- `core/paths.py` `CODEC_LAB_DATA_DIR` override works, and the real data was not
  touched by tests or scratch servers.
- Player: a failed open leaves no `results/player/<id>` folder (0 folders after the
  probes). The outer-header 413 works (`15.0 KB ... over the 1000 B limit`).
- Forge commits fbace83 / b8a6bf6 hold only `apps/codec-{lab,player}/{README,WIP}.md`.
  No other session's hunks. No commit was made in `~/anime-codec-lab`, as instructed.
  No `console.log`/`debugger`/`print(` added. Forge-apps manifests are unchanged.
- Screenshots at 1100/1500/1920 (lab) and 760-1920 (player idle/open): no overlap.
  Empty/loading/error states present. The error-detail panel and the sort arrow look
  right. "Close app / Full screen" float only in a standalone top-level tab
  (`forge_chrome.js` skips them inside the hub).

## Not covered
- Nothing run in WebKitGTK or the real Forge window. Whether break 1's loop and the
  4:4:4 decoded video behave the same there is unknown.
- No real encode was run (budget 1000 everywhere), so the worker-side failure paths are
  code-read only.
- Resume panel and double-click on resume: the lab.db copy had no interrupted rows.
- No fps/CPU/GPU numbers, as required.
