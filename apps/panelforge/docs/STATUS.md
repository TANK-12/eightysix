# PanelForge live status

Written automatically by `docs/status_snapshot.py` at 2026-09-17 22:57:29. Read `HANDOFF.md` first; this file only says how far the build got.

## Crew board

```
crew panelforge  commander: commander
goal: Build PanelForge: manga/webtoon chapters into voiced animated movies
members:
  commander (commander) seen 2.0h ago
  helper-1 (worker) seen 1.6h ago
  helper-2 (worker) seen 1.6h ago
  helper-3 (worker) seen 1.6h ago
  helper-4 (worker) seen 1.8h ago
  helper-5 (worker) seen 1.6h ago
  helper-6 (worker) seen 1.6h ago
  helper-7 (worker) seen 1.5h ago
  helper-8 (worker) seen 1.1h ago
  helper-9 (worker) seen 1.2h ago
tasks:
  1. taken [helper-1] library: fetch, import, kindle pdf, mediaforge link
  2. taken [helper-2] detect: strip, panels, bubbles, ocr
  3. taken [helper-3] scene: cast, extras, backgrounds, depth, cutouts
  4. done [helper-4] audio: kokoro voices, script, sfx, music -- Kokoro TTS wired, emotion rules, script build, 16 SFX recipes + fuzzy match, 6-mood generative music, mix_timeline, full API incl. new per-line re-speak + audition endpoints. 39 new tests pass, 69 total suite pass, black+pyright clean.
  5. taken [helper-5] render: styles, camera, transitions, previews, mp4
  6. taken [helper-6] ui: editor frontend
  7. taken [helper-7] render: depth3d cinematic style, render API, previews
  8. taken [helper-8] claude panel: two-account login switching that works
  9. done [helper-9] audio: expression-driven voice acting (cues to Kokoro delivery and DSP) -- Cue rules (face, outline, lettering, punctuation, mood, acoustics) -> script.json emotion with cues[]; numpy DSP (pitch shift, tremolo, grit, breath, rooms, radio, void); Kokoro style blending + bold-word segments; scene-aware script build keeping user emotions; POST .../script/lines/{id}/emotion. 380 audio tests, 472 full suite, black+pyright clean, real Kokoro run logged in docs/crew/helper-9.md.
```

## Files per area

- **library (helper-1)**: 10 files, 1219 lines
- **detect (helper-2)**: 13 files, 2302 lines
- **scene (helper-3)**: 14 files, 2658 lines
- **audio (helper-4)**: 16 files, 3019 lines
- **render (helper-5)**: 28 files, 3894 lines
- **ui (helper-6)**: 10 files, 3167 lines

Tests present: test_audio_cues.py, test_audio_dsp.py, test_audio_emotion.py, test_audio_line_emotion.py, test_audio_mix.py, test_audio_music.py, test_audio_preview.py, test_audio_script.py, test_audio_sfx.py, test_detect_pipeline.py, test_foundation.py, test_library_import.py, test_library_kindle.py, test_library_sources.py, test_library_verify.py, test_render_api.py, test_render_camera.py, test_render_depth3d.py, test_render_timeline.py, test_render_video.py, test_scene_cluster.py, test_scene_pipeline.py, test_scene_rig.py, test_scene_speakers.py, test_ui_static.py

## Helper logs (copied verbatim)

### helper-1
# helper-1: library (fetch, import, Kindle PDF, MediaForge link)

Priority order from commander (tight budget): 1) comix chapter fetch as a job
+ verify + chapter.json, 2) title -> chapter list -> fetch chosen chapters,
3) folder/CBZ/PDF import, 4) Kindle PDF export, 5) MediaForge button + shared
engine, 6) generic site fetcher, CBR, upload. Stop polishing past step 4 until
1-4 work.

## Done
- Reconnaissance: comix.to has no usable public JSON API (responses are
  client-side encrypted, field `"e": "..."`). Chapter list and reader page
  slots are scraped from the rendered DOM instead (same data the site's own
  JS uses). Chapter list is paginated (`.npager__num`, "Showing X to Y of N
  items"); the toolbar has a numeric chapter search box
  (`.mchap-search input`) used to confirm chapter 2's URL:
  `https://comix.to/title/3nlg-bad-born-blood/5835700-chapter-2` (WebToon
  scan group, same group as chapter 1's `5835641-chapter-1`).
- `/home/ejb/Forge/shared/forge_mangafetch.py` written: `ChromeCDP` (headless
  Flatpak Chrome over CDP, stdlib + websocket-client only),
  `capture_canvas_stable` (clipped screenshot, stability + non-blank check,
  the HANDOFF.md rule), `download_image`, `sniff_ext`, `verify_page_bytes`
  (decode/dims/blank), `seam_score` (neighbour brightness-jump check).
- `panelforge/sources/__init__.py`: registry (`comix`, `generic`),
  `find_for_url`, `get`, `list_sources`.
- `panelforge/sources/comix.py`: `fetch_title` (paginate the chapters list,
  dedupe by chapter number), `fetch_chapter` (two full passes over
  `.rpage-page[data-page=N]`, plain `<img>` downloaded with Referer, `<canvas>`
  captured via `capture_canvas_stable`, each page run through
  `verify_page_bytes` before being accepted).
- `panelforge/sources/generic.py`: MediaForge-style scroll-collect fetcher,
  DOM order, two passes (download once, retry failures). Built already
  (low cost, shares the same driver) even though it's step 6 -- not yet
  tested live.
- `panelforge/library/verify.py`: `verify_chapter_pages` (per-page checks +
  cross-page seam check).
- `panelforge/library/fetch.py`: `fetch_title`, `fetch_one_chapter`,
  `fetch_chapters` -- writes `series.json`/`chapter.json` per CONTRACTS.

## Next (in priority order)
1. `panelforge/api/library.py`: wire `/api/fetch/title`, `/api/fetch/chapters`
   as jobs on lane `net`, `/api/series*`, `/api/sources`.
2. Live check: fetch *Bad Born Blood* chapter 2 into `~/PanelForgeData` via
   the job endpoint (not the CLI prototype), verify (contact sheet, decode,
   count, scrambled pages clean). Do NOT refetch chapter 1.
3. `panelforge/library/importers.py`: folder, CBZ, PDF (pymupdf is in venv).
4. `panelforge/library/kindle.py`: export preset, split tall strip at blank
   gutter rows; `full` preset unmodified pages; bookmarks per chapter.
5. Checkpoint doc, then only if budget remains: CBR (unrar/7z/bsdtar are all
   on the system -- no need to report missing), multipart upload,
   MediaForge link (additive, needs a file claim on the shared board first).

## Contract additions
- `chapter.json` pages: `capture` is one of `"download"|"canvas-screenshot"|"import"`
  as specified. No renamed/removed fields yet.

## Checkpoint 2026-09-17 (budget relaxed by Emerson -- full quality, no corner-cutting; keep checkpointing)
- `panelforge/library/importers.py` written: `import_folder`, `import_cbz`,
  `import_cbr` (unrar/7z/bsdtar all present, picks whichever exists),
  `import_pdf` (pymupdf, 200dpi rasterise), `import_path` (dispatch by
  extension), `import_upload` (multipart bytes). All go through
  `_write_chapter` -> same `verify_chapter_pages` as fetch, `capture:"import"`.
- `panelforge/library/kindle.py` written: `split_kindle` (numpy row-stddev,
  cuts at the blank row nearest each Kindle-aspect (1072/1448) target height,
  falls back to a hard cut if no blank row found), `export_pdf` (pymupdf,
  builds one PDF page per slice/page, `set_toc` bookmarks per chapter),
  `resolve_chapters` ("all" or a number/slug list).
- `panelforge/library/mediaforge_link.py` written: `list_downloads` (walks
  `~/Downloads/MediaForge/<title>/<chapter or .pdf/.cbz>`),
  `import_from_mediaforge` (routes into `importers.import_path`). MediaForge's
  own files not yet touched -- this only reads its output folder.
- `panelforge/api/library.py` written: every CONTRACTS.md "library" endpoint
  (`/api/series*`, `/api/sources`, `/api/fetch/title`, `/api/fetch/chapters`,
  `/api/import/path`, `/api/import/upload`, `/api/mediaforge/downloads`,
  `/api/import/mediaforge`, `/api/export/pdf`, `/api/chapters/{s}/{c}/pages/{idx}`).
  All fetch/import/export run as `panelforge.jobs` (fetch on lane `net`,
  import/export on lane `cpu`).
- Tests: `tests/test_library_verify.py` (9), `tests/test_library_sources.py`
  (6, fake in-process source, no network), `tests/test_library_import.py` (5,
  synthetic CBZ/PDF/folder), `tests/test_library_kindle.py` (6, synthetic
  strip with real blank gutters -- asserts every cut lands inside a gutter
  band, plus a no-gutter fallback case and a real multi-chapter PDF+TOC
  check). **23 library tests + the existing 61 = 84 total, all passing.**
  Real output: `.venv/bin/python -m pytest tests/ -q` -> `84 passed`.
- `black` run on every touched file (11 reformatted, applied cleanly).
  `pyright --pythonpath ./.venv/bin/python panelforge/sources/
  panelforge/library/ panelforge/api/library.py
  /home/ejb/Forge/shared/forge_mangafetch.py` -> **0 errors**. Fixed along the
  way: module typing in `sources/__init__.py` (`ModuleType` instead of
  `object`), an `Optional[str]` narrowing in `fetch.py`, and pymupdf
  `Document` not being `Iterable` for `enumerate()` in `importers.py` (switched
  to `range(doc.page_count)`).
- `tests/test_foundation.py::test_app_health` (existing, not owned by me)
  passes with `library.py` mounted -- confirms the router imports cleanly
  into the whole FastAPI app, not just standalone.
- Also replaced `Image.getdata()` (deprecated in Pillow 14) in
  `forge_mangafetch.seam_score` with `tobytes()` + mean -- stdlib-plus-Pillow
  only, no new dependency.

## Next
- Live check (not yet done): fetch *Bad Born Blood* chapter 2 via the real
  `/api/fetch/chapters` job path (not the CLI prototype) into
  `~/PanelForgeData`, verify with a contact sheet. Chapter 2 URL confirmed by
  hand: `https://comix.to/title/3nlg-bad-born-blood/5835700-chapter-2`
  (WebToon scan group, same group as chapter 1). Do NOT refetch chapter 1.
- Export chapter 1 as a Kindle PDF via the real job endpoint and look at 2-3
  rendered pages.
- Then (lower priority per commander, budget allowing): MediaForge additive
  integration (claim its files on the board first), generic-source live
  exercise against a real non-comix site.

## Open risk
- `panelforge/sources/comix.py` and `generic.py` are unexercised against the
  live site as jobs (only ad-hoc CDP probes so far, run outside pytest, in
  `/tmp/.../scratchpad/`). First live job run is the next step and is the
  real check for "always two passes" and canvas capture working end to end.

### helper-2
# helper-2: detect (strip, panels, bubbles, OCR)

Crew `panelforge`, owner of `panelforge/detect/`, `panelforge/api/detect.py`,
`tests/test_detect_*`, this file.

## Status (2026-09-17)

- **v0 rough output written** for chapter 0001 (other helpers can start):
  `strip.json`, `panels.json` (138 panels), crops in `work/detect/panels/`
  (101 MB of PNG). Rough: some tall "splash" panels are really several panels,
  some caption kinds are wrong. `bubbles.json` not yet written.
- Not yet: bubbles/OCR, API, job, tests, accuracy numbers.

## Contract additions

- `strip.json` segments carry `file` (page file relative to the chapter).
- `panels.json` panels carry `art_box` [x,y,w,h]: the drawing alone; `box` also
  includes balloons and sound words in the gutter that belong to the panel.

### helper-3
# helper-3: scene (cast, extras, backgrounds, depth, cutouts, rigs, speakers)

Status: started 2026-09-17. Owned: `panelforge/scene/`, `panelforge/api/scene.py`,
`tests/test_scene_*`, this file.

## Done
- Read CONTRACTS, HANDOFF, foundation modules, forge_jan.
- Candidate models checked on Hugging Face (file lists and sizes read from the HF API).
- Jan is not running right now (`forge_jan.models()` returned `[]`), so the Jan
  mood step must fall back to rules.

## Priority order (commander, budget is tight)
1. scene.json per panel: characters (boxes, faces), saliency, mood/action, speed lines
2. depth maps  3. cast.json clustering + PUT rename/merge + speakers
4. cutouts + inpainted backgrounds  5. rigs, extras, props, SFX lettering

## Written so far (code exists)
- `scene/registry.py` (model list + cached sessions, env PANELFORGE_SCENE_MODELS=off)
- `scene/geom.py`, `scene/cluster.py` (average linkage + cannot-link, purity),
  `scene/speakers.py` (rules), `scene/rig.py` (rig boxes + facing),
  `scene/imaging.py` (saliency, speed lines, colour, grabcut, balloons, inpaint,
  heuristic depth), `scene/detectors.py` (YOLO person/face, anime-seg, CCIP, depth)
- tests: test_scene_cluster.py, test_scene_speakers.py, test_scene_rig.py

## Verified
- 17 unit tests pass (cluster sweep over 40 random worlds, tail-angle sweep,
  3000-shape rig invariant sweep).
- Face detector on every 3rd page (56 pages): 18 faces on 11 pages, all 14 crops
  looked at are real faces (precision good, recall low on this realistic style).
- Timings per 800x1280 page on CPU: face 0.3 s, anime-seg 1.5 s, depth 1.4 s.

## Models (downloaded 2026-09-17 via models.ensure, ~443 MB total)
| key | repo / file | size |
|---|---|---|
| person | deepghs/anime_person_detection person_detect_v1.3_s/model.onnx | 44.6 MB |
| face | deepghs/anime_face_detection face_detect_v1.4_s/model.onnx | 44.6 MB |
| seg | skytnt/anime-seg isnetis.onnx | 176 MB |
| ccip | deepghs/ccip_onnx ccip-caformer-24-randaug-pruned/model_feat.onnx | 150 MB |
| depth | onnx-community/depth-anything-v2-small onnx/model_int8.onnx | 27 MB |

## Next
Build scene package, tests, integration run on 30+ panels, contact sheets.

## Contract additions
(none yet)

### helper-4
# helper-4: audio

## Done (implemented, not yet all test-verified -- see below)
- `panelforge/audio/dsp.py`: numpy DSP toolkit (resample, gain, FFT low-pass,
  echo, fade, soft limiter, mix_into, sidechain duck, crossfade_concat,
  wav read/write). 48kHz stereo throughout.
- `panelforge/audio/kokoro_engine.py`: loads kokoro-onnx pointed at
  `~/NovelMakerData/tts_voices/{kokoro-v1.0.onnx,voices-v1.0.bin}` -- same
  files and package NovelForge uses (novelforge/audiobook.py). Verified: the
  model loads in 0.7s and lists 26+ voice names (af_*, am_*, bf_*, bm_*, ...).
- `panelforge/audio/voices.py`: parses Kokoro's `xy_name` convention into
  language/gender labels for `GET /api/voices`.
- `panelforge/audio/emotion.py`: punctuation/kind -> emotion rules (!, ...,
  ?, whisper, thought, ALL-CAPS normalization).
- `panelforge/audio/script.py`: build_script(bubbles_doc, existing) -- skips
  sfx bubbles, captions -> narrator, keeps edited lines on rebuild.
- `panelforge/audio/cache.py` + `mix.py` (mix_timeline, written early per
  the commander's priority order -- render depends on it).
- `panelforge/sfx/recipes.py` + `match.py` + `library.py`: 16 procedural
  recipes (clank, boom, blam, bang, ratatata, whoosh, fsssh, clap, ting,
  slash, stomp, lunge, glow_hum, crash, footsteps, thud), fuzzy onomatopoeia
  matching with repeated-letter -> stretch/repeat, ffmpeg-backed user library.
- `panelforge/music/generate.py` + `library.py`: 6 moods (tense, calm,
  action, sad, comic, mystery), scale+chords+pad+percussion, seamless loop
  via continuation-crossfade, `tile_to_length`, `crossfade_moods`.
- `panelforge/api/audio.py`: all contract endpoints plus the new
  per-line re-speak and audition endpoints (see "Contract additions" below).

## Contract additions (new requirements from the commander mid-task)
- `POST /api/chapters/{s}/{c}/lines/{line_id}/voice` -- body
  `{voice?, speed?, pitch?, gain_db?, emotion?, text?}`, resynthesises one
  line, stores the override on `script.json` lines[] as `voice_override`
  and sets `edited: true`. Wins over the cast voice in the bulk voice job.
- script.json `sfx[]`/`music[]` entries: `edited: true` is now also
  respected alongside `source: "user"` -- the auto job never touches either.
- `POST /api/sfx/audition {sound, params?}`, `POST /api/music/audition
  {mood?|track?, seconds?}`.

## Status: DONE and verified

- `pip install kokoro-onnx` into this app's `.venv` (serialised with the
  pip lock per CONTRACTS.md).
- `tests/test_audio_{emotion,script,sfx,music,mix}.py`: 39 tests, all pass.
  Full app suite (`pytest -q`, 69 tests) also passes -- no regressions in
  other helpers' areas.
- `black` run on every file I touched; `pyright --pythonpath ./.venv/bin/python`
  clean (0 errors) on all of them.
- Real check (no fixture, no mock): synthesised 3 real lines, 2 Kokoro
  voices, one thought line, through `kokoro_engine.synthesize` +
  `emotion.apply` + `dsp.limiter`:
  ```
  voice=am_michael kind=speech  dur=2.73s peak=0.684 text="We need to move now, the whole street's coming down!"
  voice=af_heart   kind=speech  dur=2.15s peak=0.510 text="I told you this would happen someday..."
  voice=af_heart   kind=thought dur=1.30s peak=0.411 text="He never listens to me."
  ```
  All non-silent, all under the 0.98 limiter ceiling, no clipping.
- Also drove the real FastAPI app (`web_app.app` via `TestClient`):
  `/api/health` loads `panelforge.api.audio` cleanly; `/api/voices` lists
  54 voices with language/gender labels; `/api/voices/audition` returns a
  258KB wav for a real line.

## Left undone / notes for whoever wires things up next
- `mix_timeline`'s SFX/music placement assumes helper-5's timeline.json
  shots have `panel_id`, `start`, `dur`, `lines:[{line_id,at}]`, `sfx:[id]`,
  and a top-level `music:[id]` list, per CONTRACTS.md. Not yet exercised
  against a real timeline.json from helper-5 -- only the fixture in
  `test_audio_mix.py`.
- `audio/auto`'s mood-from-scene fallback (no scene.json yet) is a coarse
  heuristic (shout->action, whisper->mystery, else calm) from bubble kinds
  only; once scene.json's real `mood` field is populated by helper-3 it
  takes over automatically (scene.json branch is preferred and already
  wired).
- The "?" pitch lift is an approximation (a small pre-emphasis brightness
  filter), not a true pitch shift -- Kokoro has no pitch knob and a real
  time-preserving shift needs a phase vocoder; documented in
  `panelforge/audio/dsp.py::pre_emphasis_lift`.
- Not built: an actual UI audition player (that's helper-6's `static/`).
- SFX/music library folders (`~/PanelForgeData/library/{sfx,music}/`) are
  empty on this machine -- loader code is written and covered by not-found
  error handling, but not exercised against a real user file (no such file
  exists yet to test with).

Files: `panelforge/audio/{__init__,dsp,kokoro_engine,voices,emotion,cache,script,mix}.py`,
`panelforge/sfx/{__init__,recipes,match,library}.py`,
`panelforge/music/{__init__,generate,library}.py`,
`panelforge/api/audio.py`,
`tests/test_audio_{emotion,script,sfx,music,mix,preview}.py`.

## Contract addition #2: preview_voice (Emerson, rough-movie preview)
`POST /api/chapters/{s}/{c}/voice` now accepts an optional body
`{"preview_voice": "<kokoro id>"}`. It's used only for lines whose speaker
has no voice set (cast or narrator); real voices always win. Never written
to cast.json, never stored as a line's `voice_override` (so once Emerson
picks a real voice and reruns the job, the preview audio is naturally
replaced -- the cache key differs by voice id). Job result now also reports
`"previewed": <count>`. Verified: `tests/test_audio_preview.py` (2 tests,
Kokoro monkeypatched for speed) plus a manual TestClient run confirming
cast.json is never created by a preview-only run. 86 tests total pass,
black+pyright clean.

### helper-5
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

### helper-6
_no log yet_

