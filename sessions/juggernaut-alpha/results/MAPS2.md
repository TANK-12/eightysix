# MAPS2: real-place maps, part 2 (forest and city)
date: 2026-10-06 · for: both · Relay task 36 (Sora, Nagi, Kaede; hey account), working on ~/Games/eightysix after version 015

Emerson, 2026-10-03: "get some nice maps downloaded that run here or on a MacBook Air M5, fit to the scale of the mech:
grassland, forest, and normal cities, but try to get slightly wider roads." Crew note 750: the city needs real facade
textures and mid-size props, not flat boxes.

## Try this (Emerson)
- Map list: **Allegheny forest (real place, 4 km)** and **Brilon (real town, 2 km)**, both free roam.
- Allegheny: walk off the road into the firs. Trunks block the Juggernaut, but there is always a lane between them
  (trees stand at least 6.6 m apart). Look from the ridge: a whole hillside of forest.
- Brilon: walk down the streets (1.3x their real width). Houses have plaster, brick or Sauerland slate walls with
  real-looking windows (frames, glazing bars, sills, glass that catches the sky, shop fronts on bigger houses), clay
  roofs, and about half the town is in ruins with blown-out windows and soot. Power poles line the streets,
  burnt-out trucks sit at the kerb, rubble piles stand where houses were flattened.

## What was built
| Piece | What | Files |
|---|---|---|
| Forest terrain | USGS 3DEP 1 m lidar, Allegheny National Forest PA, 4096 m at 2 m points | `assets/maps/allegheny/` (height.f32, source.json, osm.json, woods.png) |
| Trees | Poly Haven CC0 fir_tree_01 bark; bough card and far billboard drawn by `tools/maps/tree_textures.py`; per-tile MultiMeshes (near mesh + billboard), trunk colliders on the tiles round each mech; rules in the entry's `forest` block | `scripts/world/big/big_forest.gd`, `assets/trees/` |
| City terrain | DGM1 NRW 1 m model, 16 tiles round Brilon (Hochsauerland), 2048 m | `assets/maps/brilon/` |
| Streets and houses | OpenStreetMap through Overpass (`tools/maps/osm_map.py`): roads at 1.3x width carved into the ground by `BigTerrain.osm`; 6018 footprints raised to their storeys | `big_terrain.gd`, `scripts/world/big/big_city.gd` |
| Facades | new `assets/kit/shaders/facade.gdshader`: CC0 PBR wall (Poly Haven plaster x3, brick, slate, concrete) with a window grid, sills, rain streaks, rising damp, broken and sooty windows on ruins; kit.json `facade_*` materials. Each wall gets UV = (metres along, metres up), UV2 = house centre, CUSTOM0 = (wall length, storey height, ruin, storeys + seed) | `big_city.gd`, `data/kit.json` |
| Props | power poles every 45-50 m along the streets, burnt-out trucks parked at the kerb, a rubble pile on each flattened house; built 3 times per kind and copied, so hundreds of props (400+ in Brilon, checked by the test) cost a few meshes | `big_city.gd` `_build_props`, the entry's `city.props` block |
| Map list | `allegheny` (order 31) and `brilon` (32) entries with blurb, description, viewpoints, palette | `data/maps.json` |
| Credits | heights, OSM (ODbL), fir bark, plaster textures | `assets/SOURCES.md`, `assets/maps/*/source.json` |
| Bots | chase view + 3 viewpoints, fps measured twice | `tools/bot/maps_allegheny.json`, `maps_brilon.json` |

## Verified
- `tools/run_tests.sh test_real_maps`: **7/7** (2026-10-06). Covers: both maps' heights follow their survey, the forest
  leaves lanes for a mech, the city raises nearly every OSM building with walls starting under the ground, part in
  ruins, spawn on an open street, facade surfaces with tangents, one CUSTOM0 per vertex and wall UVs from 0 to the
  wall's length, 400+ props of all three kinds with no pole inside a house, and both maps play: the Juggernaut lands
  on a collider, trunks and roofs are solid.
- `test_world_look` 9/9 after fixing the plaster_* and roof_* texture imports (they were uncompressed with no
  mipmaps; now VRAM compressed with mipmaps, like the rest of the kit).
- Bot runs, off screen 1920x1080, all 0 errors: images 548-553 (`maps2-<map>-<preset>`, 4 shots each).
- fps on a quiet GPU (Intel Iris Xe, 1920x1080, vsync 60; other sessions held their bot runs):

| Map, view | Low | Medium | High |
|---|---|---|---|
| Allegheny, chase at spawn | 49.5 (1 % low 43.2) | 37.3 (34.9) | 25.8 (24.5) |
| Allegheny, in the trees | 57.2 (49.6) | 42.9 (39.5) | 30.7 (29.4) |
| Brilon, chase at spawn | 77.8 (70.3) | 61.7 (60.0) | 42.3 (40.0) |
| Brilon, down a street | 91.9 (85.1) | 72.8 (67.2) | 49.9 (45.2) |

  All runs GPU-bound (GPU 10-38 ms per frame, CPU 5-14 ms). Ultra not measured (vsync and MSAA 4x; 15 fps on the old
  big map). For comparison the old big map was Low 52 / Medium 44.5 / High 36.8 (LOOK, 2026-10-02).
- `black` + `pyright` (system Python, which has numpy and Pillow; the game has no venv) on tools/maps/*.py: 0 errors.

## Assumptions and limits
- Props are solid but do not break (a Destructible each would take seconds to build for hundreds of props). The old
  kit towns still break.
- The forest is the heavy one: High is 26-31 fps here. The M5 Air should be far faster (not measured; macOS export
  templates still wait on Emerson, A1).
- The facade look was judged from 480 px contact sheets of the bot shots, not a full-size review.

## Next
- Forest on High: thin the far billboards or shorten their draw range per preset if 30 fps on High matters here.
- Breakable trunks (snap under a mech or a shell) were in the brief as "if cheap": not done.
- A Legion mission on either map (missions.json).
