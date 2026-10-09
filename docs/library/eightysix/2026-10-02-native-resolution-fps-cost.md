# Eighty Six: what native resolution costs on the big map

date: 2026-10-02 · for: both · lane B5 part 6

Emerson asked for no upscaling or sharpening as the base, so every preset now renders at native resolution
(was Low 65 % + FSR 1 + 10 % sharpening, Medium 80 % + FSR 1). Measured in one sitting on the Iris Xe, 1920x1080,
nothing else on the GPU, `tools/bot_run.sh b5_fps --preset=<p>` (images 383-386). Average fps (GPU ms).

| Preset | Old (upscaled): still / walk / town | Native: still / walk / town | Target |
|---|---|---|---|
| Low | 85.5 / 83.7-95.2 / 68.2 (11.3 / 10.1-11.6 / 14.4) | 63.8 / 64.6-66.4 / 49.8 (15.0 / 14.4-14.8 / 19.3) | 60 |
| Medium | 61.7 / 59.3-61.9 / 49.7 (15.9 / 15.8-16.5 / 19.8) | 53.1 / 52.1-53.2 / 41.7 (18.0 / 17.9-18.2 / 23.2) | 45 |

High and Ultra were already native (part 5: High 49 / town 42, Ultra 15). This sitting ran about 17 % slower than
part 5's (old Low 85 vs 103 then), so compare within a sitting. Towns miss the target on both presets.
