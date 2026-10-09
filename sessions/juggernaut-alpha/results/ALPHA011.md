# ALPHA011: Eighty Six alpha 0.1.1, the good-looking release
date: 2026-10-07 · for: both · Emi (Relay 65, default account) · brief: `../2026-10-07-alpha-011-brief.md`

## Status
**Stopped early by Emerson (2026-10-07 22:10, crew board #1053):** "eighty six is a huge task i will dedicate time
to later, i just want an amazing guide and handoff and road map to get from 0.1 to beta". The look work that was
finished is committed (23c2c68); the version stays 0.1.0-alpha (no bump, no export, no after-set, no fps runs:
Emerson paused performance testing, #1054). The three docs he asked for:
`~/Forge/docs/library/eightysix/2026-10-07-guide.md`, `...-handoff.md`, `...-roadmap-to-beta.md`, linked from the
game's README ("Start here").

## Done and verified
- **Sky** (`assets/kit/shaders/sky.gdshader`, `scripts/world/small_map_sky.gd`): gradient in display space (blue,
  not lilac), cumulus with grey bellies and silver lining, half-res pass. Shots images/629, 631 vs 625. GPU cost A/B
  images/633-636: about +0.5 ms (noise level).
- **Hangar showroom** (`data/hangar.json`, `scripts/ui/hangar_stage.gd`): exposure 1.45, key 24, rim, warm fill, four
  ceiling lamps, seven wall washes, optional volumetric haze, floor sheen `stage.room.floor_roughness` 0.38; SSR
  follows the preset. Shot images/639 (front white point 110 -> 152). hangar.json re-dumped close to its old layout.
- **Grass** (`scripts/world/kit/kit.gd` `spread_m` / `blade_width_m`, `assets/kit/shaders/grass.gdshader` roots
  0.45 -> 0.62, `data/kit.json` 18 blades, `data/maps.json` straw colours on Ashen valley and Palouse, greener per
  map elsewhere, density about 1.6x on every map). Shot images/641 (straw clumps instead of dark sticks).
- Tests 2026-10-07 22:05: test_tone 2/2, test_look (incl. look3) 21/21, test_hangar 17/17, test_kit 10/10,
  test_world_look 9/9, test_mech_look 4/4. No Python touched.

## Done, not verified
- The last softening of the straw colour (colour_b 0.86/0.74/0.44 -> 0.8/0.7/0.44 small map, 0.9/0.76/0.45 ->
  0.84/0.72/0.46 Palouse) was made after the last shot.
- fps cost of the grass density: not measured (fps runs paused).

## Not done (stopped)
Big-map crags, Allegheny sun blow-out, CLIP leftovers, version bump to 0.1.1-alpha, Linux export, PLAYTEST
"what's new", the after-set and side-by-side sheets. All listed in the roadmap (0.1.2, 0.3 and 0.6).

## Before set (verified: bot runs, off screen 1920x1080, quiet GPU, 2026-10-07)
Bot `tools/bot/a011_views.json`: every map (chase camera at spawn + three viewpoints) and the Juggernaut close up in
the Hangar, HUD hidden, no squad. Folders: images/623-a011-before-low, 624 (medium), 625 (high), 626 (ultra).

fps (avg over 6 s in the chase view at spawn, measured about 4 s after the map loaded; single runs, read +-10 %):

| map | Low | Medium | High | Ultra |
|---|---|---|---|---|
| small_map | 67.7 | 46.9 | 27.6 | 15.0 |
| big_map | 56.4 | 47.4 | 26.2 | 15.0 |
| palouse | 69.6 | 50.0 | 25.8 | 15.0 |
| allegheny | 43.5 | 34.5 | 21.7 | 15.0 |
| brilon | 63.3 | 43.5 | 36.6 | 15.0 |

Ultra floors at 15.0 in every bot run (frame pacing, noted in LOOK3); the GPU timer is the only separator there.

## What I saw in the before set (my reading of images/625, High)
- Sky: a flat lilac-grey dome with small wispy specks for clouds, on every map. It fills a third of most frames.
- Ground: flat orange fields with thin dark grass sticks; grass reads sparse up close.
- Hangar: the mech close-ups are dim and grey.
- Big map: the far crags read blue-grey and spiky. Allegheny ridge view: the sun halo blows the top out (known, LOOK3).
