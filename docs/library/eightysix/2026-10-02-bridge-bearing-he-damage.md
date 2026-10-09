# Eighty Six: what a fired HE shell does to a bridge bearing

date: 2026-10-02 · for: both

Measured on the big map's Ash bridge (images/360 and 367-b5_bridge_shell, Relay 22). Juggernaut on the south bank, 60 m off, 57 mm HE (500 damage, destruction scale 1.6, reach 2.6 m).

- A shell bursting on the deck beside a bearing gives the bearing 150-620 hit points per hit (a direct hit would give 800).
- Bearing hit points: 2756 before (steel_rust 2500/m3 x 1.1 m3), 1378 after `destruction.weak_hp_scale` 0.5 (data/tuning.json).
- Live with 8 shells: about half of them land (the gun is fixed to the body, which settles for seconds after a park); shells 3-5 took the bearing from 1378 to 14, shell 6 broke it.
- Löwe 120 mm HE is 2500 damage: one or two hits.
