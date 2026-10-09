# App size and Text size sliders: the flip-flop and the lag

date: 2026-10-07 · for: both · Relay task 68 (Itsuki)

## What Emerson saw

"when I change the size it will keep switching, cause I think it thinks the
slider moved and changes setting when the thing resized ... also just make it
faster". He was right about the cause.

## Cause

App size is WebKit page zoom on the one view that holds the hub *and* every
app (forge.py `page_zoom` / `set_zoom_level`). Both size panels applied it on
every slider tick:

- Hub Aa panel: every `input` event ran the full `applyTheme` (glass,
  particles, visualiser, widgets...), asked forge.py for a new zoom, and posted
  the theme to every open app.
- Settings > Size: saved every 180 ms mid-drag; each save told the hub, which
  zoomed, posted the theme to every app, and Settings re-fetched its settings.

A zoom rescales the panel holding the slider under a pointer that has not
moved, so the next pointer move reads another value, which zooms again.

## Fix

- `shared/forge_theme.py`: the three size settings carry `"apply": "release"`
  (Text size also `"preview": "text_size"`). Any other setting can opt in the
  same way.
- `apps/settings/static/app.js`: a slider whose spec says `apply: release`
  (and the Preset slider) only previews while dragged: its number and the
  preset name update, Text size shows on the Settings page itself
  (`ForgeChrome.previewTextSize`, new in `shared/forge_chrome.js`), nothing
  is saved or sent. On release (`change`) it is saved once and the hub applies
  it once. Settings does not re-fetch while a drag is on.
- `hub/index.html` `Sizes`: `input` -> `Sizes.preview` (Text and Icon size on
  the hub only, App size as a number), `change` -> `Sizes.set` (one
  `applyTheme`, one zoom, one save). The Preset slider likewise.
- `hub/index.html` `applyTheme`: the theme post to every app frame is now
  `broadcastTheme()`, a throttle (first post at once, then at most one per
  80 ms, with a trailing post), so a burst of changes reaches each app once.
- No forge.py change, so no Forge restart is needed: a hub reload picks it up.

## Measured (verified, headless Chrome harness)

`apps/terminal/.venv/bin/python tests/browser/check_size_drag.py` loads a copy
of the real hub with the real Settings app inside it (throwaway config) and
drags with real CDP mouse events: 40 moves at 16 ms, then 20 one-pixel jitters
(a hand holding still), then release. forge.py's zoom is stood in by CSS zoom
on the hub root, applied a tick after the hub asks, with the pointer kept on
the same screen pixel. Raw logs: `2026-10-07-size-sliders-before.json`,
`-after.json` beside this file.

Before the fix:

- Hub App size, aimed at 1.35: ran away to 1.50 (7 zooms on the way). Aimed
  back at 1.10: ran to 0.80 (10 zooms).
- Settings App size, aimed at 1.35: reached 1.35, then flipped to 0.80 when
  the zoom landed (2 saves, 2 zooms). Next drag aimed at 1.10 ended at 1.20.
- Hub Text size: 7 full `applyTheme` runs (44.8 ms) and 7 theme posts to the
  apps per drag.
- One earlier run saw a single pointer move in Settings take 1.7 s.

After the fix (all 32 checks pass):

- Every drag ends on the value let go at, with 1 zoom (App size) or none
  (Text size), 1 save, 1 theme post to the apps, 0 flip-flops.
- Hub Text size drag: `applyTheme` 1 run, 1.2 ms total (was 44.8 ms).
- Pointer-move handling, mean: hub App size 6.7 -> 2.3 ms, hub Text size 4.1
  -> 2.2 ms (Chrome numbers; WebKit relayout of every app per zoom is heavier,
  so the real saving on Emerson's machine should be larger, not measured).

## Critic pass (opus, fresh context) - all confirmed findings fixed

- Settings Text size preview made a scrollbar appear and shifted the page
  7.5 px under the pointer: `main { scrollbar-gutter: stable; }` in
  `apps/settings/static/app.css`, and the dragged row keeps its size. The
  harness's "one step off" on that slider was this bug; now every drag lands
  exactly (harness tolerance tightened to 0.001).
- An `applyTheme` arriving mid-drag no longer undoes the hub preview.
- Icon size preview now resizes the dock too.
- Hub arrow keys on a slider commit 150 ms after the last key press.

## Not verified

- Not run in the live Forge window (Forge not restarted, by rule). The real
  WebKit view should behave the same: the fix removes mid-drag zooms entirely.
- While dragging App size nothing grows until release; that is the point.
