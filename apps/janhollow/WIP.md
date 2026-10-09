# Janhollow WIP

Status lives in `MANIFEST.json` (sessions 1-5) and `manifests/`. This file
holds the newer work notes, newest first.

## U1 sweep (2026-10-08, Relay task 74)

Group G8 of the every-app sweep, done by Relay task 83 (Hikari). Report:
`~/Forge/sessions/2026-10-07-overhaul/reports/u1-G8.md`.

What changed:
- **Header wraps** onto a second row in a narrow window. At 760 px the
  Voices, zoom and full-screen buttons used to run off the right edge where
  nothing could reach them (`overflow: hidden` on the body).
- **Backend down**: the 200 ms world poll now stretches 1 s, 2 s, 4 s, 8 s,
  then 10 s on screen (30 s out of sight); the 4 s presence heartbeat stretches
  to 30 s; the Voices panel poll returns false so ForgeIdle backs off (x2, up
  to 30 s). The header says "station not answering, trying again" in the warn
  colour, and the first good answer puts every beat back and sends a heartbeat
  at once.
- **First load** shows a "Waking the station…" card over the deck; if the
  backend does not answer it says so, retries by itself (2, 4, 8, then every
  10 s) and has a Try now button. It used to print "Janhollow could not
  start: <error>" and never retry.
- **Buttons**: Save, Load, Re-read content, Start over, the away modes, the
  chatter levels and the Voices button send one request at a time (disabled
  until answered) and show a calm toast if the backend is down instead of an
  unhandled error. Load only says "no save yet" for a real 404.
- **Start over takes a second press** within 4 s ("Press again to start
  over"): one stray click used to wipe the clock, the log and where you are.
- **Typing** in the talk box or a settings field no longer toggles names (n)
  or switches decks (Tab).
- **Rest**: out of sight (hidden tab or another Forge app in front) the
  AudioContext is suspended and resumes when shown if Sound was on; turning
  Sound off suspends it after the fade. A held walking key is let go when the
  page goes out of sight (a hidden window gets no keyup, so you kept walking).
- **Looks**: thin themed scrollbars on the side panes (incl. -webkit for
  WebKitGTK), tab hover/opacity transition, a placeholder in the crew pane
  before the first answer.
- **Backend** (reaches Emerson's Forge on its next restart, not before):
  a NaN or infinite walking direction (`/api/player/hold`) is now "let go";
  before, it became the player's speed and every `/api/world/state` answered
  500 while it was held. Non-finite or wrong-type settings keep the current
  value instead of resetting it to the default. Save slot names are capped at
  64 characters (a 500-character name was a 500 error).

Verified (scratch server on 8980, copied data dir, Jan pointed at a dead
port, headless Chrome via tests/cdp_driver.py):
- `pytest`: 127 passed (114 before + 13 new in `tests/test_u1_robustness.py`;
  the NaN tests fail against the old player.py). black clean, pyright 0 errors
  on the touched .py files.
- Server killed: fetches 7 in 0-10 s, 4 in 10-30 s (was a request every
  200 ms by the code); recovered by itself 9.5 s after restart. Boot with every
  API call failing: card shown, 2 tries per 10 s, loaded by itself 2.7 s after
  the API came back. No page errors.
- Hidden: hub-hidden 10 s = 2 world polls + 2 heartbeats, 1 rAF (unchanged,
  documented hidden beat). AudioContext running -> suspended (hub hidden) ->
  running (shown); off -> suspended and stays so across hide/show.
- Save triple click = 1 request; Start over one press = 0 requests, label
  resets after 4 s, press-press-press = 1 request; typing n in the talk box
  leaves names alone; held key cleared on hide.
- Screenshots at 760/1100/1500/1920 before and after: `/tmp/u1/G8/shots/`.

Critic follow-up (same day, after the Opus critic, 6 findings, all fixed):
dict/list values for away_mode or chatter and 400-digit numbers in
day_minutes/start_hour were still 500s (now ignored, keeping the current
value); `day_minutes: true` no longer counts as 2; save slot names are also
capped by UTF-8 bytes (63 four-byte characters were a 500); Step aboard and
Step out send one request per press and toast when the backend is down; the
day-length field goes back to the saved value when a change could not be
saved. Verified: 133 tests (6 more), the critic's curl repros now answer 200,
browser check `g8check.py fix` (join triple click = 1 request, leave double
= 1, field back to 40 with the backend down, calm toast, no page errors).

Not verified: inside the real Forge window (WebKitGTK); with real Jan
(never called); sound heard by a person.
