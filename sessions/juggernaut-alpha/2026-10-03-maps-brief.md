# Brief: real-place maps, part 2 (forest and city)
date: 2026-10-03 · for: Claude (next session, hey, Opus high) · written by Tetsu (v015 session)

Start line: `Read ~/Forge/sessions/juggernaut-alpha/PLAN.md, results/V015.md and this brief, then do it.`

**Resume state (Tetsu, 2026-10-03, written when Relay task 36 stopped at the hey weekly limit; reasoned from the tree,
the session left no results file):** committed d599298 (roof_slate/roof_clay CC0 textures, masonry batched mode, SOURCES
credits). Uncommitted in ~/Games/eightysix and yours to finish: scripts/world/big/big_city.gd, big_forest.gd (new),
big_terrain.gd, big_map.gd, data/maps.json (allegheny forest + brilon city entries), data/kit.json, tools/maps/heightmap.py,
osm_map.py, tree_textures.py, assets/maps/allegheny/, assets/maps/brilon/, assets/trees/, assets/kit/shaders/facade.gdshader,
assets/kit/textures/plaster_*/, tests/test_real_maps.gd. Last full suite: test_real_maps forest tests fail (0 trees
placed). Emerson wants AAA-looking cities, not low poly: board note 750. Write results/MAPS2.md.

Emerson 2026-10-03: "get some nice maps downloaded that run here or on a MacBook Air M5, fit to the scale of the mech:
grassland, forest, and normal cities, but try to get slightly wider roads." Free, game-ready maps at mech scale do not
exist (store environments are engine-locked or showpieces without collision), so maps are built from **real places**:
public elevation surveys + OpenStreetMap + CC0 models, on the big map's streaming tech.

Already done (a951ce4): `BigTerrain` reads `terrain.heightmap`; `tools/maps/heightmap.py <tile.tif> <out> --size 4096
--points 2049 [--centre highest|COL,ROW] [--offset DX,DZ]` makes one (Pillow + numpy, no GDAL); `big_map.tscn` plays any
maps.json entry pointing at it. Palouse grassland is the template entry (copy it). USGS 1 m tiles: TNM API
`https://tnmaccess.nationalmap.gov/api/v1/products?datasets=Digital%20Elevation%20Model%20(DEM)%201%20meter&bbox=W,S,E,N`
(about 300-360 MB per 10 km tile; download to /tmp, delete after; disk is short).

1. **Forest:** a forested, hilly 1 m USGS area (e.g. the Cascades or Olympic foothills, or the Appalachians). Trees:
   Poly Haven CC0 (`api.polyhaven.com/assets?t=models&c=nature`: fir_tree_01, pine saplings, dead trunks...), 1k
   textures, glTF; per tile MultiMeshes with a near mesh and a far billboard (impostor) so the Iris Xe holds up; trunks
   get colliders near mechs (the Juggernaut is ~4.9 m across the feet, 1.4 m ride height: spacing must leave lanes),
   breakable (they snap under a mech or a shell) if cheap. Scatter rules in the entry, not code.
2. **City:** a real town from OpenStreetMap (Overpass API, ODbL: credit in assets/SOURCES.md; personal use). Roads
   from `highway` ways at real width x ~1.3 (Emerson: slightly wider), building footprints extruded with the kit's town
   styles (town_styles.json) and heights from `building:levels`, partly ruined (86 setting). A town in a German-speaking
   region suits the anime. Flatten under the town on the survey heights (a Copernicus GLO-30 or USGS tile).
3. **Runs on both machines:** measure fps per preset here on a quiet GPU; the M5 Air is far faster. A macOS build needs
   Godot export templates (A1: waiting on Emerson).
4. Each map: test (heights follow the source, spawn on ground, colliders under every mech), bot screenshots, entry in
   the map list with a one-line blurb, source.json and SOURCES.md credit. Then the Legion: a free-roam map can take a
   mission later (missions.json).
