# Browser: work in progress

## "Never works", round 2 (2026-10-09, Relay task 122)

Emerson (2026-10-07): "the forge app browser lowkey never works for me". Task
74 fixed the main cause (the first page stayed hidden). This round built a rig
that runs the real hub, forge.py's view handler and ViewHost in a shown window
(`tests/check_real_sites.py`, private headless GNOME, scratch records and
profile) and fixed what it found:

- **Shortcuts died once a page had the keyboard.** Click into a page and
  Ctrl+L, Ctrl+T, Ctrl+W, Ctrl+D, F5 went to the page, so the app seemed dead.
  Now Ctrl+T, Ctrl+W and Ctrl+Shift+T are the app's before the page sees them
  (as in Chrome); Ctrl+L, Ctrl+D, Ctrl+R and F5 are the app's when the page
  leaves them alone (a web terminal or code editor keeps its own). Ctrl+L puts
  the whole address up for typing over (WebKit put the old caret back after
  focus, so the first typed character picks it all again), Ctrl+T puts the
  caret in the address bar, and after Enter the page gets the keyboard (arrows
  and space scroll it), only a page that shows. Alt+Left/Right are Forge's own
  (the app before or after), so they were never Back/Forward; the tooltips no
  longer say so.
- **A crashed page stayed blank for good.** WebKit's page process can die
  (crash, memory); its address is now loaded again once (never `reload()`,
  which would send a form again), with a note.
- **A local file WebKit cannot show** (a zip, say) was quietly copied into
  Downloads; now it is not, and a note says so. PDFs show in WebKit's own
  viewer (not tried with a real PDF).
- **Local files became searches.** `/path`, `~/path` and `file:///` open the
  file (the Claude panel opened `.md` docs that way on 2026-10-08 and got
  Google searches).
- **Stale script after updates.** No cache header, so the hub's WebKit served
  an old `app.js`; now every response says `no-cache` (cheap 304s).
- Not a bug after all: session 1 saw the address bar splice typed text into
  the old address, but only because the rig window was not active (WebKit fires
  no focus events then). The rig now makes its window active, as his is.

Verified: pytest 49 pass (7 new, failing on the old code first); root
`tests/test_views.py` 12 pass (4 new or changed, failing on the old
forge_views); rig `--sites none` 10/10 (the old app.js fails only the Ctrl+L
check); a full run loaded DuckDuckGo, Google, Wikipedia, YouTube, GitHub,
Reddit, the Google sign-in page, WhatsApp Web, ArtStation, X and Crunchyroll
with text and no crash; `tests/check_ui.py` (headless Chrome) all pass.
Not verified: on his own screen, which needs a Forge restart (forge_views.py
is loaded at start) and a reload of the Browser. Real sign-ins were not tried
(scratch profile). Critic (Opus, fresh context) found 11 items; fixed: the
Alt rows, a crash reload sending a form again, focus given to a hidden view,
page-handled keys taken from pages, Super/AltGr ignored in key names, local
files copied to Downloads. Left as notes: key names agree only for letters
and F keys (non-Latin layouts get no shortcuts); a cached old `index.html`
can still run once before the new no-cache header is seen; ViewHost does not
check that the sender owns a view for per-view ops (navigate was already
like that); the Claude panel can now open and read local files, by design;
the offline resolver encodes `!'()*` differently (same file). Other apps
still lack the no-cache header.

## U1 sweep (2026-10-08, Relay task 74)

Emerson: "the forge app browser lowkey never works for me".

- **Main cause (fixed in forge.py, commit 97bfd48).** Opening an app, the hub
  says which app is in front (`owner`) and the bar inset before the Browser's
  page asks for its first native view; forge.py dropped both while no view
  host existed, so the first page stayed hidden in every Forge session until
  another app had been opened. Reaches Emerson on his next Forge restart.
- **Records server away.** A calm strip above the page area says so; typed
  addresses still open (the page resolves them itself with the engine
  templates `/api/state` now sends as `search`); tab changes are saved once it
  is back; the command loop backs off 3, 6, 12, 24, then every 30 s; the page
  loads its records by itself if the boot could not.
- **Notes** now show over the tab strip (top right). At the bottom right they
  sat over the page area, where the native page covered them.
- **Robustness.** Star: a double click bookmarks once, failures say so.
  Side panel: empty states ("No bookmarks yet", "Nothing matches"), an error
  line instead of a stuck list, a fast-typing guard. Prefs and clear-history
  failures say so; the clear-history confirm hides the page while it is open.
  Backend: `/api/session` keeps only {url, title} of web tabs and the right
  open tab whatever it is sent (never a 500), an odd agent `timeout` is a 400,
  addresses over 8192 characters are not kept (`store.keepable`), and
  `store.recent` clamps its limit (SQLite read -1 as "everything").
- **Looks.** History and bookmark rows were raw grey buttons; now flat rows
  with the site initial in a chip. Thin scrollbars (WebKit spelling too), no
  scrollbar under the tab strip and bookmark bar, short fade for notes.
- **New (small):** Ctrl+Shift+T and "Reopen closed tab" in the menu bring
  back the last 20 closed tabs.

**Verified:** `pytest -q tests` 35 pass (7 new). `tests/check_ui.py --port N`
(headless Chrome in a stand-in hub, DevTools on the app frame) 17/17: rests
while hidden (only the command long-poll), backoff with the server killed
(0-10 s vs 10-30 s), calm strip, typed address opens offline, recovers by
itself with one loop, star double click, notes above the page area, empty
states, Ctrl+Shift+T. Screenshots at 760/1100/1500/1920 looked at. In a
private headless GNOME Shell with the real hub, forge.py's view handler and
real WebKit views: first page shows, navigate, new tab shows alone, switch
back, read the page, home hides every page, back shows the same page, close
drops the views (9/9).
**Not verified:** real pointer and keyboard input into a page (the rig's
Mutter input never reached the window, a rig limit); Emerson's own window.
Static changes reach his Forge on the next Browser reload; the backend
changes (web_app.py, store.py) on his next Forge restart.

**Critic follow-up (Relay task 75).** The critic
(`sessions/2026-10-07-overhaul/critics/u1-G1-critic.md`) found: a boot with
the server away could write the boot's blank tab over the saved tabs; the
strip stayed up 25 s after the server was back (the long-poll's hold); the
strip promised bookmarks and history would catch up; notes said "Failed to
fetch"; with many tabs the open tab and the + scrolled out of sight; the note
covered tabs at 760 px; `restore_tabs: "no"` read as yes; addresses with
spaces, control characters or bidi overrides were kept; a dict title or folder
was kept as text. All fixed: no session save before the records are in, and
the recovery restores the saved tabs (the untouched blank tab gives way, tabs
opened meanwhile stay); probes skip the hold while away; honest strip text;
"the server is not answering" in notes; the open tab scrolls into view, the +
stays pinned, a wheel scrolls the strip; notes wrap to two lines inside the
strip (max 36vw); store and endpoint refuse the odd values.
Verified: `pytest -q tests` 43 pass (8 new); `check_ui.py --port 8912` 21/21
(4 new checks; against the old frontend they fail, 18/21). Not fixed: Ctrl+T,
W, L, D and Ctrl+Shift+T do nothing while a native page has focus (forge.py
passes no keys to the Browser; a hub change, listed in the report).

## A8 (S8, 2026-09-26): old pages stayed on screen after close or reload

Emerson: "make the browser load better, it's a bit finicky". The backend log
was clean (8 runs, no errors) and there were no WebKit crash dumps, so the
cause was in the native views.

- **Cause (reproduced).** The hub never told forge.py to close an app's views.
  Closing the Browser only hid its pages; opening it again, pressing Reload
  (Ctrl+R), "Try again", or reloading inside the frame made new views while the
  old ones stayed alive, owned by "browser" and shown again on top. Measured
  off screen in real WebKit (`tests/smoke_browser_reopen.py`): before, the
  views went 1 -> 1 hidden -> **2 visible** after reopening -> **3 visible**
  after a reload, all stacked over the new page (a stale page could cover the
  start page or another tab, and a closed Browser kept its pages running).
  After: 1 -> 0 -> 1 -> 1.
- **Fix.** `hub/index.html`: `dropViews(key)` sends `close-owner` from
  `mountWorkspace` (every fresh frame) and `closeWorkspace`, once per app that
  made views (edit cleared with S7, who owns the hub). `static/app.js`: the
  page keeps its view ids in sessionStorage and closes leftovers when it boots,
  for a reload from inside the frame (a message sent while unloading never
  arrives, tried first).
- **Verified:** `tests/browser/run.sh` new block `hub_views` (4 checks, failed
  before the fix, pass after; whole runner ALL PASS);
  `tests/smoke_browser_reopen.py` PASS in real WebKit off screen with a
  screenshot of the page after a reload; `pytest tests` 22 passed.
- **Not verified:** in Emerson's running Forge window (needs a Forge restart
  to load the hub change; the page change loads when the Browser is reopened).
  Whether this is the finickiness he meant is asked on the board.
- **Improve next:** (1) forge_views.py has no `web-process-terminated` handler,
  so a crashed page stays blank until reloaded by hand; reload it and tell the
  page (no crash seen in the logs, so ranked below the confirmed bug).
  (2) A reload of the whole hub page still leaves views (rare; forge.py only
  loads the hub once).

## Status (2026-09-15, session 33)

Built at the user's request for a browser inside Forge with their Firefox data,
plus a way to open real Firefox.

### Verified

- `pytest tests`: 22 pass (address bar, records, Firefox profile discovery and
  reads from a synthetic profile, the profile is never written, header guard,
  open-in-Firefox command line, command queue round trip and timeout).
- `tests/test_views.py` (off screen): views open, are positioned where asked,
  move clear of the bar and dock insets, hide for another app, read page text
  and links, refuse `file:` and `javascript:` addresses, and imported cookies
  land in the profile with expired ones dropped.
- `tests/browser/run.sh` `hub_immersive`: the hub stamps the owner, converts the
  rect, refuses owner/inset from apps, routes events back, and insets for the
  dock.
- `tests/smoke_browser_window.py`, off screen with the real hub and the real
  Browser page against the live backend: the command queue opened
  https://example.com in a visible native view over the Browser's page area and
  read back "Example Domain". Picture saved and checked. The visit and tab it
  left in the records were cleared afterwards.
- Read-only against the real Firefox profile: 4 bookmarks, 3,236 history pages,
  777 unexpired cookies on 161 hosts, read in 0.03 s. Nothing was imported;
  that is the user's button to press.
- pyright 0 new errors; black run; node --check.

### Not verified

- Inside a real Forge window on screen (needs Forge restarted with the new
  forge.py): typing and clicking in a page, keyboard focus moving between the
  hub and a page, downloads, and a login surviving the cookie import.
- Sites that sniff the WebKit user agent may complain.
