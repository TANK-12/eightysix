# Comix: work in progress

## U1 sweep (2026-10-08, Relay task 74)
Worker: Relay task 78 (group G3). Static changes reach Forge on the next page
reload; the `web_app.py` and `comix/settings.py` changes only on the next
Forge restart.
What changed, nothing removed:
- **Rests and backs off (break 6).** The poll returns false when the server
  does not answer and runs with `{backoff: 2, maxMs: 30000}`; an offline bar
  with Try now shows meanwhile, and series and queue reload by themselves
  when it is back.
- **No double sends.** Sync, check, remove, pause, retry, save and Get/Skip
  are locked while their request runs; a job that vanishes is reported as
  lost instead of polling forever; the newest series click and chapter open
  win over older answers. Calm error states instead of blank panes.
- **New small feature:** a title filter above the series grid.
- **Looks.** Header wraps at narrow widths, thin themed scrollbars, short
  fades, reduced motion honoured.
- **Backend.** A setting that is not a number gets a 400 with a plain
  message (it used to be a 500); an unknown series or chapter gets 404 on
  choice/want; a broken CBZ gets 404 instead of a crash.

**Verified:** pytest 36 passed (9 new in `tests/test_api.py`); black and
pyright clean on the touched .py files; `node --check` ok. Headless check
(`/tmp/u1/G3/g3check.py`): hidden page made 0 fetches in 10 s; server killed:
fetches dropped from 2 to 1 per window, recovered by itself 13 s after the
restart; a triple-clicked Sync sent 1 request; the last series click wins;
the filter works; no page errors. Screenshots at four widths looked at.
**Critic follow-up (same day):** a network failure toasts "Comix isn't
answering" instead of "Failed to fetch"; an id past SQLite's range is 404, not
500; text settings refuse non-text, NUL characters and anything over 4096
characters (400, nothing written); a redrawn series detail cannot start a
second "Check for new chapters" while one runs. Verified: pytest 44 (8 new);
headless (`/tmp/u1/G3/fixcheck.py`): the redrawn Check button is disabled and
two clicks send one request; the offline toast reads as above.
**Not verified:** inside the real Forge window; real downloads (no network
sources used in tests); no power numbers.

## S5 fixes (2026-09-25, second session)

Emerson's asks: A18 "library page 1, page 2, and the original page 1 which
doesn't have the word page in the link, so I can get all the pages of my
library"; A20 "sometimes there isn't even a scan name"; A19 "the downloader
doesn't work with webtoon, it doesn't show up" (meaning asked on the board,
not answered yet; see below).

What changed:
- `comix/sources/comix_to.py`: pages are now parsed in Python
  (`parse_page`, stdlib `html.parser`) from the rendered HTML, so tests run
  on pages saved from the real site (`tests/fixtures/`). One walker (`walk`)
  pages both the library and chapter lists: it always starts at page 1
  (`page_url` strips any `page=N` or `/page/N` from the link), reads the
  pager and the "of N items" count to know how many pages exist, reloads a
  page that comes back empty (slow load, Cloudflare 520) up to 3 times, and
  skips (and logs) one that never loads instead of stopping there.
- Group names: a chapter with no group link uses its uploader
  ("Name (uploader)"), else "Unknown group" (`sources.UNKNOWN_GROUP`). The
  store renames old blank rows when it opens, and names blank rows on save.
- Library sync (`comix/library.py`) also re-lists series already in the
  library that still wait for a group pick (nothing downloaded, so safe).
  That repairs the 41 series his first sync saved with cut-short lists.
- Settings hint: any page of the library link works.

Verified:
- pytest 27 pass (8 new: page addresses, library and series fixtures,
  retry of a failed page, skip of a dead page, blank group naming and the
  rename of old rows, library sync re-listing).
- black; pyright 0 errors on the touched files.
- Live, his account, read-only (no DB writes): library from his saved
  `...&page=2` link = **139 series in 23 s** (the old code saw one page:
  41 in the DB). The Novel's Extra = **909 rows, 178 chapters, 8 groups in
  151 s**, no page skipped (the DB held 20 rows for it).
- Screenshot of the Settings tab with the new hint.

Found, not fixed: the real DB still holds the cut-short lists and 4 broken
entries (3 "Untitled", one titled with a 520 error). One "Sync my comix.to
library" repairs them (they are all still pending).

A19 open: in the live check, a WebToon-group chapter (Bad Born Blood ch 69)
loads in the reader like any other (106 page slots), and WebToon rows were
among the chapters the old code cut off, which may be what "doesn't show
up" meant. If he meant webtoons.com links, that is a new source module plus
one `REGISTRY` line.

## Status (2026-09-25, first session)

Built at Emerson's request: "a perfectly working comix.to chapter downloader
inside the Forge app that works with the different scans/translations, uses
my own login so I can also read it, and deals with the often very bad loading
of images". He wanted to save his series before a possible datacenter loss.

Scope agreed that day: **his library plus any series he pastes**. He also
asked for "almost all of the site"; Claude declined to build a whole-site
crawler (it would bulk-copy a scanlation catalogue and load an already
struggling site, and it would not fit on the disk anyway).

His answers (verbatim choices): home = new app "Comix"; login = "Log in in a
Forge window"; storage = "ui cna chose int th app settings but for now its
in disc" (internal disk by default, folder in Settings); groups = "Pick per
series".

### Verified

- `pytest tests`: 19 pass. Covered: group choice (one/ranked/all/pending),
  refresh only queues new chapters, a clean chapter becomes a complete CBZ,
  flaky pages are retried only after a reload (exact capture order checked),
  blank or missing pages block the CBZ and requeue with a delay, resume after
  a crash keeps saved pages, attempt limit -> failed -> "Retry failed", the
  retry delays, file naming, atomic CBZ writes, cookies read for comix.to
  only (unexpired, other sites ignored, the browser's file byte-identical
  afterwards, values never in the summary), and the comix.to DOM parsing.
- black run; `pyright --pythonpath ./.venv/bin/python` shows 0 errors on every
  file.
- Live against comix.to (scratch server on port 8497 with its data in the
  session scratchpad): looking up Bad Born Blood gave 103 chapters, 204
  chapter-by-group rows and 5 groups (Asura Scans 102, WebToon 93, Falcon
  Scans 5, Kraken Manga 2, Lagoon Scans 2).
- Live download, Bad Born Blood chapter 52 from two groups (the same chapter
  in two translations): Asura Scans 111 pages (23.7 MB CBZ) and Falcon Scans
  110 pages (26.0 MB CBZ). Every page in both CBZs decodes and is not blank.
  Both png pages (scrambled pages captured from the site's own reader canvas)
  and webp pages (downloaded directly) are present, so both capture routes
  work. ComicInfo.xml is embedded. The reader API served page 1 (image/webp),
  with prev/next.
- The multi-pass retry fired on the real site: 1 page of Falcon's chapter
  failed on pass 1 and was recovered on pass 2 after a reader reload.
- Chrome dying mid-chapter: the chapter went to "partial" with its 19 saved
  pages kept and no CBZ built.
- Resume after a restart: the chapter finished 110/110 and none of the pages
  saved earlier were fetched again (attempts = 1 for all of them).
- A bug found and fixed while testing: cleanup of leftover browsers at startup
  also killed a *second* Comix instance's live Chrome. Browser profiles now
  carry a per-database tag (`comix-fetch-<tag>-<slot>`), and cleanup only
  stops its own; covered by 2 tests (19 total).
- Headless screenshot of the Library tab: login banner, add box, pending
  series card, queue badge. A label bug it showed ("pick groups" on a series
  with chapters picked by hand) was fixed; the fix was not re-screenshotted.
- Test data, scratch server and the ~345 MB of test Chrome profiles were
  removed afterwards. The real config and database do not exist yet (first
  run creates them).

### Not verified

- **Login and library sync with a real account.** Emerson has not logged in
  through the Forge Browser yet (0 comix.to cookies in its profile on
  2026-09-25). The library page address is a setting because the right page
  could not be confirmed without a login.
- Inside the real Forge window: the "Log in" hand-off to the Browser
  (`{forge:"open", role:"browser"}` plus the Browser's `/api/agent/do open`).
- The Queue, Read and Settings tabs have only been exercised through the API.

## Improve next, in order

1. Run "Sync my comix.to library" once in the real app: it repairs the
   series saved with cut-short chapter lists (see S5 fixes).
2. Point PanelForge's `sources/comix.py` and MediaForge's downloader at this
   app's `comix/sources/comix_to.py`. There are currently two copies of the
   comix.to selectors; one should go.
3. Auto-refresh: check followed series for new chapters on a timer.
4. Each headless Chrome profile grows to about 160-180 MB (cache) under
   `~/.var/app/com.google.Chrome/comix-*`; 3 profiles (2 worker slots plus
   listing). Clearing their cache at startup would save disk.
5. Move large libraries to the AN3 drive once it is mounted (Settings folder).
6. Speed: about 2 minutes per 110-page chapter at 1 chapter at a time. The
   Settings allow 2 at once.
