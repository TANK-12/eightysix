# App power sweep (final state)
date: 2026-10-07 · for: both · status: DONE (overhaul task 4, helper-4 Ami; started by a Sonnet helper, finished on Opus)

## What it is for
Forge app pages kept polling their backends while nobody could see them (hidden window, or another app in front inside the hub). shared/forge_chrome.js already held requestAnimationFrame and CSS animations for hidden apps inside the hub ("Rest"), but timers and network kept going. This sweep closes that gap without changing what any page does while it is on screen.

## Verified vs not
Verified (real output seen):
- Node test of shared/forge_idle.js under a fake clock: `node tests/forge_idle_check.mjs shared/forge_idle.js` -> `all 13 passed` (paused while hidden by tab or hub signal; one run at once on return; 1000 random flips leave one timer and the normal rate; slow async jobs never overlap; stop() during a run; a throwing job keeps polling; hiddenMs; backoff; a brief hide keeps the old beat; now(); a job that never settles no longer ends the poll; a throwing loop frame keeps the loop).
- Headless Chrome (Flatpak, scratch servers on free ports, scratch HOME for games and Files) for 15 pages: acchan, ai-studio, board, browser, calendar, comix, jan-tune, janhollow, novelforge, panelforge, pulseforge, terminal, crewroom, files, plus arcade, emberfield, pixelforge game checks. No console errors, failed script loads or unhandled rejections on any of them; every page rendered with live data (contact sheets looked at).
- Before/after fetch counts, page CPU and backend CPU, measured A/B in one sitting (table below).
- Breaker run on Board (below) and the game checks (below).
- pytest after the edits: emberfield 123 passed, pixelforge 26 passed, ai-studio 9 passed; arcade has no tests (pytest installed into its venv, nothing to run). Earlier suites (handover): board 17, jan-tune 13, comix 27, acchan 202, terminal 11, pulseforge 336 (1 skipped), novelforge 38, panelforge 578, calendar 19, browser 22, janhollow 114. These only test the Python backends.
Not verified: inside the real Forge hub window (WebKitGTK) — the harness imitates the hub by posting {forge:"visible"} and, for the rAF check, by framing the app in an iframe in Chrome. No Python was touched, so black/pyright do not apply.

## shared/forge_idle.js (new; load after forge_chrome.js)
- ForgeIdle.shown(): not document.hidden and ForgeVisible.on !== false.
- ForgeIdle.poll(fn, ms, {hiddenMs=0, backoff=1, maxMs, immediate}) -> {stop, now}. Pauses while not shown (hiddenMs>0 keeps a slow tick). Runs never overlap; an async fn is awaited for at most max(4 x ms, 30 s), so a hung request cannot end the poll. Coming back runs at once if overdue, otherwise keeps its old beat. fn returning exactly false stretches the wait by backoff up to maxMs.
- ForgeIdle.loop(frameFn): rAF loop paused while hidden; a throwing frame is reported and the loop carries on. Unused so far.
- Adds class forge-idle on <html> while hidden (pauses CSS animations standalone).

## Changes, by app (all in the app's own static files)
- board: `ForgeIdle.poll(refresh, 3000, {hiddenMs: 15000})`. The 15 s hidden tick keeps desktop alerts (alertNew) working while the Board is out of sight; its separate visibilitychange refresh was dropped (ForgeIdle refreshes on return). Critic finding: the first version (no hiddenMs) silently killed alerts.
- jan-tune, comix, pulseforge (3 s), terminal (2 s), acchan, novelforge (15 s), browser (30 s), calendar (60 s), panelforge (15 s health, 2 s jobs drawer): setInterval -> ForgeIdle.poll, script tag after forge_chrome.js.
- ai-studio: 1.2 s models-panel poll -> ForgeIdle.poll; a second click on Models no longer starts a second poll.
- janhollow: 3 s voices poll -> ForgeIdle.poll; the world poll stays 200 ms on screen but is 5 s (was 1 s) out of sight, and polls at once when shown again (one chain only). The 4 s presence heartbeat is unchanged on purpose.
- crewroom: the room poll stops while hidden and restarts at once when shown (inline, no ForgeIdle).
- files: the 10 s drive check also skips when the window is hidden (it only checked the hub before).
- arcade: inside the hub, another app in front now pauses a running game exactly like a hidden tab already did (pause screen; music bed and sound suspend; state kept; you press Resume).
- emberfield: does not load forge_chrome.js, so it was never rested in the hub: its game loop drew at full rate behind other apps. Now a hidden tab or the hub's "not visible" message opens the normal pause screen (same as Escape). The 400 ms tutorial check skips while off screen and is cleared when the tutorial ends (it used to tick forever).
- pixelforge: sprite playback holds its frame while off screen.

## Measurements (A/B in one sitting, 12 s windows, headless Chrome)
"before" = same page with ForgeIdle replaced by a plain setInterval shim. Fetches and page CPU (Chrome TaskDuration, s) per 12 s; backend CPU from /proc for the second run.

| app | visible fetches before/after | hidden fetches before/after | hidden page CPU before/after |
|---|---|---|---|
| board | 4 / 4 | 4 / 0 | 0.044 / 0.014 (backend 0.22 -> 0.02 s) |
| jan-tune | 4 / 4 | 4 / 0 | 0.015 / 0.008 |
| comix | 4 / 4 | 4 / 0 | 0.013 / 0.014 |
| pulseforge | 4 / 4 | 4 / 0 | 0.021 / 0.012 |
| terminal | 6 / 6 | 0 / 0 (already gated) | 0.018 / 0.010 |
| panelforge | 1 / 1 | 1 / 0 | 0.014 / 0.015 |
| acchan | 1 / 1 | 1 / 0 | 0.017 / 0.011 |
| novelforge | 1 / 1 | 1 / 0 | 0.015 / 0.006 |
| janhollow | ~60 / ~60 | 15 (1 s world poll) -> 5 | see rAF below |
| crewroom (after only) | 6 | 0 | — |
| ai-studio, browser, calendar | poll only with modal open / 30 s / 60 s: nothing in 12 s either way | | |

Hidden polling now costs nothing; visible behaviour is unchanged. All pages: one fetch within 1.5 s of coming back when overdue; 200 rapid hide/show flips left the same timer count and the same fetch rate.

rAF inside the hub (app framed in an iframe so forge_chrome Rest is active), page CPU per 12 s: janhollow 5.18 visible -> 0.03 hidden -> 5.88 back; crewroom 0.67 -> 0.012 -> 0.70. So the existing Rest does its job for the games that load forge_chrome.js; emberfield did not, which is why it now pauses itself.

Plain truth on size: page-side savings are milliseconds per minute per app; the real gain is backends not woken (Board's backend went from ~1.8% of a core to ~0.2% while hidden) and emberfield/arcade no longer running a game and its music behind other apps.

## Breaker (Board, real Chrome)
Server killed while hidden, page shown with it down: 4 failed fetches in 12 s (normal rate, no storm), no new errors, 1 timer. Server back on the same port: picked up within 8 s by itself. document.hidden: 0 fetches in 12 s; hub says visible while the tab is still hidden: stays paused (0). 1000 random flips mixing both signals with fetches in flight: 4 fetches per 12 s afterwards, 1 timer. 60 s hidden then shown: fetch at once, fresh data.
Games: arcade (Aphelion) playing -> hub hide -> pause screen, title and run kept; emberfield (seed 4242) running -> hub hide -> pause veil, clock/gold/position unchanged over 3 s, resume works, emberfield's own selftest `SELFTEST PASS 64/64`; pixelforge playback frame held while hidden, advanced again on return.

## Critic (Opus subagent) findings
Fixed: Board alerts dead while hidden (bug); stuck job could end a poll for good; loop frame throw killed the loop; emberfield tutorial check never saw the hub signal; crewroom room poll ran while hidden; files drive check ignored hidden tabs; janhollow 1 s hidden poll (now 5 s with an instant poll on return); Board double refresh on return.
Left (by choice): if /shared/forge_idle.js ever 404s the page script stops at the ForgeIdle call (every app backend serves /shared, same dependency as forge_chrome.js); `immediate`/now() run even while hidden (no call site uses immediate); pixelforge's playback interval still wakes (cheap, frame is held); terminal keeps its own redundant hub check (harmless, left as is per Emerson's "don't change what works").

## Left, ranked
1. Check once in the real Forge window (WebKitGTK) that switching apps stops Board/Comix polling (watch outputs/<app>.log request lines).
2. Standalone rAF loops (cosmos, printforge viewer.js, crewroom frame) rely on the browser throttling a hidden window; unverified in WebKitGTK standalone windows.
3. eightysix, dossier, pulseforge job-bound setTimeout chains, mediaforge/novelforge/panelforge job watchers: only run during jobs and need to notice completion; leave.
4. Infinite CSS animations while visible are design, not waste; hidden they are paused (hub Rest, or forge-idle class).

## Harness (scratch, /tmp/h4; recreate if gone)
sweep.py (A/B fetch, page and backend CPU, flips, resume), breaker.py (Board), game_check.py (arcade, pixelforge, emberfield + selftest; scratch HOME /tmp/h4/home with copies of ~/ForgeArtData and ~/ForgeGameData), frame_cpu.py (iframe rAF check). Run with /home/ejb/Forge/apps/acchan/.venv/bin/python (has websockets) and tests/cdp_driver.py.
