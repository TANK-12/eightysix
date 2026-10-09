# helper-9: expression-driven voice acting (task 9)

Owner of `panelforge/audio/{emotion,dsp,kokoro_engine,script,voices}.py`,
`panelforge/api/audio.py`, `tests/test_audio_{cues,dsp,line_emotion,script}.py`.
Status: done 2026-09-17 (stopped at Emerson's session end; nothing half-done).

## Design decision
Rules are additive registries in `emotion.py` (EXPRESSIONS, OUTLINES, MOODS,
SPACES): each cue adds a delta to speed/gain/pause/reverb/pitch/tremolo/
grit/breath, face deltas scale linearly with detected intensity, the whole
sum is clamped (speed 0.6..1.8, gain -14..+8 dB, pitch +-4 st, tremolo
<= 0.75, grit <= 0.7). Every cue that fires is named in `cues[]`. A line
with no page cues produces exactly the old punctuation-only values and
`apply` on it is the identity (test proves bit-identity), so nothing already
voiced changes character. Thought bubbles and cloud outlines get the inner
voice (`room: void, eq: void`) regardless of the panel's acoustics.
Kokoro: speed plus a style-vector blend (chosen voice >= 75%, partner from
`voices.BLEND_PARTNERS` by prefix and tone; the voice id never changes).
Bold words split the line into segments (bold: 0.85x speed, +2.5 dB), joined
with 15 ms linear crossfades; a line without bold words is one call.

## Done
- `dsp.py`: pitch_shift (vectorised phase vocoder + resample, length
  preserving), time_stretch, tremolo, grit, breath (envelope-gated noise),
  room_reverb + ROOMS registry (small-room, hall, outdoor, vehicle, comms,
  void; synthetic IR, FFT convolution), radio_eq, void_voice, bandpass,
  join_crossfade. All identity at amount 0.
- `emotion.py`: `rules_for(text, kind, ctx)`; output gains expression,
  intensity, room, cues, pitch, tremolo, grit, breath, eq, blend, emphasis,
  source. `segments_for(text, emphasis)`. `apply` renders the new knobs;
  a legacy dict without `room` takes the old thought-echo path unchanged.
- `voices.py`: BLEND_PARTNERS registry + `blend_partner`.
- `kokoro_engine.py`: `synthesize(..., style=)`, `style_vector(voice, blend)`,
  `synthesize_line(text, voice, em)` (blend + bold segments).
- `script.py`: `build_script(bubbles, existing, scene)` reads the speaker's
  face in the panel, mood, action, acoustics, bubble style, balloon size vs
  chapter median; speaker falls back to scene.json `speakers`; `edited`
  lines carried whole; `emotion.source == "user"` emotions kept while text
  follows the bubble (audio cleared only when text changed). `line_context`.
- `api/audio.py`: script/build passes scene.json; `_synth_line` and the
  audition endpoint go through `synthesize_line`; cast voice `pitch` now
  actually reaches the DSP; new `POST .../script/lines/{id}/emotion`.

## Verified with real output
- `.venv/bin/python -m pytest -q tests/test_audio_*.py` -> 380 passed.
  Includes a 15,435-combination sweep (faces x outlines x moods x spaces x
  kinds x 3 intensities) checking bounds and cue names, and a per-face
  monotonic check over 11 intensities x 5 kinds x 7 outlines.
- Full suite `pytest -q` -> 472 passed (one earlier run showed
  test_render_api::test_registries failing with KeyError 'name' while
  helper-7 was editing render files; it passed on rerun and alone).
- black: 9 files reformatted; pyright on all touched files: 0 errors.
- Real Kokoro run (8 lines, wavs written to the scratchpad, then removed):
  ```
  neutral                 am_michael dur=2.01s peak=0.598 speed=1.0   gain=0    blend=none
  angry-jagged-hall       am_michael dur=1.54s peak=0.868 speed=1.356 gain=8.0  pitch=-0.9 grit=0.7 room=hall blend=dark 0.225
  scared-wobbly-trembling af_heart   dur=2.82s peak=0.180 speed=0.859 gain=-2.3 pitch=2.1 trem=0.75 breath=0.54 room=small-room blend=soft 0.2
  sad-small-text          af_heart   dur=2.24s peak=0.218 speed=0.827 gain=-6.4 pitch=-1.05 breath=0.375 room=outdoor blend=soft 0.175
  comms-determined        bm_george  dur=2.45s peak=0.532 speed=1.088 gain=2.2  grit=0.19 eq=radio blend=dark 0.15
  thought-happy           af_bella   dur=2.24s peak=0.532 speed=1.03  gain=-2.4 pitch=0.9 room=void eq=void blend=bright 0.15
  whisper-dashed          bf_emma    dur=2.65s peak=0.189 speed=0.921 gain=-10  breath=0.3 room=small-room
  bold-words-surprised    am_puck    dur=2.55s peak=0.888 speed=1.04  gain=2.1  pitch=2.0 segments=3 blend=bright 0.2
  ```
  All peaks under the 0.98 limiter ceiling; blends active wherever asked.
  Not verified by ear (no listening in this session).

## Next / left undone
- Nobody has listened to the result yet; the numbers are gentle but the
  face deltas in EXPRESSIONS are a first guess to tune by ear.
- The editor (helper-6) can show `emotion.cues` and call the new endpoint;
  no UI was built here.
- Synthesis cache keys include the full emotion dict, so every existing
  cached line re-synthesises once after this change.

## Contract additions
- script.json `emotion` also carries `pitch` (semitones), `tremolo`, `grit`,
  `breath` (0..1), `eq` (null|radio|vehicle|void), `blend`
  ({tone: bright|dark|soft, weight <= 0.25} | null), `emphasis` (bold words,
  lower-case), `lift` (bool, from "?"), `source` ("auto"|"user"), on top of
  the contract's expression/intensity/room/cues.
- `POST /api/chapters/{s}/{c}/script/lines/{line_id}/emotion` body: any of
  expression, intensity, room (re-run the rules with that cue replaced),
  speed, gain_db, pause_after, reverb, pitch, tremolo, grit, breath, eq
  ("none" clears), blend, emphasis (set directly), `reset: true` (back to
  automatic), `speak: false` (store only). Sets `emotion.source = "user"`,
  appends a "set by hand: ..." cue, re-speaks when a voice is available,
  returns `{line, spoken}`. 400 on unknown expression/room/eq, 404 on line.
- `build_script` now takes scene.json as a third argument; the build job
  reads it when present and logs when it is missing.
