# Arcade: work in progress

Critic follow-up (same day, `sessions/2026-10-07-overhaul/critics/u1-G7-critic.md`)
- Hearsay save: the temp file is now unique per write (`tempfile.mkstemp`),
  so two saves at once no longer collide (the critic saw 5 of 24 parallel
  saves fail with 500). A lone surrogate in the save is refused with 400 (it
  was stored and then could not be loaded).
- Waveguide and Lanternfall intros threw a TypeError every frame (180 in 3 s,
  pre-existing): the paint flag is cleared before painting and both games
  return early until Begin builds their state.
- A failed status ask is retried while the page stays shown (20 s doubling to
  2 min, stopped when hidden), so the menu dot recovers without a hide/show.
- Verified: pytest 21 passed (new: 20 parallel saves all 200 with a valid
  file; surrogate 400), pyright 0, `tests/check_ui.py` 13/13 PASS, the
  critic's intro script now 0 errors on all three intros and in play.

## U1 sweep (2026-10-08, Relay task 74)
Worker Rin (relay-82-work, Relay task 82). Nothing removed or renamed.
`static/index.html` reaches Emerson's Forge on the next page reload;
`web_app.py` only on his next Forge restart.

Changed
- Rest: the sound schedulers (demo tone and the per-game beds) used to keep
  their `setInterval` ticking while the sound was suspended (paused game,
  intro, menu, hidden page), only bailing inside. They now run through
  `audioEvery()`, which starts and stops them with the audio context's
  `statechange`, so a paused or hidden game wakes no timer at all.
  The animation loop itself already rests inside Forge (`forge_chrome.js`
  holds animation frames while another app is in front) and in a hidden tab.
- Backend status: `/api/status` was asked once at start, so a backend or Jan
  that came up later was never seen. It is now asked again when Hearsay opens
  or the page comes back into view while Jan is not connected, at most every
  15 s and never on a timer; a failed ask marks the backend as gone (the menu
  dot turns red, Hearsay stops trying to save) instead of keeping the old answer.
  The Hearsay intro badge updates when that answer lands.
- Looks: thin themed scrollbars (`scrollbar-width` plus `::-webkit-scrollbar`
  for the hub's WebKitGTK); the track chip no longer sits over the last row
  of cards (bottom padding on the menu); panels, the menu and the Hearsay
  dialog settle in with a 200 ms fade and rise (opacity and transform only);
  `prefers-reduced-motion` turns those off.
- Backend: `/api/jan/chat` checks its input before asking Jan: missing,
  non-list or malformed messages, a wrong role, more than 40 messages,
  non-number or out-of-range `temperature` (0-2) and `max_tokens` (1-1024)
  get a plain 400 (they were 500s); over 60 000 characters gets 413. The
  Hearsay save is capped at 1 MB (413, the old save kept) and written aside
  then moved into place, so a crash mid-write cannot leave half a save.
- New `tests/` (the app had none): `test_api.py` (19 cases, temp home, Jan
  address nothing listens on), `check_ui.py` (headless Chrome, framed like
  the hub, 13 checks). `pyrightconfig.json` added (same as Drift Peaks).

Verified
- pytest 19 passed; black and pyright 0 errors on `web_app.py` and `tests/`.
- `tests/check_ui.py` 13/13 PASS: menu hidden by the hub, 10 s with 0 fetch,
  0 animation frames, 0 timers; a game with the demo tone playing ticks its
  scheduler, hidden it pauses and does 0/0/0 for 10 s, shown but paused still
  0 timers, Resume brings the scheduler back; Hearsay intro names the built-in
  brain with Jan off; backend killed: menu dot red on the next show; 20 hide /
  show flips ask `/api/status` once; backend back: the dot recovers by itself;
  thin scrollbar; no page errors.
- Headless screenshots at 760, 1100, 1500 and 1920 px (menu, Hearsay, pause),
  before and after, looked at: `/tmp/u1/G7/shots/`.

Not verified
- Inside the real Forge window (WebKitGTK); the check imitates the hub with an
  iframe and the hub's own `forge_chrome.js`.
- Sound by ear (headless has no speakers; the check counts scheduler ticks).
- No fps, GPU or CPU numbers (not measured on purpose).
