# PrintForge WIP

## U1 sweep (2026-10-08, Relay task 74)
Done by Ami (Relay task 88, group G14). Static changes (app.js, viewer.js,
index.html) reach Forge on the next reload of the page; the Python changes
(settings checks, calm errors) only after Emerson's next Forge restart.

What changed:
- Rest: the 3D view no longer runs a frame loop forever. It draws only when
  something changes; the turntable runs through `ForgeIdle.loop`, so it stops
  while the hub hides the page and carries on when shown. The turntable speed
  is now time-based (same speed as before at 60 Hz).
- Settings are checked by type on save (light, colour, bed, beds, mode,
  roots) with a 422 naming the bad key; a bad value already stored is ignored
  per key instead of breaking the page; an unknown bed falls back to the first.
- A damaged STL is a 422 "could not read this STL" (it was a 500), NaN
  corners are refused, a too-long path is a 404, a missing xdg-open is a 503.
- The page: empty STL says "no triangles", damaged STL gets a calm message,
  opening another print cancels the download in flight, the light slider and
  colour save once after the drag (was one POST per step), Save and rescan,
  Save as custom and Open folder run once per click, save errors show a toast,
  the library says "Looking for STL files" while it loads and retries by
  itself (2 s doubling to 30 s) when the server is down, search says when
  nothing matches, bed geometry is disposed when the bed changes.
- Looks: shared `--good`/`--bad` colours, thin styled scrollbars, a 180 ms
  fade for the check rows, at 980 px and narrower the check panel moves under
  the view so the view keeps its width (at 760 it was a 170 px strip with a
  sideways scrollbar), a little more room around the model on fit.

Verified:
- `pytest`: 25 passed (11 before + 14 new: settings types, stored bad
  settings, unknown bed, damaged/NaN/empty files and long paths through the API).
- `tests/check_ui.py` (headless Chrome, scratch copy, temp folders): 15 of 15
  ok: no frames or fetches in 3 s with nothing moving; turntable 60 frames/s
  shown, 0 frames, fetches and timers in 10 s hidden by the hub, back when
  shown; empty and damaged STL messages; triple click saves once; slider drag
  saves once; no page errors; no sideways scroll at 760/1100/1500/1920 px.
  Screenshots looked at: /tmp/u1/G14/shots/pf_after/.
- black, pyright: 0 errors.

Not verified: inside the running Forge window; Open folder (runs xdg-open);
real Juggernaut STLs (36 MB) were not loaded this time (RAM was tight).

### Critic follow-up (same day)
- A body of 1e999 or NaN (`/api/settings`, `/api/open-folder`) was a 500;
  a `RequestValidationError` handler now answers 422 without echoing it.
- One symlink out of a root, a broken link or a FIFO named `.stl` made the
  whole library a 500 (or could hang it); the scan now skips just that
  entry (`library.scan`, regular files only).
- A root like `~nosuchuser/models` was accepted and then broke every
  library and info call; the roots check refuses it and `roots()` skips
  any root it cannot expand.
- The library retry ran forever, kept fetching while hidden and held
  "Save and rescan" disabled. It now runs on `ForgeIdle.poll` (2 s doubling
  to 30 s, rests while hidden) and a rescan replaces it at once.
- Not changed: at 760 px standalone the shared Close app / Full screen
  buttons float over the bottom of the check panel. The panel already has
  56 px of bottom padding, so scrolled to the end nothing is hidden; the
  floating buttons are shared chrome (hub hides them).
- Verified: 31 pytest (6 new, red on the previous commit); check_ui 15/15;
  headless retry check (scratch copy, fetch made to fail): library tried at
  0, 2, 6, 14 s, 0 tries in 12 s hidden, rescan button enabled throughout,
  rescan with the server back listed 6 files and the retry stopped.

## 2026-09-28, first version (ejb-fc, Tetsu)
Built so Emerson can look over the Juggernaut print files
(`~/Models/juggernaut/print/stl/`), and any other STL under `~/Models` or `~/Downloads`.

Verified:
- `pytest`: 11 passed (STL reading binary and ASCII, watertight, open edge, two shells,
  inside out, bed fit, scan and scale, path rule, cache, settings, API and shared three.js).
- pyright on the Python files: 0 errors.
- Headless Chrome through `tests/cdp_driver.py` (with the new optional `extra_args`
  for software WebGL): the 36 MB Juggernaut statue and the base load, render on the
  bed in 3/4 and front views, and the check panel fills in (7 s for a first check,
  cached after). Advanced panel looked at after the overflow fix.

Not verified: inside the running Forge window (needs a Forge restart to be
discovered); Open folder (runs xdg-open); Save picture download.

Improve next, most useful first:
1. A send-to-slicer button once a slicer is installed (none on this laptop today).
2. 3MF and OBJ reading, since slicers and model sites use them too.
3. A thin-wall map (colour faces thinner than the printer can make), for resin and FDM.
4. Show the print pipeline's report (`reports/*_build.json`) beside files that have one.
