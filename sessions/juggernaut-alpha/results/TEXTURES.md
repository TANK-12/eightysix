# Eighty Six textures pass: world and Legion paint

date: 2026-10-08 · for: both · helper of Riku (session ejb-6a)

Emerson's ask: "the textures for everything but the Juggernaut suck". This pass upgraded the world (ground,
cliffs and rocks, roads and town streets, town ground, house walls, ruin walls, roofs) and the Legion's paint.
The Juggernaut's look (data/finishes.json and the mech surfaces it uses) did not change. Measurements are also
in `~/Forge/docs/library/eightysix/2026-10-08-textures-before-after.md`.

## What changed, in plain words

- **Ground.** The old ground multiplied four layers of noise together, which read as orange-brown blotches. Now
  the big changes in tone come from a real aerial photo of dirt (20 m across) at a low strength, and the noise is
  kept faint. Turf and stony patches fray at their edges along the texture's own clumps and pebbles instead of
  fading as soft blobs. Stony ground and dirt tracks use a 2K gravel-and-stones set. Close up the ground keeps its
  fine grain. Every normal map is now turned into a world-space normal (the terrain has no UVs), plus the aerial
  photo's own relief (ruts, crust) within 160 m.
- **Cliffs.** Proper three-way projection weighted by the slope, with a 2K layered rock (dry riverbed rock) up
  close, the same rock at about seven times its size taking over from 15 m (so crags and ledges keep their shape
  at a distance), and a cliff-scale aerial photo of fractured rock (tone and relief, not its moss colour) at two
  scales beyond 30 m, so a mountain shows no repeating grid. The rock keeps 60 % of its own colour; the map's
  rock_tint gives the rest.
- **Roads.** Tracks are gravel and stones; Brilon's streets are 2K cracked asphalt and its town ground worn
  cobbles. Every road's edge is broken: stones and dirt eat into the surface along the last metres, the verge is
  a little paler.
- **House walls (Brilon and Allegheny, facade.gdshader).** The windows are real recesses worked out per pixel:
  the view ray goes into the opening, so from an angle you see the reveals (lit or shaded by their own normals,
  darker the deeper) and the glass and frame set back behind them, moving with parallax. Sills stick out with a
  lit top and a shadow under them. Storey bands on about half the houses, corner quoins on about a third, a
  plinth with a lit top edge, grime into corners, faint rain runs over the whole wall, rising damp. Walls are 2K
  painted plaster, brick, tile-hung (grey tiles) and concrete; damaged walls show brick where the plaster has
  fallen off.
- **Roofs (masonry.gdshader, roof_mode).** Tiles now lie along the slope, rows parallel to the eaves whichever
  way the house faces (before they were projected straight down in world axes). 2K terracotta tiles for clay
  roofs, 2K grey tiles for the others.
- **Ruin walls (masonry, kit).** 2K red brick, 2K concrete, 2K painted plaster coat.
- **Kit rocks.** The 2K layered rock.
- **Legion paint.** A new surface of their own, `legion_paint` (ambientCG PaintedMetal004, 2K, desaturated to a
  pale base, scratches and small scuffs to bare metal at a softened shine). The field livery's shell wears it,
  with less of the mottled grime on the hull and more low down. The black "cow print" blotches are gone; the
  panel lines are the model's own.

## Data and registries (declarative, as the project wants)

- `data/kit.json` **"texture_sets"**: every new world set, folder -> CC0 source id, size in metres, maps.
  `tools/fetch_kit_textures.py` (new) reads it, downloads into `~/Forge/shared/assets/polyhaven/<id>/2k/` and
  writes `color/normal/roughness/ao.jpg` with `.import` files. It never overwrites an existing folder.
- `data/kit.json` **"ground_sets"**: the ground shader's slots (ground, macro, turf, stone, road, rock, rock_far,
  town) -> {set, per_m}. `GroundLook.SETS` (a hardcoded constant) is gone; `GroundLook.sets(entry)` merges the
  defaults with a map's `palette.ground_sets`. Overrides now: Allegheny turf = forest floor; Brilon road =
  asphalt, town = cobbles.
- `data/kit.json` "materials": the walls, roofs and rocks point at the 2K sets; roofs set `roof_mode`.
- `data/maps.json` palettes: contrast 1.0 on Ashen valley, Sector 86 and Palouse (were 0.88 to 0.95, which pulled
  colour out); Sector 86 rock_tint less orange (1.08, 1.0, 0.92); Palouse grass_amount 0.75 (fewer bare-dirt
  patches on the grassland).
- `data/mech_surfaces.json`: new entry `legion_paint` with new fields `resolution` ("2K"), `bare` (albedo where
  the metalness map shows bare metal) and `metal` (a scale on the metalness map). The existing entries are
  unchanged (only the _about text grew).
- `data/legion_finishes.json`: legion_field LG_shell and LG_shell_dark wear legion_paint, roughness 0.45 / 0.5,
  grime 0.12 with grime_rise [0.3, 0.12].
- `tools/make_mech_textures.py`: reads `resolution`, `bare` and `metal`.

## Texture sets added (2K JPG, all CC0, credited in assets/SOURCES.md)

| Folder | Source | MB |
|---|---|---|
| rock_strata_2k | Poly Haven dry_riverbed_rock | 4.0 |
| rock_cliff_2k | Poly Haven aerial_rocks_02 | 3.7 |
| dirt_aerial_2k | Poly Haven dirt_aerial_02 | 2.3 |
| rocky_trail_2k | Poly Haven rocky_trail | 4.1 |
| forest_floor_2k | Poly Haven forrest_ground_01 | 4.4 |
| asphalt_2k | Poly Haven asphalt_02 | 4.3 |
| cobble_2k | Poly Haven cobblestone_floor_01 | 2.7 |
| brick_red_2k | Poly Haven red_brick_03 | 4.9 |
| plaster_painted_2k | Poly Haven painted_plaster_wall | 3.7 |
| plaster_damaged_2k | Poly Haven damaged_plaster | 3.5 |
| concrete_wall_2k | Poly Haven concrete_wall_008 | 2.8 |
| roof_clay_2k | Poly Haven clay_roof_tiles_02 | 3.4 |
| roof_grey_2k | Poly Haven grey_roof_tiles | 3.1 |
| assets/textures/mech/legion_paint | ambientCG PaintedMetal004 | 3.8 |

Total in the repo: 49 MB. Three sets were fetched, tried and dropped in this pass (rock_face looked flat and
smooth on cliffs, roof_tiles_14 turned Brilon's red roofs brown, rough_plaster_brick_04 read as a dark blank
wall); their folders went to the desktop trash (`gio trash`), their downloads stay in the shared cache. The old
1K sets are all still on disk; some are no longer used by any material (plaster, plaster_white,
plaster_yellow, plaster_damaged, brick_worn, concrete_stained, concrete_dark, stones_g112, roof_clay, roof_slate,
gravel, and rock as ground and kit rock).
`rock/color.jpg` is still used by the far hills (see open issues).

## Before and after

All on High, 1920x1080, off screen, `tools/bot_run.sh` through the GPU lock.

- First before-set: `images/687-tex-before-high` (a011_views, 23 shots) and `images/688-tex-before-legion`.
- Rounds: 691/693 (round 1), 697/698 (round 2: rock strata, clay roofs, damaged plaster, Legion scuffs
  softened), 701/702 (round 3), 699/700 (quick checks of the cliffs' mid layer).
- Same-sitting pair for the final look and fps: `images/714-tex-ab4-old` and `images/715-tex-ab4-new` (and
  `716-tex-ab4-old2`).
- Sheets: `images/717-tex-before-after/` (world-high-same-sitting.png, world-high-first-vs-round3.png,
  legion-high.png, pairs-same-sitting-1.jpg and -2.jpg).

What the sheets show [seen]: Ashen valley and Sector 86 lost the blotchy noise and gained real ground detail and
stony tracks; the cliffs are layered rock with strong relief at every distance (Sector 86's ranges were grey
before, now warm brown-grey); Brilon's windows show their reveals and depth, damaged walls show brick, roofs
are terracotta tiles along the slope, streets are cracked asphalt; the Legion shell is clean pale paint with
fine scuffs. Palouse and the Allegheny forest changed little (the grassland is mostly turf, the forest mostly
trees) and the Allegheny forest road went from grey to a paler sandy gravel. The Hangar shots of the Juggernaut
differ old to new by the same amount as old to old (RMSE 0.004, 0.0016, 0.0027 against 0.004, 0.0012, 0.0058),
so the Juggernaut is unchanged.

## Frame rate (High, same sitting, A/B/A)

| Map | avg fps old / new | GPU ms old / new |
|---|---|---|
| Ashen valley | 35.7 / 32.5 | 27.7 / 30.5 |
| Sector 86 | 38.8 / 35.7 | 25.5 / 27.8 |
| Palouse | 39.7 / 37.9 | 24.9 / 26.1 |
| Allegheny | 29.8 / 27.1 | 33.4 / 36.6 |
| Brilon | 44.2 / 39.9 | 22.4 / 24.8 |

Cost about 9 to 10 % of the average frame rate on High; the old files run a second time gave the same numbers
as the first, so the comparison holds. Earlier runs in other sittings are not comparable (machine speed drifted
by more than the cost).

## Tests

- New `tests/test_textures.gd` (5 tests): every texture set has its maps and is credited; GroundLook has no
  SETS constant and kit.json has every ground slot; every map resolves each slot to a real set with color and
  normal and a positive per_m; Brilon's road override reaches the material; the Legion's field shell wears a
  surface no Juggernaut finish uses, with albedo, normal and orm. Red first: the file did not compile before
  `GroundLook.sets` existed, and the Legion test failed (both shells on chipped_paint, a Juggernaut surface)
  until legion_paint went in. Now 5/5.
- Changed: `tests/test_world_look.gd` (uses `GroundLook.sets` instead of SETS), `tests/test_mech_look.gd` (the
  Legion shell's surface is read from legion_finishes.json instead of the literal "chipped_paint").
- Run headless, all green except one: test_textures 5/5, test_look 21/22, test_look3 6/6, test_tone 5/5,
  test_world_look 10/10, test_mech_look 4/4, test_hangar 18/18, test_kit 10/10, test_kit_edges 4/4,
  test_small_map 17/17, test_big_map 11/11, test_real_maps 7/7, test_destruction 10/10, test_graphics 5/5.
  The test_look failure (test_foot_dust_puffs_land_behind_the_foot_and_are_capped, "a puff at a gallop") also
  fails with all of this pass's files put back to HEAD, so it comes from other uncommitted work in the tree
  (the mech scripts), not from textures.
- Python: black and pyright on tools/fetch_kit_textures.py and tools/make_mech_textures.py, 0 errors.
- Shaders cannot compile headless; every bot run's godot.log was checked for SHADER ERROR. One mid-pass edit
  broke the ground shader (a helper function took samplers with two different filters) and the ground fell back
  to plain grey; that run's fast fps were thrown out and the shader fixed (`sample_nt_n` for normal maps).

## Verified and reasoned

Verified: the before and after images (looked at as sheets and full-size crops), the A/B/A frame rates, the
histogram numbers, the tests above, the Juggernaut's Hangar shots unchanged, no shader errors in the final runs.

Reasoned only: the facade's reveal and sill directions and the triplanar normal signs were worked out on paper
and look right in the shots, but no test pins them; the roof tile direction was seen on Brilon roofs from the
street and from above only at a distance.

## Open issues and decisions for Emerson

- **Far hills.** `small_map.gd` and `big_map.gd` (not this pass's files) still pass `rock/color.jpg` to the
  backdrop, so the far hills keep the old grey rock while the cliffs are now warm layered rock. A one-line change
  there (pass the map's rock set from `GroundLook.sets(entry)["rock"]`) would match them. Left for Riku.
- **Grass tufts** are still sparse: that is the scatter density in maps.json "scatter", not a texture; not
  touched.
- **Legion edge wear and panel grime** need the model's edges or UVs; the surfaces are projected and cannot
  know where an edge is. The paint is clean and pale with fine scuffs; real edge wear would need a baked mask
  from the models helper.
- **Decision:** cliffs on Sector 86 went from grey to warm brown-grey (the new rock's own colour at 60 %). If
  Emerson wants grey cliffs back there, it is one palette number: big_map rock_tint toward (0.9, 0.95, 1.0).
- **Decision:** Allegheny's forest road reads as pale sandy gravel now. A greyer road_tint in its palette would
  bring back the grey.
- Chase shots in the later runs are first person (the gun barrel, no mech in view); the first before-set showed
  the mech. That came from other work in the tree during the evening; the same-sitting pair (714/715) has the
  same view on both sides.
- Check images take room: 27 folders, about 760 MB, kept (never delete check images).
