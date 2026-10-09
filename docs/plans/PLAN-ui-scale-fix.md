> **2026-09-25:** the remaining work here now lives in `sessions/2026-09-25-S2-hub-shell.md`. Work from that brief.

# Queued: Forge hub scale fix + text size slider (asked 2026-09-25)

Not started. The session hit 97% of the 5-hour usage limit before any code was
read or changed, so this is only the brief. Nothing here is verified.

## Emerson's report (paraphrased)
- The Forge app's scale is wrong.
- Increasing the scale pushes content off centre and/or makes a sideways
  (horizontal) scrollbar appear, so he has to scroll left-right to see it all.
- He wants a text size slider as well.

## Suggested approach (reasoned, not checked)
1. Find how scale is applied now (likely a CSS `zoom`/`transform: scale` on the
   body or app container, or a native window zoom). A `transform: scale` on a
   fixed-width container is the usual cause of off-centre + horizontal scroll.
2. Switch to scaling the root font size (`html { font-size: calc(16px * var(--ui-scale)) }`)
   with rem-based sizing, or the webview's own zoom level, and make layouts
   fluid (`max-width: 100%`, `min-width: 0` on flex/grid children,
   `overflow-x: hidden` only as a last resort).
3. Add a separate text size slider in hub settings (e.g. 80%–150%), stored with
   the other hub settings, applied as a CSS variable so embedded apps can
   inherit it.
4. Verify with headless screenshots at 100%, 125% and 150% (verify skill):
   no horizontal scrollbar, content centred.
