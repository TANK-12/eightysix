# PulseForge — work in progress

## U1 sweep (2026-10-08, Relay task 74)

By Kana (relay-89-work), Relay task 89. Brief:
`~/Forge/sessions/2026-10-07-overhaul/U1-worker-brief.md`; report
`sessions/2026-10-07-overhaul/reports/u1-G15.md`.

**What changed:**
- Backend (`web_app.py`, `pulseforge/project.py`):
  - `DELETE /api/projects/%2E%2E` used to delete **all of ~/PulseForgeData**
    (the slug `..` pointed at the data folder; seen on a scratch copy). A
    small ASGI guard, `RequestGuard`, now refuses any `.` or `..` path segment
    under `/api/` with a 400. `projmod.delete` also only removes a folder
    directly inside `projects/`, and a dots-only project name gets a
    `project-<time>` folder instead of writing `project.json` into the data root.
  - NaN or Infinity anywhere in a JSON body was a 500 on every route, and in
    a project edit it was saved into `project.json`, after which the project
    could not be opened (every GET a 500). The same guard refuses it with a 400.
  - A project name over 300 characters is a 422 (5000 was a 500: folder name
    too long); folder names are capped at 80 characters, the full name is kept.
  - Duplicate / Use as template could land on top of another project: copying
    A with the name "B" replaced B's settings, and a second "A copy" overwrote
    the first. Copies now always get a new folder (`-2`, `-3` ...).
- Page (`static/index.html`):
  - Queue poll backs off while the server is down (`return false`,
    `{ backoff: 2, maxMs: 30000 }`, breaker item 6) and the queue line says
    "can't reach the PulseForge server, trying again".
  - A start that cannot reach the server shows a calm card in the project
    list and retries by itself (2 s, 4 s ... 30 s, only while shown), instead
    of one "Startup error" toast and a dead page.
  - One press, one request: Render, Preview, Make, Create, uploads, Analyse,
    Batch, Export, Duplicate, Import, Save settings, pre-flight and the
    earnings form ignore presses while their request is out (a double click
    queued the same render twice). An uncaught error there is now a toast.
  - Project names, scene/format labels and pre-flight text are escaped (a
    name with `<` in it was parsed as markup).
  - Simple editor: the preview `<img hidden>` showed as a broken-image icon
    because `display: block` beat `[hidden]`; it now hides, and an empty
    16:9 note says a real frame shows there once a picture is added.
  - A looping or silent preview video pauses while PulseForge is hidden and
    plays again when shown; a render you are listening to keeps playing.
  - Thin themed scrollbars page-wide (incl. `::-webkit-scrollbar` for the hub's
    WebKitGTK); tabs fade in over 180 ms (opacity only).
- Tests: `tests/test_u1_sweep.py` (13 cases, pytest) and
  `tests/check_ui.py` (headless Chrome, 15 checks, own backend on port 9051
  with a sandbox HOME; not collected by pytest).

**Verified:**
- pytest: 349 passed, 1 skipped (was 336 + 1 skipped). The 13 new cases
  fail on the pre-sweep code (run on a copy with the backups) and pass now.
- `tests/check_ui.py`: 15/15 PASS: 10 s hidden = 0 fetches, 0 timers, 0
  frames; the looping preview pauses/plays; triple click on Render and double
  click on Create / Make send one request; server killed: the poll asks less
  often (10-30 s window <= first 10 s, <= 3) and says so, server back: the
  page recovers by itself; blocked start: calm card, then ready by itself;
  no script errors.
- A fuzz of every POST/PUT route with junk bodies (`/tmp/u1/G15/fuzz.py`,
  Jan, reveal and analyse routes skipped): 76 answers of 500 before, 0 after.
- Screenshots at 760, 1100, 1500 and 1920 px of Simple, Compose, Scenery,
  Output, Studio and Autopilot, before and after (`/tmp/u1/G15/shots/`).
- black on the touched .py files; pyright: 1 error in web_app.py, the same
  pre-existing `forge_art` import as on HEAD.

**Critic follow-up (2026-10-08, Relay task 89):** the critic
(`sessions/2026-10-07-overhaul/critics/u1-G15-critic.md`) found 7 breaks, all
fixed:
- A number too big for a float (`1e999`) passed the NaN check and was saved as
  Infinity, after which the project or the whole app (settings) answered 500
  for good. `pulseforge/strictjson.py` now reads every request body and every
  imported `.pfproj` manifest and refuses NaN, Infinity and overflow; the guard
  also reads `Application/JSON` in any case. `config.load_settings` leaves out
  a non-finite value, so an old poisoned settings.json starts again.
- Emerson's real `~/PulseForgeData/settings.json` held `"x": -Infinity` from
  the sweep's own test run (04:43, before the guard): removed by hand (copy in
  `backups/2026-10-07-overhaul/sweep/pulseforge/critic/`); the u1 tests now
  point settings at a temp file.
- Import never overwrites a project of the same name (`unique=True`); a
  damaged manifest is a 400 and makes no project.
- Output tab list and Scenery snapshot labels show names as text, not markup.
- "Song!" and "Song?" (one slug) stay two projects; only the very same name
  reopens a project. Rename has the same 300-character cap as Create.
- The queue line tells "can't reach the server" from "the server answered
  with an error" (reasoned; not separately browser-checked).
Verified: pytest 362 passed 1 skipped; `tests/check_ui.py` 15/15 PASS; the
critic's headless script re-run: `__pwned` False on Output and Scenery, a
server with a poisoned settings.json starts and its page gets ready.

**Not verified / left:**
- The backend fixes reach Emerson's Forge only on its next restart; the page
  changes on the next reload of PulseForge.
- Not looked at in the real Forge window (WebKitGTK), only headless Chrome.
- Creating a project with the very same name as an existing one still
  reopens it (unchanged; it never wiped it).

## 2026-09-27: Spectrum Tunnel, Harmonograph Scope and particle effects

**Why.** Emerson: "make 2 new visualisers and particke effects". Brief:
`~/Forge/sessions/2026-09-27-pulseforge-visualisers-particles.md`.

**What changed:**
- Two visualizer scenes, `tunnel.py` and `scope.py` (a170938).
- `pulseforge/particles.py`: five presets (embers, snow, sparks on the beat,
  dust, petals) in one `PRESETS` table. Every visualizer, scenery and sprites
  scene gains `particles` and `particle_amount`; render.py `_feed` wraps every
  frame scene, so no scene was edited (ae36179, c58f01a).
- Sparks looked like pale dust at 1080p, so presets can now carry `streak`
  (seconds of travel drawn as a fading tail, 16 samples). Sparks use 0.06 s, a
  hotter gold and size 2.0. Other presets have no streak and are unchanged.
- `tests/check_scene_picker.py`: a headless Chrome check of the Compose tab.
  `pyrightconfig.json` (as in apps/files) lets pyright find `~/Forge/tests`.

**Verified:**
- pytest: 336 passed, 1 skipped (before the 16-sample tweak); after it,
  test_particles/test_ui/test_scenes 45 passed. New test: a streak lights a
  longer line than a dot.
- check_scene_picker.py: 9/9 PASS (both new scenes listed; Drifting Scenery's
  form offers none/embers/snow/sparks/dust/petals). 0 headless Chromes left.
- Real renders, 1920x1080, 450 frames (15 s of a DARK BASS EDM track from
  ~/Music/Forge), drift + embers and drift + sparks. Frames looked at: embers
  rise as orange dots from the bottom; sparks burst from the centre on beats as
  golden streaks that fall under gravity.
- black and pyright (0 errors) on particles.py, test_particles.py and
  check_scene_picker.py.

**Not verified:** the other three presets (snow, dust, petals) in a full
render (they pass the unit test that each preset draws); the living scene's
Scenery look panel "Particles" section was not screenshotted; Emerson has not
seen it live (needs a PulseForge restart inside Forge).

## 2026-09-24 (session 53, part 3): Autopilot becomes its own streamlined mode

**Why.** Emerson found the Autopilot tab cluttered. It sat among the editor
tabs, folders had to be typed, and the looks were text-only. He picked "own
mode, 3 steps" and all four extras: Browse, live preview, sample thumbnails
and a one-click upload pack.

**What changed:**
- **Mode.** `Autopilot` is a fourth button beside Simple, Advanced and Studio.
  In that mode the whole editor tab bar is hidden
  (`body[data-mode="autopilot"] .tabs`).
  - The page has its own nav: **Make / Library / Earnings**, with links
    `#/autopilot`, `#/autopilot/library` and `#/autopilot/earnings`.
  - The mode is saved in the existing `ui_mode` setting.
- **Make.** Three numbered steps:
  - **Songs** and **Pictures** each have a Browse button and a live summary
    ("2 songs · 0.4 min").
  - **Look** is a card per recipe showing a real frame of *your first
    picture* in that look, plus a larger preview of the chosen one.
  - The Make button says what it will do ("Make 1 mix" or "Make 12 videos"),
    or is disabled with the reason ("Lofi Radio needs a pictures folder").
  - While running, a progress strip shows the current song, a time-left
    estimate (from speed so far, shown after 5%), a Stop button, and the log
    folded under "Details".
- **Library.** Thumbnail cards. **Upload pack** opens the folder and copies
  the title, then offers "Copy description" and "Copy tags" in the order
  YouTube's form asks for them. Also Open folder, Mark uploaded, and Watch
  (once a link is set). Failed videos show their error.
- **Earnings.** Unchanged, moved to its own view. The table headers now say "Look".
- **Browse modal.** Up, Home, recent folders (localStorage, 6), and subfolders
  with song or picture counts (green when there are any). Only the home
  folder tree can be browsed; a path outside falls back to Home. Escape or a
  click outside closes it.
- **Backend** (`autopilot.py` + `web_app.py`):
  - `browse` → `GET /api/autopilot/browse`
  - `scan` → `GET /api/autopilot/scan` (counts, minutes, `to_make`,
    `skipped`, `problem`, `first_picture`)
  - `GET /api/autopilot/preview`: PNGs cached in `AUTOPILOT_DIR/previews/`,
    keyed on recipe, picture, mtime and width.
    - **Frame scenes** use `preview_frame`: a small `SceneContext` with
      `sample_features()`, frame 24. About 0.3 s.
    - **Living** uses `_living_preview`: a hidden project `autopilot-preview`,
      `_autopilot_prepare`, then `living.still`. It is hidden from
      `/api/projects`.
  - `GET /api/autopilot/package/{slug}/text`: `make_package` now stores
    `text` in `packages.json`; older packages parse `upload.txt`.
  - `/api/autopilot/recipes` now includes `per`.
- **Bugs caught while testing:**
  - Autopilot's own projects are named `autopilot-…`, so a `startsWith("#/autopilot")`
    check claimed their project links and stopped them opening. It is now the
    exact `AP_HASH` regex.
  - `openProject` in Autopilot mode had no home tab; it now switches to Simple.
  - The fourth mode button overflowed the header at phone width; the header
    now wraps under 640 px.
  - The vertical Shorts preview stretched its card; fixed.

**Files:** `static/index.html` (mode, markup, CSS, script), `web_app.py`,
`pulseforge/autopilot.py`, `tests/test_autopilot.py` (+4 tests),
`tests/test_ui.py` (the mode test now expects four modes, plus a structure
test). Backups: `~/Forge/backups/2026-09-24-pulseforge-autopilot/*.pre-mode`.

**Verified:**
- **321 passed, 1 skipped**. black and pyright are clean.
- Real previews for all four looks on a real anime picture, looked at.
- Headless Chrome screenshots against a seeded scratch copy (scratch
  `SETTINGS_PATH`, so the real settings stayed `advanced`), all looked at:
  - Make with folders filled in
  - Make with no folders (gradient samples, "add pictures to see it")
  - Library with an uploaded and a ready video
  - Earnings
  - the Browse modal (opened through a same-origin iframe test page, not app code)
  - 420 px phone width
  - a project link opening Simple mode with its tabs intact

**Not verified:**
- Clicking Make in a real window with live progress, the time-left text, and Stop.
- Clipboard copies and xdg-open (Upload pack, Open folder). Clipboard falls
  back to `execCommand` if `navigator.clipboard` is refused.
- Recent-folder chips (a fresh headless profile has none).

**Seen, not fixed:**
- When Jan has a model loaded but doesn't return usable JSON, every package waits
  out Jan's timeout before falling back to the template. Seeding two packages
  took minutes. A shorter timeout for Autopilot would help.
- Simple mode's live frame shows a broken image for non-living (drift or bars)
  projects, including Autopilot's per-song ones. This was already the case.

## 2026-09-24 (session 53): Autopilot, soft bars, better thumbnails

**What and why.** Emerson wanted something in Forge that could make money and
that people would actually enjoy watching. PulseForge already exists to feed
monetised visualiser, lofi and AMV channels, so this pass automates the slow part:
**Autopilot** turns a folder of songs into upload-ready packages, and an **Earnings**
ledger shows which style pays. The full design is in MANIFEST.md, section
"Autopilot". Nothing uploads by itself; a YouTube-API upload is listed as an
opt-in idea in `~/Forge/docs/IDEAS.md`.

**Files**:
- new: `pulseforge/autopilot.py`, `pulseforge/recipes/` (`__init__`,
  `lofi_drift`, `visualiser_bars`, `shorts_pulse`), `tests/test_autopilot.py`
- changed: `web_app.py` (autopilot routes; `/api/batch` now uses
  `autopilot.new_project`), `static/index.html` (the Autopilot tab),
  `pulseforge/config.py` (`OUTPUTS_DIR`, `AUTOPILOT_DIR`),
  `pulseforge/render.py` (`grab_thumbnail(pop=)`, title sized by the shorter
  side), `pulseforge/scenes/bars.py` (`soft` style + `flash`), `forge_app.json`,
  `MANIFEST.md`, `README.md`
- backups: `~/Forge/backups/2026-09-24-pulseforge-autopilot/`.
  `web_app.py.pre-autopilot` is the pre-edit file, rebuilt by reversing the exact
  edits because no backup was taken first. `bars.py.pre-soft` is a real pre-edit
  copy. `index.html.with-worker-draft` was taken after a helper agent had already
  added the tab. Before that the tab did not exist: its CSS block `/* ---- autopilot ---- */`, the tab
  div, the `<!-- AUTOPILOT -->` panel, the `openAutopilot()` call in the tab
  switch and the `// ---------- autopilot ----------` JS section are all new.

**Verified (run and observed)**:
- The full suite passes: **313 passed, 1 skipped** (306 before, plus 7 new in
  `test_autopilot.py`). The new tests cover:
  - the recipes name real scenes and formats
  - filename to title
  - a real `drift` render into a full package, checked with ffprobe for video and audio streams
  - the template fallback when Jan is down
  - a rerun skipping done songs
  - a failed song being recorded and retried
  - the pictures folder rotating
  - ledger totals, month replacement and validation
  - every route through TestClient
- black and pyright report 0 errors on every touched file.
- A real song (a 30 s cut of the Tollef track already in the `lol` project) with
  the anime moon picture went through all three recipes in scratch data dirs.
  Render time is roughly real time on this laptop (30 s of video in 37 s for
  lofi at 1080p, 18 s for bars, 13 s for Shorts). I looked at frames and
  thumbnails:
  - **Lofi Drift** looks good.
  - The **bars** recipes looked amateur with the old bars (a few fat additive bars
    blown out to white). That is why the `soft` style exists. After the change
    they read as a proper visualiser channel.
  - The first thumbnails were dull, because a full-frame scrim was used; `pop` fixed that.
  - The Shorts thumbnail title overflowed; it is now sized by the shorter side.
- Headless Chrome screenshots of the Autopilot tab with real packages and
  seeded earnings look right: style cards with format labels, package cards with
  thumbnails, statuses and buttons, and earnings totals and tables with recipe names.

**Not verified**:
- Pressing Make from the real UI, and watching the live job progress in a browser.
  The route and job are tested; the button wiring is only read.
- "Open folder" (xdg-open) and "Mark uploaded" (a `prompt()` dialog) in the real
  window.
- Upload text written by Jan with a model loaded. Jan had no model loaded, and
  models are deliberately not loaded from here.
- Hour-long renders. Only 30 s cuts were rendered.
- How the page looks at phone width.

### Later in session 53: Lofi Radio, and hour-long videos in two minutes

**Lofi Radio** (`recipes/lofi_radio.py`) is now the first and default style. It is
the format lofi channels actually earn on: **every song in the inbox becomes one
long mix** (60 min by default).
- Each picture becomes a living still with the built-in `lofi_lake` look (regions
  found per picture) and a `faded` grade. Pictures change with each song.
- Soft rain sits under the music, and the description gets a chapter per song.
- It needs a pictures folder, and refuses to run without one (400).

**How it is made:**
- New optional recipe fields: `per: "folder"`, `needs_art`, `look`, `ambience`,
  `tagline` (all documented in `recipes/__init__.py`).
- `web_app._autopilot_prepare` builds the shots by calling the same route
  functions the Simple editor uses (`shots_from_images`, `apply_look_to_all`), so
  a mix opens in Simple mode for fine-tuning.
- `_autopilot_chapters` reuses `get_tracklist`.
- **Speed:** a recipe with `minutes` renders the playlist **once**. Then
  `autopilot.repeat_video` stream-copies that file round to the length, with no
  re-encode. This is only safe because a pass has no fades by default. The pass
  join is a hard cut on a song change, instead of the usual dissolve.

**Verified:**
- A real **60-minute** mix of two real tracks (45 s cuts) and two anime pictures
  rendered in **126 s** (3,600.1 s long, 2.6 GB). Before the repeat step, render
  time was linear: 157 s for 3 min and 360 s for 6 min. Encoding the full length
  at 1080p runs at about real time on this power-capped CPU.
- The whole hour's audio decodes with no errors.
- I looked at frames either side of the pass join (a clean cut on the song
  change), at 30 min and at the end.
- The chapters and the now-playing caption use cleaned titles ("Time With You",
  not "01 - time_with_you").
- A mix from a generically named folder ("inbox", "songs"...) takes the recipe's
  name, and the template title reads "Lofi Radio | 1 hour of lofi beats to study
  and relax to".
- Tests: **316 passed, 1 skipped** (10 in `test_autopilot.py`, including a real
  12 s Lofi Radio render through prepare, repeat and chapters). black and pyright
  are clean.
- Every Autopilot test now stubs Jan in the fixture. One earlier run of
  `test_routes` really did call the shared Jan model; that can no longer happen.
- The **tab is reachable with no project open** (screenshot), and it has its own
  link, `#/autopilot`. That resolves the earlier open question. Screenshot of the
  four style cards and the empty states: fine.

**Still not verified:**
- The Make button and live progress in a real window.
- The xdg-open and Mark uploaded dialogs.
- Jan-written text.
- Phone width.
- The final copy change to the pictures-folder label (text only; not re-shot).
- The audio click at a pass join was not measured, only listened for in the sense
  of decode errors. Worth one listen at 1:30 in a real mix.

**Known gaps and ideas**:
- Recipe `preset` (top level) is unused. Living recipes use `look.preset`
  instead. `minutes` is applied (see above).
- With no pictures folder, Lofi Drift uses the drift scene's gradient sky. It
  works, but it is much plainer; the tab tells people to add pictures.
- The Shorts upload text uses the subtitle "shorts", which is bland.

## 2026-09-20 (hub-wide pass, session 47)

Bug fixed: `POST /api/projects/{slug}/analyse-clips` returned the `Job` object itself, which FastAPI could not serialise (a lock inside), so it was a 500 every time (five in outputs/pulseforge.log). It now returns `{job_id}` like every other job route, and `static/studio.js` reads `job_id`. The venv was missing `pluggy`, so `pytest` could not even start; installed, 306 pass, 1 skipped.

_Created 2026-09-07. First build, a v2 pass, the v3 living-still studio, then
three feature passes (v4, v5, v6)._

> Older sections moved verbatim to `WIP-archive.md` on 2026-10-07 (overhaul helper-5): from "v8 (2026-09-08) — the AMV studio" to "Browser checks".

## Still not done

- **`aurora` is still there and still not good.** Reworking or retiring it was
  deliberately left out of this pass.
- **The AMV/montage side is untouched**, as agreed — face detection for shot
  ranking still wants `opencv-python` or an ONNX model, a dependency to review.
- **No drag-to-reorder** on the shot strip or the playlist; both use ↑/↓ buttons.
- **Auto-detection is a suggestion, not segmentation.** It finds sky, water,
  foliage and bright lights by colour, position, texture and edge-connectivity.
  On a photo where a hillside is the same colour as the lake below it, the water
  region will climb the hill. Everything it produces is an ordinary brush region
  you can paint over, which is the intended workflow.
- **Region depth is differential drift, not true layer separation.** A flat
  photo has nothing behind the region to reveal, so the amount is kept small on
  purpose. For real separation, stack a transparent PNG — that path is exact.
- The `frames` effect and `sprites` emitter are tested for loading and looping
  but have not been driven with a real hand-drawn animation yet.

> Older sections moved verbatim to `WIP-archive.md` on 2026-10-07 (overhaul helper-5): from "Earlier passes" to "v1 (2026-09-07) — first build".

