# Calendar: work in progress

## U1 sweep (2026-10-08, Relay task 74)

Done by the G2 worker (Relay task 76) on top of edits left by stopped workers.
- **Server down:** any request that cannot connect shows a "Backend not
  answering, retrying" chip and stops the minute poll; a reconnect poll knocks
  after 5 s and then doubles up to a minute; the first answer hides the chip,
  redraws and brings the minute poll back. Errors in the main pane are one
  calm sentence with a Try now button.
- **Robustness (API):** `ts`/`end_ts` of nan, inf or outside years 1..9999
  and `tags` that are not a list or text answer 400 instead of 500; rows
  already stored with inf no longer break searches (`query`, `day_counts`
  skip them, an inf `end_ts` reads as none). Feeder settings with a bad
  `keep_days` or `enabled` answer 400 with the reason.
- **Robustness (page):** only the newest of overlapping draws is put on
  screen (fast clicking never shows an older month); Save and Delete ignore a
  second click; an emptied "keep days" box goes back to the saved number
  instead of quietly saving 0 (forever); an unknown `#view=` or bad `#date=`
  falls back; a Jan day summary is kept per day across redraws.
- **Looks:** the top bar wraps at narrow widths instead of pushing buttons
  out, the month grid fills the pane, short fade on view switch and dialog
  open (opacity/transform, reduced motion honoured), a slow load dims the
  pane after 150 ms, week titles wrap instead of shrinking to nothing, thin
  themed scrollbars (incl. `::-webkit-scrollbar` for WebKitGTK).
- **Critic follow-up:** a negative "keep days" is refused (400, and the
  page box reverts) instead of saving 0 = forever; searches longer than 200
  characters are clipped (50 000 used to answer 500); `ts: true`, an end
  before the start (also by PATCH against the stored time) and a PATCH with
  `ts: null` (used to move the event to now) answer 400.
- **Verified:** pytest 23 passed (4 new: 2 store tests, 2 API tests); black +
  pyright 0 errors on the .py files; `node --check static/app.js`; headless
  Chrome on scratch port 8921 with a temp data dir and collectors off
  (`/tmp/u1/G2/check/g2check.py`): 0 fetches/timers in 10 s while hidden,
  server killed: 3 fetches in 0-10 s, 1 in 10-30 s; restarted: back online
  in 4.5 s by itself; triple submit saved 1 event; 5 quick "next" clicks end
  on the right month; no page errors. Screenshots at 760/1100/1500/1920
  looked at (`/tmp/u1/G2/shots/cal-final-*`).
- **Not verified:** inside Emerson's real Forge window; the Jan summary
  button (no Jan calls in tests). Static changes arrive on the next Calendar
  reload; the .py changes only after his next Forge restart.

## 2026-09-27 check (S13 Suzu): works standalone

The "Calendar is broken" report was the port clash with Jan Tune (both on
8453; Jan Tune moved to 8461, and its `tests/test_manifest.py` guards it).
A scan of every `apps/*/forge_app.json` found no other shared port.
**Verified:** suite 19 passed; the app on a scratch port with a copy of the
real data (`FORGE_CALENDAR_DATA`, collectors off) in headless Chrome: Month
grid with the per-source dots for September, Week and Day views switch, no
page errors; `/api/feeders`, `/api/days` and `/api/events` answer in about
10 ms. A first page load in a cold headless Chrome took about 3 s before the
grid showed; the same page loaded again took 135 ms, so that was the browser
warming up, not Calendar. No code changed.

## Built 2026-09-24 (the same session as the Claude app avatars)

### Verified (real output)
- 19 tests pass: the store, every feeder on fixture data, the collector
  (runs on its interval, keeps state across restarts, survives a broken
  feeder, pause works), reminders firing once, password masking (6 real
  phrasings), and the HTTP API round trip. black done; pyright shows 0 errors.
- Live run on a scratch database against the real machine: claude +576 and
  jan +77 backfilled, the apps feeder logged a real app opening, and forge,
  hyprland and nyarch ran without errors (Nyarch: 3 chats noted). `forge-log`
  logged a milestone.
- Headless screenshots of the month, week and day views (dark, readable).
  The week view first printed titles one letter per line; that is fixed and
  checked again.

### Not verified
- "Sum up this day with Jan" was not run live (Jan was busy with another
  session's model swap).
- A reminder popping up for real (notify-send is mocked in the tests).
- Inside the real Forge window: it has not been opened there yet. Forge
  should discover it from forge_app.json.

### Ideas
- Link Claude app turns (persona and mood) as events.
- Acchan's remind_me could write reminders here.
