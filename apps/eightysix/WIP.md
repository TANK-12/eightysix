# Eighty Six (hub tile): work in progress
date: 2026-10-08 · for: both

The hub tile is finished and in use. The game itself lives in
`~/Games/eightysix` (its own repo); this app only reads and launches it.

## 2026-10-08 · U1 every-app sweep (Relay task 84, group G9)

Changed:
- **One run at a time.** `POST /api/tests/run` refuses a second run while the
  first is going (`{"started": false, "reason": "The tests are already
  running"}`); `GET /api/tests` now carries `"running"`. Play, Play version N
  and Open in Godot editor refuse the same launch again within 5 s (409
  "Already starting; give it a few seconds."), so a double click opens one
  game window. A `tests-last.json` that is not a JSON object is a clear 500.
- **Page:** buttons go busy while their request runs (a double click sends
  one request); Play is the main (accent) button; error toasts are red
  (`err`); test names, folder names and log lines are escaped (text, not
  markup).
- **Watching:** a running test run and a running share-zip job are watched
  through `ForgeIdle.poll` with backoff (3 s, doubling to 30 s while the
  server does not answer), paused while Forge shows another app. If the
  server is not answering at load the page says so calmly and fills in by
  itself when it answers. Coming back after a minute or more away refreshes
  the panels once.
- **Looks:** image viewer closes on Escape and fades; thin themed
  scrollbars; panel fades (reduced motion honoured).

Verified (2026-10-08):
- `.venv/bin/python -m pytest -q tests`: 31 passed (4 new: second test run
  refused, running flag, launch cooldown, unreadable tests file).
- `.venv/bin/python tests/check_ui.py`: 18/18 PASS in headless Chrome, framed
  the way the hub frames it, against a made-up game folder (never the real
  `~/Games/eightysix`): escaping, one request per double click, 0 fetches,
  frames and timers while hidden during a run, backoff with the server
  gone (fewer tries 10-30 s than 0-10 s), recovery, Escape, thin
  scrollbars, no page errors.
- black and pyright (0 errors) on the touched Python files.

Not verified: the refresh after a minute away and the fades (read, not
driven by a check); a real Play click starting the real game (the cooldown is
covered by a mocked test only); no fps or power numbers were taken.

Static changes reach Forge on the next page reload; `web_app.py` on the next
Forge restart.

### Critic follow-up (same day)
An Opus critic tried to break the sweep. Fixed:
- A launch that failed (a broken play.sh) no longer blocks the next try for
  5 s; `"7"` and `"007"` are one version (and one cooldown).
- A test run survives a backend restart in its own session, so its pid is
  kept in `outputs/eightysix-tests.pid` and checked (`/proc/<pid>/cmdline`
  must name run_tests.sh): no second run on top after a restart.
- fps values from the game's logs are escaped; text where a number belongs
  shows "-" and no longer makes `/api/fps` answer 500.
- After a minute away, a picked image folder that is gone falls back to the
  newest instead of a stuck "Could not read check images."
- A repeated launch (409) is a plain toast, not a red failure.
Verified: pytest 35 passed (4 more); check_ui 20/20 PASS (2 more checks;
both fail against the old lines, checked by putting them back).
