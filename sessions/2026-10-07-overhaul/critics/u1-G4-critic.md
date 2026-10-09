# U1 sweep critic: group G4 (Crew Room, Terminal)
date: 2026-10-08 · for: Claude

Critic for Tomo's G4 sweep (commits a05fa70 terminal, e62eb91 crewroom).
Scratch ports 8945 (terminal) and 8946 (crewroom), PID files, stopped by PID;
no Chrome left running. Scripts and output: `/tmp/u1/G4-critic/`
(`wsprobe.py`, `term.py` -> `term.out`, `crew.py` -> `crew.out`, `tabs.py`),
screenshots in `/tmp/u1/G4-critic/shots/`. The crewroom scratch server ran the
working tree, which includes another session's uncommitted diff
(context.py, launch.py, sources/sessions.py, app.js name labels, tests).

## Breaks

1. **Terminal: two kinds of malformed socket message still raise and drop the
   socket** (low, **verified**). `apps/terminal/web_app.py:123`
   `term.write(msg["d"].encode())` raises `UnicodeEncodeError` for a lone
   surrogate (`{"t":"in","d":"\ud800"}`, valid JSON), and
   `web_app.py:185` `await ws.receive_text()` raises `KeyError: 'text'` on a
   binary frame. Neither is in the caught set, so each gives a full ASGI
   traceback in the log and a 1006 close. Repro: `wsprobe.py` (scratch 8945):
   `lone-surrogate` and `binary-frame` -> closed 1006, the other 7 malformed
   cases (negative/huge/NaN resize, array, not JSON, unicode, 200 kB input)
   stay attached. The page recovers by itself (it treats it as a lost
   backend and prints "lost the Terminal backend", which is misleading).
   The report says malformed messages are ignored. Fix: in `handle()` encode
   with `errors="surrogatepass"` (or `"replace"`), and in the loop use
   `m = await ws.receive()`; on `websocket.disconnect` stop, skip a frame
   without `"text"`; add both cases to `tests/test_terminal.py`.

2. **Crew Room: the counts still wrap into three ragged lines at 1100 px**
   (low, **verified**). The fix in `apps/crewroom/static/room.css:126` only
   applies at `max-width: 900px`; between about 900 and 1200 px the header
   still squeezes "3 sessions (2 busy) · 1 helper · 0 Jan models" into three
   right-aligned lines. Seen in `shots/crew-1100.png` and
   `shots/crew-settings-1100.png` (cropped in `sheet-hdr.png`). Fix: raise
   the breakpoint to about 1240 px, or give `.counts` `white-space: nowrap;
   overflow: hidden; text-overflow: ellipsis; min-width: 0` above 900 px.

3. **Terminal header with many tabs: "Full screen" and "Close app" squeeze
   into two lines** (low, **verified**, pre-existing, not a regression). With
   15 tabs at 760 and 1100 px the tab strip shrinks correctly and scrolls
   (active tab kept in view: `tabs.py`), but the header buttons shrink too and
   their labels wrap (`shots/term-14tabs-760.png`, `-1100.png`, cropped in
   `sheet-hdr.png`). Both buttons are added by `shared/forge_chrome.js`.
   Fix in the app: `.bar > .btn, .bar .forge-chrome-btn { flex: none;
   white-space: nowrap; }` in `apps/terminal/static/app.css` (or nowrap in
   shared/forge.css for every app; recommend, do not touch shared/).

4. **Boot fetches have no timeout** (low, **suspected**). Terminal `boot()`
   (`static/app.js`, the `/api/session` loop) and Crew Room `boot()`
   (`ForgeArt.load`, `loadRoom`) only retry when a fetch rejects. A backend
   that accepts the connection but never answers (stopped process, stuck
   worker) leaves Terminal blank with no card and Crew Room on "Setting up
   the room…" for good. Not reproduced (would need a SIGSTOPped scratch
   backend). Fix: the same 15 s `AbortController` that `pollOnce` uses.

5. **Terminal reconnects scale with the pane count** (low, **verified**,
   design note rather than a bug). Each lost pane runs its own doubling
   timer: with 15 panes and the backend killed, 31 socket attempts in 0-10 s
   and 29 in 10-30 s (it does drop per pane, settling near 15 per 30 s;
   with one pane the worker's numbers hold). Fix if wanted: while the info
   poll is failing, let lost panes wait for `reconnectNow()` instead of
   each probing on its own, or share one retry clock across panes.

## Checked and fine
- Commit hygiene: e62eb91 holds only the worker's hunks (the foreign
  name-label hunks in app.js, the 10-07 WIP.md section, context.py,
  launch.py, sources/sessions.py and tests are still uncommitted, unchanged);
  a05fa70 touches only terminal files. No debug prints, temp files or
  commented-out code in either diff. HEAD crewroom app.js passes
  `node --check`; no leftover `poll(`/`pollTimer` callers.
- Tests: terminal pytest 14 passed, black clean, pyright 0 errors on
  `web_app.py tests/test_terminal.py`; crewroom pytest 37 passed (working
  tree).
- Terminal in headless Chrome (`term.out`): visible 10 s 5 fetches; hub
  hidden 0 fetch/ws/timer/rAF; document hidden 0 (1 stray rAF); a real
  second page (window.open) takes every shell, the first shows "taken", no
  ping-pong over 10 s, a key in the first takes it back and the second goes
  "taken"; no page errors in either. Backend killed with 15 panes: rate
  drops (see 5), down and hidden 0 fetch/ws/timer; restarted: all 15 panes
  marked gone in 4.3 s, new tab works, no page errors. Wrong token / non-ASCII
  token -> 4403, unknown shell -> 4404, foreign or missing Origin -> HTTP 403
  before accept.
- Crew Room in headless Chrome (`crew.out`): boot with the art library
  failing 3 times shows "Can't reach the Crew Room backend, trying again in
  2 s…" and recovers by itself, 4 room tabs (bindUI once); visible 10 s 4
  room fetches; hub hidden and document hidden 0 fetch/rAF/timer; killed: 2
  fetches 0-10 s, 2 in 10-30 s, calm status line; down and hidden 0;
  restarted: recovered in 5.5 s, back to 4 fetches/10 s (one poll chain);
  no page errors. Screenshots at 760/1100/1500/1920 (plain, settings open,
  backend down) look right apart from break 2.
- Crew Room API bad input: traversal, 5000-char and unicode room ids -> 404;
  bad `before` -> 422; NUL and 3000-digit session ids -> 400; wrong types and
  `[]` bodies to the launch routes -> 422 (nothing launched); 0 tracebacks.

## Not covered
- Inside Emerson's Forge window (WebKitGTK): scrollbar styling and the
  hub's own rest signal there.
- `apps/terminal/tests/check_ui.py` not re-run (it picks a random free port
  outside the critic range).
- Rapid room tab clicks, launch double click and the poll-slider debounce
  were read in the code and not re-run (the worker's `crewcheck.out` covers
  them); no real launch fired.
- Crew Room boot while hidden and down; Terminal 4409 while the taken page
  is hidden.
