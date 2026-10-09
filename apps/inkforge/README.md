# InkForge

Reads two things in one page-by-page viewer: the manga library the GTK app
Komikku already downloads and tracks, and PDFs you import.

## Data

- **Komikku's library is read-only.** InkForge opens
  `~/.local/share/komikku/komikku.db` with a SQLite read-only URI connection
  (`file:...?mode=ro`) and never writes to it. Page images are served
  straight from Komikku's own data dir
  (`~/.local/share/komikku/<server slug>/<manga name>/<chapter num>/`);
  InkForge never copies them.
- **Imported PDFs** live in `~/InkForgeData/pdfs/<doc id>/` — the original
  file (`source.pdf`) plus every page pre-rasterized to PNG at 200dpi with
  `pymupdf` (`pdfs/<doc id>/pages/0000.png`, ...). `pdfs/library.json` is the
  index.
- **Reading progress** is InkForge's own log,
  `~/InkForgeData/progress.json`, keyed by `komikku:<chapter_id>` or
  `pdf:<doc_id>`. This was a deliberate choice (Emerson, 2026-09-25): Komikku's
  db could be written to instead to keep progress in sync between the two
  apps, but that adds a real write-conflict risk for no functional gain right
  now, so InkForge stays a read-only guest of Komikku's data.

## Endpoints

- `GET /api/library` — Komikku's in-library mangas (only chapters
  `downloaded = 1`) plus imported PDFs.
- `GET /api/komikku/chapter/{id}/pages` — page filenames for one chapter, in
  natural sort order.
- `GET /api/komikku/page/{chapter_id}/{page_name}` — one page image.
- `POST /api/pdf/import` (multipart `file`) — import and rasterize a PDF.
- `GET /api/pdf/{doc_id}/page/{n}` — one rasterized PDF page.
- `GET`/`POST /api/progress/{item_key}` — read/write reading progress. A
  `GET` answers `{"page": n, "saved": true|false}`; `saved: false` means no
  progress was stored yet, so the reader starts at Komikku's own page.

## Known gaps

- No CBZ/CBR import (PanelForge's `importers.py` already has that logic if
  it's ever wanted here too — see `WIP.md`).
- No real cover art — library tiles use an emoji placeholder.
- Only one manga is in the real Komikku library as of this build
  ("My Wife is a Demon Queen", 453 chapters), so multi-manga shelf layout is
  reasoned about, not eyeballed with a full shelf.

## Running standalone

```
cd apps/inkforge
.venv/bin/uvicorn web_app:app --port 8455
```

Or through Forge itself — it's auto-discovered via `forge_app.json`, nothing
in `forge.py` needed editing.

## Tests

```
.venv/bin/python -m pytest -q tests
```

Runs against a throwaway sqlite db + `tmp_path` fixture data (see
`tests/conftest.py`), never the real Komikku db or `~/InkForgeData`.
