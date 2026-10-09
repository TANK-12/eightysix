# Hub top bar: many open apps no longer push the tray off screen

date: 2026-10-09 · for: both · Relay task 121

Emerson (2026-10-07): "when i add apps it will push the icons of non-app stuff off the screen".

## Cause

The open-app icons (`#workspaces` in `hub/index.html`) could not shrink: every icon was `flex: none` and the strip
had no minimum width or overflow. Past about twenty open apps the strip grew wider than the bar, the title shrank to
nothing, and the app's Full screen/Close and the whole tray (reload, zen, background mode, Aa, clock, settings) slid
past the right edge of the window.

## Measured before the fix (headless Chrome, 30 open apps, `tests/browser/hub_bar_many_status.js`)

| window | strip width | tray left..right | on screen? |
|---|---|---|---|
| 1400 px | 1148 px | 1460..1721 | no, the whole tray is off the right |
| 800 px | 1158 px | 1470..1731 | no |

## What changed

- The strip scrolls sideways (no scrollbar; the mouse wheel scrolls it too) and keeps room for at least one icon.
- The brand and the tray never shrink. When the bar is still too full, it gives way one step at a time until the tray
  fits: the Full screen/Close labels go (icons stay), then the title, then the strip's last icon (only "+N" is left),
  then the zen and background buttons (Alt+Z, Alt+B still work), then reload (Ctrl+R). This is measured, not a fixed
  breakpoint, so it holds at any text size.
- A "+N" button beside the strip says how many open apps are out of sight (an icon half under a fade counts as out);
  it opens the overview of every open app. It gets a dot when one of those apps has news or failed, and pulses if one
  is busy.
- A fade marks the end of the strip that has more icons (28 px, less on a very narrow strip).
- The app in front is scrolled into view, clear of the fade, whenever it changes (click, Alt+1..9, Alt+Left/Right,
  and Alt+N on the app already in front after the strip was scrolled away).
- "+N" follows an icon-size change at once (the strip keeps its box, so no observer would see it).

## Measured after (same fixture)

| window | strip shows | "+N" | tray right edge vs bar | steps taken |
|---|---|---|---|---|
| 1400 px | 617 px, 16 icons | +15 | 1383 inside 1390 | none |
| 800 px | 95 px, 2 icons | +29 | 783 inside 790 | none |
| 700 px | 2 icons | +28 | inside | labels off |
| 500 px | 51 px, 1 icon | +29 | 483 inside 490 | labels and title off |

Every bar width from 500 to 1400 px in 20 px steps, at text size 1 and 1.5: the tray, clock, settings, Aa and the
brand stay inside the bar (the harness narrows the bar in place; headless Chrome cannot go under 500 px).

Screenshots of the bar: `2026-10-09-hub-top-bar-before-1400.png` (tray gone), `-after-1400.png` (news dot on "+15"),
`-after-700.png`, `-after-500.png`. Checked by `tests/browser/hub_bar_overflow_harness.js` in `tests/browser/run.sh`
at 1400, 800 and 500 px (29, 29 and 26 checks); it fails on the hub from before the fix.

## Not covered

- Dragging an app onto a folder icon that is scrolled out of sight: the strip does not auto-scroll while dragging.
- Right-to-left layout (the hub sets no `dir` today).
- The glow around the app in front is cut off at the strip's top and bottom edge (the ring itself shows in full).
