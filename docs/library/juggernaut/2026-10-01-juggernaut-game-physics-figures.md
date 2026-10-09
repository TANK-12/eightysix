# Eighty Six: the Juggernaut's game physics figures (after A3 parts 4-5)

date: 2026-10-01 · for: both · written by Tetsu (ejb-d4, track A)

Every figure below is what the game now uses (no game-mode scales on any of them). **Measured** = from a test
or bot run; **stated** = a reasoned design figure. Full detail: `~/Forge/sessions/juggernaut-alpha/results/A3.md`.

| What | Figure | How known |
|---|---|---|
| Mass, combat loaded | 5,563.7 kg (table 5,423.3 + 140.4 kg of MG belts) | measured in game (test) |
| Centre of mass (body frame) | (0, 0.036, 0.240) m | measured (table says 0.047, 0.239) |
| Gallop top speed | 70.4 km/h | measured, flat ground and Ashen valley |
| 0-50 km/h | 1.25 s | measured |
| Drive peak power | 600 kW | stated |
| Belly clearance at rest / gallop / crouch | 0.46 / 0.25 / 0.14 m | measured |
| Slide from a gallop | 59.8 m flat test ground, 43-45 m on the valley | measured |
| Slide friction (feet skating) | mu 0.4 (setting 0.15-0.8) | stated |
| Slide spin acceleration cap | mu m g r / I, ~220 deg/s2 at mu 0.4 | stated from physics |
| 57 mm APFSDS recoil | 5,580 N s (1.2 kg + 1.6 kg propellant at 1,550 m/s, gas 1.5x) | stated; body kick 1.03-1.04 m/s measured |
| 57 mm round mass | 10.75 kg (774 kg ammo / 72 rounds) | stated |
| 12.7 mm recoil per round | 60 N s; ~16 rounds/s for the pair | stated; rate measured |
| Air turning from leg swing | 12.1 deg in 2 s held (test); 3-7 deg/s on the valley | measured; angular momentum conserved (0.0 error) |
| Running jump launch | ~22 m/s, ~7.6 m high, 2.4 s in the air | measured |
| Wire winch | 120 kW, stall 120 kN, reel 8 m/s slack / ~2.3 m/s lifting | stated; power limit tested |
| Wire cable | 16 mm steel, breaks at 170 kN (held 0.15 s) | stated |
| Abseil | 4 m/s, drum ramps 3 m/s2 while hanging | stated; tested (no snap) |
| Air drag | Cd x A 7 m2, air 1.2 kg/m3 (~2 kN at 20 m/s) | stated |
| Legs straightening at speed | 0.23% of leg-frames (was 6-8%) | measured |
| Ashen valley route | 0 stuck events, 0 flat-ground belly scrapes | measured (`score_move`) |
