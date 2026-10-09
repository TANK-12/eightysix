# helper-5: render (styles, camera, transitions, previews, mp4)

Status: in progress (session 1, 2026-09-17).

## Plan (chunks)
1. camera/ (view math, rules engine), transitions/ registry, timeline auto builder + tests
2. render/ inputs (fixture panels when panels.json is missing), context, encode (ffmpeg, vaapi), renderer with per-shot cache, styles slideshow + motion, effects, subtitles/erase + tiny mp4 test
3. styles depth3d, puppet25d, inbetween (flow morph + RIFE), model3d slot
4. api/render.py (incl. per-shot render from coordinator), previews, real checks on the test chapter

## Done
(nothing yet)

## Verified
(nothing yet)

## Contract additions
- `POST /api/chapters/{s}/{c}/shots/{shot_id}/render {style?, preview}` (coordinator request)

## Next
chunk 1
