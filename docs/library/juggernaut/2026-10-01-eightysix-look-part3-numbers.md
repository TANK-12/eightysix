# Eighty Six: sun, grain and fps numbers from lane B4 part 3

date: 2026-10-01 · for: both · by Tetsu (ejb-21). Full write-up: `~/Forge/sessions/juggernaut-alpha/results/B4.md` "Part 3".

| Measure (Medium, 1920x1080, off screen) | Before | After |
|---|---|---|
| Facing the sun: mean brightness of the top third (0-255) | 160 | 108 |
| Ground fine-detail noise (mean Laplacian), sun view | 15.1 | 10.4 |
| same, start view | 17.6 | 10.9 |
| same, town view | 20.6 | 14.8 |
| same, lake view | 16.4 | 12.3 |
| Start view fps, back to back (GPU ms) | 88.2 (11.07) | 88.5 (11.03) |
| Scoreboard route fps view / walk, back to back | 45.9 / 41.7 | 47.3 / 43.1 |

Grain probe on Emerson's own settings (Ultra, 300 m draw distance; images/212): switching off SDFGI, SSIL, SSR, SSAO,
volumetric fog, MSAA, glow or the shadow filter changed the noise by at most 12 % each; TAA to FXAA made it 40 % worse.
The grain was the ground texture's pebble detail. His settings ran **8-16 fps** in these runs.

Fps readings swing 54-88 between sittings on this laptop (other sessions' tests, machine state): compare only back
to back in one sitting.
