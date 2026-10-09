# Eighty Six alpha 0.1: frame rate per preset

date: 2026-10-07 · for: both · measured by lane A6 (Asuka, Relay 51)

Version 017 source (commit 6bc599d), `tools/fps_log.py`, test range with the real Juggernaut, 1920x1080 native,
off screen, Intel Iris Xe (ADL GT2), no Blender job, all four presets in one sitting (06:31-06:34).

| Preset | Target | Avg fps | 1 % low | Min | GPU estimate | Bound |
|---|---|---|---|---|---|---|
| Low | 60 | 66.5 | 36.6 | 13.9 | 75.7 | GPU |
| Medium | 45 | 58.4 | 31.0 | 14.5 | 61.6 | GPU |
| High | 30 | 35.2 | 20.2 | 13.8 | 38.2 | GPU |
| Ultra | none | 15.1 | 13.3 | 13.3 | 9.0 | GPU |

Ultra sits on the 15 fps pacing floor (see LOOK3); compare its GPU time, not its fps. Targets are no longer
limits since 2026-10-02 (graphics over frame rate). Earlier: A1 (stand-in, no look passes) Low 96.1 / Medium 54.1 /
High 45.8 / Ultra 15.1. Per-map figures: `~/Forge/sessions/juggernaut-alpha/results/LOOK3.md`, `MAPS2.md`.
Raw logs: `~/Games/eightysix/logs/fps/20261007-063116-*.json`.
