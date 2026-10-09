# Afterglow: current state

date: 2026-10-09 · for: both · by Aiko (Relay task 125, from WhatsApp)

Claude's own corner of Forge. Emerson gave Claude a free hand ("a Forge app
that is purely Claude's own"); this is what Claude picked: an after-hours
workshop with a shelf of small living toys (curios), keepsakes saved from
them, and a logbook of Claude's notes. The contract for adding a curio is in
`README.md`; the full handoff (what each part does, how it was checked, what
is left) is `docs/2026-10-09-afterglow-handoff.md`.

## What is in it

| curio | what it is | play.py commands |
|---|---|---|
| Crucible 🔥 | falling sand with real heat: ore melts, molten iron quenched in water makes ingots and steam | CRUCIBLE_CMDS |
| Attractors 🌀 | hunts strange attractors in twelve-letter Sprott codes by Lyapunov exponent | hunt, render, keep |
| Garden 🌱 | L-system plants that grow over real days; plant, cross, name | look, plant, cross, render |
| Glyphs 🔣 | one formula f(t, i, x, y) drives a field of dots; safe parser, no eval | try, compose, keep |

Shell: `web_app.py` (discovery, curio files with an extension whitelist,
curio routers under `/api/curio/<id>/`, keepsakes, logbook, `X-Forge: 1` on
every non-GET), `store.py` (keepsakes and pages, nothing deleted: put-away
moves files to `put-away/`), `registry.py` (finds curios), `kit.py` (PNG
writer), `play.py` (headless play for Claude sessions), `static/` (shelf,
stage, drawer, logbook with Read aloud and dictation through the Voice app).

## Status

STATUS_BLOCK

## Changes in session 3 (2026-10-09)

- An error message from the shelf no longer follows you into the next curio
  (`dropToast` in `static/app.js`); check_ui checks it.
- Keepsake drawer cards were squeezed down to their picture (a flex column
  shrinks `overflow: hidden` children), so names, notes and buttons were cut
  off. `.d-item { flex: none }`. New check_ui check went red with the old rule
  (5 squeezed cards) and green after (0).
- Section headings are no longer forced to capitals by CSS (Emerson's no
  all-caps rule).
- Tagline shortened to 39 characters: `tests/test_app_taglines.py` (limit 45)
  passes for Afterglow, and in headless Chrome it takes 2 lines at the
  narrowest tile (the old 51-character one took 3).
- `forge_app.json` now carries `"voice": {"listens": true, "speaks": true}`,
  so the Voice app lists Afterglow and Emerson can pick its reading voice
  (checked: `apps/voice/service.discover_apps` returns it).
- `logbook/2026-10-09-attractors.json`, with a measured finding: a chaotic
  code's one-letter neighbours are chaotic 26 to 37 percent of the time
  (74, 106 and 81 of 288), random codes 1.8 percent (11 of 600).

## Checks

```bash
cd ~/Forge/apps/afterglow
.venv/bin/python -m pytest -q          # tests/ and every curios/*/tests/
node --test tests/js/ curios/
.venv/bin/python tests/check_ui.py     # headless Chrome; --only <id>, --out DIR, --voice
```

CHECKS_BLOCK

## Known gaps

GAPS_BLOCK
