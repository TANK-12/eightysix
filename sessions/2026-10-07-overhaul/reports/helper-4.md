# H4 App power sweep: report (helper-4, Ami)
date: 2026-10-07 · for: both

Checks passed: node test of shared/forge_idle.js `all 13 passed`; headless Chrome on 15 pages, no console errors; game checks pass (emberfield selftest `SELFTEST PASS 64/64`); pytest emberfield 123, pixelforge 26, ai-studio 9 passed (arcade has no tests). Earlier suites for the other 11 apps passed at handover (Python only).

Full detail, numbers and the ranked list of what is left: ~/Forge/docs/library/power/2026-10-07-app-power-sweep.md

## Design decision
I added one shared helper, shared/forge_idle.js. `ForgeIdle.poll` replaces `setInterval` for polling. It stops while the page is hidden (browser tab hidden or the hub's "not visible" signal), never overlaps runs, gives up on a hung job after max(4 x interval, 30 s), and on return runs at once if a run is overdue. Polls whose callers need data while hidden can keep a slow tick with hiddenMs (Board alerts). Pages that don't load forge_chrome.js, or that use their own self-rescheduling timeouts, got small inline fixes rather than a rewrite. Games pause through their existing pause screens, so no game state can be lost.

## Changed files
- shared/forge_idle.js (new), tests/forge_idle_check.mjs (new, 13 cases)
- apps/{acchan,ai-studio,board,browser,calendar,comix,jan-tune,janhollow,novelforge,panelforge,pulseforge,terminal}/static: ForgeIdle wiring. Board keeps a 15 s hidden tick for desktop alerts. ai-studio no longer double-starts its poll. janhollow's hidden world poll is now 5 s (was 1 s) and polls at once on return.
- apps/crewroom/static/app.js: room poll stops while hidden.
- apps/files/static/app.js: drive check also skips when the tab is hidden.
- apps/arcade/static/index.html: hub hide pauses a running game.
- apps/emberfield/static/ui.js: hidden pauses (it never had hub Rest). Tutorial timer cleared at the end and skipped while off screen.
- apps/pixelforge/static/index.html: playback holds while hidden.
- docs/library/power/2026-10-07-app-power-sweep.md

## Numbers (per 12 s, A/B in one sitting)
- Hidden fetches dropped to 0 on Board, Jan Tune, Comix and PulseForge (each was 4), and on PanelForge, Acchan and NovelForge (each was 1). Visible behaviour is unchanged.
- Board backend CPU while hidden: 0.22 s, now 0.02 s.
- Janhollow hidden fetches: 15, now 5.
- In-hub iframe: Janhollow page CPU 5.18 s visible, 0.03 s hidden; Crew Room 0.67 s visible, 0.012 s hidden.
- Page-side savings are small (milliseconds). The real gains are backends no longer being woken, and Emberfield and Arcade no longer running behind other apps.

## Breaker and critic
- Breaker on Board found nothing to fix. A dead server gives no request storm and the page recovers on its own. 1000 hide/show flips leave one timer and the normal rate. After 60 s hidden it fetches at once.
- Critic: fixed 8 findings (one real bug: Board desktop alerts died while the Board was hidden), left 4 by choice. Both lists are in the doc.

## Risks and not done
- Not checked inside the real WebKitGTK Forge window. The hub was imitated in Chrome.
- If /shared/forge_idle.js ever fails to load, page scripts stop at the ForgeIdle call. Every app serves /shared, so this is unlikely.
- Nothing committed.
