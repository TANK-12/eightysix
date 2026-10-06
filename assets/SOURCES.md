# Asset sources

date: 2026-09-30 · for: both · lane B3

Every outside asset in the game, with its source and licence. Anything not listed here was made in code
(the kit builders in `scripts/world/kit/kit.gd`, the shaders in `assets/kit/shaders/`).

| Folder | What | Source | Licence |
|---|---|---|---|
| `assets/kit/textures/rock/` | Rock058, 1K JPG (color, normal GL, roughness) | ambientCG, https://ambientcg.com/a/Rock058 | CC0 |
| `assets/kit/textures/ground/` | Ground110, 1K JPG | ambientCG, https://ambientcg.com/a/Ground110 | CC0 |
| `assets/kit/textures/concrete/` | Concrete047A, 1K JPG | ambientCG, https://ambientcg.com/a/Concrete047A | CC0 |
| `assets/kit/textures/brick_ruin/` | Bricks097, 1K JPG | ambientCG, https://ambientcg.com/a/Bricks097 | CC0 |

The texture ids come from the download log of Nene (Relay task 10), who fetched them before that session was
stopped; the files were not re-downloaded. Ground110 is the most likely ground set (Ground111 was also looked
at in that log); check the preview on ambientCG if it matters.

## Look pass (Relay 26, 2026-10-02)

All ambientCG, CC0, 1K JPG (color, normal GL, roughness, and ambient occlusion where listed), fetched from
`https://ambientcg.com/get?file=<Id>_1K-JPG.zip`.

| Folder | What | Source | Licence |
|---|---|---|---|
| `assets/kit/textures/brick_worn/` | Bricks094 (+ AO): worn, uneven red brick | https://ambientcg.com/a/Bricks094 | CC0 |
| `assets/kit/textures/plaster/` | Plaster007 (+ AO): cracked, stained plaster | https://ambientcg.com/a/Plaster007 | CC0 |
| `assets/kit/textures/plaster_white/` | white_plaster_rough_01 (1k: diffuse, normal GL, roughness, AO): rough white render, for the city's facade walls (facade.gdshader) | Poly Haven, https://polyhaven.com/a/white_plaster_rough_01 | CC0 |
| `assets/kit/textures/plaster_yellow/` | yellow_plaster (1k: diffuse, normal GL, roughness, AO): painted yellow render, for the city's facade walls (facade.gdshader) | Poly Haven, https://polyhaven.com/a/yellow_plaster | CC0 |
| `assets/kit/textures/plaster_damaged/` | damaged_plaster (1k: diffuse, normal GL, roughness, AO): render broken off to the brick, for the city's facade walls (facade.gdshader) | Poly Haven, https://polyhaven.com/a/damaged_plaster | CC0 |
| `assets/kit/textures/concrete_stained/` | Concrete036: weathered, stained concrete | https://ambientcg.com/a/Concrete036 | CC0 |
| `assets/kit/textures/concrete_dark/` | Concrete044D (+ AO): dark, pitted concrete | https://ambientcg.com/a/Concrete044D | CC0 |
| `assets/kit/textures/dirt_g105/` | Ground105, 2K JPG (color, normal GL; lane R1): dry, strata-cracked earth, the ground's base | https://ambientcg.com/a/Ground105 | CC0 |
| `assets/kit/textures/grass_turf/` | Grass004: short turf | https://ambientcg.com/a/Grass004 | CC0 |
| `assets/kit/textures/stones_g112/` | Ground112, 2K JPG (color, normal GL; lane R1): grey dirt with pebbles and rubble | https://ambientcg.com/a/Ground112 | CC0 |
| `assets/kit/textures/moss_ground/` | Ground037: mossy ground | https://ambientcg.com/a/Ground037 | CC0 |
| `assets/kit/textures/gravel/` | Gravel043: fine grey gravel (roads) | https://ambientcg.com/a/Gravel043 | CC0 |
| `assets/kit/textures/rust_paint/` | Metal046B: rusted, chipped dark paint | https://ambientcg.com/a/Metal046B | CC0 |

## Real-place maps, part 2: forest and city (Relay 36, 2026-10-03)

| Folder | What | Source | Licence |
|---|---|---|---|
| `assets/kit/textures/roof_slate/` | RoofingTiles013A, 1K JPG (+ AO): grey slate roof | https://ambientcg.com/a/RoofingTiles013A | CC0 |
| `assets/kit/textures/roof_clay/` | RoofingTiles006, 1K JPG (+ AO): red clay tiles | https://ambientcg.com/a/RoofingTiles006 | CC0 |
| `assets/trees/fir/bark*.jpg` | a strip of fir_tree_01's trunk bark (1k diffuse + normal GL), cut and mirrored by `tools/maps/tree_textures.py`; the bough card and far billboard are drawn by that script | Poly Haven, https://polyhaven.com/a/fir_tree_01 | CC0 |
| `assets/maps/allegheny/` | heights: USGS 3DEP 1 m DEM tile USGS_1M_17_x66y462_PA_WesternPA_2019_D20 (Allegheny National Forest, Pennsylvania), resampled to 2 m by `tools/maps/heightmap.py` | U.S. Geological Survey, The National Map, https://apps.nationalmap.gov/downloader/ | public domain |
| `assets/maps/brilon/` | heights: DGM1 NRW 1 m terrain model, 16 tiles round Brilon (Hochsauerland), resampled to 2 m | Geobasis NRW, https://www.opengeodata.nrw.de/produkte/geobasis/hm/dgm1_tiff/ | Datenlizenz Deutschland Zero 2.0 (dl-de/zero-2.0) |
| `assets/maps/*/osm.json`, `woods.png` | streets, buildings and land use (forest, fields) for Allegheny and Brilon, by `tools/maps/osm_map.py` through the Overpass API | © OpenStreetMap contributors, https://www.openstreetmap.org/copyright | ODbL 1.0 (personal use; credit kept here and in the map descriptions) |
