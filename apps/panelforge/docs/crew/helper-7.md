# helper-7: render (depth3d cinematic style, render API, previews)

Status: paused by the commander at the end of session 1 (2026-09-17 21:45).
Chunks 1 and 2 are done and verified; chunk 3's real layered check waits for
scene.json. Takes over from helper-5's chunks 3-4 (helper-5 was cut off
after chunks 1-2).

## Plan (chunks)
1. `styles/depth3d.py`: layered 2.5D style. Background warped by its depth map
   under the camera move (single cv2.remap with a depth-driven displacement),
   character cutouts as separate layers at their own mean depth, feathered
   edges, depth of field toward the focus depth (speaker or nearest saliency
   point of the current camera key), haze by depth, vignette, mood grade,
   bubbles composited back in "keep" mode, heuristic depth fallback when
   scene data is missing. Per-shot layer cache in `ctx.cache`.
   Tests: `tests/test_render_depth3d.py` (synthetic chapter, temp data dir).
2. `api/render.py`: the render endpoints from CONTRACTS plus the per-shot
   re-render. Tests: `tests/test_render_api.py` (TestClient, temp
   `PANELFORGE_DATA`).
3. Real check on chapter 0001 once `scene.json` exists: 3-4 panels in depth3d
   at preview scale, frames to `docs/crew/helper-7-frames/`, look and iterate.
4. Full suite, black, pyright, `crew done`.

## Done
(nothing yet)

## Verified
- Baseline before any change: `.venv/bin/python -m pytest -q` -> 110 passed.

## Contract additions
- `POST /api/chapters/{s}/{c}/shots/{shot_id}/render {style?, preview?}` -> job,
  `result = {video: url}` (kept from helper-5's plan).


## Chunk 1 done (depth3d)
- `panelforge/styles/depth3d.py`: real style (layered remap parallax, character
  layers, DoF, haze, vignette, mood grade LUT, bubbles keep, heuristic fallback).
- `panelforge/render/effects.py`: `_alpha_blend` and `light_glow` now blend on
  contiguous uint8 through `cv2.blendLinear` (was float conversions through
  strided BGRA views; 44 ms -> about 7 ms per effect at 1080p).
- `panelforge/render/fixture.py`: `add_scene_layers(ch)` writes bg/depth/cutouts
  for the synthetic chapter (characters and bubbles painted out of bg).
- Verified: `tests/test_render_depth3d.py` 12 passed; black + pyright clean.
- Timing (machine loaded by another session's scene rebuild, load avg 4.7):
  depth3d render about 46 ms per 1080p frame in the profile, 14 ms at 640x360;
  whole body incl. effects 125-175 ms at 1080p under that load. Re-measure idle.

## Chunk 2 done (render API)
- `panelforge/api/render.py`: `GET /api/styles`, `GET /api/transitions`,
  `GET|PUT .../timeline` (PUT through `timeline.apply_put`, 400 on
  TimelineError), `POST .../timeline/auto` -> job, `POST .../preview`
  (`kind: styles` -> `{videos:{style:url}, grid:url}` via `encode.hstack_grid`;
  `kind: panel` -> `{video, file, probe}`), `POST .../shots/{id}/render` -> job
  `{video}`, `POST .../render {aspect, bubbles, style?, out_name?}` -> job
  `{file, url, ...stats}`, `GET /api/renders`. All jobs run in lane "render".
  Optional `height`/`fps` on preview/render bodies (tests use 90p/8fps).
- Verified: `tests/test_render_api.py` 5 passed (TestClient on a temporary
  `PANELFORGE_DATA`; asserts `paths.DATA_ROOT == tmp_path`), `/api/health`
  lists `panelforge.api.render` in `modules`.
- Full suite: `.venv/bin/python -m pytest -q` -> 472 passed. black and pyright
  clean on: styles/depth3d.py, render/effects.py, render/fixture.py,
  api/render.py, tests/test_render_depth3d.py, tests/test_render_api.py.

## Chunk 3: partly done (real check)
- `scene.json` for bad-born-blood/0001 did not exist by 21:43 (panels.json and
  bubbles.json did: 123 panels). Ran the fallback path on real panels p0004,
  p0009, p0016 at 640x360: frames in `docs/crew/helper-7-frames/fallback-*.jpg`
  (each pair = t=0.3 s and t=0.9*dur). Looked at p0009: warm action grade,
  embers, vignette, camera rotation, panel edge stays crisp. 56-122 ms per
  frame on the loaded machine (another session's scene rebuild at 4.5 cores).
- Not done: the layered (bg + depth + cutouts) look on real panels, and any
  iteration on it. The synthetic layered render was looked at (contact sheet
  in the session scratchpad): characters float in front, bubbles crisp.

## Next (for a fresh session)
1. Poll for `~/PanelForgeData/series/bad-born-blood/chapters/0001/scene.json`;
   then render 3-4 panels that have `background`, `depth` and cutouts with
   style depth3d at 360p (`render_timeline(..., preview=True)` or the
   `/preview {kind:"panel"}` endpoint), pull frames with ffmpeg into
   `docs/crew/helper-7-frames/`, and judge: parallax visible, cutout edges
   clean, DoF not too strong, grade subtle. Tune `HAZE_COLORS`, `MOOD_GRADES`,
   the 0.35 pan gain and 0.6 dolly gain in `Depth3D.render`.
2. Re-measure 1080p frame cost on an idle machine (target under 100 ms incl.
   effects; profile showed depth3d about 46 ms + effects about 35 ms).
3. `crew done panelforge helper-7 7 --note "..."` once step 1 looks right.

## Design notes
- Parallax is one `cv2.remap`: for each output pixel, sample the background at
  the inverse camera transform of (pixel - (depth - focus) * (pan + dolly
  radial)). Maps are computed at half resolution and resized. Inside the
  panel silhouette the sample point is clamped into the panel so the border
  stays rigid; outside it stays transparent over the backdrop.
- Characters: per-layer affine (`_layer_matrix`) = camera matrix, scaled about
  the frame centre by 1 + (d - focus) * lz and shifted by (d - focus) * pan;
  drawn far to near into their destination box only.
- Focus: speaker layer depth during a line, else the depth under the saliency
  point nearest the camera key (or the view centre); 7-sample 0.35 s average.
- Fallback rule: layered only when the scene bg exists and every character
  with a box has an RGBA cutout file; otherwise the whole panel is one layer
  (strength 0.6 with a real depth map, 0.45 with the heuristic one).
- Whole pipeline stays uint8 BGR through `cv2.blendLinear` / `cv2.multiply`
  / `cv2.LUT`; BGRA is assembled once at the end.
