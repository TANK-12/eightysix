# S9: Terminal, Files and a VS Code-compatible editor — session "Tools"

Written by S7 (session ejb-47) on 2026-09-26 from Emerson's message: "also
build a terminal app and file explorer perfect app and a vs code compatible
app for forge". Three new Forge apps. They touch no hub files: each one is a
new folder in `apps/` with a `forge_app.json`, which Forge discovers by
itself (see `~/Forge/README.md` for the manifest fields and frontend
contract; copy the shape of a small app such as `apps/settings/`).

Suggested model: Opus. The rules in `~/Forge/sessions/README.md` "Rules for
every session in this wave" apply (board, claims, no subagents, disk is short,
nothing installed without Emerson picking from a list with real sources, no
Forge restart without asking). Join with slot S9:
`python3 ~/.claude/skills/crew/crew.py join forge <you> --role solo --slot S9`.
Other sessions today: S7 (hub, `2026-09-26-S7-forge-polish.md`) and S8
(Claude app + Browser, `2026-09-26-S8-claude-enjoy-browser.md`).

## Owns
`apps/terminal/`, `apps/files/`, `apps/code/` (new). Pick free ports (grep
every `forge_app.json` for `"port"`). Put the tiles in the "system" or a
fitting `sections/` id. Each app gets its own `.venv`, `tests/`, `README.md`,
`WIP.md`.

## Ledger
- **A17** "terminal app" -> a real terminal inside Forge: a shell on a
  pseudo-terminal (Python `pty`, stdlib) behind a WebSocket, drawn by a
  proper terminal emulator in the page, so colours, cursor keys, `htop`,
  `vim` and resizing work. Tabs, copy/paste, font size, the Forge theme's
  colours. Candidate to vendor (needs Emerson's OK, list it on the board):
  xterm.js, MIT, https://github.com/xtermjs/xterm.js (the terminal inside
  VS Code), plus its fit addon. [core]
- **A18** "file explorer perfect app" -> a file manager good enough to use
  daily: sidebar (Home, Desktop, Downloads, Documents, Music, Pictures,
  Videos, the AN3 drive when plugged in, `~/Forge`), breadcrumb path, list
  and grid views with thumbnails for images, sort, search, multi-select,
  copy/cut/paste, rename, new folder, move to trash (never a hard delete;
  `gio trash`), open with the default app (`xdg-open`), drag and drop
  between folders, hidden files toggle, a preview pane (image, text, audio,
  video). Stdlib only on the backend. [core]
- **A19** "a vs code compatible app" -> an editor Emerson can use like
  VS Code inside Forge. Needs his pick before anything is installed; post
  these on the board and wait (build A17/A18 meanwhile):
  1. OpenVSCode Server (Gitpod), MIT,
     https://github.com/gitpod-io/openvscode-server: upstream VS Code served
     to a web page; extensions from Open VSX. Closest to real VS Code. A
     release tarball, check its size first (disk is short).
  2. code-server (Coder), MIT, https://github.com/coder/code-server: the
     same idea, more widely used, Open VSX extensions. Also a large download.
  3. Monaco editor (Microsoft), MIT,
     https://github.com/microsoft/monaco-editor: only VS Code's editor
     component, built into a small Forge app with a file tree and the A17
     terminal. VS Code keys, themes and syntax colouring, but no extensions.
     Smallest.
  Whichever he picks, it opens files from A18 ("Open in Code") and uses the
  Forge theme where it can. [core]
- Constraints: nothing that works today removed; stdlib-first; headless
  screenshots of each app; tests for backends (file operations above all:
  trash not delete, no path escapes).

## State
- Session name: Tools (S9, ejb-ea). Emerson's picks (2026-09-26, in S9's terminal): A19 = OpenVSCode Server; A17 = vendor xterm.js.
- A18 Files: done+checked. apps/files, port 8458. 32 pytest, tests/check_ui.py 13/13 PASS, screenshots looked at. Menus: Open in Code, Open terminal here (hub `hash` from S7).
- A17 Terminal: done+checked. apps/terminal, port 8459. 10 pytest, tests/check_ui.py 16/16 PASS (Ctrl+V reaches raw-mode programs as 0x16, htop, tabs, reload keeps shells), htop screenshot looked at.
- A19 Code: done, one gap. apps/code, port 8460, OpenVSCode Server 1.109.5. 8 pytest pass; browser check passes everything except that Restricted Mode still shows (see apps/code/WIP.md "Open" #1, needs Emerson's call).
- None of the three have been seen in the real Forge window: they need a Forge restart (Emerson's or Hub's call).
- Shared: ~/Forge/tests/cdp_driver.py drives headless Chrome for app checks.

## Quick start for a fresh session finishing Tools' work
1. Read this file, then apps/code/WIP.md, apps/terminal/WIP.md, apps/files/WIP.md ("Improve next"/"Open").
2. Checks, all from the app folder: `.venv/bin/python -m pytest -q tests` then `.venv/bin/python tests/check_ui.py`.
3. Undone, in order: (a) Code Restricted Mode (ask Emerson: accept it, or keep hunting); (b) after a Forge restart, open all three inside Forge and screenshot them; try `claude` in Terminal with an image on the clipboard (Ctrl+V); (c) the WIP "Improve next" lists.
