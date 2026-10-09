# Juggernaut Model 2: game export v3 figures

date: 2026-09-30 · for: both

Export of milestone `mk2_m32_left_strut.blend` by `~/Models/juggernaut/model2/export_game.py` (lane B1
part 3, Sakura), files in `~/Models/juggernaut/model2/export/game/`. v1 and v2 figures are in the
2026-09-29 and 2026-09-30 v2 docs beside this one.

**Verified** (run on 2026-09-30):
- Full mesh `juggernaut_mk2.glb`: 501,967 triangles, 15.9 MB.
- Lite mesh `juggernaut_mk2_lite.glb`: 129,677 triangles, 4.8 MB (Yuna asked for about 120-150k).
- 55 parts, 55 with colliders, cut into 66 convex hull pieces (receiver 6, barrel 7).
- 13 sockets: muzzle, sub-arms R/L, wire anchors R/L, cockpit and eye cameras, logo R/L, and the new
  sole_FR/FL/RR/RL.
- Godot 4.7 headless load, both files: 55 meshes, 54 bones, 13 sockets, 7 clips.
- Unit tests for the export maths: 8 pass.

**Placeholders** (reasoned, not sourced; Emerson expects a lighter "aluminium coffin"):
- Total mass 12,254 kg, gun 6,062 kg, centre of mass [-0.0006, 1.637, 0.404] m (glTF axes).
- Gun elevation static torque 1,796 N m (it swings with every small change to the gun's balance).
