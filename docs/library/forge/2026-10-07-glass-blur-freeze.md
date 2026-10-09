# Forge freezing on Frosted or Liquid glass (Relay task 63)

date: 2026-10-07 · for: both

Emerson's Forge froze when he picked Frosted or Liquid glass in Alt+Shift+M.
Found, fixed, and checked in real WebKitGTK; the frame-rate re-measure after
the fix is still to run (Emerson: performance runs go last).

## Cause (verified)

Measured by Kana and Koharu (task 63) in a private headless GNOME Shell at
3072x1728 with WebKitGTK 2.54 and the real hub, visualiser fed fake levels:

| live-blurred panes on screen | hub frames a second |
|---|---|
| 8 | 60 |
| 13 | about 9 |
| 17 | about 1 |
| 52 (every tile, chip and widget) | 0, and with Liquid the page's main thread hung (no answer for 20 s and more) |
| 3 (bar, search, dock only) | Frosted 62, Liquid 61 |

Live blur is CSS `backdrop-filter`: WebKitGTK repaints whatever lies behind
each blurred pane on every frame, and the cost climbs steeply with their
number. The visualiser, the 3D wallpaper and the blur radius were ruled out
one at a time. Emerson's crash dumps matched: WebKit's compositor thread deep
in layer painting, the page's main thread waiting on it.

## The fix

- `shared/glass/frosted.css`, `shared/glass/liquid.css`: live blur only on
  `.glass:not(.tile)`, which is the bar, search, dock, popups and an app's
  loading card. Tiles, filter chips and widgets draw their glass: a thicker
  milky fill and a soft light from the top. The first try (Kana) blurred
  `.glass` and missed that the hub builds its tiles as `tile glass`; the rig
  still showed 41 blurred panes, 0 fps on Frosted, and Liquid hung. Hence
  the `:not(.tile)`.
- `shared/forge_widgets.css`, `desktop/particles.html`: widgets draw their
  glass too.
- `forge.py`: a hang watchdog (`hub_hang_watchdog`, `hub_hang_ender`). Every
  4 s it asks the page whether its main thread runs and, with Forge in
  front, whether it paints a frame. No answer for 10 s, or 10 s of no frames
  while the window itself got frames, ends the page; the crash reloader
  brings it back with the heavy looks off (`?safe=1`). Needs a Forge
  restart to take effect; the CSS is live on a hub reload.
- A bug found on the way: WebKit's `call_async_javascript_function` refuses a
  boolean argument ("Invalid parameter frames"), so the first watchdog's
  every question failed at once, and as an error counts as an answer it
  could never see a hang. Its unit tests used a fake WebKit and passed. The
  flag now goes as 1 or 0, a failed question is printed once, and a test
  checks the argument types.

## Checked after the fix (2026-10-07 ~22:20)

`tests/browser/check_hub_hang_webkit.py` in `tests/browser/headless_gnome.sh`,
all PASS:

- live blur on 4 panes (the Alt+V hint, bar, search, dock), none of the 39
  tiles, in both Frosted and Liquid; pictures looked right;
- a healthy hub ran 20 s in front without the watchdog ending it, and the
  window's frame clock moved on (90 -> 917 frames);
- `requestAnimationFrame` swallowed (frames stopped): ended once, back with
  `?safe=1`, running;
- `for (;;) {}` on the main thread: ended once, back with `?safe=1`, running.

The rig's GNOME has no seat, so it focuses no window; the check's window
reports itself in front. Everything else is real.

Unit tests: `tests/test_hub_hang.py`, `tests/test_glass_budget.py`,
`tests/test_hub_crash.py`, 24 pass (`apps/dossier/.venv/bin/python -m
pytest`). Two new tests fail on the old code: the argument-type test on the
boolean, the class-scan test on the plain `.glass` selector. In headless
Chrome, `tests/browser/run.sh` hub_glass: all PASS, including "blurs only
single panes" for both kinds.

## Critic fixes (2026-10-07 ~23:00)

A critic's run in real WebKit found the watchdog ending healthy pages:

- an app's `confirm()` (even in a cross-origin app frame) blocks the hub's
  main thread until answered; the page was ended 15 s into the dialog. Now
  WebKit's `script-dialog` signal pauses the count until the page answers
  again. Known gap: a page that comes back from a dialog already stuck is
  not caught.
- Forge's own GTK loop blocked for 11 s: the page's answer sat unread and
  the late tick ended it. Now a tick more than two pings late gives the
  page one more ping, once per question, so a hang that also stalls Forge
  is still caught a ping later.
- after a hang the safe-mode note said "crashed twice"; it now says
  "crashed or froze".

A second critic (report: /tmp/t63/critic3/report.md, scratch, may be gone)
found more, all fixed the same evening:

- a page stuck before its load finished was never asked (the watchdog
  waited for FINISHED). Now it starts at COMMITTED, with a 30 s limit
  (`HUB_HANG_LOAD_LIMIT`) until the load finishes: Forge starting with a
  heavy look saved, and the safe reload itself, are covered.
- a page stuck right after a `confirm()` was answered was never caught.
  WebKit draws its own dialog inside the view (`WebKitScriptDialogImpl`);
  each tick looks for it, and once it is gone the count starts afresh.
- `window.print()` keeps the page waiting like `confirm()`: it pauses the
  count too.
- a page that crashed with a question out logged "the hang watchdog's
  question failed"; a crashed page is now asked nothing more.
- its mutation run (26 mutants, 8 survived): tests added for main()
  wiring the watchdog, the question's frame wait (run in node), the reset
  on a new page, the mapped check and dock items wearing glass. All 7
  mutants tried again were caught.

Checked: rig `check_hub_hang_webkit.py`, now 7 checks and 23 PASS lines,
exit 0, in real WebKit (adds: a `confirm()` held open 27 s is not ended and
the page runs on after; WebKit's own dialog shows in the view, is not ended,
and a page stuck after OK is pressed is ended and back in safe mode; a page
stuck while loading is ended and back in safe mode). Unit tests 39 pass.
Seen on the way: four ends in two minutes leave the "keeps crashing" page,
as `after_hub_crash` says.

Known gaps, not fixed (low):

- the question runs in the page's own JavaScript world, where
  `shared/forge_framecap.js` wraps `requestAnimationFrame`; a bug there
  could make a healthy page look frameless. An isolated world (a world
  name in `call_async_javascript_function`) would stop that, but the rig's
  "frames stopped" check would need another way to stall frames.
- a page stuck right after a print dialog (or a dialog some other handler
  took) is not caught: those pause the count until the page answers.
- with all five popups open at once 9 panes blur (8 ran at 60 fps); normal
  use is 6 or 7.
- app pages blur on their own and `tests/test_glass_budget.py` does not
  scan `apps/`; `classList.add("glass")` on a repeated item is not caught
  by the scan (the browser suite's count of at most 8 blurred panes is).

## Frame rate after the fix (2026-10-07 ~23:40)

`check_hub_hang_webkit.py --fps` in the headless GNOME (3072x1728, real
WebKitGTK 2.54, visualiser fed, 12 s each), median and lowest fps:

- flat: 55, lowest 36
- frosted: 54, lowest 47
- liquid: 53, lowest 47

Before the fix the same hub gave frosted 0 fps and liquid hung. Another
session's headless browser was running at the same time, so treat these as
a floor, not a ceiling.

That run also showed one flake: a page stuck while loading was ended, and
then the safe reload was ended a second time mid-load. The likely cause
(reasoned, not proven): the frame test applied while the page was still
loading, and a loading page may rightly paint nothing. Now only "does it
run" is asked until the load finishes; the frame test starts at FINISHED.
After that change the rig ran clean twice (23 PASS, exit 0, each run);
unit tests 39 pass.

## Still to do

- Emerson: restart Forge once for the watchdog (the CSS is live on a hub
  reload).
