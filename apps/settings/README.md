# Settings

How Forge looks and behaves: the wallpaper, the accent colour, the glass, the
gaps and corners, animations, the clock and what Forge opens on. Runs at
<http://127.0.0.1:8441> inside Forge, or standalone:

```
FORGE_SHARED_DIR=/home/ejb/Forge/shared \
  .venv/bin/python -m uvicorn web_app:app --host 127.0.0.1 --port 8441
```

## How it fits

This app owns no theme logic. Everything lives in **`shared/forge_theme.py`**,
because `forge.py` needs the same code at launch:

| What | Where |
|---|---|
| The settings, with defaults and limits | `forge_theme.SETTINGS` - one line per setting |
| The user's choices | `~/.config/forge/settings.json` |
| Wallpaper copies, blurred copies, palettes, thumbnails | `~/.cache/forge/` - safe to delete |
| The theme the hub reads at launch | `hub/theme.js`, a script global like `status.js` |

A change travels two ways at once:

1. **Live.** The page saves it, gets the resulting theme back and posts
   `{forge: "theme", theme}` to the hub. The hub restyles itself and passes
   the part an app needs to every open app, where `shared/forge_chrome.js`
   applies it. Nothing restarts.
2. **Next launch.** Saving also rewrites `hub/theme.js`.

The hub finds this app through `"role": "settings"` in `forge_app.json`, not by
its name, so the gear in the top bar keeps working if the app is renamed.

## Wallpaper

By default Forge **follows the desktop wallpaper**, read from
`~/.local/state/caelestia/wallpaper/path.txt`. Picking one here stops following.
The picker lists `~/Pictures/Wallpapers`. A thumbnail is only served for a name
in that listing, never for a path built from the URL.

The originals are 5-28 MB. Forge draws a 2560 px JPEG copy (about 200 KB) and
a pre-blurred copy for behind apps, both made once per picture with ImageMagick
in about 0.3 s. Without ImageMagick the original is used unblurred.

Thumbnails are warmed in a background thread when this backend starts: current
wallpaper first, one at a time, at `nice 15`. Measured: the first 21 (the first
rows of the grid) were ready 5 s after start. Cached, so later launches do
nothing.

## Colour

Taken from the wallpaper's own palette (`magick ... -colors 8`), not by running
matugen - matugen applies its templates, so running it would rewrite the
desktop's theme too. The most saturated colour wins, weighted a little by how
common it is, and is lifted to a lightness that reads on dark glass. A grey
wallpaper gets the default blue rather than an invented hue.

## Layout

The Layout section (in the section list, just above About) sets how Settings
itself looks: the section list as a sidebar, tabs or one long page, comfortable
or compact spacing, normal or wide, and which sections are pinned to the top
(the star beside each one). Kept in this browser's localStorage under
`forge.settings.layout`. Until 2026-09-27 this was a pop-up behind a Layout
button in the header; Emerson found it floating over the top right, so it
became a section. Checked by `tests/browser/settings_sections_harness.js`
(run with `tests/browser/run.sh`).

## Tests

```
.venv/bin/python -m pytest tests -q
```

34 tests, no network. ImageMagick is used for real where a test needs it.

## Speed and detail, and `also` (2026-09-27)

A setting in `shared/forge_theme.py` may carry `"also": [GROUP, ...]`: the same control is drawn again in those cards, after the card's own settings, labelled "<its group>: <label>". Both controls follow one setting. Speed and detail uses it to collect every frame-rate and particle-detail slider. The page re-reads the settings on every theme message from the hub (a change made in the Power app, or the charger being plugged in or pulled out) and marks the plugged-in or battery row that is in use now, from the theme's `power_pairs`.

## Sliders applied on release (2026-10-07)

A field whose spec in `shared/forge_theme.py` says `"apply": "release"` (App
size, Text size, Icon size) only previews while its slider is dragged: the
number and preset name update, and `"preview": "text_size"` shows the size on
this page through `ForgeChrome.previewTextSize`. Nothing is saved or sent to
the hub until release (`change`), then once. App size zooms the whole Forge
window, this page included, so applying it mid-drag moved the slider under
the pointer and the size flip-flopped. The Preset slider works the same way.
Drag check: `tests/browser/check_size_drag.py` in the Forge root;
measurements in `docs/library/forge/2026-10-07-size-sliders.md`.
