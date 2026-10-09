# Keymap

Views and edits every Hyprland keybind across all three shells (end4-pC,
Brain Shell, Caelestia) and the personal `custom/keybinds.lua` overrides,
from one page in the Forge hub.

## What it reads

On every `GET /api/binds`, it re-parses the Lua source directly (`parser.py`)
rather than caching anything — the list is always exactly what Hyprland would
actually load. Scope tags (Universal / end4-pC / Brain Shell / Caelestia) are
derived by reading `~/.config/hypr/hyprland/shells.lua` at request time
(`sources.py`), so a new shell added there later shows up automatically with
no code change here.

## What's editable and what isn't

Most binds are a plain string literal (`hl.bind("SUPER + T", ...)`) or a
`vars.kbXxx` reference resolved against `~/.config/hypr/variables.lua`
(Caelestia's pattern) — both are point-editable in place.

Binds assembled inside a Lua `for` loop (workspace switching, window-focus
arrows, etc.) or from a variables.lua entry that's a table of multiple
combos are listed and fully filterable/sortable, but shown as "generated —
edit source" rather than an inline edit box. Rewriting the loop or array that
produces them is a structurally different, higher-risk kind of edit than
patching one literal, and this tool deliberately doesn't attempt it — see the
"What editable actually means here" section of the plan this was built from
for the reasoning (`~/.claude/plans/dapper-plotting-cloud.md` as of
2026-09-12, or ask a fresh Claude session to re-derive it from this file).

## Safety model

Every write (`editor.py`):
1. Backs up the whole target file to `data/backups/<timestamp>-<file>`.
2. Patches only the exact matched literal — nothing else on the line or in
   the file changes.
3. Runs `luac -p` on the result. If that fails, the backup is restored
   immediately and the error is returned — the file is never left broken.
4. Appends an entry to `data/history.jsonl` (file, line, old/new text,
   description, scopes, timestamp).

Undo (`POST /api/undo/{id}`) replays the same patch+backup+`luac` path in
reverse and appends a new `revert` entry rather than deleting the original,
so the log stays a complete audit trail.

`data/` (backups and history) is local to this app and not committed
anywhere — Forge has no version control (see `~/Forge/CLAUDE.md`).

## Verified

- `test_parser.py` (8 cases) runs against the real config files on this
  machine and passes: finds known static binds, flags loop-generated binds
  as non-editable, resolves `vars.kbTerminal` correctly, and confirms
  `vars.kbPrevWs` (a table value) is correctly *not* offered as editable.
- Manual end-to-end check on 2026-09-12: edited `kbEmoji` in
  `variables.lua` through the running API, confirmed `luac -p` passed and
  the file changed on disk, then undid it through `/api/undo` and confirmed
  the file came back byte-identical to its pre-edit backup.
- Launched inside the real Forge hub (`python3 ~/Forge/forge.py`) on
  2026-09-12: `outputs/keymap.log` shows the hub's own iframe requesting
  `GET /` then `GET /api/binds` and getting `200 OK` for both, confirming
  the app is discovered, started, and its frontend actually fetched real
  data inside the hub window (not just standalone via `curl`).
- Not verified: what it visually looks like on screen. This session had no
  working screenshot path (`grim` needs a Wayland protocol Mutter doesn't
  expose here; `gnome-screenshot`'s D-Bus portal call was denied). The
  frontend follows the shared `forge.css`/`forge.js`/`forge_chrome.js`
  contract from `~/Forge/README.md`, but a human still needs to actually
  look at the Keymap tab at least once.
