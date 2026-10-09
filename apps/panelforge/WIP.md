# PanelForge: work in progress

Short pointer file. **`HANDOFF.md` is the real handoff**: read its top
sections in order ("Session 4", "Later in session 4", "After the 04:09
window reset"), then `CONTRACTS.md`.

## U1 sweep (2026-10-08, Relay task 74)
Done by Relay task 88 (group G14). The static changes (app.js, core.js,
app.css) reach Forge on the next reload of the page; the web_app.py
handlers only after Emerson's next Forge restart.

- **Bad numbers:** a body of `1e999` (Infinity) on any route was a 500,
  because FastAPI echoes the rejected value and cannot write Infinity as
  JSON. A `RequestValidationError` handler now answers 422 with each
  field's location and message, without the value. A job POST given it
  starts no job.
- **Over-long ids:** a 3000-character series, chapter or line id hit the
  disk as a file name and was a 500 (`ENAMETOOLONG`). An `OSError` handler
  turns exactly that errno into a 404; every other disk error is still a
  500 with its traceback.
- **Polls rest and back off (break 6):** the health poll and the jobs
  drawer poll stretch their wait while the server is not answering
  (health 15 s to 30 s; drawer 2 s to 30 s), and a strip under the tabs
  says "The PanelForge server is not answering" until it comes back.
  `PF.watchJob` now runs on `ForgeIdle.poll` (keeps checking every 5 s
  while hidden so a finished job still settles, backs off to 10 s while
  the server is away) and gives up with an error after three straight
  404s (tries at about 0, 1.6 and 4.8 s) instead of polling a lost job
  forever. Jobs live only in memory, so after a backend restart every old
  job is a 404 and its watcher now ends with "the server no longer knows
  this job".
- **Looks:** thin dark scrollbars instead of the native grey ones.
- **Verified:** 584 pytest pass (new `tests/test_sweep_errors.py`, red on
  the old `web_app.py`, green now); black, pyright 0 errors on the touched
  Python. Headless Chrome on a scratch copy with temp data: all six tabs
  and four widths (760-1920) without page errors or sideways scroll; lost
  job stopped after 3 calls with its error; hidden page made 0 API calls
  in 9 s; server killed: health polled at 12 s and 42 s, drawer at 1, 5,
  13, 29 s, note shown, cleared when the server came back.

### Critic follow-up (same day)
- **NaN or Infinity inside a body** (`{"lines": [], "x": 1e999}`) was
  stored, and every later read of that document was a 500. An app-wide
  dependency in `web_app.py` (`_finite_json`) now refuses NaN, Infinity
  and 1e999 anywhere in a JSON body with a 422 before any route runs.
- **Ids of `..` or `.`** reached the data root (`PUT
  /api/series/%2e%2e/words` wrote `glossary.json` there). `paths.py`
  `series_dir`/`chapter_dir` now refuse empty, `.`, `..`, slashes, NUL and
  names over 255 bytes (`paths.BadId`, a 404).
- **Job status file:** `Job._save` also survives a result that is not plain
  JSON (writes its repr). The one case seen was a test stub in
  `tests/test_batch.py` returning the job itself; the stub is fixed.
- **Verified:** 593 pytest pass (new cases red on the previous commit);
  black, pyright 0 errors.

State on 2026-09-19 18:00 (session 4, third window, 15-minute ticks from here):

- **Tests:** 547 pass (`.venv/bin/python -m pytest -q`); one order-dependent
  flake noted in the handoff.
- **Data:** all ten WebToon chapters of Bad Born Blood fetched and analysed;
  series cast of 20 characters + 15 extras, **every one with a voice**
  (c01 by hand, the rest cast by the model from their pictures);
  `docs/crew/chain-all.sh` (log `docs/crew/logs/chain-all.log`) re-reads
  and rebuilds chapters 1-3 through the timeline, then re-reads 4-10;
  `docs/crew/after-chain.sh` (log `after-chain.log`) then re-voices
  chapter 1 with the cast voices and renders `lookie-09`. Check both logs
  for "done".
- **Films:** `chapters/0001/renders/lookie-08.mp4` (93.8 s, depth3d, from
  the model-read script), `watch-test2.mp4` (just-watch), `vertical-test`
  (9:16), `subs-test` (erase + subtitles).
- **New at 17:55, the scroll reader:** Render tab Mode "Scroll reader":
  the strip as drawn, whole width, scrolling down at reading pace and
  pausing on each panel while its lines play -- nothing cut, no cut-outs.
  Emerson asked for this because the fancy styles cut panels and objects
  apart. `docs/crew/scroll-renders.sh` is rendering whole chapters 1-3
  that way (`renders/scroll-16x9.mp4`, `scroll-9x16.mp4`). If he likes
  it, make it the default mode.
- **What works now:** the reader cleans balloon-edge strokes, the I read
  as 1/T/[, stray letters, and learns the series' names (glossary) so
  Ilay, Bellato, Corite, Kartika stay whole; `tools/renormalize.py`
  re-cleans every chapter without OCR; Jan page reading in a compact
  pipe format (3x fewer output tokens; delivery as words), with the panel
  picture for unsure speakers where two characters stand
  (`llm_pass.vision_pass`), retried once after a dropped connection, and
  cancellable between batches; scan-group choice in the fetcher, Library
  tab and MediaForge; cast across chapters with a hand-edit ledger and a
  crop bench; casting by the model (Cast tab button, and between the
  gather and build phases of a bulk run); "just watch" mode; 2.5D puppet
  style; in-between (morph)
  style; parallel shot rendering; bulk chapter runs; render list shows
  style/sound; detect/analyze in a crash-proof child process.
- **Session 46 closed 19:12** (final handoff; see HANDOFF.md "Where things
  stand"). Scratch server 8460 left running; all scroll renders (chapters 1-3) finished 18:46.
- **Session 46 closed 14:25 on 2026-09-20.** Emerson: "it's fine, just still
  wrong characters but I'll fix that, ok it's great, just finish up." He
  fixes speakers himself in the Lines card. Suite 569. Nothing running.
- **State 01:45 (2026-09-20):** every chapter 1-10 has a scroll film
  (`renders/scroll-16x9.mp4`; 1-3 also 9:16), read by the model, voiced
  by the cast voices, with mood music. Emerson has seen 1-2 and disliked
  the ring (removed) and something else about chapter 2 he has not named.
- **Improve next, ranked (20:10):** (0) Emerson watches
  `chapters/0001/renders/scroll-16x9.mp4` (final since 20:57 with
  the new music plan, the glow on the spoken balloon and 42 thought
  balloons moved from the narrator to their characters, and from 20:18
  the window rests on each balloon while its line plays; chapters 2-3 the
  same) and says what is still wrong with the voices and music -- only
  he can hear it. Everything he needs to fix speakers and voices is in the
  Cast & voices tab's Lines card (faces, Edit, hear, Speak changed lines,
  Render scroll film); music moods are edited on the Timeline tab. (1)
  If the music is still wrong: real tracks from the library
  (`~/PanelForgeData/library/music/`) instead of the synth pads, chosen
  per mood; (2) an anime face landmark model so
  puppets blink and talk on every face; (3) judge and fix the series cast
  with the crop bench (c01 merges two people, c03/c07 one person split);
  (4) page re-capture for the glitched comix.to page (its place on the
  strip is not recorded; look for it by eye). Jan's mid-request unloads
  are explained and fixed (Dossier's idle watcher; live when Dossier
  restarts).
- **Machine facts:** Jan's router runs on port 1337 (started by this
  session; models release when idle); scratch PanelForge on port 8460 (PID
  in `docs/crew/scratch-8460.pid`); Emerson's own PanelForge is on 8449 --
  never restart it. Pacing rule and usage script: `~/.claude/CLAUDE.md`.

## 2026-09-27 (S12 helper, stopped early to save tokens)

- **Why 2.5D and 3D "vanished":** the default render mode has been the
  scroll reader since 2026-09-19 (`static/js/core.js:218`). In scroll mode,
  `render/timeline.py` `plan_scroll` (about line 135) sets every shot's
  style to `scroll`, and `api/render.py` (about line 495) renames the film
  the same way. So Cinematic 3D (`depth3d`) and 2.5D puppets (`puppet25d`)
  stayed in the Style list but were silently replaced. Both styles are still
  registered and enabled (`GET /api/styles` checked).
- **Fix (UI only):** on the Render tab (`static/js/tabs/render.js`,
  `loadStyles`), picking a style other than scroll now switches the Mode to
  panel to panel and shows a toast. Picking the scroll reader clears the
  style. The Settings dialog (`static/js/app.js`) gained the missing
  "Scroll reader" mode option, so saving there no longer resets the mode.
  **Verified:** `node --check`, Render tab screenshot with both styles
  listed, suite 569 passed. **Not verified:** the change handler was not
  clicked in a browser, and no depth3d or puppet film was rendered.
- **Not done:** the Timeline tab has not been checked (no bug found yet).
  No new effects were added: `render/effects.py` is the place to look
  first. There is also no backend guard: an API call with an explicit
  non-scroll style and `mode: scroll` still renders as scroll.

## 2026-09-27 (S13 Suzu: scroll guard, timeline editor, new effects)

- **Backend scroll guard (done, verified):** `api/render.py`
  `_mode_for_style`: a render that asks for a style other than scroll while
  the mode (asked for or saved) is scroll now goes panel to panel, and the
  job log says why. No style, or style scroll, leaves scroll alone, so the
  Cast tab's scroll render (`cast.js` `renderScroll`) is unchanged. Test:
  `test_render_api.py::test_an_explicit_style_is_not_turned_into_the_scroll_reader`.
- **Timeline editor (done, verified in real headless Chrome with real mouse
  input):** four faults found and fixed in `static/js/tabs/timeline.js`:
  1. a click on a shot never selected it: the pointerdown drag redrew the
     lane on pointerup, which destroyed the block before the browser's click
     fired; the click also marked the shot "edited by hand". Selection now
     happens on pointerup when the press did not move (4 px slop), and
     nothing is marked edited unless it changed. Same slop for line and SFX
     drags.
  2. the shot Style list read `s.id`, but `/api/styles` sends `name`, so
     every option was "undefined". It now lists enabled styles by label
     (Cinematic 3D and 2.5D puppets included).
  3. Transition kinds were a fixed list; they now come from
     `/api/transitions` (so Morph, Screentone and Flash show up).
  4. Shot starts are derived by the server from durations on save, so
     dragging a shot sideways never stuck. The body drag is gone (a press is
     a click); the right-hand handle resizes and pushes later shots along
     live, as the server will.
  Also: shot thumbnails and the camera-keyframe picture were blank because
  `work/detect/panels/*.png` crops had been cleaned away (true of
  bad-born-blood). `api/detect.py` `panel_image` now cuts the panel from the
  strip (640 px wide JPEG) when the crop file is missing, building the strip
  map from chapter.json if strip.json is missing too. Test added to
  `test_detect_pipeline.py`. Browser check: `tests/check_timeline_ui.py`
  (8/8), run with `../files/.venv/bin/python tests/check_timeline_ui.py`
  because this venv has no `websockets`.
- **New effects (done, unit-tested; no film rendered):**
  `transitions/screentone.py` (halftone dots on a 45-degree grid swell in
  from the side the new shot comes from) and `transitions/flash.py` (burn to
  white, back on the new shot), both in `TRANSITION_MODULES`. Neither is
  picked by the auto chooser yet; pick them per shot in the Timeline.
  `render/effects.py`: `film_grain` (mid-tone grain on tense, mystery and
  sad panels, repeatable per frame) and `rgb_split` (red/blue pull apart for
  0.18 s at each impact). Existing camera shake at impacts already covers
  "impact shake"; speed lines and impact flashes already existed. Tests:
  `tests/test_render_new_effects.py` (9). **Not verified:** how grain and
  the split look in a real rendered chapter; Emerson checks renders himself.
- Suite: 578 passed.

### Improve next
1. Let the auto transition chooser use Flash on impact panels and
   Screentone on scene changes (changes existing auto timelines, so ask).
2. A per-shot "effects off" checklist in the Timeline inspector
   (`style_settings.effects_off` already works in the renderer, no UI).
3. Install `websockets` into this venv so `check_timeline_ui.py` runs
   with the app's own Python.
