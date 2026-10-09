# Files: WIP

## U1 sweep (2026-10-08, Relay task 74)
Worker: Relay task 78 (group G3). Only static files and a test changed, so it
all reaches Forge on the next page reload; no backend change.
What changed, nothing removed:
- **Rests and backs off (break 6).** The drive poll is `ForgeIdle.poll` every
  10 s with `{backoff: 2, maxMs: 30000}` and returns false when the server is
  down, so the gap grows to 30 s instead of a request storm. A small "Backend
  not answering, retrying" chip shows in the status bar and the folder
  refreshes by itself when the server is back. A failed first load shows a
  calm card with Try now and an automatic retry. `forge_idle.js` is now loaded.
- **Robustness.** The newest folder load or search wins (old answers are
  dropped), the list dims only after 150 ms; a paste or move claims the job
  slot before the request, so a double Ctrl+V runs once; the job watch backs
  off and says the job was lost instead of reporting false success; Trash and
  Restore lock per item; fetch errors show friendly text.
- **Looks.** The toolbar wraps at narrow widths instead of squeezing labels,
  buttons never break mid-label, themed thin scrollbars, short fades on menus
  and dialogs, reduced-motion honoured.
- `tests/check_ui.py`: two new checks (double Ctrl+V pastes once, rapid
  navigation shows the last folder) and a steadier restore target.

**Verified:** pytest 40 passed; `tests/check_ui.py` 20/20 pass over six runs;
`node --check` ok. Headless check (`/tmp/u1/G3/g3check.py`): hidden page made
0 fetches in 10 s; with the server killed the poll slowed down, and after a
restart the page recovered by itself (28 s) and redrew 60 items; no page
errors. Screenshots at 760/1100/1500/1920 looked at before and after.
**Critic follow-up (same day):** thumbnails and previews no longer stay
broken after a backend restart (the page fetches the new token when it comes
back online and redraws); a job the backend answers 404 for is reported lost
at once instead of after a minute; the job watch asks nothing while the page
is hidden. Verified headless (`/tmp/u1/G3/fixcheck.py`): 7 of 7 thumbnails
drawn in a fresh folder right after a restart, 0 job fetches in 10 s hidden,
lost reported within 0.01 s of the 404; pytest 40, check_ui 20/20 twice.
**Not verified:** inside the real Forge window (WebKitGTK); no power numbers
(measure-this items are in `sessions/2026-10-07-overhaul/reports/u1-G3.md`).

## S17 (2026-09-27, ejb-94): Tools "Improve next"
Added, nothing removed:
- **Restore from the trash**: in the Trash place, the item menu and the
  preview pane offer Restore. It follows the freedesktop trash spec: reads
  `Trash/info/<name>.trashinfo`, moves the item back (a taken name gets
  "(copy)", a missing folder is made again), then drops the record. That is the
  one removal in fsops.py, fenced in `_drop_trashinfo`, and the no-delete guard
  test allows exactly it. The Trash place now follows `XDG_DATA_HOME`.
- **Extract here / Compress to .zip** (bsdtar, as background jobs with the
  same bar as copy/move; the page's `runJob` now serves all four). Extract
  checks the archive can be read before making the folder.
- **PDF thumbnails** (first page, pdftoppm) in the grid.
- "Open in Code" already existed (the old list was out of date).
Verified: pytest 40 passed (7 new); tests/check_ui.py 19/19 PASS in headless
Chrome (compress, Extract here in the menu, extract contents, Restore in the
trash menu, restore puts the file back); screenshot looked at.

## State (2026-09-26, S9 ejb-ea)
Built from scratch this session. Verified: 32 pytest tests pass; `tests/check_ui.py`
13/13 PASS in real headless Chrome (copy/paste, numbered copy, F2 rename, Delete to
trash, cut/paste move, new folder, Alt+Up, drag onto folder, search, Ctrl+H, text
preview); screenshots checked for list, grid with thumbnails + preview pane, and a
900 px wide header. Not yet seen inside the running Forge window (needs a Forge
restart, which is Emerson's call).

## Improve next
1. Drop files from outside Forge (desktop drag-in) and drag out.
2. Restore for trashes on other drives (`.Trash-1000` on AN3); today only the
   home trash is listed and restorable.
3. Archive progress: extract/compress show a busy bar, not a percentage.
