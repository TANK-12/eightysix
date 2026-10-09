# S23: 2.5D / 3D wallpapers (after S22)

Emerson 2026-09-27: "separate things from the wallpaper like people to make
2.5d or 3d effects". Install approved (he said go with the recommendation,
both): rembg (github.com/danielgatis/rembg, MIT) with the isnet-anime model,
about 170 MB, and Depth Anything V2 Small as ONNX (github.com/DepthAnything,
Apache-2.0), about 100 MB. Into one app's .venv, models under ~/Forge (disk
is short: 71 GB free), nothing system-wide. Run once per wallpaper on the CPU
and cache the cut-out and depth map. Then layered parallax on the pointer,
Alt+V moving the depth to the beat, particles flying between the subject and
the sky; a setting for each.

## State
- done+checked by S26 (77100ab), see sessions/2026-09-28-S26-finish-wave.md item 6. No install was needed: the models PanelForge already has were used (isnetis = rembg's isnet-anime; Depth Anything V2 Base).
