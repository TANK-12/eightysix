# Eighty Six: look pass numbers (fps per preset, anti-aliasing, texture import cost)

date: 2026-10-02 · for: both

Lane LOOK (Relay 26). Big map `tools/bot_run.sh b5_fps --preset=<p>`, 1920x1080 off screen, avg fps (GPU ms).

| preset | before (B5 part 6) | new look, textures uncompressed | new look, textures VRAM + mipmaps |
|---|---|---|---|
| Low | 64 open / 50 town | 22.7 (43) | 52 still, 47.5 town (18.5) |
| Medium | 53 open / 42 town | 20.9 (46) | 44.5 still, 40.4 town (21) |
| High | 49 | 18.7 (52) | 36.8 still, 37.1 town (25) |
| Ultra | 15 (92-110 ms) | 15 (172-210 ms) | 15 (130-160 ms) |

Texture import: uncompressed, no mipmaps cost the ground shader about 30 ms a frame on Low. Godot's detect_3d only
fixes imports for textures the editor sees in 3D; textures loaded from script need compress mode 2 and mipmaps
set by hand in the .import.

Anti-aliasing on Ultra (sharpness, higher is sharper, `tools/sharpness.py`): TAA + MSAA 2x 4.5; MSAA 4x 15.5;
MSAA 2x 16.0; FXAA + MSAA 4x 11.7. Ultra is now MSAA 4x, no TAA.

Images: before 392 (small), 393 (big); after 423, 424.
