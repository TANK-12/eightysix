# Forge change manifest

> **Frozen on 2026-09-26.** Nothing is added here any more: session briefs in
> `~/Forge/sessions/`, `PROGRESS.json` and git history took over. Paths below
> are as they were then; the root `PLAN-*.md`, `IDEAS.md` and
> `DESKTOP-REACH.md` files have since moved (see `~/Forge/README.md`,
> "Directory layout").

A running record of every change, written as each one lands, so any change can
be found and undone without the conversation that made it. Newest session
first. Each entry lists the files touched, where the pre-edit copy is, and
whether the result was **verified** (run and observed) or only **reasoned**
about.

## Session 53 (2026-09-24): PulseForge Autopilot, laptop tune-up, ideas backlog

- **PulseForge Autopilot** (new tab): songs folder → upload-ready packages, plus an
  earnings ledger.
  - New files: `apps/pulseforge/pulseforge/autopilot.py`,
    `apps/pulseforge/pulseforge/recipes/*`, `apps/pulseforge/tests/test_autopilot.py`.
  - Changed: `apps/pulseforge/web_app.py`, `static/index.html`,
    `pulseforge/config.py`, `pulseforge/render.py` (`grab_thumbnail` `pop=`,
    portrait title size), `pulseforge/scenes/bars.py` (`soft` style, `flash`),
    `forge_app.json`, `MANIFEST.md`, `README.md`, `WIP.md`.
  - Pre-edit copies are in `backups/2026-09-24-pulseforge-autopilot/`. The
    `web_app.py` copy was rebuilt by reversing the edits; the `index.html` copy
    already contains the new tab. See the PulseForge WIP entry for how to remove it.
  - **Verified:** 313 tests, a real song through all three recipes with frames
    inspected, and tab screenshots. **Not verified:** the Make button in a live
    window, Jan-written text, long renders.
- **Later in the session:** Lofi Radio (the whole inbox as one hour-long mix of
  living stills with rain and chapters). The one-pass render plus a stream-copy
  repeat made a 60-min video in 126 s instead of about an hour. `#/autopilot` deep
  link. Autopilot tests now stub Jan. **Verified:** 316 tests, a real 60-min mix.
- **Then Autopilot became its own mode:** a fourth mode button with Make,
  Library and Earnings views, folder Browse, real look previews and an upload
  pack. There are new `/api/autopilot/browse|scan|preview|package/{slug}/text`
  routes. Backups are the `*.pre-mode` files in the same backup folder.
  **Verified:** 321 tests and screenshots of every view. **Not verified:**
  clipboard and xdg-open in a real window.
- **`IDEAS.md`** (new): civilisation text sim run by agents, a paper-trading
  sandbox (real-money trading and mining deliberately declined, with reasons),
  and an opt-in YouTube upload.
- **Outside Forge:** `~/LAPTOP-TUNEUP.md` records about 4 GB of caches cleared
  (yay, pip, uv, selenium, thumbnails), what was kept on purpose, and a sudo
  command left for Emerson.
- **Memory:** `prefer-inline-over-subagents` (two Sonnet workers burned about 5.5× the
  main session's token rate and were stopped; their partial work was kept and
  finished inline).

## Session 44 (2026-09-17) -- PanelForge on a second account

No hub files changed except this file and `PROGRESS.json`. All app files are
new or app-local; there is no backup folder because nothing pre-existing
outside `apps/panelforge` and `apps/claude` was edited.

### 1. PanelForge detect and scene pipelines
- New: `apps/panelforge/panelforge/detect/{style,merge,pipeline}.py`,
  `api/detect.py`, `scene/{understand,cast,pipeline}.py`, `api/scene.py`,
  `tests/test_detect_pipeline.py`, `tests/test_scene_pipeline.py`.
  Edited: `detect/ocr.py`, `detect/bubbles.py` (lettering cues),
  `scene/registry.py` (OpenVINO iGPU backend), `HANDOFF.md`, new `README.md`
  and `WIP.md`. **Verified:** chapter 1 detect run and the unit tests;
  iGPU timings. **Reasoned only:** the scene run on chapter 1 (still running
  at the stop).
- Helpers: `styles/depth3d.py`, `render/effects.py`, `render/fixture.py`,
  `api/render.py`, `tests/test_render_{depth3d,api}.py` (helper-7);
  `audio/{dsp,emotion,voices,kokoro_engine,script}.py`, `api/audio.py`,
  `tests/test_audio_{dsp,cues,line_emotion,script}.py` (helper-9);
  `apps/claude/runner.py`, `web_app.py`, `tests/` (helper-8, cut off before
  its docs). `openvino` installed into `apps/panelforge/.venv`.

## Session 36 (2026-09-16)

Backups for this session: `backups/2026-09-16-cosmos-puzzles/` (every edited
file, plus `PROGRESS.before-handoff.json` and `MANIFEST.before-handoff.md`).

### 1. Cosmos: orbit puzzles

- New files in `apps/cosmos/`:
  - `static/core/nbody3d.js`, `puzzle.js`, `levelgen.js`
  - `static/modes/puzzles/` (`mode.json`, `mode.js`, `view.js`)
  - `tools/solve_level.mjs`
  - `tests/test_puzzles.py`
  - `tests/js/{nbody3d,puzzle,levelgen,levels}.test.mjs`
  - `manifests/session-02.json`
- Edited in `apps/cosmos/`:
  - `web_app.py` (levels, progress and sounds endpoints)
  - `static/index.html` (loads `/shared/forge_sound.js`)
  - `static/app.css` (the `.pz-*` block)
  - `forge_app.json`, `README.md`, `WIP.md`, `MANIFEST.json`,
    `manifests/roadmap.json`
- Data outside the app:
  - `~/ForgeGameData/cosmos/levels/` (11 files)
  - `~/ForgeGameData/sounds/cosmos-*.json` (5 files)
  - `~/ForgeGameData/cosmos/puzzle-progress.json`, created on first play
- Nothing in `forge.py`, `hub/`, `shared/`, the map or the sandbox changed.
- Undo:
  - delete the new files and the data above
  - restore the edited files from the backup folder
- **Verified:**
  - Tests: pytest 38 pass, `node --test` 59 pass.
  - Checks: black and pyright 0 errors.
  - Headless Chrome screenshots of every puzzle screen.
  - A WebKitGTK window ran at 48 fps with Jan loaded.
- **Not verified:** real play, real mouse gestures, inside the running Forge
  window, the sounds by ear.

### 2. PROGRESS.json split

- `PROGRESS.json` was 179 KB. `session_2_work` to `session_29_work` moved
  unchanged into the new `PROGRESS-archive.json` (checked entry by entry).
- Undo: restore `PROGRESS.before-handoff.json` and delete the archive.

### 3. Cosmos: huge galaxy, saved discoveries, power

- The user reported "stars dont save". Level stars did save; the Galaxy
  playground saved nothing. Galaxy discoveries now save at once
  (`explore` in `~/ForgeGameData/cosmos/puzzle-progress.json`).
- `explore-galaxy.json` regenerated:
  - 40 star systems on spiral arms, about 8,400 units across
  - 92 planets and 10 belts
  - a galactic glow
  - pre-change copy in `backups/2026-09-16-cosmos-galaxy/`
- Edited in `apps/cosmos/`:
  - `web_app.py`, `static/core/puzzle.js`, `static/modes/puzzles/mode.js`,
    `view.js`, `static/app.css`
  - tests, `README.md`, `WIP.md`, `MANIFEST.json`, `forge_app.json`,
    `manifests/session-02.json`
- Pre-edit copies are all in `backups/2026-09-16-cosmos-galaxy/`.
- **Verified:**
  - Tests: pytest 45 pass, `node --test` 61 pass.
  - An isolated test server saved and merged a discovery.
  - Screenshots of the galaxy.
  - Power, flying the galaxy with the GPU idle: 12.0 W in Power saver,
    14.5 W on Smooth, 16.4 W before.
- **Not verified:** the user's running Cosmos backend still has the old code
  until it is restarted; nobody has flown the big galaxy by hand.

## Session 35 (2026-09-15)

Backups for this session: `backups/2026-09-15-session35/` (`PROGRESS.json`,
`MANIFEST.md`).

### 1. New app: Cosmos (astronomy map and gravity games)

- New app `apps/cosmos/` (port 8446, order 15, `"fullscreen": "auto"`),
  with:
  - its own `.venv` (48 MB, same package versions as Wallpapers)
  - `forge_app.json` with a `manifest` block
  - `README.md`, `WIP.md`, `MANIFEST.json`, `manifests/`
  - pytest and Node tests
- Nothing in `forge.py`, `hub/` or `shared/` changed; the app is discovered.
- Data outside the app:
  - `~/ForgeGameData/cosmos/scenarios/` (6 presets)
  - `/run/media/ejb/AN3/Cosmos/stars/` (HYG v4.4, 13.6 MB source plus
    3.1 MB built)
  - `~/.cache/forge/cosmos/` (3.1 MB copy)
- Undo:
  - delete `apps/cosmos/`, `~/ForgeGameData/cosmos/`,
    `~/.cache/forge/cosmos/` and `/run/media/ejb/AN3/Cosmos/`
  - restore `PROGRESS.json` and `MANIFEST.md` from the backup folder
- **Verified:**
  - Tests: pytest 20 pass, `node --test` 21 pass. Planet positions agree
    with JPL Horizons to 0.5 degrees.
  - Checks: black and pyright 0 errors.
  - Headless Firefox screenshots of the menu, the map (solar system, Earth,
    nearby stars, galaxy) and the sandbox.
- **Not verified:** inside a real Forge window (Forge was not restarted),
  real pointer gestures, frame rate on the integrated GPU.

## Session 33 (2026-09-15)

Backups for this session: `backups/2026-09-15-session33/` (`forge.py`,
`README.md`, `PROGRESS.json`, a tarball of `hub/`, `shared/` and
`apps/settings/`, and the original Hyprland files under `hypr/`).

### 0. Regression check after the cut-off session 32

- All test suites pass: hub tests (fast close, app discovery, CSS tokens),
  Dossier 253, Foresight 104, Keymap 8, Power 66, Settings 20.
- All 14 backends answered HTTP 200 on their ports in the running Forge.
- The errors in `outputs/*.log` are old "address already in use" lines from
  earlier launches, not from the current one.
- **Verified.**

### 1. Super+T opens GNOME Terminal; Super+E opens one file manager

Outside Forge, in the desktop's Hyprland config.

- Cause: the Caelestia session loads `hyprland/keybinds.lua` and then
  `caelestia-keybinds.lua`, and both bound Super+T and Super+E. Super+E
  launched Dolphin (base) and Thunar (Caelestia) together.
- `~/.config/hypr/custom/variables.lua`: `terminal = "gnome-terminal"`. This
  file is the documented override slot, loaded right after the base
  variables, so it also changes Super+Return and Ctrl+Alt+T.
- `~/.config/hypr/caelestia-keybinds.lua`: first attempt removed Caelestia's
  own Super+T and Super+E binds. That broke the Keymap app's test (and its
  ability to edit those keys through `vars.kbTerminal`), caught by the
  end-of-session regression run. Final version: Caelestia `hl.unbind`s the
  shared Super+T and Super+E (for whatever keys `vars.kbTerminal` and
  `vars.kbFileExplorer` hold) and then binds its own, as before.
- `~/.config/hypr/variables.lua` (Caelestia's): `terminal = "gnome-terminal"`,
  `fileExplorer = "dolphin"`. Super+E opens Dolphin only; Super+Shift+E still
  opens the file manager picker.
- Undo: restore `backups/2026-09-15-session33/hypr/*.orig` (also beside the
  files as `*.bak-1789421762`), then run `hyprctl reload`.
- **Verified:** `hl.unbind` tested on an unused combo (bound, seen, unbound,
  gone). After `hyprctl reload`: no config errors; exactly one Super+T, one
  Super+E and one Super+Return. GNOME Terminal, run through Hyprland's own
  exec, opened a new window. Keymap tests 8 pass. Not verified: a physical key
  press.

### 2. Wallpapers app, and favourites in Settings

- New app `apps/wallpapers/` (port 8442, order 98, role `wallpapers`), with
  its own `.venv` (48 MB, same package versions as Settings), `forge_app.json`
  including a `manifest` block, `MANIFEST.md`, `README.md`, `WIP.md`, tests.
- New shared module `shared/forge_wallpapers.py`: index, fingerprints,
  look-alike copies, favourites, preview, desktop setters.
- `shared/forge_theme.py`: `list_wallpapers` now includes sub-folders (named
  `sub/picture.jpg`) and skips hidden folders such as `.git`. Top-level names
  are unchanged, so the saved `"wallpaper": "anime2.jpg"` still works.
- `hub/index.html`: new `{forge: "open", role | app}` message so one app can
  open another without the hub naming either.
- `apps/settings/`: `GET /api/favourites`; thumbnail route accepts sub-folder
  names; the Wallpaper card gains a favourites strip and an "Open Wallpapers"
  button. The old grid is kept, folded into "Quick picker for Forge's
  wallpaper", so nothing it did is lost.
- Undo: delete `apps/wallpapers/` and `shared/forge_wallpapers.py`; restore
  `hub/`, `shared/forge_theme.py` and `apps/settings/` from
  `backups/2026-09-15-session33/hub-shared-settings.tgz`.
- **Verified:** Wallpapers 25 tests, Settings 22 tests, pyright 0 errors on the
  touched Python, `node --check` on both scripts. Live: 236 pictures indexed,
  3 copies hidden, matching an independent scan; desktop set through caelestia.
  Screenshots of the grid, the side panel, and the Settings favourites strip
  (from a scratch Settings backend with a scratch config). **Not verified:**
  the "Open Wallpapers" button and live theme change inside a real Forge window.
  The Settings backend Forge is running still has the old code until Forge is
  restarted.

### 3. Apps follow the wallpaper, and many more settings

- `shared/forge_theme.py`: the settings table grew from 10 to 32 entries, each
  with `label`, `group` and optional `unit`/`help`/`labels`, so Settings builds
  its form from the table. New `surfaces()` (panel, border and text colours in
  the wallpaper's hue, or the classic greys), `FONTS`, `NEUTRAL_SURFACES`.
  `theme()` now passes every ordinary setting through without naming it.
- New settings: panel colours (wallpaper or plain), tint, text contrast, font,
  size inside apps, window border, wallpaper behind apps, shadows, animation
  length, seconds and date in the bar, CPU/memory/battery chips, dock mode and
  icon size, big clock, greeting, tile width, start full screen, apps fill the
  screen, top edge reveal and its delay.
- Dock default is now "only at the bottom edge", at the user's request (one
  bar, the top one; the dock shows on hover and the other modes stay).
- `shared/forge_chrome.js`: apps take the tinted surfaces, the font and the
  size. `hub/index.html`: applies the same surfaces and every look setting.
- `apps/settings/static/`: the hand-written glass and clock cards were replaced
  by cards generated from the table; every control they had is still there.
- **Verified:** Settings 31 tests (including 7:1 text and 4.5:1 quiet-text
  contrast on every panel across modes, tints and six accents), black, pyright
  0 errors; screenshot of the generated form; screenshot of Power inside the
  real hub with tinted panels. `hub/theme.js` regenerated (old copy in the
  backups folder).

### 4. Smart full screen and the top-edge bar

- New manifest field `"fullscreen": "auto"`, read by `forge.py` into the status
  the hub gets. Added to `arcade`, `emberfield`, `codec-player` (originals in
  `backups/2026-09-15-session33/manifests/`).
- `hub/index.html`: `immersive` mode (automatic) beside the existing
  `chromeless` (asked for); both slide the bar and dock away and fill the
  window; a 6 px top edge reveals the bar with every app's number and the
  clock. `{forge: "open"}` message from change 2 lives here too.
- `forge.py`: Start full screen fullscreens the window at launch without
  hiding the hub's bar, and in that state Esc stays with the apps; F11 still
  toggles.
- **Verified:** `tests/browser/run.sh` gained `hub_immersive`, which runs the
  real `hub/index.html` in headless Chrome: 21 checks pass. Hub discovery test
  covers the manifest field. **Not verified:** start full screen in a real
  launch (needs a Forge restart), and the reveal under a real mouse.

### 5. Faster open: apps start on demand

- Measured first: every backend imports in 0.21-0.76 s (5.0 s of CPU for all
  15 together), the theme applies in 0.04 s, closing already takes about
  0.2 s, and the running Forge holds about 2.1 GB. The user was offered "keep
  Forge ready in the background" (instant open and close, memory kept) and
  chose "start apps on demand" instead.
- New setting `start_apps` (Home screen card): `demand` (default) or `launch`.
- `forge.py`: `BackendManager(lazy=True)` leaves every backend `idle`;
  `start_one(name)` starts one, once; apps added while open wait to be opened.
  The hub asks through a WebKit script message handler named `forge`.
- `hub/index.html`: opening an idle app sends `{start: name}` and shows the
  starting card; Try again on a failed or idle app asks again.
- **Verified:** `test_on_demand_nothing_starts_until_the_hub_asks`; four new
  `hub_immersive` browser checks; the WebKit message channel itself in an
  off-screen GTK WebView. **Not verified:** a real Forge launch with the new
  code (the running Forge is still the old code until it is restarted).

### 6. Browser app, real web views, Firefox

- New `forge_views.py` beside `forge.py`: `ViewHost` lays real WebKit views
  over an app's workspace (message protocol in its docstring). `forge.py` now
  puts the hub in a `Gtk.Overlay` and creates the host lazily on the first view.
- New app `apps/browser/` (port 8444, order 13, role `browser`,
  `fullscreen: auto`): tabs, address bar with search engines, bookmarks and
  history, start page, downloads, Import from Firefox (bookmarks, history,
  cookies; read-only copies), open in Firefox, and a command queue
  (`/api/agent/*`) for the Claude panel. Own `.venv`, manifest block,
  `README.md`, `MANIFEST.md`, `WIP.md`.
- `hub/index.html`: passes `{forge: "view"}` messages on with the sending
  frame's name and window coordinates, shows only the open app's views, and
  insets them for the revealed bar and the peeking dock.
- Records: `~/.local/share/forge/browser/`; WebKit profile:
  `~/.local/share/forge/browser-profile` (created by the smoke check, empty of
  imported data).
- **Verified:** Browser 22 tests; `tests/test_views.py` 3 off-screen tests;
  `hub_immersive` browser checks for the message passing; the off-screen smoke
  check `tests/smoke_browser_window.py` (real hub + real Browser page + live
  backend + example.com, read back and photographed); read-only counts from the
  real Firefox profile. **Not verified:** on screen in a restarted Forge.

### 7. Claude panel: Claude Code inside Forge, using the Browser

- New app `apps/claude/` (port 8445, order 14, role `claude`): conversations
  over a streaming `claude -p` process each (`runner.py`), an MCP server giving
  Claude the Forge Browser (`browser_mcp.py`), attachments (paperclip, drop,
  paste, and the page open in the Browser), links in answers open in the
  Browser, per-conversation folder, model and permission level (default: read
  and browse only). Own `.venv`, manifest block, `README.md`, `MANIFEST.md`,
  `WIP.md`, tests with `tests/fake_claude.py`.
- `tests/smoke_browser_window.py` gained `FORGE_SMOKE_HOLD` to keep the Browser
  page alive for another program to drive.
- Data: `~/.local/share/forge/claude/`.
- Spend during this work: $0.04 probe of the CLI's stream-json, $0.09 real
  end-to-end turn.
- **Verified:** 15 tests (free, fake CLI); the real turn in which Claude used
  `tabs`, `open` and `read` on the Browser and answered correctly; screenshots
  of the chat page (a layout bug found and fixed). **Not verified:** on screen
  in a restarted Forge.
