# Codec Lab: work in progress

The code lives in `~/anime-codec-lab` (a git repo with no commits yet; its
first commit is Emerson's call). This file records hub-side sweeps.

## U1 sweep (2026-10-08, Relay task 74)
By Rin (relay-92-work), Relay task 92. Files changed in `~/anime-codec-lab`
(not committed there; originals in
`~/Forge/backups/2026-10-07-overhaul/sweep/codec-lab/`): `server.py`,
`core/paths.py`, `static/index.html`, `README.md`, `CLAUDE.md`; new
`tests/conftest.py`, `tests/test_u1_sweep.py`, `tests/check_ui.py`.

What changed:
- Upload: a clip name holding a path (`../../x.mp4`) was written outside
  `clips/uploads/`; now only the file name is kept, odd characters are dropped,
  and an upload never replaces an existing clip (`name-2.mp4`).
- `POST /api/runs`: missing or wrong-typed fields, NaN/Infinity, a zero fps or
  scale were 500s (or got stored); they are now 422s naming the field. A bad
  strategy in the middle of a batch used to leave the control and the first
  configs queued; every config is now checked before any row is written. A
  clip ffprobe cannot read is a 422, not a 500.
- `/api/runs/resume` with a bad `run_ids`, `/api/results` with `limit=0` or a
  NaN filter, `/api/runs/{id}/video/<anything else>` and exporting a run whose
  files are gone are now clean 4xx answers.
- `core/paths.py`: `CODEC_LAB_DATA_DIR` moves lab.db / results / clips (tests
  and scratch servers use it; unset, nothing changes).
- Page: every name from the server is escaped (a clip named with markup ran
  it). The memory guard's 413 advice was silently dropped by run batch; it is
  now shown and the batch is kept so the scale can be fixed. Upload and resume
  errors are shown. Run batch sends one request per press. The 2 s poll moved
  to `ForgeIdle.poll`: it rests while hidden and backs off 2 s to 30 s while
  the server is down, says so in the header, and recovers by itself (a failed
  first load used to leave blank panes forever). The comparison videos pause
  while hidden. Empty and loading states for clips, strategies and results;
  "-" instead of "-x" on unfinished rows; a sort arrow; a themed file button;
  thin scrollbars; a 200 ms fade on the comparison panel.
- New: clicking a failed run shows why it failed (the stored error).

Verified: `.venv/bin/python -m pytest -q tests` 55 passed (36 of the 43 new
cases fail on the original code). `tests/check_ui.py` (headless Chrome,
scratch ports 9082/9083, temp data dir) 24 PASS, 1 SKIP (the comparison videos
did not start playing in headless Chrome, so their pause-while-hidden is only
checked in code, not run). black clean; pyright 0 errors (was 11 on the
originals, all pre-existing `str = None` hints fixed). Screenshots before and
after at 760/1100/1500/1920: `/tmp/u1/G18/shots/`.

Not verified: nothing was seen in the real Forge window (WebKitGTK). The
decoded comparison video is lossless H.264 4:4:4, which `web_player.py`'s
notes say WebKitGTK cannot decode; offscreen WebKit loads no media at all, so
whether the right-hand "output" video plays in Forge is unchecked (left as
is). `static/index.html` reaches Emerson's Forge on the next page reload;
`server.py` changes only on his next Forge restart.

## U1 critic follow-up (2026-10-08, Relay task 92)
By Kaito (relay-92-work). A fresh critic (report:
`sessions/2026-10-07-overhaul/critics/u1-G18-critic.md`) found 10 breaks and
2 suspected ones; all 12 are fixed. Files changed in `~/anime-codec-lab` (not
committed there; the files as Rin left them are in
`~/Forge/backups/2026-10-07-overhaul/sweep/codec-lab/after-sweep-1/`, the
original strategies in `.../codec-lab/strategies/`): `server.py`,
`static/index.html`, `strategies/registry.py`, `README.md`, the tests.

- The comparison videos never played: `playTogether()` kept its `canplay`
  handler, and its seek to 0 fired `canplay` again, about 150 restarts a
  second with the time stuck at 0, which also restarted them while hidden.
  The start is now one-shot and does not play while the page is hidden.
  (This bug was older than the sweep; the sweep's UI check had skipped it as a
  headless-codec problem.)
- `POST /api/runs` checks every param against the strategy's schema (unknown
  name, wrong type, not whole, out of range, select value not offered) and
  answers 422 before queuing anything. That also ends the 500 on params
  nested 1000 levels deep.
- Upload names are capped at 255 bytes, not 120 characters (a long CJK or
  emoji name was a 500), and the file is written to a private temp file and
  linked under the first free name, so two same-name uploads at once cannot
  overwrite each other.
- At 760 px the page no longer scrolls sideways (the comparison columns and
  the main grid can shrink; the results table scrolls in its own box).
- The header line says what failed when the server answered with an error,
  and only says "not answering" when it really cannot be reached. Long error
  notes wrap.

Verified: pytest 77 passed (13 of the 21 new cases fail on the code as Rin
left it; the rest guard the round trip of every strategy and the good path).
`tests/check_ui.py 9082 9083`: 29 of 29 PASS in headless Chrome, now including
"comparison videos play (time moves)", "no seek/restart storm",
"pause while hidden and stay paused 10 s" (0 media events) and no sideways
scroll at 760 px. black clean; pyright 0 errors on server.py, web_player.py,
the tests, registry.py and ffmpeg_baseline.py, and no new errors in the other
strategies (their cv2/scipy stub errors were there before).

Not verified: still nothing seen in the real Forge window (WebKitGTK), and the
4:4:4 decoded video question stands.
