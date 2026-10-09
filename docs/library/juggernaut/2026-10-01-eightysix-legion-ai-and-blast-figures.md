# Eighty Six: Legion AI, HE blast and Legion fps figures

date: 2026-10-01 · for: both · lane A4 part 2 (Kenji, relay-12)

## HE blast (scripts/combat/blast.gd; Kinney-Graham fit, ground x1.8, reflected)
Face impulse for 2.0 kg TNT on the ground: 772 Pa s at 2 m, 225 at 5 m, 64 at 15 m.
Löwe 120 mm HE beside the 5,564 kg Juggernaut: 6,279 N s at 2 m (1.13 m/s), 2,827 N s at 5 m (0.51 m/s),
1,022 N s at 15 m (0.18 m/s). For scale, the 57 mm APFSDS recoil is about 5,600 N s.
Passing 120 mm dart (Whitham N-wave at 3.5 m): ~1 kPa over 0.36 ms, push and pull cancel: under 1 N s.

## Legion CPU and fps (Iris Xe, 1920x1080, default preset, off-screen bot)
- 4 walking units, headless: 4.9 ms a physics tick before, 1.7 ms after (one hitbox Area3D per joint, pose
  written once per frame).
- In game, wave 3 on Ashen valley (Löwe, 2 Grauwolf, Ameise + 5 wrecks): 15 fps (CPU 70 ms) before,
  40-49 fps (CPU 12-17 ms) after; no Legion: 44 fps. images/210-a4_fps_legion and 211.
- Lite model past 150 m: effect within run-to-run noise.

## AI checks (tests/test_ai.gd)
Scout spots at 320 m in 0.1 s, keeps ~239 m; Grauwolf pack widest spread bearings -152 / 110 / 113 deg;
blade lands after 3.3 s; Löwe first 120 mm at 300 m lands 1.1-2.4 m from centre (3 runs).
