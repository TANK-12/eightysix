# Keymap — work in progress

## U1 sweep (2026-10-08, Relay task 74)

Swept by Relay task 91 (group G17). Keymap had no WIP.md before this.
- **History tab fixed.** It never opened: the shared `initTabs` only wires
  `nav .tab`, and this page uses a `.mode-switch` (`#tabs button`), so Undo
  was unreachable. The page now wires its own two buttons.
- **Edits stay inside the keybind files.** `POST /api/binds/edit` wrote to
  any path it was given (it backed up, patched and ran `luac -p` on whatever
  file was named). It now refuses any file that is not in the scope registry
  (`sources.load_scopes()`) or Caelestia's `variables.lua`, before reading or
  backing it up. Undo checks the same. An empty old combo or a new combo with
  a line break is refused; a listed file that has gone or is unreadable is a
  per-target error instead of a 500; a `1e999` line number is a 422 without
  the value echoed (new `RequestValidationError` handler).
- `editor.read_history()` skips damaged lines in `data/history.jsonl` instead
  of failing the whole History tab.
- Page: "Reading your keybinds…" while loading; if the server is not there,
  "The Keymap server is not answering. Trying again by itself…" and a retry
  2 s doubling to 30 s (`ForgeIdle.poll`, only while shown, stops once read);
  "No keybinds match this filter." for an empty filter; History has an empty
  state and an error row. Save is one at a time (a second click or Enter is
  ignored while it runs); Enter saves and Escape cancels in the edit box;
  Undo is one at a time; network failures say so instead of throwing.
- Looks: at 760 px the table scrolled sideways (848 px); long source paths
  now wrap and cells are tighter under 820 px. Thin themed scrollbars.
- Tests: new `tests/test_web_api.py` (9, on a throwaway Hyprland config in
  tmp_path; 7 of them fail on the old code) plus the 8 in `test_parser.py`:
  `.venv/bin/python -m pytest -q test_parser.py tests` → 17 passed. black,
  pyright 0 errors on `web_app.py`, `editor.py`, the new test. httpx added
  to the venv for `TestClient`.

**Verified** in headless Chrome on a scratch copy (port 9071, temp HOME with
a copy of `~/.config/hypr`, history blanked because its entries name the real
files): 228 binds, no sideways scroll at 760/1100/1500/1920; an edit sent
with Enter three times made one POST and changed the copy; History opened
and a double-clicked Undo made one POST and put the file back (the copy
equals the real config again); hidden 10 s: 0 fetches, rAF or timers; API
failing for the first 6 s of a load: error row shown, then the list filled in
by itself. Screenshots looked at in `/tmp/u1/G17/shots/`.
**Not verified:** inside the real Forge window, and a real edit to Emerson's
config (none was made). The page change reaches Forge on the next reload of
Keymap; `web_app.py`/`editor.py` changes on Emerson's next Forge restart.

**Critic follow-up** (same day): a history line with a text timestamp
made the History tab a 500, and an entry with only an id and timestamp made
its Undo a 500. History lines are now checked for the full shape (id, number
timestamp, whole line number, file / old / new text) and skipped otherwise;
Undo no longer needs `description` / `scopes`. An empty new combo is refused
through the API as well (its Undo would have been refused). Tests: 19 pass
(`pytest -q test_parser.py tests`), the new history test fails on the old code.
