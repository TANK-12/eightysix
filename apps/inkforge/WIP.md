# InkForge — WIP

## U1 sweep (2026-10-08, Relay task 74; done by Relay task 87)

What changed:
- Reader: "Fit width" pages can now be scrolled (the stage was
  `overflow: hidden`, so a tall page was cut off). Tall strip pages
  (webtoon style, taller than 2.5x their width, like the Komikku manga here)
  open fit to width until the Fit button is used. Click the left third of
  the page to go back, anywhere else to go on (new; arrows and keys still
  work). The next page is fetched ahead. A page that fails to load says so.
  Fades in (200 ms, opacity only); the list behind it does not scroll.
- "resume p.N" in the chapter list now really resumes there: with no
  InkForge position saved, a chapter opens at Komikku's own last page.
  `/api/progress/<key>` answers with `saved: true|false` (added field).
- Library: "Loading library…" first; if the server does not answer, a calm
  line and a retry through `ForgeIdle.poll` (3 s doubling to 30 s, rests
  while hidden, stops once loaded). A Komikku db that cannot be read no
  longer fails the whole library: PDFs still list, with a note.
- Import: button reads "Importing…" and a second click does nothing; a
  broken or fake .pdf is a 400 "That file is not a readable PDF." and its
  half-made folder is removed (only that import's own fresh folder). Upload
  streams to disk and pages render in a worker thread (the server stays
  responsive during a long import).
- API: progress page must be 0..1,000,000 (422 otherwise), key 1-300
  characters (400); damaged `progress.json` / `library.json` read as empty
  instead of 500; JSON written through a temp file + rename; one lock around
  every read-modify-write (20 parallel saves keep all 20 keys); Komikku
  chapter routes give 404/503 with a reason instead of a 500.
- Looks: themed file picker button, thin themed scrollbars, tile lift on
  hover (transform, 180 ms), keyboard focus on tiles and chapter rows,
  reduced-motion respected.

Verified:
- `pytest -q tests`: 14 passed (6 old, one loosened for the new `saved`
  field; 8 new in `tests/test_u1_robustness.py`). black clean, pyright 0
  errors on `web_app.py tests/`.
- Scratch copy on port 9031 (temp data dir, copy of the real Komikku db),
  headless Chrome: screenshots at 760/1100/1500/1920 and the reader
  (`/tmp/u1/G13/shots/after-ink-*`); 453-chapter list; chapter 1 opened at
  4/23 (Komikku's "resume p.4"); double click opened it once; fit width
  scrolls (8884 px page in an 810 px stage); click zones turn pages.
- Hidden 10 s: 0 fetch / timer / rAF callbacks. Server killed: 3 fetches in
  0-10 s, 1 in 10-30 s, calm line; restarted: loaded by itself.

Not verified: inside the real Forge window (WebKitGTK). Page changes reach
Forge on the next reload of InkForge; the `web_app.py` changes on the next
Forge restart (not restarted here). A really large PDF import (hundreds of
pages) was not timed.

Built 2026-09-25, first session. Everything below is either verified (stated
with the check that proves it) or explicitly marked not done.

## Critic follow-up (2026-10-08, same task)
The critic (`sessions/2026-10-07-overhaul/critics/u1-G13-critic.md`) found
four InkForge items; all fixed:
- Space or Enter while reading re-opened the chapter behind the reader
  (scroll to top, page turns lost): the row's key handler does nothing while
  the reader is open, the row loses focus when the reader opens and gets it
  back on close. Verified headless with real mouse clicks and keys: no
  second fetch, page and scroll kept, focus back on the row after Escape.
- A long title stretched the shelf row and pushed covers out of their
  tiles: tiles align to the top and the title stops at three lines (full
  name on hover). Verified at 1100 px with an 85- and a 190-character title.
- A disk error during import (full, no permission) was reported as "not a
  readable PDF": now a 500 "Could not save the import (...)", still cleaned
  up (new test).
- README: `/api/progress` documents the `saved` field.
Tests: 15 pass.

## Verified

- `pytest -q tests` — 6/6 pass (`.venv/bin/python -m pytest -q tests`):
  library listing against a fixture db, chapter page ordering, page
  traversal-guard (`../` in a page filename → 404), progress round-trip, PDF
  import → rasterize → serve, non-PDF rejected.
- `black` — clean (`web_app.py`, `tests/*.py`).
- `pyright --pythonpath ./.venv/bin/python web_app.py tests/` — 0 errors.
- Real run against the live `~/.local/share/komikku/komikku.db`:
  `/api/library` correctly lists "My Wife is a Demon Queen" (453 chapters,
  real per-chapter page counts pulled from Komikku's page-metadata JSON, not
  a raw count field — that field turned out to be a JSON blob, not an int,
  caught only by hitting the real db).
  `/api/komikku/chapter/1/pages` and `/api/komikku/page/1/01.jpg` both served
  correctly from Komikku's real on-disk chapter folder.
- Two headless-Chrome screenshots, looked at directly: the library grid
  (real data, dark theme, readable contrast) and the reader view (a real
  chapter page loaded through `/api/komikku/page/...`, bar buttons legible
  on the black background). The reader screenshot was taken from a scratch
  harness reusing the shipped CSS/markup verbatim rather than a real click,
  because headless Chrome's CLI screenshot mode has no built-in way to click
  first — see the session transcript if that ever needs redoing properly
  (e.g. with a CDP client).

## Not done

- **No CBZ/CBR import.** Only Komikku (read) and PDF (import) are wired up.
  PanelForge's `panelforge/library/importers.py` already has CBZ/CBR/folder
  import logic that could be lifted in if Emerson wants it.
- **No cover art.** Shelf tiles are an emoji placeholder
  (📚 manga / 📄 PDF); Komikku doesn't obviously expose a cached cover image
  path in the schema this session used — would need checking.
- **Only ever tested against a one-manga library.** Shelf/grid layout with
  many series is reasoned about (`repeat(auto-fill, minmax(160px, 1fr))`),
  not eyeballed.
- **Not registered in any hub "look" or app-group scheme** — none exists in
  Forge yet (queued as item 2 and item 5 of `~/Forge/docs/plans/PLAN-hub-next.md`, unrelated
  work, not started here).
- Not launched through Forge's own GTK shell in this session — only run
  standalone via uvicorn and hit directly with curl/Chrome. Opening it
  through Forge itself (the actual "one window" experience) hasn't been
  checked.

## Next steps, if picked back up

1. Launch Forge itself and confirm the InkForge tile appears (section
   "watch", order 17) and opens correctly inside the hub shell/iframe.
2. Decide on CBZ/CBR import — reuse PanelForge's `importers.py` rather than
   re-writing it if wanted.
3. If the library ever grows past one manga, eyeball the shelf grid with a
   real multi-series screenshot.
