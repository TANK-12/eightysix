# PrintForge

Look over 3D-print files (STL) before slicing them. PrintForge lists every STL under
the chosen folders, shows it on a print bed in a 3D view, and checks what a slicer
cares about. It never changes the files.

## Use
- Pick a print on the left (grouped by project and folder; a folder named like `1-35`
  shows as scale 1:35). Search box on top.
- Drag to turn, right-drag or Shift-drag to pan, scroll to zoom, double-click (or `f`)
  to fit. Buttons: 3/4, Front, Side, Back, Top, Turntable (`r`), Wireframe (`w`), bed
  class and Bed on/off. Front is +Y in the file, which is how the Juggernaut faces.
- The right panel shows size, scale, triangles, volume (ml of resin if solid), surface,
  **Watertight** (every edge shared by exactly two triangles facing the right way;
  "almost" means parts touch along a line, which slicers usually cope with), **Pieces**
  (separate shells), an inside-out warning, and which bed classes it fits standing or
  laid over. The bed outline turns red when the print is too big for it.
- Advanced mode adds light brightness, a custom bed (slider plus number), the folder
  list, and Save picture.

## Run and test
- In Forge: it is discovered from `forge_app.json` (port 8462, Create section).
- Standalone: `cd ~/Forge/apps/printforge && FORGE_SHARED_DIR=~/Forge/shared .venv/bin/python -m uvicorn web_app:app --port 8462`
- Tests: `.venv/bin/python -m pytest -q tests`

## Files
- `stl.py`: binary/ASCII STL reading, `analyse` (numpy), `fits`.
- `library.py`: settings, folder scan, path rule (only `.stl` inside a configured
  folder is ever served), analysis cache.
- `web_app.py`: FastAPI routes (`/api/settings`, `/api/library`, `/api/info`, `/api/stl`,
  `/api/open-folder`).
- `static/`: `index.html`, `app.js` (page), `viewer.js` (three.js view and STL parser).
  three.js r186 comes from `~/Forge/shared/vendor/three/` (a copy of Cosmos's, MIT).
- Data: `~/.config/forge-printforge/settings.json`, `~/.cache/forge-printforge/info.json`.
