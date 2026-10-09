# Cosmos — work in progress

## 2026-10-08 · U1 every-app sweep (Relay task 84, group G9)

Changed (static files only: they reach Forge on the next page reload):
- **Rest:** the menu sky draws 30 frames a second instead of 60 (the twinkle
  is slow) through `ForgeIdle.loop`, so it stops while Forge shows another
  app (`index.html` now loads `/shared/forge_idle.js`). The puzzles' sound
  device sleeps while hidden and wakes when shown.
- **Server not answering:** the menu says so calmly and asks `/api/modes`
  again through `ForgeIdle.poll` with backoff (3 s doubling to 30 s, never
  while hidden), then fills in by itself. A puzzle result or explore save
  sent while the server does not answer is kept, one calm toast says so,
  and it is retried the same way until it lands; a refusal from the server
  still shows its own error. `api()` errors now carry `.status` to tell
  the two apart.
- **Sandbox:** Save sends one request for a double click.
- **Looks:** thin themed scrollbars in WebKitGTK; at 760 px the puzzle top
  bar and the level-list head wrap clear of the Full screen button; toasts
  fade in.

Verified (2026-10-08):
- `.venv/bin/python -m pytest -q tests`: 45 passed. `node --test tests/js/`:
  61 passed.
- `.venv/bin/python tests/check_ui.py` (new): 28/28 PASS in headless Chrome,
  framed the way the hub frames it, temp HOME (never the real saves): menu,
  map, sandbox and puzzles each 0 fetches, frames and timers for 10 s while
  hidden and draw again when shown; menu sky about 30 frames a second;
  sound device suspended while hidden; menu backoff, no tries while hidden
  and recovery; a puzzle result kept while not answering, 2-4 tries in 7 s,
  saved exactly once when the server is back, then the tries stop; one
  sandbox save per double click; 760 px toolbars clear of Full screen; no
  page errors.
- black and pyright (0 errors) on `tests/check_ui.py`.

Not measured: power and frame rate after the 30 fps menu cap (see the U1
G9 report's "measure this" list).

### Critic follow-up (same day)
- The hub's "Close app" button follows Full screen in the page flow, which
  put it at the top left over the map, sandbox and level "Menu"/"Levels"
  buttons (not from this sweep; found by the critic). `app.css` now pins it
  beside Full screen (top 10 px, right 108 px).
- The menu, when the server answers `/api/modes` with an error, names it
  ("Cosmos could not list its modes (...)") instead of "not answering",
  and keeps retrying with the same backoff.
- `tests/check_ui.py`: a layout pass over every screen at 1500 and 760 px
  (no control under Full screen or Close app, the two not overlapping),
  each width in a fresh browser; a refused-mode-list check (`?u1refuse=`).
  The layout pass failed on the old CSS (5 screens: the chip over "Menu"
  and "Levels").
Verified: check_ui 39/39 PASS, pytest 45, node 61; a 760 px screenshot of
the sandbox shows Close app beside Full screen, clear of "← Menu".

Last updated at the end of session 2 (2026-09-16), after the user's first
play.

## State

Cosmos has three finished modes:

- **Map:** session 1.
- **Gravity sandbox:** session 1.
- **Orbit puzzles:** session 2.
  - Ten levels and an endless mode.
  - A huge **Galaxy playground**: 40 star systems along three spiral arms,
    about 8,400 units across.
  - Flying close to a star in the galaxy discovers it. Each discovery is saved
    at once, under `explore` in `~/ForgeGameData/cosmos/puzzle-progress.json`.

Nothing is half-built.

- **Tests:** all pass.
  - `node --test tests/js/`: 61 tests.
  - `.venv/bin/python -m pytest -q tests`: 45 tests.
- **Checked by eye:** headless Chrome screenshots of every puzzle screen,
  including the whole galaxy, a galaxy flight and a discovery.
- **Power:** measured in a real WebKitGTK window with the GPU idle, flying
  the galaxy at 1×.
  - **Power saver** (the default, 24 frames drawn per second): 12.0 W.
  - **Smooth:** 14.5 W.
  - The laptop idles at about 10.5 W.
  - The user's goal was about 13 W.
- **Session record:** `manifests/session-02.json` holds the full record,
  including the addendum after the user played.

## Do first next time

1. **Restart Cosmos inside Forge once.** Its backend was started before
   galaxy saves existed. Until it restarts, discoveries are refused with a 400
   and a toast says so. Level stars already save.
2. **Play the galaxy by hand.** Check the crossings between systems, how burns
   feel at `burn_rate` 12, and time warp at this scale. Tune the JSON.
3. **Play levels 1 to 10 and tune pars and bonus times.** A solver set them.
4. **Real mouse input in the Forge window.**
   - Drag to aim.
   - Shift-drag for elevation.
   - Hold the burn buttons.
   - Press `f` for full screen.
5. **Session 1's map and sandbox checks, still open.** Pointer gestures,
   sandbox Save, and the map's frame rate.

## Improve next

1. **Tune from play:** proven solvable is not proven fun.
2. **Orbit and landing goals in endless mode.** The braking autopilot can
   already prove them solvable.
3. **Galaxy extras:** named nebulae and a map of which stars have been found.
   These would add to the file-based discoveries.
4. **Roadmap session 3,** the arcade gravity shooter.

## Gotchas

- `static/core/*.js` must stay free of the DOM and Three.js, so Node can test
  it.
- **Headless screenshots:**
  - Use `--use-angle=swiftshader --enable-unsafe-swiftshader`; with
    `--disable-gpu` the 3D canvas is black.
  - `pzfire=1` saves real results. For test flights, run a scratch server with
    `HOME` pointed at a scratch folder that symlinks
    `ForgeGameData/cosmos/levels`, and set
    `FORGE_CONTENT_DIR=/home/ejb/ForgeGameData` for sounds.
- **URL hooks:**
  - `?pz=LEVEL` opens a level, `&pzfit=1` shows all of it, `&pzfps=0` or
    `30` sets the frame cap.
  - `pzfire`, `pzwarp` and `pzghosts` also exist.
  - The mode's root element carries `__debug`, and `__debug.state.renders`
    counts frames drawn.
- **Frosted-glass panels:** `backdrop-filter` blur over the moving 3D view
  cost about 2 W. It is off in the puzzles; keep it off.
- **Galaxy file:** `explore-galaxy.json` was generated once from a seed. The
  generator is gone and the JSON is the source.
  - Star ids must match `^[a-z0-9][a-z0-9_-]{0,79}$`, or discoveries of them
    are refused.
  - `levels.test.mjs` checks this.
- **Slingshot levels are sensitive:** re-solve with
  `node tools/solve_level.mjs FILE --write` after editing bodies.
- **Power readings need root, and Jan distorts them.** Check graphics power
  first (see `MANIFEST.json` `how_to_check.power`).
