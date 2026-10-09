> **2026-09-25:** the remaining work here now lives in `sessions/2026-09-25-S2-hub-shell.md`. Work from that brief.

# Hub next: queue of five builds (handoff)

Written 2026-09-25 by session s56 (autopilot-standalone-mode), which built the
home-screen sections (see `README.md` "Sections", `PROGRESS.json`
`session_56_work`). **Nothing below is started.** Every item is unbuilt and
unverified.

## How Emerson wants this run (his answers, verbatim)

- "How should I run these five builds?" → **"Solo, one per session"**
- "Which should come first?" → **"The Alto-style game"**
- "Where should the game live?" → **"Its own Forge app (Recommended)"**
- "Which hub looks do you want to switch between?" → **"Hyprland, Material 3,
  Brain Shell, Minimal / zen-ish, also an otpyion for the way it is now"**
- Then: "dont do anything yourself just make manifests and hand off for the
  next claude to do it"

His original ask (verbatim): "also reanagee the app that might be inside eahc
otehr or somthing oalso iw at diefrnt lokos to be indetstings or whatever mabye
eve make it cat liek hyperland md3 or brain shell idk have a vilsuliser and
falling petal ofr rain or lihst or whatever is in the many differnt backgrousn
and liek a zen mode with out the aps or focus stuff or liek a copy of the 2 alto
adveture gmaes that you code and looks coll and theme dependes an dmany sprts
and liikle like alto so less liek sprkits and mor elike low ish m[oly art and
its alot liek alto"

## Rules for every session in this queue

- One item per fresh session, in the order below. Start with the
  `forge-session` skill, then `crew` shared mode (ListAgents, `crew join forge`,
  claim files before editing, release at the end).
- Plan mode first; show the plan before building.
- Check usage with `python3 ~/.claude/tools/usage.py`; stop and write a handoff
  at about 95%.
- Finish per `forge-session`: tests, headless screenshots, black and pyright,
  the app's `WIP.md`, `PROGRESS.json` (replace `status`, add `session_N_work`),
  and **tick the item off in this file** with what is verified.

## Queue

### 1. Alto-style game (own Forge app) — FIRST
An endless downhill snowboarding game in the spirit of Alto's Adventure and
Alto's Odyssey. **Our own game**: original name, art and characters, no Alto
assets, names or music.
- **Look:** low-poly flat-shaded art, not pixel sprites ("less like sprites
  and more like low-ish poly art"). Layered parallax mountains, soft gradient
  skies, silhouettes. Lots of props (trees, rocks, huts, bunting, lanterns,
  animals to chase, ruins), per Emerson's "many sprites".
- **Theme-dependent:** the palette follows the Forge theme accent and
  wallpaper colours (`shared/forge_theme.py` sends them via `sendTheme`). Also
  a day/night cycle and weather (snow, rain, fog, lightning, sandstorm-style
  gusts).
- **Feel:** one-button play (jump, hold to flip), backflips chained into
  combos and a speed boost, grinds on rails and ropes, chasms, rocks, a
  run score, plus goals/levels and a relaxed "zen" endless mode.
- **Build:** `apps/<name>/` with `forge_app.json` (`"section": "play"`,
  `"fullscreen": "auto"`, unique port), FastAPI `web_app.py` plus a `static/`
  canvas game. Follow the pattern of `apps/cosmos` or `apps/arcade`. Use
  `shared/forge_sound.js` for sound, the fullscreen postMessage and F11, simple
  and advanced settings, and slider plus number fields. Saves go to
  `~/ForgeGameData/<name>/`.
- **Memory:** read the `emberfield-project` and `cosmos-project` memories and
  `user-editable-generated-assets` (Emerson wants authored art editable
  through a shared tool, so make the low-poly shapes data files, not baked
  code).
- Name candidates for Emerson to pick from (not yet asked): Drift Peaks,
  Windward, Snowline, Kumo Slopes.

### 2. Switchable hub looks
A Look setting in Settings (`shared/forge_theme.py`, Layout group), applied by
`hub/index.html` as a body class plus tokens, and passed to apps if cheap:
- **Classic**: exactly how the hub looks now (Emerson asked for this option).
- **Hyprland**: glass, gaps, gradient borders, workspace bar (close to
  Classic, but more Hyprland: sharper and denser).
- **Material 3**: tonal colours from the wallpaper, big rounded shapes,
  springy motion, an MD3 top app bar and nav.
- **Brain Shell**: copy the style of Emerson's Brain Shell. Source QML is in
  `~/.local/src/Brain_Shell/`; notes are in `~/hypr-for-windows/BRAIN-SHELL-PORT.md`.
- **Minimal**: almost no chrome, fine type, lots of space.
Keep looks declarative: one file per look (CSS tokens plus a class) in a
registry, not if-chains.

### 3. Wallpaper effects plus visualiser
- Weather and ambience layers that suit the wallpaper: falling petals, rain,
  snow, light rays or dust, fireflies. Chosen automatically from the
  wallpaper (a tag in `shared/forge_wallpapers.py` metadata, or colour
  analysis), with a manual override in Settings. Build on the `Particles`
  engine in `hub/index.html`: add kinds as a registry.
- A music visualiser on the home screen that reacts to the background music
  (`Music` in `hub/index.html`, Web Audio `AnalyserNode`). Styles: bars, ring,
  wave. Off by default; it draws only on the home screen.

### 4. Zen mode
The home screen without apps: wallpaper, the effects, the clock, and focus
tools (a pomodoro or focus timer, a one-line intention, optional ambient
sound). Entered from a bar button or key; Esc leaves. Tiles, the dock and the
bar hide.

### 5. Rearrange apps: nest related ones in groups
Use the existing group mechanism (`groups/<id>.json` plus `"group"` in each
app's manifest; README "Groups"). **Ask Emerson to confirm the pairings
first.** Candidates:
- Codec Lab + Codec Player → "Codecs"
- Dossier + Foresight → "Research"
- Board + Crew Room (+ Claude?) → "Crew"
- Media + MediaForge → "Media"
- Wallpapers inside Settings?
Also still open: `apps/jan-tune/forge_app.json` needs `"section": "assistants"`.
Its old session asked that `apps/jan-tune` be left alone, so ask Emerson.

## Done log
- 2026-09-25 ejb-63: **items 1, 2 and 3 done** (Emerson: "more like alto,
  apart from that do what is best with options for customization").
  1. Drift Peaks, `apps/driftpeaks` (see its WIP.md). Verified by tests and
     headless screenshots; fps and sound inside Forge not yet checked.
  2. Looks: `hub/looks/*.css` + Settings > Look (Classic default). Verified:
     tests/test_hub_looks.py, screenshots of all five, hub suite 106 PASS.
     Brain Shell is its frame, notch bar, dot workspaces and colours, on the
     hub's own layout (not a full port of its panels).
  3. Particles petals/rain/snow/rays/fireflies/dust + "Match the wallpaper"
     (name words, then colours; per-file override in
     ~/.config/forge/ambience.json) + Particle amount; visualiser bars/ring/wave
     + size, off by default. Verified: tests/test_hub_ambience.py, screenshots.
     The visualiser has not been seen with real music yet.
  Also: jan-tune got `"section": "assistants"`. Next: item 4, zen mode.
