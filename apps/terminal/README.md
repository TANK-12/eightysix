# Terminal

Real shells inside Forge (A17 in `sessions/2026-09-26-S9-terminal-files-code.md`).
Port 8459, role `terminal`, section "system".

## Layout
- `ptyhost.py`: one `Term` per tab. The shell (`$SHELL -l`) runs on a pseudo-terminal
  started with `subprocess` + `setsid -c` (safe in a threaded server, and it gives the
  shell a controlling terminal so Ctrl+C, job control and resize work). Output is read on
  the asyncio loop; the last 256 KB is kept so a reloaded page gets its screen back.
  Closing a tab sends SIGHUP (then SIGTERM after 1.5 s) to the shell's process group.
  The app's own `.venv` is scrubbed from the shell's PATH/VIRTUAL_ENV.
- `web_app.py`: `/api/terms` (list/create/delete, need `X-Forge: 1`) and `/ws/{id}`
  (needs the per-run token from `/api/session` **and** an Origin equal to this server).
- `static/`: xterm.js 6.0 + fit + web-links + search addons vendored in `static/vendor/`
  (MIT, licences kept beside them; Emerson OK'd 2026-09-26).

## Keys
Ctrl+Shift+C copy, Ctrl+Shift+V paste, **plain Ctrl+V goes to the program** (Claude Code
pastes images that way), Ctrl+Shift+T / Ctrl+Shift+W new/close tab, Ctrl+Shift+F find in scrollback, Ctrl+PageUp/PageDown
switch, Ctrl+= / Ctrl+- text size, Ctrl+click opens a link, right-click menu, middle-click
a tab closes it. Ctrl+0..9 and Ctrl+Tab belong to Forge (caught by GTK).

Links in: `#cwd=/some/folder` opens a new tab there (Files' "Open terminal here").

## Checks
- `.venv/bin/python -m pytest -q tests`: auth refusals, real shell I/O, resize,
  scrollback replay, exit, close, foreground program name.
- `.venv/bin/python tests/check_ui.py [--shots DIR]`: headless Chrome via
  `~/Forge/tests/cdp_driver.py`: typing, Ctrl+V as byte 0x16 in raw mode, Ctrl+C,
  stty size, htop on the alternate screen, tabs, font size, reload reattach, exit.
