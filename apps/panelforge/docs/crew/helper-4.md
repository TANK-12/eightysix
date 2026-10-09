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
