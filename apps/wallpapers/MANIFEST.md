# Wallpapers: manifest

The long form of the `manifest` block in `forge_app.json`: what the app does,
what it needs, and what it lacks.

## Summary

A full-window picker over `~/Pictures/Wallpapers` and its sub-folders. It
indexes resolution and a visual fingerprint for every picture, hides
lower-resolution look-alike copies behind the best one, keeps favourites, and
sets a picture as the desktop wallpaper, Forge's wallpaper, or both.

## Features

| feature | detail |
|---|---|
| Index | Resolution, bytes, mtime and a 256-bit difference hash per picture in `~/.cache/forge/wallpaper-index.json`; re-read only on change; niced background thread at start. |
| Hidden copies | Same aspect (3 %) and hash within 12 bits = one picture. Highest resolution shown, then largest file. Never moved or deleted. |
| Favourites | Star on each tile and in the panel; sorted first; own view; shown in Settings. `~/.config/forge/wallpapers.json`. |
| Set wallpaper | Desktop, Forge, or both. Desktop via caelestia / awww / swww. Forge via the shared `wallpaper` setting plus a live theme message to the hub. |
| Browse | Search (`/`), sort by name, resolution, date or size; filter by shape and minimum resolution; tile-size slider; uncropped preview; badges for what is in use on the desktop and in Forge. |

## API (`/api`)

| method | path | purpose |
|---|---|---|
| GET | `/wallpapers` | Everything: rows with `width`, `height`, `hash`, `bytes`, `mtime`, `favourite`, `duplicate_of`; index progress; Forge's and the desktop's current picture. |
| POST | `/reindex` | Start an index pass if none is running. |
| GET | `/thumb?name=` | 480x270 cropped thumbnail (shared cache with Settings). |
| GET | `/preview?name=` | Whole picture, at most 1600 px, cached in `~/.cache/forge/previews`. |
| POST | `/favourite` | `{name, on}`; answers the full favourites list. |
| POST | `/apply` | `{name, desktop, forge}`; answers each result and Forge's new theme when it changed. |

Names are paths relative to the folder and are only accepted if the folder
listing contains them, so `../` cannot reach outside it.

## Dependencies

- Required: fastapi, uvicorn (in `.venv`), ImageMagick `magick`.
- Optional: `caelestia` (current desktop shell), `awww`, `swww`.

## Data

- `~/.config/forge/wallpapers.json`: favourites (user data).
- `~/.config/forge/settings.json`: Forge's wallpaper (shared with Settings).
- `~/.cache/forge/`: index, thumbnails, previews (safe to delete).

## Known gaps

- Copies are hidden, not removed, by the user's choice.
- The first index of ~240 pictures takes a couple of minutes.
- Setting the desktop through caelestia also changes the desktop's colour
  scheme, because that is what caelestia does.
