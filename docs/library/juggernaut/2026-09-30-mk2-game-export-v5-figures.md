# Juggernaut Model 2: game export v5 figures

date: 2026-09-30 · for: both

Export of milestone `mk2_m37_shin_tube.blend` by `~/Models/juggernaut/model2/export_game.py` (lane B1 part 5,
Sakura), files in `~/Models/juggernaut/model2/export/game/`. The v4 files are kept unchanged in
`export/archive/v4_m35/`. v1-v4 figures are in the docs beside this one.

**Verified** (run on 2026-09-30 11:39):
- Full mesh `juggernaut_mk2.glb`: 532,091 triangles, 16.6 MB (v4: 529,327). The change is the legs: round
  grooved shells, a slim round shin tube, short knee plates, ribbed knee rams.
- Lite mesh `juggernaut_mk2_lite.glb`: 129,642 triangles, 4.8 MB.
- 55 parts, 55 with colliders, 66 convex hull pieces (as v4).
- JSON keys, `joints`, `legs` and `sockets` identical to v4 (13 sockets, same positions).
- Godot 4.7 headless load, both files: 55 meshes, 54 bones, 13 sockets, 4 soles, 7 clips.
- Unit tests for the export maths: 8 pass.

**Placeholders** (reasoned, not sourced): total mass 12,165 kg (v4 12,259; slimmer shins), gun 6,060 kg,
centre of mass [-0.001, 1.638, 0.407] m (glTF axes).
