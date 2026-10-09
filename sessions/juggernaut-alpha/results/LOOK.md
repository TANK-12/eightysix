# Lane LOOK: the world's look pass (colours, materials, ground, anti-aliasing)

date: 2026-10-02 · for: both · Relay 26 (hey account), over two sessions. Emerson's note: the game looks "not pretty",
and the evidence says it is the colours, materials and models of the world, not Godot. No upscaling or sharpening
as the base (B5 part 6 stays). fps has no target now: graphics win, but the numbers are reported.

## Try this (Emerson)
- Start the big map (Ashen valley / Frontier) and walk off the road: the ground is turf and dry earth with gravel
  roads and slate rock on the hills, under an overcast-morning grade (blue sky, cool light). The small map keeps
  its golden afternoon but with real textured ground, painted and rusted walls.
- Settings > Graphics: pick **Ultra** again. Ultra is now MSAA 4x with no TAA (sharpness 15.5 against 4.5 for TAA,
  see below). Your saved settings still say TAA until you re-pick the preset.
- Look at a ruined house up close: brick shows plaster patches, a damp dado, rust streaks; far hills no longer have
  the screen-door grain.
- Switch the map's mood in `data/maps.json` ("palette" per map: ground tints, grass/stone amounts, kit tints).

## What changed
1. **The big find: the kit textures were imported uncompressed with no mipmaps.** Godot only switches a texture to
   VRAM compression and mipmaps when the editor sees it used in 3D; ours are loaded from script, so they never
   were. Every ground sample was a cache-missing full-size fetch (the "grain" and shimmer too). All 45 kit
   `.import` files now say compress mode 2 and mipmaps on. Low on the big map went 22.7 -> 49 fps from this alone
   (the first after-run with the new ground shader was 5x slower than before the pass). Test:
   `test_every_kit_texture_is_compressed_and_mipmapped` (red against the old settings).
2. Ground (`assets/kit/shaders/ground.gdshader`, `scripts/world/ground_look.gd`): ambientCG dirt, turf, stones,
   gravel and rock, mixed by large-scale noise, kept off slopes, rock projected two ways, far rock fading to its
   mean, palette uniforms per map. Brightness variation now comes from the noise already sampled instead of a
   second fetch of each texture; stones only sampled where they show.
3. Walls (`masonry.gdshader`): brick and concrete with plaster patches, dado, streaks; steel with rust and paint.
   New CC0 sets are in `assets/kit/textures/` and `assets/SOURCES.md`.
4. Per-map palette (`data/maps.json` "palette", `Kit.apply_palette`); big map weather `frontier_morning`.
5. Shrubs have thinner leaves, grass blades bend in two segments.
6. Ultra preset: MSAA 4x, no screen-space AA (measured below).

## Before / after (same views, Ultra, HUD off)
- Small map: before `images/392-look_small`, after `images/423-look_small`. Big map: before `images/393-look_big`,
  after `images/424-look_big`. Side by side: `tools/contact_sheet.py <before> <after> out.png --only l_ground,town`.
- Not done: bigger model upgrades (blocky ruined walls and shrub leaf cards are still the original meshes),
  decals (cracks, scorch) and baked AO. These are the next steps for the look.

## Anti-aliasing on Ultra (images/401-look_aa, `tools/sharpness.py`, higher is sharper)
TAA + MSAA 2x 4.5 (moving 4.3); MSAA 4x alone 15.5 (16.4); MSAA 2x alone 16.0 (16.8); FXAA + MSAA 4x 11.7.
Frame rate was the same in each mode at the time (15.0, SDFGI and shadows dominate).

## Frame rate (`tools/bot_run.sh b5_fps --preset=<p>`, 1920x1080 off screen, big map; avg fps, GPU ms)
| preset | before the pass (B5 part 6, native) | after, textures uncompressed (broken) | after the fix (final) |
|---|---|---|---|
| Low | 64 open / 50 town | 22.7 still | 52 still, 50 walking, 47.5 town (18.5 ms) |
| Medium | 53 open / 42 town | 20.9 still | 44.5 still, 38-43 walking, 40.4 town (21-24 ms) |
| High | about 49 | 18.7 still | 36.8 still, 34-38 walking, 37.1 town (25-27 ms) |
| Ultra | 15 (vsync cap, 92-110 ms) | 15 (172-210 ms) | 15 (vsync cap, 130-160 ms) |
Open ground is 12-17 % slower on Low/Medium than before the pass for the richer ground and walls; town is about
equal. Ultra is about 40 % more GPU time (MSAA 4x instead of 2x with TAA). Images: 415-418 (broken), 422, 425-427 (final).
Ran on a quiet GPU apart from the first block (checked by a re-run, 419).

## Verified / not verified
- Verified: shots read in all 8 matched views on both maps; no shader errors in godot.log; tests
  `test_world_look` 8/8, `test_graphics` 5/5, `test_kit` 6/6; full suite earlier in the session 387/390 with the
  3 failures being two music tests (music moved to assets/audio/86 by another session) and the Ultra MSAA test
  (updated to 4x since).
- Not verified: Windows/macOS export of the VRAM-compressed textures (project has s3tc and etc2 on, an export
  was not run); the look on the small map at dusk/night weathers.

## Scoreboard row (small map, score_look, Low / Medium / High, avg / low-1%)
Low 47.7 / 51.1, Medium 45.7 / 43.8, High 38.9 / 37.6 (images/430-score_look-medium). Earlier rows (125 / 73 / 54 at
B4 part 4) were before the native-resolution change (B5 part 6) and ran without the two wingmen (A5), so they do not
compare like for like; the row is the new baseline. Row in ~/Forge/docs/library/juggernaut/2026-10-01-eightysix-scoreboard.md.
