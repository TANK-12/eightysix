# Juggernaut Model 2: game export v4 figures

date: 2026-09-30 · for: both

Export of milestone `mk2_m35_feet.blend` by `~/Models/juggernaut/model2/export_game.py` (lane B1 part 4,
Sakura), files in `~/Models/juggernaut/model2/export/game/`. The v3 files are kept unchanged in
`export/archive/v3_m32/`. v1-v3 figures are in the docs beside this one.

**Verified** (run on 2026-09-30 11:20):
- Full mesh `juggernaut_mk2.glb`: 529,327 triangles, 16.6 MB (v3: 501,967). The rise is the new foot pads,
  the round sight housing and the hood rod loops.
- Lite mesh `juggernaut_mk2_lite.glb`: 129,606 triangles, 4.8 MB.
- 55 parts, 55 with colliders, 66 convex hull pieces (as v3).
- JSON keys, `joints` and `legs` identical to v3; the same 13 socket names.
- Sole sockets moved 4.8 cm outboard (FR: x 2.824 -> 2.864 m, z -1.926 -> -1.952 m, glTF axes), because
  the foot spike is now centred under the foot point (front blueprint), not under the ankle.
- Godot 4.7 headless load, both files: 55 meshes, 54 bones, 13 sockets, 4 soles, 7 clips.
- Unit tests for the export maths: 8 pass.
- The glTF exporter prints "MeshOptimizer is not available" (a Blender add-on library message); the files
  are written and load in Godot.

**Placeholders** (reasoned, not sourced; Emerson expects a lighter "aluminium coffin"):
- Total mass 12,259 kg, gun 6,060 kg, centre of mass [-0.001, 1.635, 0.404] m (glTF axes).
- Gun elevation static torque 1,766 N m.
