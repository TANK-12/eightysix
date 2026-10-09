# Forge

One desktop window hosting the local tools under `apps/`: **NovelForge**
(long-form novel writing), **MediaForge** (subtitles, video, media library),
**AI Studio** (image and video generation), **Codec Lab** (experimental anime
video codecs), **Codec Player** (plays the `.acv` files Codec Lab produces),
**Arcade** (seven small games + four experiments, one game driven by Jan),
**PulseForge** (music-reactive videos, visualisers and beat-cut AMV montages
for YouTube), the game-studio pair **Emberfield** + **PixelForge**, and
**Dossier** (sourced factual portfolios on political and business figures,
parties, countries, companies, alliances and wars), plus **Power** (Cool / Auto / Performance modes for this laptop,
auto-switching on the charger, and what starts at login), **Settings** (the
wallpaper, colours and look of Forge itself), **Wallpapers** (the wallpaper
collection with favourites and hidden copies, set for the desktop and/or
Forge), **Browser** (real web pages inside Forge with your Firefox bookmarks,
history and logins), **Claude** (Claude Code inside Forge, using the Browser,
with file attachments) and **Study Companion** (built in a parallel session;
see its own folder). Apps are discovered from their `forge_app.json`, so this
list is whatever is in `apps/`.

Forge opens on a **Hyprland-style home screen**: your wallpaper, a top bar of
numbered app workspaces with status dots, a clock and CPU / RAM / battery,
launcher tiles you can search by just typing, and a dock. Apps open as
gapped, rounded windows with a gradient border over a blurred copy of the
wallpaper, and slide in and out like workspaces. **Ctrl+1..9** opens an app,
**Ctrl+0** goes home, **Ctrl+Tab** cycles, **Ctrl+R** reloads, **F11** is full
screen - all of them work while an app has focus.

Since session 33 (all changeable in Settings): Forge **starts full screen**;
games, the player and the Browser **fill the screen by themselves** (manifest
`"fullscreen": "auto"`), and touching the **top edge** brings the bar back
with every app's number and the clock; the dock waits at the **bottom edge**
instead of showing all the time; each app's backend **starts the first time
it is opened**; and every app's panels are **tinted by the wallpaper**. What
each session changed, with what is verified, is in its brief in `sessions/`
and in `PROGRESS.json`; the old change log (to 2026-09-24) is frozen in
`docs/archive/`.

Launch it with the **Forge** entry in the app launcher, or:

```
python3 /home/ejb/Forge/forge.py
```

**Forge is the only launcher entry.** Each tool also still has its own
`.desktop` file under `~/.local/share/applications/`, but they are all
`NoDisplay=true` now — hidden from Super-key search, kept only so
`AnimeCodecPlayer.desktop` still registers the `.acv` file association. The
standalone launchers (`run.py`, `app_window.py`, the codec lab's
`desktop_app.py`) still work from a terminal for debugging and A/B comparison.

**Claude sessions working on Forge** each keep a brief in
[`sessions/`](sessions/README.md) (`<date>-<slot>-<topic>.md`, with a State
section they keep current), and talk to each other and to Emerson on the
**Board** app: the `forge` board, with an Everyone / Me / Crew talk / Sessions
view. Start there to see who is doing what.

---

## 1. How it fits together

Forge is a **thin orchestrator**. It contains no application logic at all.

Each tool keeps its own FastAPI backend, its own virtualenv and its own port,
exactly as it ran standalone. `forge.py` starts them, shows one GTK + WebKit2
window with the home-screen shell, and stops every backend again when the
window closes. (The diagram below still shows the original sidebar layout; the
wiring is unchanged - one iframe per tool - only the shell around it is new.)

```
        forge.py  (GTK window, no browser chrome)
             |
             |  loads hub/index.html over file://
             |
        +----+----------------------------+
        |  sidebar  |   <iframe> per tool  |
        +-----------+----------------------+
                          |
   +--------+--------+--------+---------+---------------+
   |        |        |        |         |               |
  :8421   :8422    :8430    :8431     :8432
  novel-   media-   ai-      codec-    codec-
  forge    forge    studio   lab       player
  (own     (own     (own     (~/anime-codec-lab,
   venv)    venv)    venv)    shared venv, via "root")
```

The diagram shows the original five; the port range now runs to **8440**:
`:8433` Arcade, `:8434` Emberfield, `:8435` PixelForge, `:8436` PulseForge,
`:8437` Dossier, `:8438` Foresight, `:8439` Keymap, `:8440` Power, `:8441`
Settings, `:8442` Wallpapers, `:8443` Study Companion, `:8444` Browser, `:8445`
Claude (each its own `apps/<name>/.venv`).

The Browser is the one app whose pages are **not** in its iframe: websites
refuse to be framed, so `forge.py` lays real WebKit views over the Browser's
page area (`forge_views.py`), driven by messages that pass through the hub.
See "Real web pages are native views" in section 4. Power is the only app with a root-owned helper; see
`apps/power/README.md` before touching its sudoers rule.

Dossier is the only app that writes its data outside `$HOME`: its library lives
on the AN3 USB drive at `/run/media/ejb/AN3/DossierData/`, because it grows
without limit and the internal disk is nearly full. It falls back to
`~/DossierData-local/` and says so in its header when the drive is absent.

AI Studio runs on **8430** inside Forge, not 8420 — 8420 is what its
standalone `app_window.py` binds, and a Forge-launched copy sharing that port
failed with `address already in use`. Codec Lab and Codec Player both live in
the separate `~/anime-codec-lab` repo and are pulled in with the `root`
manifest field (see section 3); they share that repo's one `.venv`.

Each tool is iframed rather than inlined. AI Studio already had a complete web
frontend, so an iframe let it join with zero changes; the other two got fresh
frontends written for them. Inlining all three into one shared-DOM page is a
possible future step — it would allow real cross-tool features — but iframes
were the low-risk way to get everything under one roof.

### Why the apps have web frontends at all

All three were originally customtkinter desktop apps, and customtkinter itself
was the main source of their sluggishness: the old apps did one Tk textbox
insert **per streamed token**. The port kept every business-logic module
completely untouched (none of them ever imported customtkinter — they were
already separated behind plain `log` / `progress` / `stream` / `should_stop`
callbacks) and replaced only the delivery layer.

The actual performance fix is in the SSE endpoint: it **batches** events in
~120ms windows so a burst of tokens becomes one network message.

---

## 2. Directory layout

```
Forge/
  forge.py              The launcher. Discovers apps, starts them, owns the window.
  forge_views.py        Real WebKit views over an app's workspace (the Browser).
  README.md             This file.
  CLAUDE.md             Rules and reading order for Claude sessions.
  PROGRESS.json         Session-by-session history and open questions.

  docs/                 Hub-wide docs, so the root stays clean:
    IDEAS.md            Ideas backlog.
    DESKTOP-REACH.md    Desktop reach and multi-account project.
    plans/              Hub-wide plans (PLAN-*.md); each says at the top
                        whether it is built.
    archive/            Frozen records, e.g. the change log to 2026-09-24.
                        App-specific plans live in apps/<app>/docs/.

  apps/
    novelforge/         One self-contained tool...
    mediaforge/         ...each with its own .venv, source, static/ and
    ai-studio/          ...a forge_app.json manifest.

  shared/
    forge.css           THE palette and component styles for all three tools.
    forge.js            THE shared frontend helpers (SSE, jobs, toasts, modes).
    forge_chrome.js     THE full-screen control and the theme receiver. One
                        script tag per app.
    forge_theme.py      THE look: settings, wallpaper copies, colour, theme.js.
                        Used by forge.py at launch and by the Settings app.
    forge_wallpapers.py The wallpaper index, look-alike copies, favourites and
                        desktop setters. Used by Wallpapers and Settings.

  hub/
    index.html          The home-screen shell: bar, tiles, dock, app windows.
    status.js           Generated at launch. See "The file:// rule" below.
    status.json         Same data, for debugging only.
    theme.js            Generated at launch and by Settings. Same rule.

  pyrightconfig.json    Lets pyright resolve shared/ for forge.py.

  outputs/              One log per backend: novelforge.log, mediaforge.log, ...
  backups/              Pre-edit copies (ignored by git, see .gitignore).
  sessions/             One brief per Claude session (see sessions/README.md).
```

**User data lives outside this folder and must stay there.** Both apps resolve
it through `Path.home()`:

- `~/NovelMakerData/` — projects, series, style library, TTS voices
- `~/MediaForgeData/` — settings, `file_index.db`, organiser undo manifests,
  the thumbnail cache
- `apps/ai-studio/models/` — ~12GB of checkpoints (this one *is* inside)
- `~/.config/forge/settings.json` — Forge's own look (Settings app)
- `~/.cache/forge/` — wallpaper copies, blurred copies, palettes, thumbnails,
  the wallpaper index and previews; safe to delete, all regenerated
- `~/.config/forge/wallpapers.json` — wallpaper favourites
- `~/.local/share/forge/browser/` — Browser bookmarks, history, tabs;
  `~/.local/share/forge/browser-profile/` — its cookies and site storage
- `~/.local/share/forge/claude/` — Claude panel conversations and attachments

---

## 3. Adding an app

Drop it in `apps/` with a `forge_app.json` beside a `.venv` and a FastAPI app.
**Nothing in `forge.py` needs editing** — the app list is discovered, not
declared, and the hub sidebar is built from the same data.

`apps/<yourapp>/forge_app.json`:

```json
{
  "name": "yourapp",
  "label": "Your App",
  "tagline": "What it does, one short line",
  "port": 8423,
  "module": "web_app:app",
  "src_dir": ".",
  "accent": "#e0a458",
  "order": 4
}
```

| field | meaning |
|---|---|
| `name` | Internal id. Also the log filename (`outputs/<name>.log`). |
| `label` / `tagline` | Shown on the app's home-screen tile, dock tooltip and the top bar. |
| `accent` | The app's colour: its tile and dock icon. Inside the app, the wallpaper's colour replaces it while Settings has "use this colour in every app" on. |
| `icon` | Optional. One emoji for the tile and the dock. Without it, the first letter of the label. |
| `role` | Optional. Lets the hub find a special app without naming it: `"settings"` is what the gear in the top bar opens; an app opens another with `postMessage({forge: "open", role})` (Settings opens `"wallpapers"`, Claude opens `"browser"`). |
| `fullscreen` | Optional. `"auto"`: the hub fills the screen with this app when Settings' "Apps fill the screen" is on Smart (the default). Arcade, Emberfield, Codec Player and Browser say so; tools leave it out. |
| `group` | Optional. The id of a `groups/<id>.json`, e.g. `"pixel-games"`. The app then has no tile of its own: it sits behind that group's single tile, which opens a chooser. Its window, its `#app=<name>` link, its full screen and its lazy start are unchanged. An id with no file is ignored and the app keeps its tile. |
| `section` | Optional. The id of a `sections/<id>.json`, e.g. `"create"`: the heading the app's tile sits under on the home screen. No section, or an id with no file, puts it under "Other". A group takes the same field in its own file. |
| `port` | Must be unique. Deliberately different from the tool's own standalone port so a Forge-launched backend and a directly-launched one never collide. |
| `module` | The uvicorn target, e.g. `web_app:app`. |
| `src_dir` | Working directory for uvicorn, relative to the app root. `.` for most, `src` for AI Studio. |
| `order` | Position in the workspace bar, the tiles and the dock - and so its Ctrl+number. |
| `ready_timeout` | Optional, seconds to wait for the port to answer. Default 180. |
| `start_at_launch` | Optional, `true` starts the backend when Forge launches even while Start apps is on demand, for an app with work to pick up on its own (the Claude app carries on conversations a restart cut off). |
| `root` | Optional. Absolute path (or `~`-relative) to a codebase kept **outside** `apps/`. The `apps/<name>/` folder is then just a stub holding this manifest. Used by `codec-lab` and `codec-player`, whose code stays in the separate `~/anime-codec-lab` git repo. `.venv`, `src_dir` and `module` all resolve against `root`. |
| `manifest` | Optional. A nested object describing the app itself, not its wiring: `summary`, `features[]` (`{name, description}`), `data_dir`, `services[]`, `dependencies` (`{required[], optional[]}`), `standalone_launch`, `api_base`, `known_gaps[]`, `docs[]`. `forge.py` never reads it — it exists so a session (or a future hub feature) can answer "what does this app do / need / lack" from the manifest instead of re-deriving it from the code. NovelForge, MediaForge, Arcade, Codec Lab and Codec Player carry one, each mirrored by a longer `MANIFEST.md` in the same folder. |
| `voice` | Optional. `{"listens": true, "speaks": true}`: the app takes speech (a mic button) and/or speaks replies through the shared Voice app (`apps/voice`, port 8467). The Voice app lists exactly the apps that carry this field, each with its own speech-to-text model, voice, speed and speak-replies setting (`~/.config/forge/voice.json`); nothing in `forge.py` reads it. Models live in `shared/voice_registry.json`; apps use `shared/forge_voice.py` or `shared/forge_voice.js`. |

### Sections: headings on the home screen

A section is one file in `sections/`, discovered like a group:

```json
{ "label": "Create", "icon": "🔨", "order": 1, "blurb": "Write, draw, animate and make music videos" }
```

An app (or a group, in its `groups/<id>.json`) joins with `"section": "create"`.
`forge.py` writes them to `hub/status.js` as `window.FORGE_SECTIONS`, sorted by
`order`; the hub draws one heading per section with a tile count and a
collapse arrow, a filter chip per section beside the search box, and puts
anything with no known section under "Other" at the end. With no section
files at all the headings and chips hide and the home screen is one grid.
Collapsed sections and the chosen chip are remembered in the page's
localStorage. A search looks through every section, collapsed or not. The six
today: create, watch, play, assistants, research, system. Sections are read
at page load, so a new section file shows after a Forge restart.

The home screen also has a "Jump back in" row of the last six apps opened
(localStorage), and the top bar numbers only apps opened this session (Ctrl+1..9
still reach every tile by its number). When more apps are open than the bar has room for, their icons scroll
sideways in their strip (the wheel works too), a "+N" button beside it counts the ones out of sight and opens
the overview (with a dot when one of them has news or failed). The clock, settings and the rest of the tray
always stay on the bar: if it is still too full, the app controls' labels, the title, the strip's last icon, the
zen/background buttons and reload give way in that order (Relay task 121; `tests/browser/hub_bar_overflow_harness.js`,
docs/library/forge/2026-10-09-hub-top-bar.md). Particles (Settings, Home screen):
Off, Soft drift, Lively, Forge embers, Constellation; a click on the home
screen throws a burst of sparks. Checked by `tests/test_app_sections.py`
and the `hub_sections` block of `tests/browser/run.sh`.

### Groups: one tile for several apps

A group is one file in `groups/`, discovered exactly like an app:

```json
{
  "id": "pixel-games",
  "label": "Pixel games",
  "tagline": "Pick a pixel world to play",
  "icon": "👾",
  "accent": "#9d7bff",
  "order": 7
}
```

An app joins with one line in its own `forge_app.json`: `"group": "pixel-games"`.
Nothing in `forge.py` or `hub/index.html` names a group or an app. The hub shows
the group as a single tile, dock icon and number (its `order` places it among
the apps); opening it shows a chooser of member cards, and picking one opens
that app's normal window. A group with one member still shows the chooser, and a
group nobody joins is not shown at all.

`forge.py` writes the groups beside the apps in `hub/status.js`
(`window.FORGE_GROUPS`), because every key of `window.FORGE_STATUS` is treated
as an app. Groups are read when the page loads, so a group file added while
Forge is running appears after a restart — unlike a new app, which is adopted
live.

### Jan: each app picks its own models and gives the memory back

`shared/forge_jan.py` is the one place that knows how to choose a Jan model,
load it on demand and release it when nothing is using it (Emerson asked for
this on 2026-09-16, "cause ram saving": two idle models held about 9.8 GB).
It is stdlib-only, so every app's virtualenv can import it. Wiring an app is
three lines beside its FastAPI app:

```python
sys.path.insert(0, os.environ["FORGE_SHARED_DIR"])   # already set inside Forge
import forge_jan
jan = forge_jan.mount(app, "myapp", roles=("chat",))  # adds /api/jan/settings
```

and one guard around each call, which is what marks the model as this app's:

```python
with jan.using(jan.model_for("chat")):
    ...post to Jan...
```

The app's choices live in `~/.config/forge/jan/<app>.json`: a model per role
(empty means "whatever Jan has", the old behaviour) and `idle_minutes`, after
which a model **that no app or session has used at all** is unloaded; the next
request loads it again. Jan itself is never started, stopped or reconfigured.
`shared/forge_jan.js` draws the settings — `ForgeJan.panel(element)` — so no app
writes Jan settings code of its own.

Wired so far: Arcade, Study Companion. Dossier, Foresight, NovelForge,
PulseForge and MediaForge still use their own Jan code and are next;
`apps/dossier/janidle.py` is the original this helper generalises.

An app that lives outside `apps/` can't reach `shared/` with a relative path,
so `forge.py` exports **`FORGE_SHARED_DIR`** to every backend. Mount it as
`/shared` when it's set (`codec-lab`'s `server.py` and `codec-player`'s
`web_player.py` show the pattern); fall back to a relative hop or skip it when
it isn't, so the app still runs standalone.

An app whose `.venv/bin/python` or `src_dir` is missing is skipped at launch
and its workspace shows a "not installed" card instead of a broken iframe.

### The frontend contract

A new app's `static/index.html` should use the shared kit so it looks and
behaves like the others:

```html
<link rel="stylesheet" href="/shared/forge.css">
<style>
  /* The ONLY tokens an app overrides. The neutrals are what make the three
     tools read as one product. */
  :root { --accent: #e0a458; --accent-2: #c98b3d; --on-accent: #1a1206; }
</style>
...
<div id="toast" class="toast hidden"></div>
<script src="/shared/forge_chrome.js"></script>
<script src="/shared/forge.js"></script>
<script> /* your app */ </script>
```

`forge_chrome.js` is the only one of those that needs no wiring at all: it
mounts itself on load. If the page has a button with `id="go-fullscreen"` it
uses that one; otherwise it injects a small floating button in the corner. Put
the id on a button in your own header if you have somewhere sensible for it.

It is a separate file from `forge.js` on purpose. The apps that most want a
full-screen button are the ones that do NOT load `forge.js` — AI Studio and
PixelForge have their own DOM helpers, and `forge.js`'s `val`/`toast`/`checked`
globals would collide with them.

`forge_chrome.js` also provides `window.ForgeVisible`: the hub posts
`{forge: "visible", visible: bool}` to every mounted app whenever the
workspace changes or the window hides, `ForgeVisible.on` is that flag (true
standalone), and `"forge-visible"` fires on `document` with `detail.visible`.
A page that polls or animates should slow down or stop while it is false —
Jan Hollow drops from 5 requests a second to 1, Power from every 5 s to every
30 s. Standalone in a browser nothing arrives and the page runs as before.

A page that reads the PS5 pad itself (Exo Lab's game) posts
`{forge: "pad", native: true}` once it runs and `native: false` on
`pagehide`. While that app is in front the hub sends `{pad_native: true}` to
`forge.py`, which writes 0 to `$XDG_RUNTIME_DIR/forge/pad-focus`, so
`forge-pad.service` sends no mouse or keys and the game's presses are not
doubled. A new frame starts as not native. App frames are allowed `gamepad`:
WebKitGTK refuses `getGamepads()` in a cross-origin frame without it.

Real web pages (YouTube in Media, every tab in Browser) are native WebKit
views the hub lays over the app's page area: an app posts
`{forge: "view", op: "create", id, url, rect}` and then `rect`, `navigate`,
`show`/`hide`, `close`; the hub stamps the owner and forwards to
`forge_views.py`. Any app may own views; the Browser and Media do.

and its backend must serve that directory — copy the `/shared` mount from any
existing `web_app.py`. It must be mounted **before** the catch-all `/` static
mount, which would otherwise swallow the path.

---

## 4. Rules that are easy to break

These are all bugs that have actually happened here. Read them before touching
the streaming or the hub.

### One EventSource per job

Job events travel through a `queue.Queue` on the server, which is
**single-consumer**. A second `EventSource` on the same job does not mirror the
stream — it *steals half of it*, including, unpredictably, the terminal `done`
event, so the panel hangs forever with its buttons disabled.

This has been written as a bug twice: once in NovelForge's audiobook panel and
once in MediaForge's storage scan. If a panel needs log text **and** progress
**and** a status line, they are all callbacks on one `forgeStream()` call.

### The file:// rule

`hub/index.html` is loaded from disk over `file://`, whose origin is opaque.
**Any `fetch()` it makes for a sibling file is blocked as cross-origin**, with
no visible error.

This is why `forge.py` writes `hub/status.js` containing
`window.FORGE_STATUS = {...}` and the shell reads that global — a `<script>`
tag has no such restriction. An earlier version used `fetch("status.json")`,
silently got `{}`, and rendered "this tool isn't ported into Forge yet" for
**every** workspace while all three backends were running perfectly.

For the same reason the shell cannot probe the backend ports itself, so
`forge.py` polls them natively and pushes the result in via
`window.forgeSetStatus(...)`. An `<img>` probe is not a substitute: it cannot
tell a refused connection from a 404, since both fire `onerror`.

### color-scheme: dark

WebKitGTK renders native controls — `<select>` popups, number spinners,
checkboxes, `<audio>` players, scrollbars — with the **GTK theme**, not with
page CSS. Under a light GTK theme that means a white popup, while the
near-white `color` the page sets on `<select>` is inherited by its `<option>`s:
white text on white. MediaForge has 30 selects, so most of its tabs had
unreadable dropdowns.

`color-scheme: dark` in `shared/forge.css` fixes this for every native widget
at once. Don't remove it, and keep it in `hub/index.html` too (that page can't
use the shared sheet — see below).

### The hub can't use shared/forge.css

`shared/` is served over http by each *app's* backend. The hub shell loads from
`file://` before any backend is necessarily up, so it keeps its own copy of the
palette. **If you change the palette in `shared/forge.css`, change it in
`hub/index.html` too.**

### The theme reaches apps by postMessage, and apps go see-through

The hub reads `hub/theme.js` (a script global, for the file:// reason above).
Apps are on their own http origins and cannot read it, so the hub posts
`{forge: "theme", theme}` into each iframe when it loads and whenever Settings
changes something; `shared/forge_chrome.js` receives it and sets `--bg`,
`--panel`, `--panel-2` (and the accent, if unified) **inline on `<html>`**,
which beats an app's own `:root`. `--bg` becomes translucent and `<html>`'s own
background is cleared - both paint `var(--bg)`, and two translucent layers come
out nearly solid.

The frosted look behind apps is a **pre-blurred JPEG**, not `backdrop-filter`.
Live blur redraws every frame and is heavy on the Iris Xe; the blurred copy is
made once per wallpaper in about 0.1 s. Arcade loads neither shared script, so
it stays opaque.

### A class with `display` beats `[hidden]`

`.chip { display: inline-flex }` overrides the browser's own `[hidden]` rule,
so the top bar's stat chips and reload button showed on the home screen while
marked hidden. `hub/index.html` has `[hidden] { display: none !important; }`
for this; keep it.

### Closing hides first, then stops everything at once

Measured with all thirteen backends: each exits 0.15-0.2 s after SIGTERM. The
old `stop_all()` stopped them one after another, which kept the window on screen
for about 2.2 s. The window now hides on `delete-event`, every process group is
sent SIGTERM together, and anything still running after 3 s is SIGKILLed and
reaped. `tests/test_fast_close.py` checks both the parallel stop and the
deadline.

### Workspace shortcuts are caught by GTK, not the page

Once an app is open its iframe has keyboard focus, so a keydown listener in the
hub never hears Ctrl+1. `forge.py` catches Ctrl+0..9 and Ctrl+Tab in its
`key-press-event` handler and calls `window.forgeKey(...)` in the hub.

### A top-level `const` is not on `window`

Every app's Full screen button did nothing for a while, and the cause is worth
remembering because it is silent. `ForgeChrome` was declared as a top-level
`const` at the bottom of `shared/forge.js`. In a classic script — which all of
these are — `var` and function declarations become properties of `window`, but
`let`, `const` and `class` go into the global *lexical* environment and never
reach `window`. Dossier's `if (window.ForgeChrome)` guard was therefore always
false, no error was thrown, and the button was simply inert.

If a shared file means to publish a global, it must assign it:
`window.ForgeChrome = ForgeChrome;`. `shared/forge_chrome.js` does, and says so
in a comment, because this is not a mistake you see by reading the call site.

### An undefined CSS token silently paints black

Dossier's mind map drew its labels with `fill: var(--fg)`. Nothing in Forge has
ever defined `--fg`. An unresolved `var()` with **no fallback** makes the whole
declaration invalid, so `fill` reverted to its initial value — black — on a
near-black canvas, and the labels were simply unreadable with nothing in the
console. `python3 tests/test_css_tokens.py` scans every app stylesheet for this
and needs no per-app configuration.

### Errors aren't always JSON

An unhandled server exception returns plain text, so `res.json()` throws and
replaces the real error with a confusing parse error. Use
`errText(res, fallback)` from `forge.js`.

### Apps start when first opened

With Settings' "Start apps" on demand (the default), `forge.py` starts no
backend at launch; every app shows `idle`. Opening one makes the hub call
`window.webkit.messageHandlers.forge.postMessage(JSON.stringify({start: name}))`
and `BackendManager.start_one()` starts it once. That message channel is the
only way the page talks to `forge.py`; `forge.py` talks back with
`run_javascript`. An app added while Forge runs also waits to be opened.

### Real web pages are native views, not iframes

A site refuses to be framed, so the Browser's pages are WebKit views that
`forge.py` owns (`forge_views.py`), laid over the rect the Browser page reports.
The page sends `{forge: "view", op, ...}` to the hub; the hub stamps the
sending frame's name as `owner` (never trusting the message), moves the rect
into window coordinates and passes it on. Only the open app's views show, and
views shrink out of the way of the revealed top bar and the peeking dock,
because nothing the hub draws can sit on top of a native view. Anything drawn
over the page area by an app (a menu, a dialog) must hide the view while open.
The WebKit profile is created on the first view, never at launch.

### The Browser and Claude backends only answer `X-Forge: 1`

A web page open in the Browser can reach `127.0.0.1`. The private routes
(Firefox cookies, the command queue, Claude conversations) require a custom
header, which a cross-origin page cannot send without a CORS preflight these
apps never grant.

### Version control

`~/Forge` became a git repo on 2026-09-26 (no commits yet, no remote).
`.gitignore` keeps out everything that is generated, downloaded or written at
runtime: `__pycache__`, `node_modules`, logs and PID files, `outputs/`,
`backups/`, `hub/status.js(on)`, `apps/ai-studio/{models,bin,outputs}/`
(about 2.8 GB), `apps/code/openvscode-server/` and `apps/code/data/` (holds a
connection token), and per-app state such as `apps/keymap/data/backups/`.
Those files exist only on this disk, so they are not covered by git. Until
there is commit history, still copy a file into `backups/` before a large
rewrite. Moving the apps into this folder required rewriting the
absolute shebangs in every `.venv/bin/*` console script — if you move things
again, remember that.

---

## 5. Debugging

Run one backend by hand:

```bash
cd /home/ejb/Forge/apps/novelforge && .venv/bin/python -m uvicorn web_app:app --host 127.0.0.1 --port 8421
cd /home/ejb/Forge/apps/mediaforge && .venv/bin/python -m uvicorn web_app:app --host 127.0.0.1 --port 8422
cd /home/ejb/Forge/apps/ai-studio/src && ../.venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 8430
cd ~/anime-codec-lab && FORGE_SHARED_DIR=/home/ejb/Forge/shared .venv/bin/python -m uvicorn server:app --host 127.0.0.1 --port 8431      # Codec Lab
cd ~/anime-codec-lab && FORGE_SHARED_DIR=/home/ejb/Forge/shared .venv/bin/python -m uvicorn web_player:app --host 127.0.0.1 --port 8432  # Codec Player
cd /home/ejb/Forge/apps/arcade && FORGE_SHARED_DIR=/home/ejb/Forge/shared .venv/bin/python -m uvicorn web_app:app --host 127.0.0.1 --port 8433   # Arcade
```

(Standalone AI Studio still uses 8420 via `app_window.py` — the Forge copy was
moved to 8430 so both can run at once. sd-server's own ports, 1234/1235, are
still shared, so don't run standalone and Forge AI Studio at the same time.)

Always `python -m uvicorn`, never `.venv/bin/uvicorn`: NovelForge's venv is
`--system-site-packages` and resolves uvicorn from system site-packages with no
console-script wrapper, so that path does not exist.

Checks that don't require running anything:

```bash
python3 -m py_compile web_app.py                    # backends
# frontends: extract the <script> block and run node --check on it
```

Gotchas:

- `pgrep -f forge.py` returns both a bash wrapper and the real `python3`
  process. SIGTERM the one whose `comm` is `python3`.
- `pkill ... ; ps ...` pipelines in this shell sometimes exit 144 spuriously.
  Verify with a separate plain `ps aux | grep ...`.
- `~/anime-codec-lab` is now a Forge app (Codec Lab / Codec Player) but is
  still its own git repo and can still be run on its own. A uvicorn from there
  on port 8731/8732 is its standalone mode, not Forge's.
- The desktop apps still work: `run.py` in novelforge and mediaforge,
  `app_window.py` in ai-studio, `desktop_app.py` in the codec lab. Useful for
  A/B comparison.

---

## 6. Where the important code is

| path | what |
|---|---|
| `forge.py` | Backend discovery, concurrent startup, the GTK window, status and stats push, workspace shortcuts, the parallel close. |
| `hub/index.html` | Home screen: top bar, tiles, search, dock, app windows, theme application, status cards. |
| `forge_views.py` | `ViewHost`: real WebKit views over an app's workspace, the view message protocol, cookie import, downloads. |
| `shared/forge_theme.py` | The settings table (labels, groups, limits; Settings builds its form from it), wallpaper copies and blur, palette and accent, wallpaper-tinted `surfaces()`, `hub/theme.js`. |
| `shared/forge_wallpapers.py` | Wallpaper index, difference-hash look-alikes, favourites, desktop setters. |
| `apps/settings/` | The Settings app: a thin API over `forge_theme.py`, favourites strip, generated settings cards. |
| `apps/wallpapers/`, `apps/browser/`, `apps/claude/` | Each has a `README.md`, `MANIFEST.md` and `WIP.md` saying what is verified. |
| `shared/forge.css` | Palette, every shared component, the `color-scheme` fix. |
| `shared/forge.js` | `forgeStream` (the one SSE implementation), `pollJob`, `errText`, `toast`, `ForgeMode`, `initTabs`, `initClearButtons`, `fileThumb`. |
| `shared/forge_chrome.js` | `ForgeChrome` — the sidebar postMessage, real fullscreen, the `f` key and Escape; `ForgeVisible` — is this app the one on screen. Self-mounting. |
| `shared/forge_attach.py`, `shared/forge_attach_api.py`, `shared/forge_attach.js` | Files and pictures in any chat box: safe names, no-overwrite save into `attachments/YYYY-MM-DD/`, the `Attached files:` note; `Attachments(root).router()` gives an app `POST /api/attach` and `/api/attach/paste-image`; `ForgeAttach.wire({box, picker, upload, onAdd})` does paste, drop and the picker. Used by Relay, Mission, Board and Crew Room (Relay task 118). |
| `shared/forge_mangafetch.py` | Headless Flatpak Chrome over the DevTools protocol, canvas capture and page checks: the engine behind PanelForge's site fetchers and MediaForge's manga downloader (through `apps/panelforge/tools/fetch_cli.py`). |
| `apps/media/` | Media: library player, YouTube and Crunchyroll as native views, yt-dlp downloads. `README.md` and `WIP.md` say what is verified. |
| `tests/` | `test_app_discovery.py`, `test_fast_close.py`, `test_css_tokens.py`, `test_views.py` (off screen) and `browser/run.sh` (which also runs the real `hub/index.html` as `hub_immersive`). `smoke_browser_window.py` drives the whole Browser path off screen against a live backend. Run them after touching the launcher, the hub or any stylesheet. |
| `apps/*/web_app.py` | Each tool's REST + SSE surface. Business logic is in the packages beside it and is **untouched** by the port. |
| `apps/novelforge/novelforge/engine.py` | The generation loop. Modified only for two bug fixes. |
| `apps/mediaforge/mediaforge/` | Completely untouched by the port. |
| `apps/ai-studio/src/model_manager.py` | Owns the two sd-server child processes. |

Long-running work in every backend follows the same shape: a `Job` object with
a background thread and a `queue.Queue`, drained by
`GET /api/jobs/{id}/events`, plus `GET /api/jobs/{id}` for status and result
and `POST /api/jobs/{id}/stop` to cancel.

## PS5 controller (Forge pad)

`shared/pad/forge_pad.py` runs as the user service `forge-pad.service` and turns a
DualSense into a mouse and keyboard, only while a Forge window has focus. Forge writes
`$XDG_RUNTIME_DIR/forge/pad-focus` (1 or 0) from `forge_popout.track_pad_focus`, which
works on GNOME and Hyprland. With no flag file the service falls back to `hyprctl`.
The flag is also 0 while the main window's app in front reads the pad itself (a page
that posted `{forge: "pad", native: true}`, see the frontend contract above).
The left stick moves the pointer and the right stick scrolls. Cross is left click, square
is right click, circle is Esc and triangle is Enter. The d-pad sends the arrow keys.
L1 is Alt+Space, R1 is Alt+M (visualiser settings) and PS goes home (Ctrl+0).
L2 and R2 go back and forward, Create is Tab, Options is F11 and L3 is middle click.
The buttons and the pointer speed (`mouse_speed`, 8) are set in
`shared/pad/forge_pad.json`: edit that file, then run `systemctl --user restart forge-pad`.
Tests: `tests/test_forge_pad.py` (4/4 on 2026-10-03). Not yet checked with real
presses, because Forge needs a restart to start writing the focus flag.
