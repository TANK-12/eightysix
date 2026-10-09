# Final analyst: power code audit of the overhaul wave
date: 2026-10-07 · for: Claude · analyst of the final review swarm (commander Nene, relay-63-work)

This is a code audit only. Emerson's note 1054 says no power or performance runs until all other work is done, so nothing here is a CPU, GPU or fps measurement. Each finding is marked **verified** (code read, plus a page harness where one ran) or **reasoned** (cost inferred from the code and earlier measured docs). The numbers in brackets come from earlier docs (task 71, `docs/library/performance/2026-10-07-cpu-gpu-bursts.md`), not from this audit. The plan for the real measurements is in `docs/library/power/2026-10-07-overhaul-numbers.md`.

Harness used (scratch only, `/tmp/t63/final-analyst/`): a copy of the real `hub/index.html` with Emerson's real `hub/theme.js` and `status.js`, plus a pre-script that tags every requestAnimationFrame and timer with the line that scheduled it. It ran in off-screen WebKitGTK (`tests/page_probe.py`) with fake system-audio levels at 60 a second. Off-screen WebKit throttles rAF to about 8 a second, so the rates below only show **who** asks for frames, not how fast. Raw output: `/tmp/t63/final-analyst/raf_counts_webkit.txt` and `timers_anims_webkit.txt`.

## 1. Note 971: "an app open in front of Forge, GPU still high". What still draws

Emerson's settings (`~/.config/forge/settings.json`) choose most of this: `particles_in_apps: true`, `visualiser_in_apps: true`, `visualiser: bars` with `visualiser_source: system`, `wall_tint: true`, `behind_apps: sharp`, `glass: 0.46`, `particle_fps: 25`, `max_fps: 60`, glass style `flat`. An app's page background is translucent: `shared/forge_chrome.js:340` sets `--bg` to the glass alpha (0.46), and `.workspace .inner` (`hub/index.html:451`) is about 16% opaque. So whatever moves behind the app shows through it, and each frame of it makes WebKit composite the whole window again: wallpaper, tint, scrim, the two canvases and the app's own layers.

With an app in front, on AC, window visible (harness phase "app open"):

| What | Runs with an app open? | Rate | Evidence |
|---|---|---|---|
| Particles canvas (full window) | **yes** (`Particles.showing`, `hub/index.html:2284`) | draws 25/s and wakes rAF at the screen rate to skip frames | verified: harness `particles.raf=true`, callers `forge_particles.js:307` |
| Visualiser canvas (full window, bars) | **yes** while sound plays (`hub/index.html:2413`) | 60/s (max_fps 60 means no cap), plus cava at 60/s pushed by forge.py through `run_javascript` | verified: harness `visual.running=1`, caller `index.html:2488` (Visual.frame) |
| `#wall-tint` 60 s background-colour transition | **yes, always**, on home and in apps | a main-thread CSS transition, so a style and paint update on every display frame, around the clock | verified: harness `#wall-tint:background-color running, 60000 ms` in both phases |
| Power tier | stays `full` | none | verified: harness `tier=full` with an app open. `ForgePower` has no input for "an app is in front" |
| 2.5D depth drift | stops (`drift` checks `current === null`, `hub/index.html:2180`) | none | verified (code read) |
| Hero clock shimmer, widgets breathing orb | paused (`hub/index.html:373`) | none | verified: harness shows `#big-clock:shimmer` and `wg-orb` only on home |
| Widgets' 1 s card updates | skipped when `in-app` (`shared/forge_widgets.js:240`) | timer fires, no work | verified (code read) |
| Clock `tick()` | yes | 1/s, rewrites four text nodes even when unchanged | verified: harness `index.html:1826 @1000` |
| NowPlaying ask, Visual keep-alive | yes | every 3 s, every 5 s | verified: harness timers |
| Bar icon busy glow (`.ws.busy`) | would run, but no app sends `busy` (grep found no sender) | n/a | reasoned |
| Desktop page (`desktop/particles.html`) around a Forge window that is **not** maximised | yes: particles 30/s (amount 2.0), visualiser 40/s, at full tier while 35% or more of the desktop shows | 30-40/s | verified (code read: `desktop/particles.py` rests only when covered or under a maximised window) |

Hidden window (harness phase "window hidden"): particles and visualiser both stop, no rAF at all. Verified. Mostly covered (forgeShare 0.2): visualiser off, particles at the reduced rate. Verified. On battery at 60% (above Emerson's `battery_saver: 50`): visualiser off, particles still running, tier still reads `full`. Verified.

**Answer.** With an app in front, the hub still draws the particles at 25 fps and, whenever music or any sound plays, the bars at 60 fps. Both are full-window canvases behind a 46%-translucent app, so each of their frames re-composites the whole 3072x1728 window, the app included. On top of that, the wallpaper tint's 60-second colour transition never ends: one finishes, the next minute's colour starts another. That keeps the page producing a frame every display refresh even when nothing else moves, on battery too, because the frame cap only wraps rAF and the lite mode only stops animations, not transitions. Task 71 measured particles as the largest steady GPU cost (home: about 30% GPU with them, 4.5% without). The tint fits inside the 4.5% / 11%-core residue left with everything else off (reasoned). The tier cannot help, because it does not know an app is in front.

## 2. Ranked audit: what is left, by likely cost

Each entry gives where, why it costs, the fix and its status. Wave commits checked: 35ef508 (Mission), 994989b (app sweep), be02b98 (Claude app), b132a41 (hub, desktop, tier), acc42c6 / 7d13c63 / a15cd03 (icons), 3665850 (size sliders), 13136b1 (layer vars), a5788ee (glass).

1. **Particles keep drawing behind an open app at the full tier.** `hub/index.html:2284` (`Particles.showing`), `shared/forge_power.js:61-115` (no "app in front" input). Why: a full-window canvas redrawn 25 times a second, plus a full-window composite under a translucent app each time (task 71: particles are about 25 points of GPU on home; 25 to 12 fps saved about 10 points). Fix that keeps the look: pass `app: current !== null && !Zen.on && !Ambient.on` in `powerState()` (`hub/index.html:1903`). In `ForgePower.values()`, when `state.app` is set, cap `particle_fps` at 15 (`APP_FPS`) and leave amount and size alone. Make `tier()` report `"reduced: app in front"` only if the visualiser rule below should follow it. Call `powerChange` from `selectWorkspace`. Through 54% of opaque app, 15 fps of slow drift is hard to tell from 25. Status: running verified, cost reasoned.
2. **Visualiser at 60 fps behind an open app while sound plays.** `hub/index.html:2413`, `2483-2495`. Why: full-canvas `clearRect` plus 32 gradient bars a frame at visualiser_size 2.0, a full-window composite each frame, and forge.py runs a `run_javascript` 60 times a second for cava's levels (task 71: forge.py at 14-34% of a core while he chatted). Fix: under the same `state.app`, step `Visual.frame` down to 30 fps (skip inside rAF as particles do) and ask cava for `fps: 30` in `Visual.ask` (`hub/index.html:2373`). Optionally clear and draw only the bottom band the bars style uses. Status: running verified, cost reasoned.
3. **`#wall-tint` transition never stops.** `hub/index.html:48`: `transition: background-color 60s linear`, with `WallFx.tint()` setting a new colour every 60 s (`hub/index.html:2256`). Why: a non-composited full-window colour transition that is always in progress, so main-thread style and paint plus a window composite run on every display frame. That happens on home, in apps, on battery and in lite mode, and it is not capped by `ForgeFrameCap`. Fix: `transition: none` (one minute's step is under 0.5% alpha, which nobody can see). If a fade is wanted, `transition: background-color 2s linear`, which runs 2 s a minute (3% of the time). Status: always running verified in WebKit, cost reasoned (bounded by task 71's 4.5% GPU / 11% core residue).
4. **The power tier does not know an app is in front.** The structural cause behind 1 and 2. `shared/forge_power.js:61` (`level`), `hub/index.html:1903` (`powerState`). Fix as in 1. Unit cases go in `tests/test_power_tier.py` (state.app gives APP_FPS, and leaves amount and visualiser_shown unchanged). Status: verified (harness `tier=full`).
5. **Music Web Audio graph never suspends.** `hub/index.html:3085` (`Music.graph`). Why: about 4% of a core always, and an audio stream stays open (task 71, measured). Fix: `actx.suspend()` when the music is paused, the visualiser source is not `music` and Alt+V is off. `resume()` on play is already wired at `hub/index.html:2336`. Status: reasoned here, measured by task 71. Left by task 71 out of caution about silencing his music.
6. **Claude app busy indicators.** `apps/claude/static/enjoy.css:96` animates `box-shadow` forever while a run is running, which repaints every frame (best practice 6). `apps/claude/static/app.css:20,212,255,267` pulse opacity at 60 fps with a permanent `will-change: opacity` (`app.css:313`). Task 71 measured the panel's busy dots at about +5% GPU. Fix: e-breathe as opacity on a `::after` ring instead of box-shadow, and `steps(12)` timing on the pulses, as task 56 did for the clock shimmer. They pause when hidden through forge-resting. Status: verified (code read), cost from task 71.
7. **Desktop page around a Forge window that is not maximised.** `desktop/particles.py:158` (`resting`) rests only when covered or under a maximised window. While 35% or more of a screen shows, it draws particles at 30/s (amount 2.0) and the visualiser at 40/s at the full tier. Fix: none needed if Forge is normally maximised. Otherwise treat "Forge is the focused window on this screen" like the reduced tier. Status: reasoned (code read; depends on how he places Forge).
8. **Particle loop wakes at the display rate to draw at 25.** `shared/forge_particles.js:275-277` asks for the next rAF on every skipped frame, so 60 wakes a second for 25 draws. Fix: sleep on a timer until just before the due frame, the way `ForgeFrameCap.pump` does (`shared/forge_framecap.js:39-44`). Small CPU only, because skipped frames paint nothing. Status: verified (code read). It follows best practice 2 as written; the doc could add "sleep between skipped frames".
9. **Clock `tick()` rewrites text every second.** `hub/index.html:1809-1826` sets `textContent` on `#clock`, `#big-clock`, `#big-date` and `#greet` even when unchanged, which causes a style and layout pass each second, in apps too. Fix: write only on change, and with `clock_seconds` off, time the next tick to the next minute. Status: verified (code read), cost small.
10. **Hero clock shimmer with a large drop-shadow filter.** `hub/index.html:270-274`: `steps(66)` over 11 s (6 repaints a second) of 132 px gradient text under `filter: drop-shadow(0 6px 30px ...)`. Home only. Fix: move the shadow to a static sibling or `text-shadow` on a copy, so each step repaints the text without refiltering. Status: reasoned.
11. **Blur cost outside the glass budget.** `#overview` uses `backdrop-filter: blur(14px)` (`hub/index.html:199`), above the doc's 10-12 px, but only while Alt+Space is open. `#fx-hud` keeps `backdrop-filter: blur(10px)` at `opacity: 0` (`hub/index.html:640`). Fix: blur 10 px on the overview, and put `#fx-hud`'s backdrop-filter on `#fx-hud.show` only. Status: reasoned, small.
12. **Mission Control** (audited from `git show HEAD:`; task 73 is reworking `apps/mission` right now, so this may be stale). Polls go through `ForgeIdle.shown()` with backoff, SMIL sprites pause when hidden or calm, and markup is patched only on change. All good. Left: `app.css:253` `.spr.live > i { will-change: transform }` gives one layer per live sprite, so dozens with 50 sessions. `app.css:383-384` puts two stacked `drop-shadow` filters on sparks that fly along edges (up to 8 at once, 1.3 s bursts). Fix: no will-change on step-end sprites (they do not interpolate), and a pre-drawn glow circle instead of the double filter. Status: verified (code read at HEAD).
13. **Bar icon busy glow** `hub/index.html:175-179` animates `box-shadow`. Dormant: no app posts `{forge: "busy"}` (grep). Fix if it is ever used: opacity on a pseudo-element. Status: reasoned.

Fine as built (verified by code read unless marked): hidden stops everything in the hub (harness); 2.5D drift off in apps and on battery, with depth canvas resolution at 0.75 (0.5 reduced) capped at 1920 wide; particle and visualiser canvases at CSS pixels (below any DPR cap); glass blur on single panes only and none at all on Emerson's `flat`; widget glass drawn, with no live blur; desktop GNOME extension is event-driven with debounced timers (120 ms, 400 ms); app polls (994989b) through ForgeIdle; parallax variables on their layers (13136b1); size sliders post once per drag (3665850); icons are static SVG (acc42c6, 7d13c63, a15cd03; no loops found).

## 3. Against the best-practice checklist (docs/library/power/2026-10-07-power-best-practice.md)

| # | Item | State |
|---|---|---|
| 1 | Nothing runs while hidden | pass in the hub (harness) and in the swept apps (994989b). Small fixed timers (1 s, 3 s, 5 s) still fire, cheaply |
| 2 | rAF, not timers, for drawing | pass. Particles wake at the display rate between draws (item 8) |
| 3 | Move by time | pass (particles `k`, visualiser `dt`, depth drift) |
| 4 | Smaller canvases | pass |
| 5 | Polls back off | Mission yes. Claude app `loadEveryone` every 5 s and accounts every 60 s are fixed, gated by `ForgeIdle.shown()` (`apps/claude/static/app.js:1071,1245`). Partial |
| 6 | No always-running heavy CSS | **fail**: `#wall-tint` transition (item 3), e-breathe box-shadow (item 6). Overview blur 14 px |
| 7 | Infinite animations stop when not needed | hub home paused in apps (pass). Apps pause through forge-resting (pass). Lite mode stops animations but not transitions (item 3) |
| 8 | will-change only while animating | partial: Claude busy dots, Mission live sprites |
| 9 | content-visibility on long lists | **not used anywhere** (grep of hub, shared, apps/*/static). Candidates: Mission session grid, Claude chat list, Board |
| 10 | Batch DOM work | pass where checked (Mission `setHtml`, relay strip compare) |
| 11 | One power tier | pass for hidden, covered and battery. **Missing "app in front"** (item 4) |
| 12 | Looks not traded away | every fix above keeps the picture: fewer frames behind an app, never fewer effects |

## 4. Suggested order of fixes (cheapest first, biggest effect first)

1. `#wall-tint` transition to none (one line, invisible change).
2. `state.app` in ForgePower: particles at 15 fps and visualiser at 30 fps behind an app (about 30 lines plus tests).
3. Suspend the Web Audio context when nothing needs it (needs a careful music check).
4. Claude app busy indicators to opacity with `steps()`.
5. The small ones (tick, fx-hud blur, particle wakes, Mission will-change).

None of these were applied: this lane is read-only. Every one should go into the before/after table in the numbers doc.
