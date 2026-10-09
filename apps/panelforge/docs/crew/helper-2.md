# helper-2: detect (strip, panels, bubbles, OCR)

Crew `panelforge`, owner of `panelforge/detect/`, `panelforge/api/detect.py`,
`tests/test_detect_*`, this file.

## Status (2026-09-17)

- **v0 rough output written** for chapter 0001 (other helpers can start):
  `strip.json`, `panels.json` (138 panels), crops in `work/detect/panels/`
  (101 MB of PNG). Rough: some tall "splash" panels are really several panels,
  some caption kinds are wrong. `bubbles.json` not yet written.
- Not yet: bubbles/OCR, API, job, tests, accuracy numbers.

## Contract additions

- `strip.json` segments carry `file` (page file relative to the chapter).
- `panels.json` panels carry `art_box` [x,y,w,h]: the drawing alone; `box` also
  includes balloons and sound words in the gutter that belong to the panel.
