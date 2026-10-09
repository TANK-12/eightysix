# Overhaul wave: final harsh critic (looks and feel)
date: 2026-10-07 · for: Claude · reviewer: final-critic (helper of relay-63-work)

Screenshots: /tmp/t63/final-critic/shots/ (about 90 JPEGs; sheets in /tmp/t63/final-critic/*.jpg). Taken in headless Chrome (Flatpak), not WebKitGTK. The pages were the hub (new, and the snapshot tag via `git archive`) and desktop/particles.html, both from file://. Scratch servers on 8700-8716 ran Claude (new plus the snapshot copy), Mission (real data, read-only), Board, Calendar, Files, Comix, Crew Room, Terminal and Settings. Every server was stopped by PID at the end. Widths were 760/1100/1500/1920. States covered: home, Alt+W widgets, an app open in the hub, starting/failed tiles, Classic icons, first paint at 50/250/600/1200 ms, empty/no-match filter, full with a sent turn, and an Enjoy task.
Not covered: the Mission map and tab switching (task 73 has them), and fps/GPU. The server-down state is not covered either: my kill only reached the PID wrapper, so those two shots are void and the breaker has that state.

The wave mostly holds up. Hub, desktop page and the six power-sweep apps match the snapshot at all four widths: no layout regression, no first-paint flash, and the drawn icons are consistent. Classic icons switch cleanly. The defects found are below, ranked.

## Defects

1. **Claude classic: the new Normal/Ultracode toggle, Limits and the "Can" permission select are clipped off the header with no visible way to reach them.** Verified (seen and measured).
   - Where: apps/claude/static/app.css:329-330. `.head-controls` is `flex-wrap:nowrap; overflow-x:auto; scrollbar-width:none` with a fade mask.
   - Measured scrollWidth/clientWidth: 1100 → 1027/620 (#run-host cut, Can fully out); 1500 → 1083/960 (Can cut); 1920 fits. Inside the hub at a 1500 window the same thing happens (shots/hub-open-claude-1500.jpg: Limits cut, Can gone). At 760 everything after Model is out (shots/claude-new-760.jpg).
   - The scroll is hidden and only works with Shift+wheel or a sideways trackpad swipe, so the wave's headline feature is invisible below about 1900 px. The snapshot wrapped instead and showed everything (shots/claude-old-1500.jpg).
   - Fix: put the run controls on the title row, which has room, and let the rest wrap to at most two rows. In index.html move `<span id="run-host">` out of `.head-controls` to sit just before `#go-fullscreen`. In app.css change `.head-controls` to `flex-wrap: wrap; overflow: visible; row-gap: 6px;`, drop the `.more` mask, and add `.head-controls .field-inline input { width: clamp(110px, 12vw, 220px); }`. That gives two rows at 1100-1500 and three at 760, with nothing hidden.

2. **Mission Control session cards repeat the crew chip once per membership: "forge forge forge overhaul · lead".** Verified (seen on Kaito's card at 1100/1500/1920 and in the hub; shots/mc-full-1500.jpg, hub-open-mission2-1500.jpg).
   - Where: apps/mission/static/app.js:444 maps every entry of `s.crews`, and /api/overview gives one entry per member id (ejb-ab, ejb-1f, ejb-15 are all in forge).
   - Fix: deduplicate by crew name and keep the lead flag. Replace `...(s.crews || []).map(` with `...[...(s.crews || []).reduce((m, c) => m.set(c.crew, m.has(c.crew) ? { ...c, commander: c.commander || m.get(c.crew).commander } : c), new Map()).values()].map(`.

3. **Claude classic at 760: the avatar-off pane still takes 200 px, and the composer is about 150 px wide with the placeholder wrapping to 5 lines.** Verified (seen; shots/claude-full-760.jpg, claude-new-760.jpg).
   - Where: apps/claude/static/app.css:343. `clamp(200px, 18vw, 260px)` bottoms out at 200 px, so at 760 the chat column gets 347 px. The pane holds only "Turn on the avatar" and the avatar's mini chat.
   - Fix: below 900 px start that pane collapsed to its existing ⟩ strip. Use `@media (max-width: 900px) { #app.claude:has(.stage-off) .stage-pane { width: 44px; } }`, or call the same collapse the ⟩ button does on load when `innerWidth < 900`. Shorten the placeholder under 900 px to "Ask Claude…" (app.js sets it; the full hint stays in the title).

4. **Enjoy task title is cut mid-word with no ellipsis** ("…a markdown table and a c", hard against the "quiet" pill). Verified (seen; shots/enjoy-task-1100.jpg).
   - Where: apps/claude/static/enjoy.css:129 `.e-title-input`.
   - Fix: add `text-overflow: ellipsis;` (it applies to an input while it is not focused).

5. **Hub "Jump back in": "Mission Control" wraps to two lines while the other chips are one line, so the row looks uneven.** Verified (seen; shots/hub-t1200-1500.jpg, hub-classic-1500.jpg).
   - Where: hub/index.html:334. `#recent` uses `minmax(168px, 1fr)`, and the label is free to wrap.
   - Fix: `#recent .tile .name { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }` (use the chip's real label selector), or `minmax(190px, 1fr)`.

## Checked and fine (no report)
- Hub new vs snapshot at 760/1100/1500/1920: same layout, same entrance timing (frames at 50/250/600/1200 ms), and no jump of the search box or the tiles. The only difference is the icons, which are consistent.
- Alt+W widgets page (1100/1920): clean. Error-state tiles show a red dot for failed and a pulsing amber dot for starting.
- desktop/particles.html: the widget cards are darker than in the snapshot, which reads better on a light wallpaper.
- Board, Calendar, Files, Comix, Crew Room and Terminal at all four widths: no visible change from forge_idle.js. The diffs are script includes and poll wrappers.
- Mission: Swarm, Messages (empty state), Crews, Relay, the no-match search and the Needs-you empty state are all tidy. First paint at 150 ms is already complete, with no skeleton flash.
- Enjoy at 760 now has the top strip (the earlier critic's item 1 is fixed).

## Taste (seen, low)
- New drawn icons at 1100 are thin same-hue glyphs on tinted squares (NovelForge blue on blue). They are less legible than the emoji. Consider a stroke of 2 px at 36 px tiles.
- Calendar at 760: "October 2026", "Full screen" and "Close app" each wrap to two lines. This was already like that before the wave.
