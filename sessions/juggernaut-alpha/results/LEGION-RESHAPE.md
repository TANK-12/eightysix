# Legion reshape: Grauwolf and Löwe

date: 2026-10-08 · for: both (Emerson, Riku and the next Claude session)

Emerson's ask: "the enemy models for the larger 2 enemies suck". Before, both units were boxes on thin
stick legs (`~/Models/legion/images/19_m12_hi_night/*_sheet.jpg`). This pass reshaped the Grauwolf
(dragoon type) and the Löwe (tank type) from the anime stills, the design sheets and the scale sheet, and
put them into the game. The Ameise (scout) is unchanged; it was only rebuilt at the new tags so the export
script finds all three units. Final milestone: **m18_hi_night**.

## What changed per unit

**Grauwolf** (`~/Models/legion/units/grauwolf.py`)
- Side profile is now the anime's swept X: the upper hull (`back_plate`) is a faceted wedge rising from
  behind the head to a raised point at the rear (4.7 m high), with a crest along its spine; the lower plate
  (`belly_plate`) falls away to the rear.
- V head shield (`head`): a wide helm with two lens circles in the top corners, angry brow lines and a centre
  seam, a big purple visor low in the V (`visor`), and a dark slotted chin running down to a point. The face
  tilts so the chin sits forward.
- Rocket box (`launcher`): a rounded capsule on a short post (`launcher_mount`) over the front half, top at
  4.3 m (was 3.9 m), so it clears the rising hull as it turns. Six tubes in its front face with caps.
- A fan of eleven leaf-shaped feather fins (`comb_00`..`comb_10`) under the raised rear.
- Blades and blade arms are faceted plates (chisel tip, fuller, cuff, guard).
- Legs: broad faceted plates (chamfered sections, a crease down each face, wider before the knee, a flatter
  knee cap). Hip, knee and foot positions are the same as before, so the game's gait is unchanged.

**Löwe** (`~/Models/legion/units/loewe.py`)
- A long angular wedge turret tapering forward, its spine rising toward the rear with a comb of spikes.
- A tall face block (`front_block`) at the nose with a big round sensor lens (housing ring, dark glass,
  inner ring, pupil) and a small cyan light bar; the gun's mantlet sits under the lens. The gun axis moved
  down from 4.55 m to 4.4 m (scale sheet: about 4.3 m).
- Hexagonal faceted shoulder blocks (`wing_R`, `wing_L`): the top falls from the inner edge to the outer,
  a gem-cut front, a layered plate on top and outside, bolts, ear fins.
- New part `chin`: a wide chamfered block jutting from the hull's front with a dark recess and four cyan
  light strips (as in c6 61-66). New part `fin`: a swept fin standing over the face block.
- 16-sided faceted saucer hull with a rim band; the rear fan moved to the turret's end so its hub (a weak
  point) shows; two round sensors under the chin.
- Legs: broad faceted plates, as the Grauwolf's.

**Shared code**
- `lib.py`: `Kit.plate`, `plate_rings`, `d_plate` (faceted armour plates, shaded crisp at 6 degrees so the
  facets read), `leg(style="plate")` (the Ameise keeps the default `"blade"`), `loft(sharp=...)`.
- `export_game.py` + `gamedata.own_collider`: a unit's GAME table may name `no_collider` patterns.
- `units/grauwolf.py` GAME: `"no_collider": ["comb_*"]`, rocket and optic sockets at the new places.
  `units/loewe.py` GAME: muzzle and coax at the new gun height, optic on the lens.

## Milestones (each folder has `<unit>_sheet.jpg` and `<unit>_vs_refs.jpg`)
| Tag | Look | Folder (`~/Models/legion/images/`) | What it tried |
|---|---|---|---|
| m13_hi_night | clay | `20_m13_hi_night` | first reshape: V head, capsule, plate legs, wedge turret, face block, chin |
| m14_hi_night | clay | `21_m14_hi_night` | launcher raised, thicker rising plate, bigger visor, leaf feathers, wider legs |
| m15_hi_night | clay | `22_m15_hi_night` | upper hull as a deep wedge (the X reads from the side), crisp plate shading, gem-cut shoulder blocks |
| m16_hi_night | clay | `23_m16_hi_night` | broader feathers, smaller shoulder blocks clear of the front legs, turret spine rising to the rear |
| m17_hi_night | eevee | `24_m17_hi_night` | all three units with the night livery |
| m18_hi_night | eevee | `25_m18_hi_night` | final: the visor rides the head joint (see below) |

Refs montages used for every comparison: `~/Models/legion/critic/round3/grauwolf_refs.jpg`,
`loewe_refs.jpg`. Blends: `~/Models/legion/blends/<unit>_m13..m18_hi_night.blend` (m12 and older kept).

## Tests and checks (all run, real output)
- `test_parts.py -- m18_hi_night`: ALL PASS (one root each; 6 / 6 / 8 legs; a hip turn moves only its own
  leg, rigidly; every detail mesh moves with its part, 10/10). Output in
  `~/Models/legion/images/25_m18_hi_night/test_parts.txt`.
- `python3 -m unittest discover -s tests` in `~/Models/legion`: 14 OK (3 new for the collider rule; they
  failed first, before `own_collider` existed).
- `./export_game.sh m18_hi_night`: 0 problems on all three json files; Godot loads all six glb files.
- `legion_check.gd`: sockets 0.0 m from the json; collider hull boxes within 1.5-1.6 cm of the meshes; joint
  extras 18/18, 23/23, 26/26; nothing missing.
- Triangles, full / lite: Grauwolf 46,046 / 9,270 (was 38,086 / 5,782); Löwe 55,966 / 9,870 (was 50,988 /
  7,668); Ameise 35,744 / 5,296 (unchanged). Parts with colliders: Grauwolf 49, Löwe 99 (was 97: chin, fin).
- In the game after `tools/sync_models.py legion` and the import (exit 0, no errors), `tools/run_tests.sh`:
  test_legion 21/21 plus test_legion_sounds 5/5, test_ai 25/25, test_models 2/2, test_damage 16/16,
  test_combat 28/28, test_mission 32/32. (The runner also reported `test_textures.gd` and
  `test_world_look.gd` as "does not compile": those are the textures helper's files in progress, not
  touched here.)

Two real breaks the tests caught, fixed in the model, no test changed:
1. test_legion `test_a_unit_lying_on_its_side_or_back_rights_itself`: the Grauwolf stayed at 103 degrees.
   The new feather fins were big enough to get colliders and propped it up on its back. They now ride the
   body's collider (`no_collider`); it is upright in 10 s again.
2. test_ai `test_a_grauwolf_closes_and_cuts_with_its_blade`: the blade never landed. A diagnostic run showed
   the Grauwolf pushing the Juggernaut along 7.2 m away, past its 6 m blade reach. The visor hung on the head
   pivot (since m12), so it counted as a fixed body collider, and the new bigger visor touched first. It now
   rides the head joint (a hitbox); first cut after 3.2 s.

## In the game
New bot `~/Games/eightysix/tools/bot/legion_reshape.json` (small map: clears the Ameise wave, trails and
frames the Grauwolf pack, clears it, trails and frames the Löwe). The older `look3_legion` bot shows only
the Ameise. Runs, preset High, off screen, one at a time through the GPU lock:
- before (old m12 models): `~/Games/eightysix/images/695-legion-reshape-before/` (692 and 694 are first
  tries whose Löwe shots framed the wrong unit; kept).
- after (m18): `~/Games/eightysix/images/705-legion-reshape-after/`, with side-by-side sheets
  `before_after_grauwolf.jpg` and `before_after_lowe.jpg` (left before, right after). Looked at: the
  Grauwolf now shows broad plate legs, the rising rear blade, the feather fan and the capsule; the Löwe shows
  plate legs, the wedge turret and the shoulder blocks (these shots see it from the side and behind).
- Frame rate: the HUD counter reads 29-35 fps before and 32-35 after in the Grauwolf shots (one after shot
  13); 9-13 before and 17-26 after in the Löwe shots near the town. These are single readings from shots
  taken while the map streams in, not a measurement; nothing here says the new models cost or save frames.
  Triangles rose about 20% (Grauwolf) and 10% (Löwe) in the full models.

Desktop copies (hard links): `~/Desktop/Juggernaut/Renders/Legion enemies - m18 reshape/Pictures/`
(m18 stills and sheets, m16 clay sheets, the two in-game before/after sheets).
Disk added: about 45 MB of check stills, 6 MB of blends, 85 MB of bot images (four runs).

## Verified versus reasoned
- Verified: everything under "Tests and checks", the sockets and colliders in Godot, and the pictures named
  above (each was looked at).
- Reasoned, not checked: that the new shapes match the anime closely enough for Emerson's eye (the sheets
  are side by side with the refs, the judgement is his); that the mass split by collider volume still feels
  right in play (total masses unchanged at 10 t and 50 t; the Grauwolf's centre of mass moved 3 cm up, the Löwe's 6 cm down
  and 11 cm back).

## Open issues
- The Grauwolf launcher pitched up to its 45 degree limit dips its rear into the rising hull (visual only:
  neither is a collider against the other). The game's rocket range keeps the pitch low in practice.
- When the Löwe turret swings, its shoulder blocks pass close over the front thighs; some clipping is
  possible at large yaw angles. Not seen in the shots.
- The livery in the check renders (night, EEVEE) looks bright and flat; the in-game paint is the textures
  lane's (`data/legion_finishes.json`), not changed here.
- The Löwe's lens and cyan strips are detail meshes, so the lite model (past 150 m) shows the face block
  without them.
- The lowpoly build (`./run.sh <tag>` without DETAIL) now also builds the new shapes; the frozen
  `lowpoly/*_lowpoly.blend` files are untouched.

## Commit
`~/Games/eightysix` 937f5a7: the three json sidecars, `SOURCE.json` and the new bot. The glb files are
git-ignored there; their sha256 is in `assets/models/legion/SOURCE.json`. `~/Models/legion` is not a git repo.
