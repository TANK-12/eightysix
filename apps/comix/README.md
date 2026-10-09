# Comix

Saves the comix.to series you read as CBZ files, using your own login. It
handles comix.to's many scanlation groups and its unreliable image loading.
It's a Forge app on port 8456, discovered from `forge_app.json`.

## Using it

1. **Log in once.** Press "Log in on comix.to". Forge switches to the Browser
   and opens comix.to. Log in there, come back, and press "I've logged in".
   Comix borrows that login (its cookies); no password is stored.
2. **Add a series.** Paste a series page link (`https://comix.to/title/...`)
   and press Look up. Every chapter is listed once per scanlation group. Pick:
   - *One group only*: chapters that group never did are skipped;
   - *Best group per chapter*: rank the groups; each chapter comes from the
     highest group that has it, and from whoever did it otherwise;
   - *Every group's version*: all translations, the most disk.
   The choice can be changed later from the series page.
3. **Or sync your library.** Put your comix.to library/bookmarks page link in
   Settings, then press "Sync my comix.to library". Each series is added
   waiting for you to pick its groups; nothing downloads until you do.
4. **Queue** shows progress. **Read** opens any saved chapter.

Files: `<download folder>/<Series>/<Group>/Chapter_0012.cbz` (default folder
`~/ComixData`, set in Settings). Pages of chapters still in progress sit in
`<download folder>/.work/`.

## How it copes with bad loading

The site's API needs a token that an obfuscated script builds, and some pages
are scrambled. Comix therefore lets the real reader run in headless Flatpak
Chrome (`shared/forge_mangafetch.py`), so the site un-scrambles its own pages.
Then, per page:

- plain image pages are downloaded straight from their address (3 tries), even
  when the reader's own image stalled;
- scrambled (canvas) pages are captured by a screenshot that is accepted only
  once two captures in a row match and are not blank;
- every page must decode and not be blank before it counts as saved.

Missing pages get further passes, with a growing pause and a reader reload
before each (Settings: passes, default 4). A chapter still missing pages goes
back in the queue for 5 min, 10, 20 … up to 6 h, and is marked failed after
6 tries ("Retry failed" requeues it). A CBZ is built only when every page is
saved. Saved pages are never fetched twice, so stopping or crashing loses at
most one page.

## Code

| file | what |
|---|---|
| `web_app.py` | FastAPI routes, background jobs, reader |
| `comix/store.py` | SQLite: series, chapters (states), pages; `choose()` group rule |
| `comix/downloader.py` | the worker: passes, retries, CBZ |
| `comix/session.py` | reads the login cookies from the Forge Browser's profile |
| `comix/sources/` | one module per site plus `REGISTRY`; `comix_to.py` today |
| `static/` | the page |

Adding a site means one module in `comix/sources/` exposing the functions
listed in `sources/__init__.py`, plus one `REGISTRY` line.

Tests: `.venv/bin/python -m pytest -q tests` (fake reader, no Chrome).
