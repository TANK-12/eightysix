# Juggernaut Model 2: why 12 t, and a realistic aluminium-coffin mass

date: 2026-09-30 · for: both

## Why the export says 12,165 kg (verified)
The export (`~/Models/juggernaut/model2/gamedata.py`) prices each part as **convex hull volume x one
density per class**. A convex hull is a shrink-wrap round the part, so hollow and concave parts count
the air inside them. By class: gun mechanism 2,971 kg, ammo 2,232, barrel 1,929, legs 1,770, armour
1,117, cockpit 952, joints 641, sensors 310, feet 157, other 88. The receiver alone is 2,722 kg
because its hull is 3.4 m³ (the real modelled solid is 1.4 m³).
**Removing all armour-class parts from the placeholder still leaves 11,048 kg.** Armour is not the
problem; the gun and ammo (7.1 t) are.

## Realistic version (reasoned estimates, not sourced)
Measured surface area and closed volume of every part from `mk2_m37_shin_tube.blend` (verified), then
each part priced as what it would be made of: 8 mm aluminium skin on the pod and hatch (the anime's
"aluminium coffin"), 10 mm aluminium add-on plates, 7075 aluminium leg shells, a steel 57 mm tube
(5.0 m, 160 to 95 mm outside diameter), steel joints and rams, 6 kg per 57 mm round.

| Figure | kg |
|---|---|
| Empty | 4,589 |
| Combat loaded (129 rounds + 60 kg pilot) | 5,423 |
| No add-on armour, empty | 4,334 |
| No add-on armour, loaded | 5,168 |
| Add-on armour plates (flank, visor, side panels) | 255 |

Groups (empty + load): gun 1,389 · legs 1,060 · ammo 182 + 774 rounds · internals 688 + pilot 60
(power pack 350 assumed, cockpit fit-out 120, wiring 5%) · hull 467 · blades/anchors/winches/arms 433
· armour 255 · sensors 114. Centre of mass loaded [0.0, 1.457, 0.239] m (glTF axes; placeholder was
[-0.001, 1.638, 0.407]).

Biggest single parts: receiver 674 kg (breech + recoil 350, autoloader 120, housing), barrel 469,
magazine 89 + 486 of rounds (81), power pack 350, pod tub 296.

Softest assumptions: power pack (350 kg), rounds per box (105 per m³), frame fractions. Change them in
the script and re-run.

## Files
- `~/Models/juggernaut/model2/realistic_mass/realistic_mass.py`: the calculation (run with python3)
- `.../realistic_mass/realistic_mass.json`: every part with empty and load mass and a note, for the physics side
- `.../realistic_mass/measure_blend.py` + `measured_m37.json`: the Blender measurement it reads

Not wired into the game yet: `~/Games/eightysix` still takes its masses from the 12 t export.
