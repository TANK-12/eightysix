# Juggernaut Model 2: game export v2 figures

date: 2026-09-30 · for: both

Export of milestone `mk2_m29_subarm_hood.blend` by `~/Models/juggernaut/model2/export_game.py`, files in
`~/Models/juggernaut/model2/export/game/`. Replaces nothing: v1's figures are in
`2026-09-29-mk2-game-export-figures.md` beside this file.

| Figure | v1 (m24) | v2 (m29) |
|---|---|---|
| Total mass (placeholder densities) | 12,174 kg | 12,137 kg |
| Gun mass (on gun_pitch) | 5,980 kg | 5,944 kg |
| Parts / colliders | 54 / 54 | 55 / 55 |
| Triangles | 479,062 | 498,250 |
| glb size | 15.1 MB | 15.8 MB |
| hip_pitch.FR static need | 165,146 N m | 161,353 N m |
| knee.FR static need | 90,265 N m | 89,996 N m |
| gun_elevation static need | 586 N m | 18 N m (the gun is balanced on its pitch axis; near zero either way) |

The mass is a placeholder (steel-shell densities). Emerson expects much less for the "aluminium coffin";
a bottom-up mass from real parts is still to do. Godot 4.7 load check: 55 meshes, 54 bones, 9 sockets,
7 clips (verified 2026-09-30).
