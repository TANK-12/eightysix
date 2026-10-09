# Settings: work in progress

## U1 sweep (2026-10-08, Relay task 74)
Worker Itsuki (relay-80-work), Relay task 80. Static files only (`static/app.js`,
`static/app.css`, `static/index.html`): they reach Emerson's Forge on the next
page reload, no restart needed. Nothing removed or renamed.

Changed:
- **First load**: until it works the page shows one calm card ("Loading
  settings…"), not every hand-made section half-filled. If the backend is not
  up, the card says so and tries again by itself through `ForgeIdle.poll`
  (2 s growing to 30 s, resting while hidden), with a Try now button.
  `shared/forge_idle.js` is now loaded.
- **Saving**: a change made while the backend is down is kept, not dropped,
  and sent again with the same backoff; the header says "Not saved yet …
  Trying again by itself". One save at a time, so an older answer can no
  longer arrive last and put back an older value; edits made while a save is
  out are kept. A refused change (4xx) says why and re-reads what is stored.
- **Reset to defaults** now needs a second press within three seconds, like
  each page's own Reset, and is locked while it runs (a stray click used to
  wipe every setting).
- **Follow my desktop wallpaper**: unticking it when the desktop's picture is
  outside the wallpaper folder used to do nothing visible (the box ticked
  itself again). It now says so and opens the quick picker.
- **Missing thumbnails** (desktop picture outside the folder, file gone) show
  an empty tile instead of a broken-image icon.
- Looks: thin themed scrollbars incl. `::-webkit-scrollbar` (WebKitGTK),
  short fade when a section opens, colour transitions on the section list,
  long status text ends in an ellipsis instead of pushing the header.

Verified (headless Chrome, scratch server on 8950 with a sandbox config,
cache, hub dir and wallpaper folder; `/tmp/u1/G5/g5check.py`, output
`/tmp/u1/G5/g5check-*.out`): 0 fetch / rAF / timer callbacks in 10 s visible,
hub-hidden and document-hidden; server killed with a change pending: 3 then 1
save attempts (0-10 s, 10-30 s), 0 while hidden, saved by itself 3.8 s after
the restart and the sandbox file holds the value; first load with the server
down: calm card, 2 then 2 attempts, page loads by itself after the restart;
Reset: one press sends nothing, a triple press resets once; no page errors.
pytest 34 passed. Screens at 760/1100/1500/1920 before and after in
`/tmp/u1/G5/shots/`.
Not verified: inside the real Forge window (WebKitGTK).

Critic follow-up (same day, `sessions/2026-10-07-overhaul/critics/u1-G5-critic.md`):
- Reset now waits for a save already on its way (up to 10 s), and a save
  answer that lands after a reset is ignored, so the page no longer shows an
  old value with "Saved" while the file holds the defaults.
- A change not yet saved is only dropped once the reset has worked; Reset
  while the backend is down keeps it and keeps retrying.
- Not fixed here (shared/forge_theme.py): a wallpaper in a sub-folder of the
  wallpaper folder counts as "not in the folder" (the backend sends only the
  bare file name), and the `wallpaper` setting accepts any string.
Verified with the critic's own repro (`/tmp/u1/G5-critic/crit.py`, output
`/tmp/u1/G5/critfix.out`): delayed save then Reset -> page 0.5, server 0.5;
down + Reset -> pending kept. g5check re-run all pass, pytest 34 passed.
