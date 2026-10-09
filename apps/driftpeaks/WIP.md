# Drift Peaks: work in progress

Critic follow-up (same day, `sessions/2026-10-07-overhaul/critics/u1-G7-critic.md`)
- Coming back into view no longer skips the save backoff: a retry owed is
  sent at once only if the last failed try is older than its wait, otherwise
  it waits out the rest (the critic counted 11 tries in 30 s of hide/show).
- `DELETE /api/shapes/<id>` for a shape the game never shipped was a 500
  (`forge_content.delete` does not exist); it now removes the store entry
  through `forge_content.SHARED.delete` and answers 404 when there is none.
  This one is in `web_app.py`, so it reaches Forge on the next restart.
- Verified: pytest 21 passed (new revert test), node tests 13 passed,
  `node --check`, black, pyright 0, `tests/check_ui.py` 13/13 PASS.
  The show-respects-backoff path itself is reasoned, not re-counted.

## U1 sweep (2026-10-08, Relay task 74)
Worker Rin (relay-82-work, Relay task 82). Static files and a check script
only, so it reaches Emerson's Forge on the next page reload. Nothing removed.

Changed
- Rest: the background music kept playing while another app was in front in
  Forge (only a running ride paused). It now pauses whenever the page is out
  of sight (hub hidden or a background tab) and carries on from the same spot
  when it is back. The sound effects' audio device is suspended while hidden
  and wakes with the next effect. The drawing loop already rested
  (`forge_chrome.js` holds animation frames; the loop skips while hidden).
- Saving: a failed settings or run save used to be dropped silently. It is
  kept and tried again, 2 s doubling up to 30 s, only while the game is on
  screen, and sent at once when the game comes back into view; every try sends
  the newest save. A 413 (too large) is not retried.
- Art editor: Save and "Put the original back" are locked while one is on its
  way (a double click sends one request), and a server that does not answer
  gets "The game's server is not answering, so nothing changed" instead of an
  unhandled error; the buttons come back afterwards.
- Looks: thin scrollbars on the panels and the shape editor (the white default
  bar showed on Settings), 200 ms panel fade and rise, button hover fades,
  visible keyboard focus, disabled look, `prefers-reduced-motion` honoured.
- `tests/check_ui.py`: headless Chrome, framed like the hub, 13 checks.

Verified
- pytest 20 passed, node tests 13 passed, `node --check` on the changed JS,
  black and pyright 0 errors on `tests/check_ui.py`.
- `tests/check_ui.py` 13/13 PASS (sandbox save, store and a one-second music
  file): a key starts the music; hidden by the hub the music pauses and 10 s
  pass with 0 fetch, 0 animation frames, 0 timers; shown, the music carries on
  and the mountain draws; server killed: save tries 0-10 s then 10-30 s fall
  off; hidden with the server down: no tries for 20 s; server back and shown:
  the change lands in save.json by itself; Art double click saves once, dead
  server gets the calm sentence and the buttons come back; thin scrollbars; no
  page errors.
- Headless screenshots at 760, 1100, 1500 and 1920 px (title, settings, Art),
  before and after, looked at: `/tmp/u1/G7/shots/`.

Not verified
- In the real Forge window (WebKitGTK); the hub is imitated with an iframe and
  its own `forge_chrome.js`. The music pausing by ear.
- No fps, GPU or CPU numbers (not measured on purpose).

## Change (2026-09-27, Kenji / ejb-eb): the Alto soundtrack plays in the game

Emerson: the downloads in ~/Music/Alto were one-hour loops; cut them to the
real track length, put them in the game, and keep only the short ones.

- Loop points were measured, not guessed: a spectral self-similarity scan,
  then raw-waveform correlation. Adventure repeats every 250.000 s (r = 0.99
  from the first second, a clean digital loop). Odyssey is not a clean loop
  (r 0.80-0.95): it matches at 325.8 s and slightly better at 651.6 s, so the
  cut keeps the full 651.6 s cycle (10:52) rather than lose half of it. If he
  wants it shorter, `ffmpeg -i in.mp3 -t 325.8 -c copy out.mp3` gives 5:26.
- ~/Music/Alto now holds `Alto's Adventure - Soundtrack.mp3` (4:10, 4.3 MB)
  and `Alto's Odyssey - Soundtrack.mp3` (10:52, 11 MB); the two one-hour files
  are deleted (118 MB freed). `apps/driftpeaks/music/` holds hardlinks to the
  same two files (no extra disk); git ignores that folder.
- `web_app.py`: `GET /api/music` lists audio files in `MUSIC_DIR` (env
  `DRIFTPEAKS_MUSIC`) in name order; `GET /music/{name}` serves only a listed
  file. `static/js/music.js` plays them in turn, round and round, starting
  on the first key or click (browser rule). New setting `music` ("Music
  volume", default 45 %, 0 = off) in the settings table.
- Verified: pytest 20 passed (5 new music API tests), node tests 13 passed
  (2 new), `tests/check_music.py` in headless Chrome 4/4 (no music before a key,
  a key press fetches the track, Settings shows Music and Sound volume),
  screenshot looked at, pyright 0 errors, black on the Python files.
- Not verified: hearing it (headless has no speakers), and the Odyssey loop
  seam by ear (it is not a clean loop, so a small jump there is possible).
  Needs Drift Peaks reopened inside Forge to be heard.

## Change (2026-09-25, session S3 / ejb-49): frame rate readable in Zen
Emerson: "framerate doesn't show up in zen mode". It was never hidden: the
readout was near-white 12px text at 70% opacity bottom-left, over white snow.
Now a dark pill under the distance (top-left, `#fps` in app.css), "… fps"
until the first reading, measured from real frame time (it summed the step
capped at 1/30 s, so anything under 30 fps read as 30), and "Show frame rate"
is in simple Settings. Checked: headless Zen screenshot with Emerson's save
shows the pill; 14 pytest + 11 Node pass. Not checked: the number itself in
the Forge window (headless runs too few frames).

## State (2026-09-25, session ejb-63, built from ~/Forge/docs/plans/PLAN-hub-next.md item 1)
Emerson's direction: "more like alto, apart from that do what is best with
options for customization". Name picked by Claude from the plan's list.

**Verified**
- 14 pytest cases (shape seeding into the shared store, edit kept across
  reseed, revert, bad shapes/ids refused, broken store file falls back, levels,
  save round trip and size cap, sounds seeded, index + /shared served).
- 11 Node cases (same seed = same mountain; no chasm before 400 m; ropes clear
  the ground; coins above snow; every feature builds; riding untouched never
  crashes on the opening run; a held full flip lands and counts 1; a half flip
  crashes; flip counting; rope catch -> grind -> rope end; zen recovery; goals).
- black + pyright clean on web_app.py and tests.
- Headless Chrome screenshots looked at: title, day ride, night + snow +
  aurora, dusk thunderstorm (zen), Art grid, Settings. Text contrast fine.

**Not verified**
- Real frame rate inside Forge's WebKit on the Iris Xe (headless Chrome only
  runs a few frames). Turn on Settings > Advanced > Show frame rate.
- Sound output (recipes load; headless cannot play audio).
- Tricks as played by a human: timing and feel are reasoned plus unit-tested,
  not play-tested. Tunables are all in Settings > Advanced.
- Not yet opened inside the Forge window (needs a Forge restart to discover it).

## Improve next (ranked)
1. Play-test feel: jump height, flip speed, combo timer (2.2 s), boost size.
2. Measure fps in Forge; if low, cache the far ranges to an offscreen canvas.
3. A Shapes tab in Pixel Forge for the new shared `shapes` type (the store is
   ready; only the in-game editor exists now), with point dragging rather
   than JSON.
4. More biomes (desert canyon, forest, temple ruins) as palette + feature sets,
   the way Alto's Odyssey varies.
5. Wingsuit / power-ups bought with coins; a daily seed.
