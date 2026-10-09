# Mission Control map redo (Relay task 73)
date: 2026-10-07 · for: both

Ask (Emerson, ~22:50): "ok now map just look really bad, in mission control",
on top of the standing map asks: bigger, no sideways scroll, no dead space,
no overlapping boxes, readable at a glance.

## What changed (apps/mission)
- Map is HTML lanes, not SVG. `mc/graph.py` groups agents into lanes (crews
  with commander first, then Relay, shared boards, solo sessions, Jan); each
  agent once; Relay run inside a crew = "task N" badge. `static/app.js`
  (`renderMap`, `placeLanes`, `layoutMap`) packs lanes into columns and picks
  the fit zoom (180% down to 100%). CSS in `static/app.css` under `#map`.
- Top bar wraps instead of overflowing; helper count hides under 1440 px.
- Tab switch fade (`.view.enter`) removed: views no longer dim on switch.
- Details and verified figures: `apps/mission/WIP.md`, top section.

## Verified
- pytest 70 passed, incl. new `tests/test_map_browser.py` (1/6/15/40
  sessions x 900/1300/1536 px, no overlap, no sideways scroll).
- Tab switch dimmed frames: 165 before, 0 after (16 switches, headless).
- Before/after screenshots: /tmp/t73/before, /tmp/t73/after4.

## Not verified
- On Emerson's own screen inside Forge (headless Chrome only). Forge needs
  no restart: Mission Control's page picks the new static files on reload.

## Next
- If he still dislikes it: ask what reads badly on his screen; the layout
  knobs are `MAP` (col, colMax, rows, laneGap) and `FIT` in `static/app.js`.
