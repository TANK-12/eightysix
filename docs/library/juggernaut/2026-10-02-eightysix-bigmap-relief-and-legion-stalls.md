# Eighty Six big map: relief numbers and where the Legion stall (B5 part 3)

date: 2026-10-02 · for: both · measured by Relay task 20 (lane B5 part 3); details in
`~/Forge/sessions/juggernaut-alpha/results/B5.md` part 3

## Relief of the playable area (3.4 km square, 25 m grid, 8 m central difference)
| slope band | share of the ground |
|---|---|
| 0-10 degrees | 44 % |
| 10-20 | 36 % |
| 20-30 | 14 % |
| 30-40 | 5 % |
| 40+ | 1.8 % |

The Legion's slope limit is 38 degrees (Löwe 32). 94 % of the interior is under 30 degrees. The rim mountains
(edge band, 340 m wide) are where the steep ground is (up to 80 degrees).

## Wire on steep slopes (live, bot `b5_wire_slopes`)
Parked 45 m below three of the steepest interior slopes (55-62 degrees): the wire preview said "ok" and attached on
all three (cable 47-52 m).

## Legion on the big map: the finale run (bot `b5_finale_long`, Juggernaut standing at the spawn, waves 1-3 cleared)
Distance to the player over time of the last wave (Löwe, 2 Grauwolf from the lake road and east shore, Ameise from the
farm track), at 60 s / 120 s / 200 s / 320 s:

| run | Löwe | Grauwolf A | Grauwolf B | Ameise |
|---|---|---|---|---|
| before any fix (images/342) | 1030 / 880 / 893 / 908 | 1288 / 747 / 676 / 691 | 1230 / 767 / 680 / 695 | 507 / 524 / 559 / 573 |
| path-finding (images/343) | 1033 / 760 / 714 / 729 | 1339 / 839 / 650 / 665 | 1240 / 832 / 669 / 695 | 516 / 529 / 562 / 577 |
| path-finding + upright keel (images/345) | 1033 / 762 / 715 / 787 | 1332 / 717 / 651 / 666 | 1368 / 1379 / 1409 / 1424 | 468 / 472 / 507 / 521 |

In every run the units end motionless. Before the keel they were lying upside down (tilt 114-174 degrees); with it
nobody is upside down but they still stop (planted feet 0-1, speed 0). Open problem, top of B5 part 4.

## Other numbers
- Legion path grid: 16 m cells over the 3.9 km Legion area (244 x 244), built in 69 ms; a path query is a few ms.
- Bridge column (wave 3): three Grauwolf cross the 69 m bridge in about 25 s at 4-5 m/s.
- Fall damage: a Grauwolf dropped 12 m ends at 27 % hull; 1.5 m costs nothing.
