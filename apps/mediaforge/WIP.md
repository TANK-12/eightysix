# MediaForge — work in progress

## U1 sweep (2026-10-08, Relay task 74, group G16)

What changed:

- **Security**: `/api/dedupe/thumbnail` used to serve any file on disk
  (`/etc/passwd` too). It now serves only page images listed by a pending
  Duplicate Slayer review; anything else is a 404.
- **Settings**: `POST /api/settings` checks each value's type
  (`config.value_problem`), so `{"jan_base": 5}` is a 400. `load_settings`
  drops wrong-typed saved values: a saved `jan_base: 5` used to crash startup.
- `/api/subtitles/probe` on a missing file is a 404 ("scan the folder again")
  instead of pretending it has one audio and one subtitle track.
- Storage search: `min_mb` must be finite, `limit` is clamped.
- Page: one request per click (`onClickOnce` on 21 buttons), every fetch
  checks `res.ok`, a page-wide catcher turns a failed request into a calm
  toast ("MediaForge's server is not answering"). Start-up loads through
  `boot()`: a server that is not up yet gets a banner over the panels and a
  retry through `ForgeIdle.poll` that slows from 2 s to 30 s and rests while
  the page is hidden; the banner clears by itself when the server answers.
  The name-check `setInterval` became `pollJob`.
- Copy: brand reads MediaForge, "Kill" not "KILL", "Jan is offline: open Jan
  and start its local API server". Thin themed scrollbars, panel fade, room at
  the bottom so the Close app / Full screen pills do not cover the last card.
- `Job.result` is typed `Any`: pyright on the touched files went from 54
  errors at HEAD to 40, none new.

Verified: `pytest tests` 19 pass (new `tests/test_u1_robustness.py`).
Headless Chrome on a scratch server (port 9061, own HOME): 0 requests in 5 s
visible and 10 s hidden at rest; server down gives the banner, 4 fetches per
retry, retries spacing out, 0 requests while hidden, recovery by itself;
3 quick clicks give 1 POST; screenshots of Subtitle Studio, Manga and
Settings at 760, 1100, 1500 and 1920 px show no sideways overflow.

Not measured (no CPU or GPU runs in a sweep): CPU while a long job streams
its log in a hidden window.

Critic follow-up (same day): the thumbnail check crashed (500 on every page
image) once a Storage duplicates job, whose result is a list, was in the job
list; it and `dedupe_finish` now read only dict results. Validation errors
come back as one line ("min_mb: Input should be a valid number"), so toasts
no longer say "[object Object]" (the shared `errText` should join list
details too: in the report, not done, `shared/` is out of a sweep's scope).
Probing a file that is not media (a text file) is a 400. 21 tests pass;
headless check: empty Min MB and a non-media probe give readable toasts.

## Manga downloader: works in the Forge window (2026-09-20, session 47)

Emerson: "make the bloody manga downloader in forge actually work ... show me
a list of the scans, who did the scans, not just the chapters shown on page
one ... bulk download all the images in a way that works".

What was wrong: session 46 wired comix.to into the **Tk** module
(`mediaforge/modules/manga.py`) only. The Forge window runs `web_app.py`,
whose `/api/manga/*` routes still used the Selenium scrape, which finds no
`<img>` on comix.to's canvas reader, and Selenium cannot drive the only Chrome
on this machine (Flatpak) anyway.

Now, in `web_app.py`:

- `POST /api/manga/fetch` for a comix.to link runs PanelForge's fetcher
  (`apps/panelforge/tools/fetch_cli.py list <url> --all`, new `--all` flag)
  and returns every row the site lists on every page of its own pager, one
  per chapter *and* scan group, plus `groups`.
- `POST /api/manga/download` runs `fetch_cli.py get` per chapter into
  `<save folder>/<Title>/Chapter_NNNN/Chapter_NNNN_001.webp`, then compiles
  PDF/CBZ as before; two chapters at a time (one headless Chrome each);
  `job.result` says how many saved and failed; Stop kills the fetcher.
  Other sites keep the Selenium path.
- The fetch helpers moved to `mediaforge/modules/manga_fetch.py` so the web
  backend never imports customtkinter; `manga.py` re-exports them.
- The page: series link with an "Open comix.to" link, scan-group chips
  ("Scanned by: All groups (202) · Asura Scans (101) · WebToon (92) ...",
  picking one selects exactly that group's chapters), select all/none, a
  live count on the Download button, a progress bar, chapter folders named
  by the site's chapter number (Chapter_0012, Chapter_0012.5), the
  Selenium-only controls hidden for comix.to, last link and folder
  remembered. The PDF/CBZ compile now skips a page that will not open
  instead of giving up on the chapter.

Verified 2026-09-20:

- `tests/test_manga_web.py` (new, 4 pass): fetch returns every group; other
  sites 409 without Selenium; download lays out pages and compiles PDF and
  CBZ; empty selection is refused. The fetcher is faked, so no Chrome.
- Live against comix.to through the web API on port 8499: Bad Born Blood ->
  102 chapters, 202 rows, 5 groups (Asura Scans, Falcon Scans, Kraken
  Manga, Lagoon Scans, WebToon); chapter 1 (WebToon) -> 166 pages as webp,
  PDF 15 MB and CBZ 33 MB built. Output deleted afterwards.
- The page itself, on screen in WebKit: typed the link, pressed Fetch, the
  chips appeared, WebToon (92) selected its 92 chapters. Snapshot looked at.
- Not exercised live: pressing Download from the page (the API it calls was
  the one run above), and the Selenium path for other sites.

_Last touched: 2026-09-04, unattended session._

## Anime sorting (Task from the user) — BLOCKED on the drive not being mounted

The external drive `14DE4324DE42FD8C` (931 GB NTFS, shows as `/dev/sda1`) was
**not mounted** during this session and it can't be mounted unattended:
`udisksctl`/`ntfs-3g` both fail (NTFS left dirty, or the kernel ntfs3 driver),
and there's no passwordless sudo.

A prior run on 2026-09-04 15:22 already sorted **2211 files** (391 parked in
`_DUPLICATES/`) — manifest at
`~/MediaForgeData/manifests/20260904-152231_anime-sort.json`.

To finish it, mount the drive and run the new helper:

```
sudo ntfsfix -d /dev/sda1
udisksctl mount -b /dev/sda1
bash ~/MediaForge/finish_anime_sort.sh          # dry run — review the plan
bash ~/MediaForge/finish_anime_sort.sh apply    # execute
```

`finish_anime_sort.sh` wraps `tools/anime_sorter.py`, which already does exactly
what you want: `.mkv`/`.mp4` only, never deletes/overwrites, revertible
manifest, competing-encode / identical files → `<library>/_DUPLICATES/<original
path>`, an `.mkv` + `.mp4` of the same episode both kept. Edit the `SCAN=(...)`
list in the helper if your scattered folders live elsewhere than
`<drive>/sorted`, `<drive>/Downloads`, `~/Downloads`, `~/Videos`.

## Done this session

### Library Organiser — `_DUPLICATES` conflict mode (new)

`modules/organizer.py` gained an **"On name clash → duplicates_folder"** option.
When the target already exists (identical content *or* a competing encode), the
**source** file is moved to `<library>/_DUPLICATES/<path relative to the messy
source folder>` and recorded in the manifest — never left scattered in the
source tree, never deleted. This makes the GUI match the behaviour of the CLI
`tools/anime_sorter.py` and your standing preference for how duplicates are
handled.

### Verified

All nine modules + Settings build and render cleanly (`mediaforge.app` import
OK, every module page instantiates). `py_compile` clean across the tree.

## Known small issues not fixed (low priority)

* `modules/dedupe.py` `_review()` — thumbnail `CTkImage` objects aren't retained,
  so review thumbnails can be GC'd blank; and `_compile` can `IndexError` on
  `pil[0]` if every image in a group fails to load. Manga-only feature.
* `modules/anime_library.py` docstring mentions a "Fix names" button that isn't
  wired up (only "Name check" exists).
* `modules/organizer.py` `_edit_row` maps a text click to a row via
  `(line-1)//2` — correct only while every row is exactly 2 lines (it is today).

---

_2026-09-05, third session (drive was unmounted since, now fixed)._

## HDD repair

The drive had real NTFS corruption (`$MFTMirr does not match $MFT`), not just
a dirty flag — fixed with `ntfsfix -d /dev/sda1` (a scoped MFT-mirror resync,
not a reformat), verified read-only first, data confirmed intact (804 GB used,
everything present) before trusting it read-write. SMART health checked first
(PASSED, 0 reallocated/pending sectors) to rule out a dying drive before any
write. USB enclosure (JMicron JMS583 bridge) throws UAS command timeouts under
sustained I/O and the kernel resets it — recovers cleanly each time but is
worth a permanent fix eventually: `/etc/modprobe.d/99-jms583-no-uas.conf` with
`options usb-storage quirks=152d:0583:u` **was drafted but never written** —
sudo got locked out mid-session from a heredoc/stdin mistake and wasn't retried.
Apply it yourself if the resets keep happening: forces the bulk-only-transport
fallback instead of UAS, needs a reboot (or module reload) to take effect.

## Anime-sorter bug found + fixed: `SEASON_HINT` overwrote a correctly-parsed season

`tools/anime_sorter.py`'s folder-hint lookup (`SEASON_HINT[kk]`) had no
`season is None` guard, unlike every other season-setting line in that
function — so a file correctly parsed as Season 2 from its own filename
(`S02E01`) got silently reset to Season 1 by an *outer* ancestor folder's hint
on the very next loop iteration. Fixed (one-line guard added).

This had wrongly quarantined **21 real, unique episodes** as "duplicates" in
the original 2211-file sort. Found by systematically re-checking all 391
parked "duplicate" entries' file sizes against what they were claimed to
duplicate (a real dupe should be near-identical size; these weren't):

* **Irregular at Magic High School Season 2** (13 episodes, "Visitor Arc")
  — rescued to `The Irregular at Magic High School (2014)/S02E01`–`S02E13`.
* **ReLIFE "Final Arc"** (4 files, a real epilogue OVA, not S1E1-4)
  — rescued to `ReLIFE (2016)/Specials/SP01`–`SP04`.
* **Toradora! "SOS!"** (4 files, a real 4-min OVA short series, not S1E1-4 —
  the size mismatch was obvious: 41-52 MB vs 250-280 MB for full episodes)
  — rescued to `Toradora! (2008)/Specials/SP01`–`SP04`.
* Manifests: `20260904-234116_rescue-irregular-s2.json`,
  `20260904-234241_rescue-specials.json`.

Confirmed correct (not bugs, left as-is): Ao no Hako/Blue Box dupes
(byte-identical, verified), Ningen Fushin S01E08/S01E11 (genuine competing
re-encodes, same episode, different quality).

**Still unresolved, needs the user**: one file,
`Anime/_DUPLICATES/Adrianne Lenker/Nisekoi fakelove/S01E01 - The Promise
(2)this is probably season 2.mkv` — the user's own filename suggests it may be
`Nisekoi:` (Season 2) episode 1, not Season 1, but there's no way to confirm
from the filename alone. Left untouched in `_DUPLICATES`.

## Library Organiser crash — fixed, systemic across 5 modules

`ui.button()` set `fg_color`/`hover_color` explicitly based on `primary=`, so
any call site that *also* passed `fg_color=`/`hover_color=`/`text_color=` for
a custom-coloured button (every red "KILL"/"Delete"/"Revert" button in the
app) collided — `TypeError: got multiple values for keyword argument
'fg_color'`. Affected `organizer.py`, `storage.py`, `manga.py`, `enhance.py`,
`subtitles.py`. Fixed once, centrally, in `ui.button()` (`kw.setdefault(...)`
instead of passing the colour twice) — resolves all five call sites.

## New tool: `tools/media_type_sorter.py` + `mediaforge/audiohash.py`

For non-anime downloads (YouTube music-mix rips etc.) that `anime_sorter.py`
correctly won't touch. Identity is decided by **actual decoded audio content**
(first ~2-3 min → raw PCM → SHA1 via ffmpeg), not filename or byte-hash — so a
`.mp4` and a re-encoded `.mp3` of the same recording are recognised as the
same file even with totally different names/sizes, and two files with the
*same*-looking name but different audio are kept as distinctly-named separate
files (duration-tag disambiguation, e.g. `Title [12m34s].mp4`). Same safety
model as everything else: moves only, never deletes, revertible manifest,
true dupes parked in `_DUPLICATES/<original path>` (fixed a path bug of my
own here first: it was nesting the full absolute path inside `_DUPLICATES`
instead of a clean relative one — caught in the dry-run report before
applying, fixed before running for real).

**Ran it for real this session** across every confirmed 4K-Video-Downloader
source (`4K Video Downloader`, `4K Video Downloader2`, `sorted/4K Video
Downloader`, `EDM`, `OneDrive - Curtin/4K Video Downloader+`): 80 files found,
**46 sorted** into `4K Video Downloader/mp4/` and `4K Video Downloader/mp3/`,
**34 confirmed true duplicates** parked in `_DUPLICATES/` (turned out
`4K Video Downloader2` was almost entirely a duplicate re-download of
`4K Video Downloader` — now empty of files). Manifest:
`20260905-040832_media-type-sort.json`. 0 failures.

Deliberately **left untouched**: `A/` (5085 media files) and the rest of
`OneDrive - Curtin/` (9098 files) — these are the user's general
music/personal backup, not 4K-downloader output, and were far too large and
ambiguous to auto-sort without being asked specifically.

## Still waiting on the user (unchanged from before, nobody's answered yet)

* The Nisekoi file above.
* `DUPLICATE_VAULT/` (5 files) and ~51 empty leftover directories under
  `sorted/` — asked twice now whether to clean these up; no response yet.
* Whether to apply the USB-quirk modprobe config (needs sudo, needs a reboot).

## 2026-09-19 17:45 -- comix.to path exercised without the window

`manga.panelforge_fetch(["list", "https://comix.to/title/3nlg-bad-born-blood",
"--group", "WebToon"])` returned the title, 102 chapters and the five scan
groups (10 chapters have no WebToon version and take the first listed);
`["get", <chapter 2 url>, <folder>, "Chapter 2"]` captured 186 pages as
`Chapter 2_001.webp`... in 163 s, the names the gap check and the PDF/CBZ
compile expect. A wrong title link now logs "no chapters at ... use the
title page's link" (PanelForge's `tools/fetch_cli.py`). Only the Tk
buttons themselves (`_fetch`, `_download`) remain unexercised -- they call
exactly these two functions.

