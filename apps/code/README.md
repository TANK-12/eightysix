# Code

VS Code inside Forge (A19 in `sessions/2026-09-26-S9-terminal-files-code.md`), built on
**OpenVSCode Server v1.109.5** (Gitpod, MIT, github.com/gitpod-io/openvscode-server).
Emerson picked it on 2026-09-26. Port 8460, role `code`, section "system".

## Layout
- `openvscode-server/`: the release tarball, unpacked (244 MB; sha256 checked against the
  GitHub release digest). To upgrade: download the new `linux-x64` tarball, replace this folder.
- `web_app.py`: starts `node out/server-main.js` (node itself, not the `bin/` script, which
  doesn't `exec`, so stopping it left node running) on a free 127.0.0.1 port with a fresh
  connection token each start; stops it on shutdown. `/api/session` (needs `X-Forge: 1`)
  hands the page the address and token; `/api/url?path=&root=` builds the address that
  opens a folder, or a file inside `root` (or inside its own folder).
- Forge defaults (dark theme with Forge's neutrals, CaskaydiaCove font, autosave, no
  telemetry) ship as a tiny built-in extension, `openvscode-server/extensions/forge-defaults`,
  rewritten on every start. OpenVSCode keeps a person's own settings **in the browser**, so a
  server-side settings.json is ignored; extension defaults are the supported route, and
  anything Emerson sets himself wins.
- `data/` (made on first run): extensions, server state, `server.log`, the token (mode 600).
- `static/index.html`: frames the editor; `#path=/file/or/folder` opens it (Files' "Open in
  Code" sends this through the hub).

## Checks
- `.venv/bin/python -m pytest -q tests`: starts the real editor; token required (right token
  -> cookie + 200, none/wrong -> 401/403), stop really ends node, URL building, header guard.
- `.venv/bin/python tests/check_ui.py [--shots DIR]`: headless Chrome: workbench loads, file
  opens in a tab by link, explorer shows the folder, typing + Ctrl+S saves to disk, syntax
  colouring, dark theme default, and (still failing) no Restricted Mode.
