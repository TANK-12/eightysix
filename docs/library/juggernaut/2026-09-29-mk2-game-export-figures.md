# Juggernaut Model 2: game export figures (mass and actuators)

date: 2026-09-29 · for: both · from lane B1 (Kenji / ejb-65), milestone `mk2_m24_rear_block.blend`

Source: `~/Models/juggernaut/model2/export/game/juggernaut_mk2.json`, made by `export_game.py`.
Masses are collider-hull volume x an effective density per part class (`gamedata.py`): **reasoned
estimates, not sourced figures.** Actuator needs are static, at a two-leg stance from the rest pose.

total 12,174 kg, gun (on gun_pitch) 5,980 kg, centre of mass [-0.0005, 1.6388, 0.3817] (glTF axes, m), 54 parts, 54 with colliders, 479,062 triangles (bevels at 1 segment), glb 15.1 MB.

| Class | Mass (kg) |
|---|---|
| gun_mech | 2,916 |
| ammo | 2,232 |
| gun_barrel | 1,942 |
| leg | 1,874 |
| armour | 1,153 |
| cockpit | 952 |
| joint | 559 |
| sensor | 310 |
| foot | 144 |
| other | 92 |

Front-right leg and the gun (the other legs mirror):

| Joint | Static need (N m) | Test-bench kind | Rated | Power (kW) | Current at 96 V (A) | Seconds to overheat |
|---|---|---|---|---|---|---|
| hip_yaw.FR | 24,772 | rotary | 30,965 N m | 7.1 | 74 | 480 |
| hip_pitch.FR | 165,146 | rotary | 206,433 N m | 47.6 | 496 | 72 |
| knee.FR | 90,265 | linear | 1,019,308 N | 39.2 | 408 | 87 |
| ankle.FR | 4,513 | rotary | 5,642 N m | 1.3 | 14 | 2,634 |
| gun_elevation | 586 | linear | 1,564 N | 0.1 | 1 | 56,980 |


## Emerson on the mass (2026-09-29, after part 1)
No target weight, but he does not expect 12.2 t: the Juggernaut is the "aluminium coffin". The 12.2 t
from `gamedata.DENSITY` (steel-shell guesses) is a **placeholder**. At some point, rebuild the mass bottom
up from real parts: the alloys and metals per part (the shell is a thin aluminium skin: in the anime it is called the aluminium coffin because it has next to no armour, which also matters for A3's damage model), real motor weights for actuators of
this size (the real machine, not the game's power figures), the 57 mm ammo weight, and battery or fuel
weight depending on how the power question goes. Not started; no session has been given this yet.
