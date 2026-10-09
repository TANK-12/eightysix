# U1 sweep, group G13 critic: NovelForge and InkForge
date: 2026-10-08 · for: Claude · critic for Asuka (relay-87-work), Relay task 87

Commits checked: f8325f2 (InkForge), db58dff (NovelForge). Scratch servers on
9035 (NovelForge, `HOME` and `FORGE_JAN_SETTINGS_DIR` in
`/tmp/u1/G13-critic/`, copy of `~/NovelMakerData` without `tts_voices`) and
9036 (InkForge, temp data dir, sqlite-backup copy of the Komikku db, Komikku
pages read-only). No generation route called, Jan not restarted, both servers
and every Chrome stopped by PID (`pgrep` for G13-critic Chromes: 0).
Scripts: `/tmp/u1/G13-critic/{serve.sh,probe.py,battery.py,ikreader.py,ik2.py}`.

Note on the environment: during this run the laptop was out of RAM (swap
8/8 GB, about 500 MB free, /tmp tmpfs 13 of 16 GB, none of it from this group)
and headless Chrome died seconds after start on most first tries; every
browser result below came from a retry that ran to the end.

## Breaks

### 1. NovelForge: names "." and ".." still create files outside a project folder (high, verified)
- Where: `apps/novelforge/web_app.py:315` `_known()` (also `get_project`
  :307, `get_series`, `create_project`, `create_series`); root cause
  `novelforge/project.py` `slugify()` keeps dots, so `slugify("..") == ".."`.
- Repro (scratch): `GET /api/projects/%2E%2E`, `GET /api/projects/.`,
  `GET /api/series/%2E%2E`, `POST /api/projects {"name": ".."}`,
  `POST /api/projects {"name": "."}`.
- Saw: all 200. `_known()` says yes because `projects/..` and `projects/.`
  are real folders, so the new 404 guard lets them through. Afterwards the
  data root held new `bible.json`, `state.json` and `chapters/` (the `..`
  case writes straight into `~/NovelMakerData`), the projects folder held the
  same three (the `.` case), and Home listed a project called "chapters"
  (visible in `/tmp/u1/G13-critic/shots/nf-a.png`). The report says
  "path-like names: all 4xx", which is not true for these two. The POST side
  is older than this sweep, but the GET side is the guard this commit added.
- Fix: refuse a slug that is "", "." or ".." or starts with "." (400 on
  create, 404 on read), in one helper used by `_known`, `_check_name_length`
  and the create routes; better still, make `slugify` strip leading dots.
  Add both names to `tests/test_u1_names.py`.

### 2. NovelForge: name length is counted in characters, not bytes, so CJK names are still a raw 500 (medium, verified)
- Where: `apps/novelforge/web_app.py:321` `if len(name) > 120`.
- Repro: `POST /api/projects {"name": "漫" * 100}` and the same on
  `/api/series`.
- Saw: `500 Internal Server Error` for both (100 characters pass the check,
  but they are 300 bytes, over the 255-byte folder-name limit).
- Fix: check `len(slugify(name).encode("utf-8")) > 200` (or 255), keeping
  the "name is too long" message; add the CJK case to the test.

### 3. NovelForge: at 760 px in Advanced mode the header status, including the new "Server not answering, retrying" line, is off screen (medium, verified)
- Where: `apps/novelforge/static/index.html:21`
  (`header .status { white-space: nowrap; flex: none; }`) together with the
  rework's Writer and Planner pickers in the header.
- Repro: scratch copy with Emerson's real setting `advanced_mode: true`,
  window 760 px wide.
- Saw: header `scrollWidth` 958 against 750 visible; the status sits at
  x 889-958, fully off screen, and the whole page scrolls sideways
  (`shots/nfadv760.png`). With the two worker rules undone it is 935 wide,
  still off screen, so most of the overflow is older than this sweep, but the
  calm offline line, the point of break 6, can't be seen at this width. The
  worker's 760 px check ran in Simple mode only (`/tmp/u1/G13/shots/after-nf-760.png`).
  Emerson's own NovelForge is in Advanced mode.
- Fix: let the header wrap (`header { flex-wrap: wrap; row-gap: 6px }`)
  or shrink the pickers below about 900 px
  (`header .model-pick select { max-width: 140px }`, hide the "Planner"
  label text), and keep `.status` `flex: none` so it moves to the next row
  whole. Check the 760 px shot in Advanced mode.

### 4. InkForge: Space or Enter while reading re-opens the chapter (scroll jumps to top, recent page turns lost) (medium, verified)
- Where: `apps/inkforge/static/app.js:55-57` `onActivate()` keydown on the
  `tabindex=0` chapter rows and tiles; the row keeps focus behind the open
  reader.
- Repro: click a chapter row (a mouse click focuses it), read in fit width,
  scroll down a tall page, press Space (a common way to scroll down).
- Saw: Space was swallowed (`preventDefault`), the chapter was fetched again
  (3 fetches) and `readerStage.scrollTop` went 2000 → 0. Two ArrowRight
  presses followed by Enter within 300 ms put the reader back two pages
  (6/8 → 4/8), because the re-open reads progress before the 300 ms debounced
  save has gone out.
- Fix: in `onActivate`'s keydown, return when `reader` is set; also blur the
  row in `openReader()` (`document.activeElement?.blur()`) or move focus to
  `#readerClose`, and give it back to the row on close.

### 5. InkForge: one long PDF title stretches the whole shelf row and pushes the other covers out of their tiles (low, verified)
- Where: `apps/inkforge/static/index.html:35-38` (`.tile` grid items stretch
  to the row height; `.cover` has `aspect-ratio: 2/3`, so a taller tile means a
  wider cover).
- Repro: import a PDF named
  "Some Really Long Book Title - The Complete Collected Edition (Author Name, 2019) [Scan].pdf"
  next to short-titled ones, 1100 px.
- Saw: every tile in the row is 370 px tall and the short-titled tiles' covers
  stick out 10 px past their right border (`shots/ik-longtitle2-1100.png`).
  With a 200-character title (the new cap) the row was 728 px tall and covers
  overflowed by 90 px. The CSS is older than this sweep, but long lists and looks
  were in scope.
- Fix: `.shelf { align-items: start }` and clamp the title to 3 lines
  (`display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden`
  plus a `title` attribute with the full name).

### 6. NovelForge: a failing `/api/projects` at start-up still stops the poll from ever starting (low, suspected)
- Where: `apps/novelforge/static/index.html` `init()`: `await loadProjects()`
  runs before `ForgeIdle.poll(...)` and is not caught.
- Not reproduced: the page is served by the same backend, so this only
  happens if the server dies between the HTML and the first API call. The report says
  "a failed first `/api/state` no longer kills start-up", which holds only while
  `/api/projects` works.
- Fix: `await loadProjects().catch(() => {})` (pollState already reloads
  the list on recovery).

### 7. InkForge: any import failure is reported as "That file is not a readable PDF." (low, suspected)
- Where: `apps/inkforge/web_app.py` `import_pdf` `except Exception`.
- Disk full, a permissions error or a pymupdf import error would give the same
  message. Suggest catching `OSError` separately ("Could not save the
  import: ...").

### Already known, not counted as breaks
- `PUT /api/projects/ghostbook/bible` still creates a ghost project (seen,
  200, folder created). The worker lists this under "Left for others" (the
  rework's `_existing()` helper).
- InkForge README does not mention the `saved` field of `/api/progress` yet
  (the worker's own note).
- A name made only of emoji or symbols ("📖"*100, "!!!") becomes "untitled"
  and opens the existing "untitled" project. This is older than this sweep (`slugify`).

## Checked and fine
- Commit hygiene: db58dff carries only the worker's hunks. The current
  `git diff apps/novelforge` matches the saved
  `backups/.../preexisting-uncommitted.diff` apart from context lines and the
  hunks now in HEAD; no worker identifier (`pollState`, `_known`,
  `_check_name_length`, `serverAway`, scrollbar rules) is left unstaged. The
  rework's untracked files are untouched. f8325f2 touches only
  `apps/inkforge` and the InkForge tree is clean. No debug prints,
  `console.log`, temp files or commented-out code in either commit.
- The committed `static/index.html` at HEAD has no `<script` inside its
  inline script (the H4 slip is fixed in git).
- Tests: NovelForge working tree 41 passed; HEAD export
  (`/tmp/u1/G13-critic/headcopy`) 8 passed; InkForge 14 passed.
  `black --check` clean on all five touched .py files. pyright: InkForge
  0 errors; NovelForge 2 errors, both older than this sweep (`Job.thread`, lines
  183/151), the same in the working tree and in HEAD.
- Hidden 10 s (hub signal): NovelForge and InkForge both 0 fetch / timeout /
  interval / rAF; NovelForge did 1 fetch on being shown again.
- NovelForge server killed: 0 fetches in 0-10 s, 1 in 10-30 s, header
  "Server not answering, retrying", project list kept (16 rows), recovered by
  itself within 40 s of restart (header back to the Jan state), no JS errors.
- InkForge library retry with the server down: 3 fetches in 0-10 s, 1 in
  10-30 s, calm note, old shelf kept; after restart it loaded by itself, the note
  cleared, the retry stopped (`libraryRetry === null`).
- InkForge API battery: page -1 / "abc" / 1.5 / 1e12 all 422; key over 300
  or empty 400; unicode key saved and read back with `saved: true`; non-JSON
  body 422; `pdf/%2E%2E`, `komikku/page/1/%2E%2E`, unknown chapter all 404;
  fake, empty and header-only-garbage PDFs 400 with no folder left behind;
  `../../evil.pdf` imported safely as "evil"; `.txt` refused; 20 parallel
  progress saves kept all 20 keys.
- InkForge reader with real mouse and keys: double click on a chapter row
  opened it once; Komikku chapter with 8 tall pages opened in fit width
  (stage 7620 px scroll height in 810 px, `overflow-y: auto`); right and left
  click zones turn pages; ArrowRight works; Escape closes and restores body
  scroll; no JS errors.
- NovelForge bad names: wrong types 422, 200 kB name 400, empty series 400.
- Screenshots looked at (50 %) at 760/1100/1500/1920 for both apps
  (`/tmp/u1/G13-critic/shots/`): fine apart from breaks 3 and 5.

## Not covered
- Either page inside the real Forge window (WebKitGTK).
- NovelForge Story/Generate tabs and any generation, export or audiobook route
  (Jan, out of scope).
- A large PDF import (timing and responsiveness while it renders).
- InkForge PDF reader view and the 1920 px webtoon scaling.
