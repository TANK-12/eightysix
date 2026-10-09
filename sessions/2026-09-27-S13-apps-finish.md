# S13: apps finish, session "ejb-ae" (Suzu)

Session ejb-ae, default account, Opus 5.5, 2026-09-27. Split from Hagane
(S12, ejb-72) at Emerson's request. Hagane's ledger items B13, B15, B16 and
B17 are mine; the ask text is in sessions/2026-09-27-S12-hub-apps-wave.md.
I do not commit: finished file lists go to ejb-72, who commits.

## Owns
apps/panelforge, apps/arcade, apps/calendar, apps/claude/static/enjoy.*
(plus the claude backend only where Enjoy needs it). Backups:
backups/2026-09-27-S13/.

## Ledger
| # | Ask | Plan |
|---|---|---|
| B16a | PanelForge: explicit non-scroll style not turned into scroll | Guard in api/render.py render_chapter; cast.js scroll render keeps working; API test. |
| B16b | PanelForge timeline editor "broken" | Scratch server + tests/cdp_driver.py on static/js/tabs/timeline.js; fix; check. |
| B16c | PanelForge "more effects" | New registry entries (transitions, render/effects.py): screentone halftone, speed lines, impact shake, film grain; a test each. No long/GPU renders. |
| B17 | Arcade matches the theme | Shared Forge theme mechanism, still works standalone; screenshot. |
| B13 | Calendar broken (port clash with Jan Tune, now 8461) | Headless check on a test port; fix what else turns up. |
| B15 | Claude Enjoy layout finished | WIP improve-next: model/effort/permission pickers in task view, drag loose task onto project, image paste, polish + animation. |

## State
- Started 2026-09-27; usage 25% of 5h, 78% of 7-day.
- B16a done+checked: style guard in api/render.py, API test.
- B16b done+checked: timeline click/select, style names, registry transitions, resize ripple, thumbnails from strip; tests/check_timeline_ui.py 8/8.
- B16c done+checked (unit tests; no film rendered): screentone + flash transitions, film_grain + rgb_split effects. Suite 578 passed. File list sent to ejb-72.
- B17 done+checked in headless Chrome (fake hub, same origin): Arcade follows the theme, standalone unchanged, game starts. Not seen in the real WebKit hub yet (needs Forge restart).
- B13 done+checked: Calendar works standalone (19 tests, headless Month/Week/Day on a data copy, no errors); no port clash left in any manifest; no code change, WIP.md note only.
- B15 done+checked (headless Chrome, synthetic drag events): Enjoy task pickers (model/effort/may) saving + remembered for new tasks, drag task onto project / back to loose, file drop onto chat, view/row/toast motion. check_enjoy_ui.py 11/11 x4, suite 108. Not seen in the real WebKit window.
- All four items done; nothing left running (scratch servers stopped, checked with pgrep). Changes show after the apps are reopened / Forge restarted.
