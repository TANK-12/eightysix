# Wallpapers

A Forge app for the wallpaper collection in `~/Pictures/Wallpapers` (and its
sub-folders). It fills the whole window with the pictures, reads each one's
real resolution, hides lower-resolution copies of the same picture, keeps
favourites, and sets a picture as the **desktop** wallpaper, **Forge's**
wallpaper, or **both**.

Port 8442. Opened from the dock or home screen, or from the "Open Wallpapers"
button in Settings (the hub finds it by `"role": "wallpapers"`).

## Layout

| file | what it is |
|---|---|
| `web_app.py` | FastAPI backend: listing, index thread, thumbnails, previews, favourites, apply. |
| `static/` | The page: toolbar, grid, side panel. `app.js` does all filtering and sorting in the browser. |
| `../../shared/forge_wallpapers.py` | The logic: index, fingerprints, look-alike copies, favourites, desktop setters. Shared with Settings. |
| `../../shared/forge_theme.py` | Forge's own wallpaper setting, thumbnails, the folder listing and the hub's `theme.js`. |
| `tests/` | `test_index.py` (shared module), `test_web.py` (API). |
| `forge_app.json` | Wiring plus a `manifest` block; `MANIFEST.md` is the long form. |

## How the pieces work

- **Index**: `~/.cache/forge/wallpaper-index.json`. Built niced in a thread at
  backend start; a picture is only re-read when its size or mtime changes. The
  page polls `/api/wallpapers` every 2 s while it runs.
- **Hidden copies**: a 256-bit difference hash per picture. Same shape (aspect
  within 3 %) and within 12 bits = the same picture. Highest pixel count wins,
  then the larger file. Nothing on disk is moved or deleted; "Show hidden
  copies" displays them.
- **Favourites**: `~/.config/forge/wallpapers.json`. Starred tiles sort first in
  every view; Settings shows them as a strip.
- **Desktop**: first installed tool in `forge_wallpapers.DESKTOP_SETTERS`
  (`caelestia wallpaper -f`, then `awww img`, then `swww img`). Add a tool with
  one row.
- **Forge**: saved as the `wallpaper` setting; the API returns the new theme
  and the page posts it to the hub, so Forge changes at once.

## Run and test

```sh
cd ~/Forge/apps/wallpapers
FORGE_SHARED_DIR=~/Forge/shared .venv/bin/python -m uvicorn web_app:app --host 127.0.0.1 --port 8442
.venv/bin/python -m pytest tests -q          # 25
pyright --pythonpath ./.venv/bin/python web_app.py ../../shared/forge_wallpapers.py tests
```
