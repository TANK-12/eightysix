# Files

A file manager inside Forge (A18 in `sessions/2026-09-26-S9-terminal-files-code.md`).
Port 8458, section "system". Stdlib-only backend (FastAPI + uvicorn in its own `.venv`).

## Layout
- `fsops.py`: every rule. The path guard (`resolve()`: only home and the drive mount
  parents `/run/media/$USER`, `/media/$USER`, `/mnt`), trash-only removal (`gio trash`,
  no unlink/rmtree in the module; a test reads the source to keep it that way),
  copy/move jobs with byte progress, name search bounded by count and time,
  thumbnails (the desktop's own freedesktop cache when current, otherwise
  ffmpeg at nice 15 into `~/.cache/forge-files/thumbs/` as small JPEGs).
- `web_app.py`: thin HTTP layer. Every `/api` route needs `X-Forge: 1` or `?t=<token>`
  (token only for `<img>`/`<video>` src; fetched from `/api/session` with the header).
- `static/`: the page (`app.js`, `app.css`), shared Forge kit.

## Features
Sidebar from `~/.config/user-dirs.dirs` + `~/Forge` + mounted drives (rechecked every
10 s) + Trash; breadcrumb (double-click or Ctrl+L to type a path); back/forward/up
(also mouse side buttons); list and grid (Ctrl+G; Ctrl+wheel sizes tiles); sort by
name/size/type/modified; search (Ctrl+F); multi-select (click, Ctrl, Shift, rubber
band, Ctrl+A, type-ahead); copy/cut/paste (Ctrl+C/X/V, paths also go to the system
clipboard); rename (F2); new folder (Ctrl+Shift+N); move to trash (Delete); open with
the default app (Enter/double-click, `xdg-open`); drag and drop onto folders, sidebar
places and breadcrumb parts (Ctrl while dropping = copy); hidden files (Ctrl+H);
preview pane (F3): image, video, audio, text.

Links in: `#path=/folder`, `#select=/folder/file`, `#view=grid|list`.

## Checks
- `.venv/bin/python -m pytest -q tests` (unit + HTTP, includes a real `gio trash` into a
  sandbox trash via `XDG_DATA_HOME`).
- `.venv/bin/python tests/check_ui.py`: drives the real page in headless Chrome
  (Flatpak) against a sandbox folder; prints PASS/FAIL lines.
