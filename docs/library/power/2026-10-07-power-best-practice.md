# Power best practice for Forge pages (best-guess checklist until a proper test)
date: 2026-10-07 · for: both · written by Umi (overhaul commander)

Emerson (2026-10-07): until a proper test can take place, do the general, best-guess, research-backed power work, as well as it can be done. So the overhaul helpers stop long measuring runs on the busy machine, apply this list, check briefly that the page still works and goes quiet when hidden, and leave real numbers to one proper test at the end (AC and unplugged, with Emerson).

Status: research and reasoning, **not measured** on this laptop yet. Sources at the bottom.

## Ranked by expected saving on the Iris Xe (shared CPU/GPU power budget)
1. **Nothing runs while hidden.** Every rAF loop, setInterval, poll, WebSocket redraw and audio analyser stops on `visibilitychange`/`forge-visible` (shared/forge_idle.js) and resumes on show. WebKitGTK only marks a view hidden when it is minimised, on another workspace or fully covered, and Forge's GDK "fully obscured" signal arrives ~4 s late, so the page must also obey the shared power tier ("paused: hidden", "mostly covered").
2. **requestAnimationFrame, never timers, for drawing.** Timers under 16.7 ms overdraw; rAF lines up with the display and is throttled by the browser. For a lower fps, skip frames inside rAF (draw only when `now - last >= 1000/fps`), don't switch to setTimeout.
3. **Move by time, not by frame.** Speed = units per second x dt, so a 30 or 15 fps cap looks slower-but-smooth, not slow motion (fixes the note #931 kind of bug).
4. **Smaller canvases.** Cap the backing store at devicePixelRatio min(dpr, 1.5) for decorative layers (1.0 for blurred/soft backgrounds, which look the same at lower resolution), and size to the element, not the screen. Fill rate is the iGPU's weak point.
5. **Polls slow down when idle.** Back off on no change (2 s, 5 s, 15 s, cap 30-60 s), snap back on user input or a server push; prefer one server-sent stream over many timers.
6. **No always-running heavy CSS.** `backdrop-filter` is redrawn every frame when anything under it moves: keep blur radius modest (<= 10-12 px), on small elements, few at once, never over an animated canvas while the reduced tier is on (swap to a flat translucent fill). Never animate `filter`, `box-shadow`, `width/height/top/left` or big gradients; animate `transform` and `opacity` only (150-250 ms).
7. **Infinite CSS animations stop when not needed.** Spinners, shimmer, pulsing dots: `animation-play-state: paused` when hidden or idle, and under `prefers-reduced-motion` and the reduced tier.
8. **`will-change` only while animating.** Add it just before a transition and remove it after; every promoted layer costs video memory and compositing work.
9. **`content-visibility: auto`** (with `contain-intrinsic-size`) on long lists and off-screen panels, so layout/paint skip what isn't on screen.
10. **Batch DOM work.** Keyed patches instead of rebuilding innerHTML each poll; skip the render when the data hasn't changed (compare a hash or an etag).
11. **Shared power tier is the one switch** (shared/forge_power.js): read particle_amount / particle_fps / max_fps / visualiser_shown from the eased theme the host hands you, never the raw theme. full = as configured; reduced = fps <= 30 (widget visualiser 20), fewer particles, no backdrop blur over moving layers; paused = nothing drawn.
12. **Looks are not traded away.** Reduced keeps the same design, just fewer frames and particles; when in doubt, pick the cheaper way to draw the same picture (pre-rendered gradient image, CSS transform on a static layer, cached offscreen canvas) instead of dropping the effect.

## Quick check each helper does (instead of measuring)
- Page works at 760/1100/1500 (headless screenshot looked at).
- Hidden: no rAF callbacks and no network polls for 10 s (count them with a tiny injected counter in the headless check).
- Reduced tier: fps cap and particle drop take effect; nothing looks broken.

## Quiet window for real measurements (Emerson, 2026-10-07)
"if the power thing needs to it can tell sessions to stop and then it can run tests, i'm allowing up to 10 mins total of stoppage, and then it starts them again". Tool: `python3 ~/Forge/tools/quiet_window.py run --seconds 120 --label "<what>" -- <command>`. It freezes every other Claude session and its children (SIGSTOP/SIGCONT), never Emerson's Forge, Relay, Jan, GNOME or Whatsie; one pause is at most 180 s; all pauses share a 600 s budget kept in ~/.local/share/forge/quiet_window.json (`status` shows it); a detached watchdog thaws everything at the deadline even if the test crashes; `release` thaws everything by hand. Verified: 6 tests in tests/test_quiet_window.py (freeze during, thaw after, budget cap, overrun cut-off, watchdog) and a dry run on the live machine (41 processes picked, two claude sessions, none of the protected apps). Not yet done: a live pause of real sessions.

## Sources
- WebKitGTK hidden-view throttling and visibilityState: https://bugs.webkit.org/show_bug.cgi?id=285167 , rAF outside-viewport throttling: https://bugs.webkit.org/show_bug.cgi?id=178396
- backdrop-filter redraw cost and blur radius advice: https://docs.coherent-labs.com/cpp-prysm/integration/optional_features/globalbackdropfilter/ , https://www.react.doctor/prompts/rules/react-doctor/no-large-animated-blur.md , https://forum.hypr.land/t/understanding-blur-different-ways-to-set-and-performance-hit/112
- rAF vs timers, overdraw: https://github.com/zoltanharmath/Windows-universal-samples/blob/master/Samples/EfficientAnimations ; DPR cap trade-off: https://developer.playcanvas.com/user-manual/optimization/runtime-devicepixelratio/
- will-change memory, content-visibility: https://developer.mozilla.org/docs/Web/CSS/will-change , https://cursos.ceslava.com/en/curso/css/leccion/css-performance-pro
