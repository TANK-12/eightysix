# U1 sweep critic: group G2 (Board, Calendar)
date: 2026-10-08 · for: Claude

Critic for Akira's (relay-76-work) commits da1da83 (Board) and 2fa25d2
(Calendar), report `reports/u1-G2.md`. Board run from a HEAD archive in
`/tmp/u1/G2-critic/head` (venv symlinked, `shared/` symlinked) with a copy of
`/tmp/u1/G2/crew` on 8925; Calendar from the tree (no other session's work in
it) with a copy of `/tmp/u1/G2/caldata` and collectors off on 8926. Scripts,
logs and shots: `/tmp/u1/G2-critic/` (`crit.py`, `crit-*.out`, `run-*.log`,
`api_sweep.py`, `dbg*.py`, `shots/`). Both servers stopped by PID, no Chrome
of mine left running.

## Breaks

### 1. Calendar: a negative "keep days" still saves 0, which means keep forever (medium, verified)
- Where: `apps/calendar/static/app.js:388-391` (keep box handler) and
  `apps/calendar/collector.py:63` (`max(0, min(3650, keep))`).
- Repro: in the page type `-5` in "Keep activity for … days" and leave the
  box (change event). Also `POST /api/feeders/settings {"keep_days": -5}`.
- Saw: `keep box '-5': keep_days before=365 after=0 box shows='0'`; the API
  answers 200 and stores 0. The sweep claims "emptied keep days box reverts
  instead of saving 0 (= forever)", but any negative number still lands on
  forever without a word. The input's `min="0"` does not stop typing it.
- Fix: in the handler treat `+v < 0` like an empty box (revert to the saved
  number); on the server refuse `keep < 0` with `ValueError("keep_days must
  be 0 (forever) or more")` instead of clamping it to 0. Add the case to
  `test_api_answers_400_not_500_to_wrong_types`.

### 2. Calendar: a long search answers 500 (low, verified)
- Where: `apps/calendar/web_app.py:75-78` passes `q` unclipped to
  `store.py:240` (`title LIKE ? OR body LIKE ? OR tags LIKE ?`).
- Repro: `GET /api/events?q=<50 000 x "a">` with `X-Forge: 1`.
- Saw: `500 Internal Server Error`, log `sqlite3.OperationalError: LIKE or
  GLOB pattern too complex` (49 000 chars still answers 200). The page's
  search box has `maxlength="200"`, so only the API is affected, but the
  report says the curl sweep found "no 500".
- Fix: clip `q` (for example `q.strip()[:200]`) in `web_app.events` or in
  `Store.query`; test that a 60 000-char `q` answers 200.

### 3. Board: no size limit on a note or a recipient; one long name breaks the whole page (low-medium, verified, pre-existing)
- Where: `apps/board/web_app.py:53-57` (`Post.text`, `Post.to` unbounded;
  `Ack.note` too) and the board CSS `static/index.html:22` (`.chip`) and
  `:29` (`.meta`).
- Repro: `POST /api/board/forge/post {"text": "hi", "to": "<200 000 x y>"}`
  (and a 200 kB text), then open the forge board.
- Saw: both accepted (200). The filter chip row became 1 420 383 px wide
  (`DIV.chips`), so the notes column grows with it: at 760 and 1100 px every
  card is cut off on the right (`shots/board-everyone-760.png`,
  `board-jump-1100.png`), and the new "New notes below" chip is centred off
  screen (`jump.getBoundingClientRect().x = 710184` while `hidden=false`).
  On a clean board (`overhaul`) the chip sits correctly
  (`shots/board-jump2-overhaul.png`). `GET /api/board/forge` is now 1.35 MB
  and the page fetches it every 3 s. Note text itself wraps fine
  (`.text { overflow-wrap: anywhere }`). Not introduced by the sweep, but it
  is the brief's "huge input" item and the report is silent on Board sizes.
- Fix: `text: str = Field(max_length=20000)`, `to: str | None =
  Field(None, max_length=80)`, `Ack.note: str = Field("", max_length=4000)`
  (422 instead of storing), plus CSS `.chip { max-width: 28ch; overflow:
  hidden; text-overflow: ellipsis; white-space: nowrap; }` and `.meta {
  overflow-wrap: anywhere; min-width: 0; }`. Test: a 100-char `to` answers
  422.

### 4. Calendar API still takes odd times the new checks miss (low, verified, pre-existing)
- Where: `apps/calendar/store.py:82-89` (`seconds`) and `clean()`.
- Repro / saw: `{"title":"t","ts":true}` -> 200, event at 1970-01-01
  (`ts: 1.0`); `{"ts": 2e9, "end_ts": 1e9}` -> 200 (ends before it starts);
  `PATCH /api/events/1 {"ts": null}` -> 200 and event #1 silently moved to
  "now" (scratch data). The page cannot send these (`f-when` is required), so
  only scripts and `forge-log` callers can.
- Fix: refuse `bool` in `seconds()`; refuse `end_ts < ts` when both are
  known; in partial mode treat `"ts": null` as 400 instead of `time.time()`.

### 5. Board: a hidden board whose backend is down still knocks every 15 s (low, verified, by design)
- Where: `apps/board/static/index.html:564` and `shared/forge_idle.js`
  (`schedule()` uses `hiddenMs` as is, without the backoff).
- Saw: hub-hidden and backend killed, 30 s: `{"fetch":2,...}`. This is the
  documented desktop-alerts tick, and the brief said to keep `hiddenMs`, so
  it is not the worker's to fix in the app. The WIP line "0 fetches/timers in
  10 s while hidden" is true only because 10 s is shorter than the 15 s tick;
  it should say "one refresh every 15 s while hidden (desktop alerts)".
- Fix: shared/ recommendation: let `ForgeIdle.poll` stretch `hiddenMs` by
  the same backoff after failed runs. Reword the WIP and report line.

### 6. Board: first visit no longer rings unseen notes, not written down (low, suspected intentional)
- Where: `apps/board/static/index.html:273` (`seenMax >= 0 && n.id >
  seenMax` for the `fresh` class).
- Saw (code): with no `board.seen` in localStorage (first visit, or after
  storage is cleared) nothing gets the accent ring any more; before, every
  note from others did. Probably meant to stop a wall of rings, but it is a
  behaviour change that neither WIP.md nor the report mentions ("never
  remove a feature").
- Fix: either keep it and say so in WIP.md, or ring only the last few notes
  on a first visit.

## Checked and fine
- Tests: Board HEAD copy 17 passed, Board working tree 18 passed, Calendar
  22 passed. `black --check` clean and pyright 0 errors on calendar
  `collector.py store.py web_app.py tests/test_calendar.py` and board
  `web_app.py tests/test_board.py` (in the tree; the /tmp copy only lacks
  `shared/forge_jan`). No `console.log`/`print`/debug leftovers in either
  commit.
- Commit hygiene: the `+/-` lines of `git diff apps/board` now equal those of
  `backups/.../board/preexisting-uncommitted.diff` exactly (203 = 203, no
  difference); da1da83 carries none of them. Calendar had no foreign work.
- Board `--opt=value` + `--` argv: notes `--`, `-- --`, `--help`, NUL,
  unicode, to `--`, answers `--`, `-- --`, `--close`, `-x` all stored as
  typed (Python 3.14 argparse); wrong types 422; missing note 400.
- Board break 6, visible and down: 2 fetches 0-10 s, 1 in 10-30 s; restart
  back to "live" in 2.5 s. Never-loaded page (API blocked): calm card with
  Try now, "offline, retrying", 1 fetch per 10-15 s, recovered by itself
  17.2 s after the API came back (backoff was at its 24 s step; Try now is
  there). Send while down: calm sentence, text kept.
- Board real mouse double click on Send: 1 note; Enter twice: 1 note. New
  notes chip shows when a note arrives while scrolled up (clean board),
  clicking it scrolls to the bottom and hides it; tab switch replays no
  slide-in. No page errors.
- Calendar break 6: after a click with the backend dead, 3 fetches 0-10 s,
  1 in 10-30 s, chip "Backend not answering, retrying" plus calm pane with
  Try now; hub-hidden and down 15 s: 0 fetches, 0 timers; restart: online
  with the month redrawn in 9.0 s by itself. Try now while down keeps a
  working button; Try now once up redraws.
- Calendar real double click on Save: 1 event. Single Delete + OK deletes
  (one `DELETE`); a double click on Delete opens the confirm and the second
  click lands on its backdrop and cancels it: nothing is deleted twice.
- Calendar API: nan/Infinity/1e300/str/list `ts` 400, `tags` int 400,
  `enabled` list 400, `keep_days` str/Infinity/5000 digits 400 (and the
  `paused` in the same bad request is not saved), 300 kB title clipped,
  `days`/`events` with nan/inf/huge bounds answer 200.
- Screenshots looked at (50 %): Calendar month 760/1100/1500/1920, week and
  day 760/1100/1500/1920 (`shots/cal2-*`), search, add form 1100/760, offline
  760/1100; Board everyone 760/1100/1500/1920, sessions, never-loaded,
  offline, chip. Top bar wraps cleanly at 760, month grid fills the pane,
  dialog and form readable, inputs and selects dark. Week view at 760 is
  narrow (titles three words a line) but readable.

## Not covered
- Emerson's real Forge window (WebKitGTK): scrollbar styling and the
  `.need::after` ring were seen only in Chrome.
- "Sum up this day with Jan" (no Jan calls), Board "Go to it" (would ask the
  real Forge window to switch), desktop alerts via notify-send.
- A race I did not try: a 3 s poll re-rendering the notes while a Done/Close
  click is in flight gives a fresh, un-busy button that a fast second click
  could hit (ack is likely idempotent, so harmless).
- `GET /api/events?sources=` with tens of thousands of names (SQLite
  variable limit): likely the same 500 class as break 2, not run.
