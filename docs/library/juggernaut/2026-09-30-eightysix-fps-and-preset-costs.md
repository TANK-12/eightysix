# Eighty Six: frame rates per preset and what each High feature costs

date: 2026-09-30 · for: both · lane A1 part 2 (Yuna, ejb-27)

Machine: Dell Latitude 5430, Intel Iris Xe (ADL GT2), Mesa 26.2.2, Godot 4.7.2 Forward+ (Vulkan), Jolt.
Scene: the throwaway test range with the stand-in box walker, 1920x1080, off screen (headless mutter, mailbox
presentation, so nothing caps the frame rate), no Blender job running. Route: `tools/bot/fps_route.json`, 20 s.
Real maps (lanes B3, B5) will cost more; re-measure there.

## Per preset (logs/fps/20260930-062852-*.json)
| Preset | Target | Avg fps | 1% low | Min | GPU ms/frame | Met |
|---|---|---|---|---|---|---|
| Low | 60 | 96.1 | 46.5 | 14.8 | ~10 | yes |
| Medium | 45 | 54.1 | 28.1 | 14.3 | ~18 | yes |
| High (retuned) | 30 | 45.8 | 25.0 | 13.3 | ~20 | yes |
| Ultra | none | 15.1 | 13.3 | 13.3 | ~120 | no target |

The old High (with SDFGI, SSR, 128x96 fog, TAA, 4096 shadows) ran 15.4 fps on the same route.

## What each High feature costs (standing still, each removed on top of the last)
| Removed | GPU ms saved | fps after |
|---|---|---|
| (full old High) | (58.4 ms) | 16.8 |
| SDFGI | 20.1 | 25.2 |
| SSR | 3.8 | 27.9 |
| Fog 128x96 → 64x64 | 5.7 | 33.6 |
| Clouds high → low | 0.4 | 33.7 |
| Shadows 4096/soft 2 → 2048/soft 1 | 3.0 | 37.5 |
| TAA → FXAA | 5.7 | 46.5 |
| Scale 1.0 → 0.8 with FSR1 | 1.8 | 54.3 |

The route costs about 1.47x the standing view. The 1% lows (28, 25) are under the Medium and High targets:
work for lane A6.
