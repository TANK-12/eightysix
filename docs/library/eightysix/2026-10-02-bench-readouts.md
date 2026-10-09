# Test bench readouts, Juggernaut Model 2 on the flat pad

date: 2026-10-02 · for: both

Measured by the bot run `tools/bot_run.sh bench_check` (images/414-bench_check, Test bench physics, 5.5 t, 96 V bus,
60 kWh pack). Part of lane B6; see results/B6.md.

- Standing: 4.4 kW, 45 A, 96.0 V, hottest joint 20.1 C (rear-left hip pitch).
- Walking (8 s forward): 10.6 kW, 111 A, 95.9 V, 20.4 C; HUD speed about 1 km/h.
- Mid jump: 46 kW, 486 A, 95.5 V. Battery 99.9 % afterwards.
- Standing hip torque per leg 25 to 42 kNm, knee 11 to 21 kNm (HUD, front legs lighter than rear).
- Rough field relief on a test cross: -0.26 to 0.94 m (set amplitude 1.6 m).
- Heat never matters at this mass: the actuators in parts.json are sized for the old 12.25 t export.
