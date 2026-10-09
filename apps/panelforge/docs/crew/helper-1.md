# helper-1: library (fetch, import, Kindle PDF, MediaForge link)

Priority order from commander (tight budget): 1) comix chapter fetch as a job
+ verify + chapter.json, 2) title -> chapter list -> fetch chosen chapters,
3) folder/CBZ/PDF import, 4) Kindle PDF export, 5) MediaForge button + shared
engine, 6) generic site fetcher, CBR, upload. Stop polishing past step 4 until
1-4 work.

## Done
- Reconnaissance: comix.to has no usable public JSON API (responses are
  client-side encrypted, field `"e": "..."`). Chapter list and reader page
  slots are scraped from the rendered DOM instead (same data the site's own
  JS uses). Chapter list is paginated (`.npager__num`, "Showing X to Y of N
  items"); the toolbar has a numeric chapter search box
  (`.mchap-search input`) used to confirm chapter 2's URL:
  `https://comix.to/title/3nlg-bad-born-blood/5835700-chapter-2` (WebToon
  scan group, same group as chapter 1's `5835641-chapter-1`).
- `/home/ejb/Forge/shared/forge_mangafetch.py` written: `ChromeCDP` (headless
  Flatpak Chrome over CDP, stdlib + websocket-client only),
  `capture_canvas_stable` (clipped screenshot, stability + non-blank check,
  the HANDOFF.md rule), `download_image`, `sniff_ext`, `verify_page_bytes`
  (decode/dims/blank), `seam_score` (neighbour brightness-jump check).
- `panelforge/sources/__init__.py`: registry (`comix`, `generic`),
  `find_for_url`, `get`, `list_sources`.
- `panelforge/sources/comix.py`: `fetch_title` (paginate the chapters list,
  dedupe by chapter number), `fetch_chapter` (two full passes over
  `.rpage-page[data-page=N]`, plain `<img>` downloaded with Referer, `<canvas>`
  captured via `capture_canvas_stable`, each page run through
  `verify_page_bytes` before being accepted).
- `panelforge/sources/generic.py`: MediaForge-style scroll-collect fetcher,
  DOM order, two passes (download once, retry failures). Built already
  (low cost, shares the same driver) even though it's step 6 -- not yet
  tested live.
- `panelforge/library/verify.py`: `verify_chapter_pages` (per-page checks +
  cross-page seam check).
- `panelforge/library/fetch.py`: `fetch_title`, `fetch_one_chapter`,
  `fetch_chapters` -- writes `series.json`/`chapter.json` per CONTRACTS.

## Next (in priority order)
1. `panelforge/api/library.py`: wire `/api/fetch/title`, `/api/fetch/chapters`
   as jobs on lane `net`, `/api/series*`, `/api/sources`.
2. Live check: fetch *Bad Born Blood* chapter 2 into `~/PanelForgeData` via
   the job endpoint (not the CLI prototype), verify (contact sheet, decode,
   count, scrambled pages clean). Do NOT refetch chapter 1.
3. `panelforge/library/importers.py`: folder, CBZ, PDF (pymupdf is in venv).
4. `panelforge/library/kindle.py`: export preset, split tall strip at blank
   gutter rows; `full` preset unmodified pages; bookmarks per chapter.
5. Checkpoint doc, then only if budget remains: CBR (unrar/7z/bsdtar are all
   on the system -- no need to report missing), multipart upload,
   MediaForge link (additive, needs a file claim on the shared board first).

## Contract additions
- `chapter.json` pages: `capture` is one of `"download"|"canvas-screenshot"|"import"`
  as specified. No renamed/removed fields yet.

## Checkpoint 2026-09-17 (budget relaxed by Emerson -- full quality, no corner-cutting; keep checkpointing)
- `panelforge/library/importers.py` written: `import_folder`, `import_cbz`,
  `import_cbr` (unrar/7z/bsdtar all present, picks whichever exists),
  `import_pdf` (pymupdf, 200dpi rasterise), `import_path` (dispatch by
  extension), `import_upload` (multipart bytes). All go through
  `_write_chapter` -> same `verify_chapter_pages` as fetch, `capture:"import"`.
- `panelforge/library/kindle.py` written: `split_kindle` (numpy row-stddev,
  cuts at the blank row nearest each Kindle-aspect (1072/1448) target height,
  falls back to a hard cut if no blank row found), `export_pdf` (pymupdf,
  builds one PDF page per slice/page, `set_toc` bookmarks per chapter),
  `resolve_chapters` ("all" or a number/slug list).
- `panelforge/library/mediaforge_link.py` written: `list_downloads` (walks
  `~/Downloads/MediaForge/<title>/<chapter or .pdf/.cbz>`),
  `import_from_mediaforge` (routes into `importers.import_path`). MediaForge's
  own files not yet touched -- this only reads its output folder.
- `panelforge/api/library.py` written: every CONTRACTS.md "library" endpoint
  (`/api/series*`, `/api/sources`, `/api/fetch/title`, `/api/fetch/chapters`,
  `/api/import/path`, `/api/import/upload`, `/api/mediaforge/downloads`,
  `/api/import/mediaforge`, `/api/export/pdf`, `/api/chapters/{s}/{c}/pages/{idx}`).
  All fetch/import/export run as `panelforge.jobs` (fetch on lane `net`,
  import/export on lane `cpu`).
- Tests: `tests/test_library_verify.py` (9), `tests/test_library_sources.py`
  (6, fake in-process source, no network), `tests/test_library_import.py` (5,
  synthetic CBZ/PDF/folder), `tests/test_library_kindle.py` (6, synthetic
  strip with real blank gutters -- asserts every cut lands inside a gutter
  band, plus a no-gutter fallback case and a real multi-chapter PDF+TOC
  check). **23 library tests + the existing 61 = 84 total, all passing.**
  Real output: `.venv/bin/python -m pytest tests/ -q` -> `84 passed`.
- `black` run on every touched file (11 reformatted, applied cleanly).
  `pyright --pythonpath ./.venv/bin/python panelforge/sources/
  panelforge/library/ panelforge/api/library.py
  /home/ejb/Forge/shared/forge_mangafetch.py` -> **0 errors**. Fixed along the
  way: module typing in `sources/__init__.py` (`ModuleType` instead of
  `object`), an `Optional[str]` narrowing in `fetch.py`, and pymupdf
  `Document` not being `Iterable` for `enumerate()` in `importers.py` (switched
  to `range(doc.page_count)`).
- `tests/test_foundation.py::test_app_health` (existing, not owned by me)
  passes with `library.py` mounted -- confirms the router imports cleanly
  into the whole FastAPI app, not just standalone.
- Also replaced `Image.getdata()` (deprecated in Pillow 14) in
  `forge_mangafetch.seam_score` with `tobytes()` + mean -- stdlib-plus-Pillow
  only, no new dependency.

## Next
- Live check (not yet done): fetch *Bad Born Blood* chapter 2 via the real
  `/api/fetch/chapters` job path (not the CLI prototype) into
  `~/PanelForgeData`, verify with a contact sheet. Chapter 2 URL confirmed by
  hand: `https://comix.to/title/3nlg-bad-born-blood/5835700-chapter-2`
  (WebToon scan group, same group as chapter 1). Do NOT refetch chapter 1.
- Export chapter 1 as a Kindle PDF via the real job endpoint and look at 2-3
  rendered pages.
- Then (lower priority per commander, budget allowing): MediaForge additive
  integration (claim its files on the board first), generic-source live
  exercise against a real non-comix site.

## Open risk
- `panelforge/sources/comix.py` and `generic.py` are unexercised against the
  live site as jobs (only ad-hoc CDP probes so far, run outside pytest, in
  `/tmp/.../scratchpad/`). First live job run is the next step and is the
  real check for "always two passes" and canvas capture working end to end.
