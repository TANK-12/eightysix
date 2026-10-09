# H7 Mission Control looks pass: report
date: 2026-10-07 · for: both · helper-7 (Haru), crew overhaul

## Checks
- `cd ~/Forge/apps/mission && .venv/bin/python -m pytest -q tests`: 41 passed (unchanged count; no Python touched, so no black/pyright run; `node --check static/app.js` ok).
- Headless screenshots looked at: sessions at 760/1100/1500/1920, map at 760/1500, crews, relay, drawer, on a scratch fixture server (real-data copy, 0 sessions, 40 sessions with very long names, all idle). Scratch servers stopped; no headless Chrome left.
- CDP-driven checks (scratch /tmp/h7/live.py): no page errors; unchanged polls keep the same card DOM nodes; card click opens the drawer, Escape closes it; Advanced shows `.adv`; 3 -> 40 sessions renders 40 cards; idle cards run 0 looping animations; reduced motion: 0 looping CSS animations, map SMIL paused; hidden in the hub (forge-visible false): 0 fetches and 0 rAF in 10 s, map SMIL paused, one poll on show; map sprites step.

## Design decision and why
Kept the existing layout (sidebar + responsive grid + map + crews + relay + drawer) and gave it a design system rather than switching to Enjoy's list-and-pane layout: every feature stays where Emerson knows it, and the grid fills the width. Enjoy's language taken over: calm dark panels with hairline borders, one accent, status colours used one way everywhere, one primary action per item, sentence-case labels, generous spacing. Forge character kept: Crew Room pixel sprites that animate by state. Motion is either one-shot (150-280 ms transform/opacity) or a loop tied to something live (typing sprite, needs-you halo), never a loop while idle, all paused while hidden.

## What changed (apps/mission/static only)
- index.html: icon symbols, logo, live line, stat tiles slot, icon nav, search with icon, view titles, skeleton loading cards, loads shared/forge_idle.js.
- app.css: rewritten: status colour system (--st-needs/working/idle/ended), accent, type scale, buttons (primary/ghost/icon), thin scrollbars incl. ::-webkit-scrollbar, cards, map, crews, relay, drawer, dialogs, empty/offline/no-match states, breakpoints 1600/1240/1040/900/640, prefers-reduced-motion.
- app.js (patched, same features): sprite strips + keyframes by state (strip, spriteOf, avatar, syncSprites; SMIL steps on the map, smilSteps/syncMapClock); keyed patchList with FLIP glide and fade-in (no jumps on polls); gridCols fills the width; stat tiles with count-up; Relay button; folded waiting rows; living map (kept nodes, colour transitions, spawn/fade, icons for Relay/forge board/Jan/Relay task, speech bubbles, dotted note arcs for who talks to whom, one-off sparks on a new note or helper step); view/drawer/dialog entrance; drawer title with state and one primary; crews notes keep scroll; forge-visible honoured for polls; body.advanced fix (shared forge.css hid .adv in Advanced mode); helpers per card default 5 -> 3.
- WIP.md: new "Looks pass (H7)" section with verified and open items.
- Backups: pre-pass static in ~/Forge/backups/2026-10-07-overhaul/mission-looks/static/; helper-1's unfinished parallel restyle (all three files) in .../mission-looks/unclaimed-edit-2011/.

## Screenshots
Before: /tmp/mission-shots/final-sessions.png, final-map.png; /tmp/h7/shots/before-*.png.
After: /tmp/h7/shots/f-map.png, f-map-760.png, f-forty.png, f-drawer-1100.png, g-top-1500.png, g-top-1100.png, e-crews.png, e-relay.png, c-zero.png, c-real-1920.png (scratch /tmp, not kept long).

## Numbers (rough: single 30 s runs, headless software rendering, busy machine)
Page CPU, Chrome process tree, visible: idle data before/after about equal (map 2.5 vs 3.3 %, sessions 4.9 vs 1.2 %, noise ~2 points). With 2 sessions + 5 helpers working: map ~2.8 -> ~8 %, sessions ~2.5 -> ~4.4 % (the typing sprites; slowed 1.6x and synced to one beat to cut repaints). Hidden: 0 polls, 0 rAF. Further measuring stopped per board note 17.

## Critic (Opus, harsh, vs enjoy.dev)
Fixed: blank animated sprites on the map, map labels shrinking at narrow widths, "~" titles, top-bar vs sidebar count mismatch, meters reusing needs-you pink, "taken" chips in working green, waiting rows flooding the page, crews notes scroll reset, drawer title/buttons, uppercase labels, sidebar rebuilt each poll, live dot hidden <1240, header overflow at 1500.
Left: map at scale (one cluster per lone session; needs a mc/graph.py change), uneven card heights in a row, needs-you halos out of step, Crews still rebuilt per poll (scroll kept).

## Risks
- Real WebKitGTK not checked (headless Chrome only): SMIL on SVG images, CSS step animations and ::-webkit-scrollbar should work there but are unverified on screen.
- Shared power tier has no app-page API yet; only prefers-reduced-motion sets calm.
