# Wallpapers: work in progress

## Status (2026-09-15, session 33)

Built in one session, at the user's request for a wallpaper app that indexes
the collection, hides duplicates (keeping the highest resolution), has
favourites, and sets a wallpaper for the desktop and/or Forge.

### Verified

- `pytest tests`: 25 pass. `pyright`: 0 errors. `black` run.
- Forge adopted the app while running (no restart) and the backend answered on
  8442.
- Real index of the real folder: 236 pictures, 0 unread, 3 hidden copies,
  matching an independent scan (`brain-shell-default-1.png` behind its 2x
  upscale; `minimal-beton-building.jpg` behind `room-dark.png`;
  `sunset-mountain-beautiful.jpg` behind the byte-identical `cyberpunk1.jpg`).
- Real `POST /api/apply {desktop: true}` with the current desktop picture:
  caelestia accepted it in 0.4 s.
- Screenshots (headless Firefox via `apps/pulseforge/tools/shot.py`) of the grid
  and of the side panel with an uncropped preview.

### Not verified

- "Set in Forge" from inside a real Forge window (the hub receiving the theme
  message). The API half is tested; the message path is the same one Settings
  already uses.
- Starring from inside Forge and seeing the strip update in Settings (covered
  by tests of both endpoints, not watched live).


## S21 (2026-09-27): particles per wallpaper
The panel has "Particles on this wallpaper": Match (automatic), any kind, or
Off. GET/POST /api/particles, saved by file name in
~/.config/forge/ambience.json through forge_theme.set_wallpaper_particles.
When it is Forge's wallpaper the answer carries the new theme, which the page
posts to the hub. Verified: tests/test_web.py (30 passed). Not screenshotted.

## 2026-10-07 (overhaul helper-3): nothing changed here
"The Forge desktop" in the overhaul brief is `~/Forge/desktop/` (particles.py,
the GNOME extension), not this app. Its power work (rests when covered,
reduced tier when mostly covered or the machine is busy) is in
docs/library/power/2026-10-07-hub-desktop-power.md. Wallpapers' own tests:
see below.
