# Media: work in progress

## U1 sweep (2026-10-08, Relay task 74)

Koharu (relay-90-work), Relay task 90, group G16. Static changes reach the
Forge window on the next page reload; the `web_app.py` / `media_lib.py`
changes only on Emerson's next Forge restart.

What changed:
- Start: the page used to run `loadSettings().then(loadLibrary)` once; with
  the server not up yet it stayed blank with an uncaught error. Now the list
  says "Can't reach the Media server. Trying again by itself…" with a Try
  again button, and retries through `ForgeIdle.poll` (2 s doubling to 30 s,
  only while shown; `forge_idle.js` now loaded), stopping once it is in.
- Library list: loading, empty ("Nothing here yet…"), no-match and error
  notes instead of a blank card; one scan at a time (Rescan is disabled while
  scanning, a second request runs once after); search redraws 120 ms after
  typing stops; off-screen rows use `content-visibility: auto`.
- Download: one request per click on Download (double clicks started two
  jobs); a failed job lookup after Find is a toast, not an uncaught error;
  Stop failures are a toast; the "Up to" number is clamped to 1-500.
- Settings Save is disabled while saving. Server errors read "the Media
  server is not answering" instead of "Failed to fetch".
- Backend: `limit` must be 1-500 (-5 used to start a real yt-dlp search),
  `kind` must be audio or video, at most 500 urls, volume 0-100, at most 50
  folders, no empty download folder, no NUL bytes in paths (`/api/file` with
  one was a 500) and size caps on every text field; a hand-edited
  settings.json with junk volume or folder falls back to the defaults.
- Looks: 180 ms fade between tabs; under 900 px the tabs take their own row
  (at 760 px the header ran 98 px past the edge and pushed Full screen off);
  Download / Settings span the window so their scrollbar sits at the edge
  (it sat mid-screen at the 960 px column); thin themed scrollbars.

Verified:
- `pytest tests`: 34 pass (20 new in `tests/test_u1_robustness.py`).
  black + pyright clean (0 errors before and after).
- Headless Chrome on a scratch copy (port 9060, temp settings and a temp
  library with a unicode and a 120-character name), scripts in
  `/tmp/u1/G16/` (`mcheck.py`, `shots.py`): hidden (hub signal and
  document hidden) 10 s each: 0 fetch, 0 timer, 0 interval, 0 rAF. API down
  at start: calm note, 2 fetches in 0-10 s, 2 in 10-30 s, 0 while hidden,
  filled itself once the API came back; server killed after load: Rescan
  toasts and keeps the rows, works again after restart. 5 Rescan clicks -> 1
  request; 3 Download clicks -> 1 request; 5000 fake rows render in 19 ms;
  search for 日本 and for `zzz<b>` (shown as text). Screenshots at 760,
  1100, 1500, 1920 px before and after looked at.

Not verified: inside the real Forge window (WebKitGTK); YouTube/Crunchyroll
views (need the hub) were not touched.

Critic follow-up (same day): the folder cap is 500, not 50 (51 folders used
to save before the sweep). Validation errors come back as one line, so a
refused save reads "Not saved: folders: List should have at most 500
items…" instead of "Not saved: [object Object]". 35 tests pass; headless
check of 501 and 51 folders on the scratch server.

## Status (2026-09-25, session S3 / ejb-49: downloader fixed)

Emerson: "the youtube downloader in the media thing is not working".
yt-dlp (system, 2026.08.19) and the backend were fine; the page was broken:

1. `app.js` called `streamJob()`, which only ever existed inside MediaForge's
   own page, never in `shared/forge.js`. Find threw, the list never filled.
   Now uses the shared `forgeStreamInto()`.
2. Opening Media at `#download` (or any tab hash) threw "Cannot access
   'views' before initialization" and killed the whole script. The hash
   tab switch now runs at the end of `app.js`.
3. The page had no `#toast` box, so every error and "finished" message was
   silently dropped. Added.
4. Pick-list rows ran title and duration together (`.picks label` was
   `display: contents`, beating the `.item` grid). Fixed in `app.css`.

The yt-dlp command lines moved to `shared/forge_ytdlp.py` (media_lib
re-exports them), so the hub's "add a YouTube link to the background music"
uses the same downloader.

### Verified (2026-09-25)
- `pytest tests`: 14 pass. New `tests/test_downloader.py`: list and
  download through the real API with a fake yt-dlp on PATH, a failed video
  not stopping the batch, every function `app.js` calls being defined by a
  script the page loads (the check that catches bug 1), the toast box.
- `tests/browser/run_download_flow.sh`: headless Chrome clicks Find then
  Download in the real page; all PASS with the fake yt-dlp, and all PASS
  with `--real` (the 19 s "Me at the zoo" saved as mp3, ffprobe: 19.0 s,
  title and artist tags). Screenshot of the Download tab looked at.
- black + pyright clean on `tests/test_downloader.py`.

### Not verified
- Clicking Find/Download inside the Forge window itself (the page is the
  same file; Media was not running during this session).

## Earlier status (2026-09-20, session 47 -- built this session)

Asked for by Emerson: "add media for mp3 and mp4 and youtube and crunchyroll
... move it or make it inside forge, download music using a youtube
downloader from tokyo echo sounds or whatever channel it is".

### Verified

- `pytest tests`: 9 pass (settings bounds, library scan skipping hidden
  folders and non-media, the `/api/file` guard refusing paths outside the
  library, channel/search/link targets for yt-dlp, listing parse, download
  command lines, progress parsing, the runner fake).
- Live backend on port 8450: `/api/library` found the 5 files under
  `~/Videos`; `/api/yt/list` with "Tokyo Echo Sounds" returned 8 videos of
  TOKYO ECHO SOUNDS (channel UCgmg1ePUt_V7ZcgqSos-AVA); `/api/yt/download`
  saved a real 1-hour track as mp3 (117 MB, title and artist tags, checked
  with ffprobe). Deleted afterwards; nothing left in the scratch folder.
- Headless Chrome screenshots of the Library and Download tabs (layout
  right, tabs work, `#download` opens on that tab).
- Inside the real hub on screen: opening Media and clicking YouTube created
  a native view owned by `media`, placed over the page area, titled
  "YouTube". YouTube itself plays video in this WebKit (an ordinary video
  decoded; a live stream said "unavailable").
- pyright 0 errors on `media_lib.py` and `web_app.py`; black run.

### Not verified

- Playing a file from the page inside the Forge window (only the route and
  the page were checked, not a click on a row with sound out).
- Crunchyroll: the view is the same code path as YouTube and was not opened
  separately. Playback there is known not to work in WebKitGTK (no Widevine);
  Watch in Firefox is the intended path and `POST /api/open-firefox` was not
  pressed live.
- mp4 (video) downloads: the command line is tested, no live run.
- The `Close app` / stop behaviour of a download in flight (stop terminates
  the current yt-dlp; the job then ends).

### Improve next

1. Play-from-page check inside Forge with a real file (a click, then the
   time counter moving). Cheap and the one thing a user touches first.
2. Remember the last played file and position per file, so a long video
   resumes.
3. A "Download this channel's newest" button that remembers channels, for
   the Tokyo Echo Sounds habit: one click to fetch what is new.
4. Cover art in the library rows for mp3s (ffprobe/embedded picture) --
   the rows are plain text now.
5. Crunchyroll: if a WebKitGTK build with Widevine ever appears on Arch,
   drop the Firefox hand-off.
