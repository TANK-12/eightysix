# PanelForge contracts

This is the shared agreement between the modules. The data formats and
endpoints below are the contract. A module may **add** fields and endpoints,
but must not rename or remove ones listed here without the commander's
agreement. Record every addition in your own `docs/crew/helper-N.md`.

## Ground rules (apply to every helper)

- **Animation, not video generation.** The movie modes animate the manga's own
  drawings. Panels are the key frames ("base frames"). Motion comes from
  animation techniques:
  - camera moves
  - layered cutouts and parallax
  - rigged, mesh-warped puppets
  - in-betweens between key drawings
  - effects layers: speed lines, particles, shake, light
  - rules, patterns and math

  Never use an image-to-video diffusion generator that invents the footage.
  AI is fine as a tool inside that process: segmentation, depth,
  interpolating between two real drawings, OCR, vision for understanding.
- **Hardware:** Intel Iris Xe, no CUDA, 31 GB RAM. Use CPU ONNX runtime or
  ncnn/Vulkan. Heavy jobs go through `panelforge.jobs` (one per lane) so the
  laptop stays usable. Overnight renders are fine.
- **Models:** download only through `panelforge.models.ensure(...)`, only from
  the project's official GitHub or Hugging Face source, and within the 15 GB
  total budget. Prefer small models. Every feature must still do something
  sensible with classical math/rules when its model is missing.
- **Jan** (127.0.0.1:1337) is shared live with other sessions. Never restart
  it. Use `shared/forge_jan.py` (`forge_jan.mount`, `jan.using(model)`).
  Models load on demand and unload when idle.
- **Emerson picks every voice.** Never auto-assign a voice to a character.
- **Never remove existing features** in other Forge apps. MediaForge changes
  are additive only.
- **Python:**
  - Python 3, stdlib-first. Run black, then
    `pyright --pythonpath ./.venv/bin/python <files>`.
  - Install only into `./.venv`, and serialise installs:
    `flock /tmp/panelforge-pip.lock .venv/bin/pip install X`.
  - List what you add in `docs/crew/helper-N.md`.
- **Tests:** in `tests/`, run with `.venv/bin/python -m pytest`. Use the real
  test chapter (below) for integration checks. Name tests after your area:
  `tests/test_<area>_*.py`.
- **No ALL-CAPS** in UI strings or log messages.
- **Leave a trail:** update your `docs/crew/helper-N.md` every few minutes
  with what's done, what's verified (with real output), what's next and what
  was added to the contract. A cut-off session must be resumable from it.
- Scratch servers run on free ports other than 8449 (Forge's own). Never
  use `pkill -f`.

## Test chapter

`~/PanelForgeData/series/bad-born-blood/chapters/0001/` is a webtoon: 166
strip pages of 800×1280 (one is 800×1241). They are hardlinked from
`testdata/bad-born-blood/ch001/`, and `chapter.json` is already written.
The pages are clean and in order (verified; see HANDOFF.md).

## Data layout

```
~/PanelForgeData/series/<series>/
  series.json      {schema, series, title, source{site,url}, format: "webtoon"|"manga"|"comic"}
  cast.json        (scene)  named cast, extras, voices chosen by Emerson
  assets/cast/<cast_id>/*.png   assets/extras/  assets/backgrounds/  assets/props/  assets/sfx/
  chapters/<chapter>/          chapter = paths.chapter_slug(number), e.g. "0001"
    pages/NNN.ext              original pages in reading order
    chapter.json   (library)
    strip.json     (detect)
    panels.json    (detect)
    bubbles.json   (detect)
    scene.json     (scene)
    script.json    (audio)
    timeline.json  (render)
    work/<area>/   each area's scratch and cache, safe to delete
    audio/  previews/  renders/
```

All JSON goes through `panelforge.store` (atomic writes) and carries
`"schema": 1`. Coordinates are integer pixels. `box` is always `[x, y, w, h]`.

### chapter.json (library)
```json
{"schema":1,"series":"bad-born-blood","chapter":"0001","number":1,"title":"Chapter 1",
 "source":{"site":"comix.to","url":"..."},"layout":"strip"|"pages","reading":"ttb"|"rtl"|"ltr",
 "pages":[{"idx":1,"file":"pages/001.webp","w":800,"h":1280,"sha1":"...","capture":"download"|"canvas-screenshot"|"import"}]}
```

### strip.json (detect)
Pages are stacked into one tall virtual strip. Panels and sprites that cross
page boundaries get joined here.
```json
{"schema":1,"width":800,"height":212000,
 "segments":[{"page_idx":1,"strip_y":0,"h":1280}]}
```

### panels.json (detect)
```json
{"schema":1,"panels":[{"id":"p0001","order":1,"box":[x,y,w,h],   // strip coordinates
  "kind":"panel"|"splash"|"caption-only"|"transition",
  "shape":"rect"|"slanted"|"borderless","polygon":[[x,y],...]|null,
  "image":"work/detect/panels/p0001.png",
  "edited":false}]}                                              // true once Emerson fixed it
```

### bubbles.json (detect)
```json
{"schema":1,"bubbles":[{"id":"b0001","panel_id":"p0001","order":1,"box":[x,y,w,h],   // strip coords
  "kind":"speech"|"thought"|"caption"|"shout"|"sfx"|"whisper",
  "text":"THIS WILL INCREASE MY WORTH!","ocr_conf":0.93,
  "tail":[x,y]|null,                       // point the tail aims at, if found
  "speaker":null|"<cast_id>"|"narrator",   // detect guesses, scene/editor refine
  "speaker_conf":0.0,"edited":false,
  "angle":0.0}]}                           // baseline tilt in degrees, downhill-to-the-right > 0 (2026-09-19)
```

### cast.json (scene, per series)
```json
{"schema":1,
 "cast":[{"id":"c01","name":"Luca","auto_name":"character 1","color":"#...",
   "samples":["assets/cast/c01/s1.png"],"embedding":"work/.. or null",
   "voice":null|{"kokoro":"am_michael","speed":1.0,"pitch":0,"gain_db":0},   // set only by Emerson
   "rig":null|"assets/cast/c01/rig.json","model3d":null}],
 "narrator":{"voice":null},
 "extras":[{"id":"x01","label":"soldier","samples":[...]}],
 "backgrounds":[{"id":"bg01","label":"training hall","image":"assets/backgrounds/bg01.png","panels":["p0003"]}],
 "props":[{"id":"pr01","label":"rifle","image":"..."}]}
```

### scene.json (scene, per chapter)
```json
{"schema":1,"panels":{"p0001":{
   "scene_id":"s01","location":"training hall","mood":"tense"|"calm"|"action"|"sad"|"comic"|"mystery",
   "action":0.0,                                   // 0..1 how much motion the panel implies
   "characters":[{"cast_id":"c01"|null,"extra_id":null,"box":[x,y,w,h],"face":[x,y,w,h]|null,
                  "facing":"left"|"right"|"front"|null,"cutout":"work/scene/cut/p0001_0.png"}],
   "background":"work/scene/bg/p0001.png"|null,    // characters and bubbles removed, holes filled
   "depth":"work/scene/depth/p0001.png"|null,      // 16-bit, near = bright
   "saliency":[[x,y,weight],...],                  // interest points, panel coordinates
   "sfx_text":[{"box":[..],"text":"CLANK"}],
   "speed_lines":{"present":true,"angle_deg":35}|null,
   "rigs":[{"char_index":0,"head":[x,y,w,h],"eyes":[[x,y,w,h],...],"mouth":[x,y,w,h]|null,
            "pivot_neck":[x,y],"pivot_hip":[x,y]|null}]}},     // for 2.5D puppets, panel coordinates
 "speakers":{"b0001":{"speaker":"c01","conf":0.7,"why":"tail points at face"}}}
```
The editor applies a speaker guess by writing `bubbles.json` through the detect
PUT endpoint. scene never writes `bubbles.json` itself.

### script.json (audio)
```json
{"schema":1,"lines":[{"id":"l0001","bubble_id":"b0001","speaker":"c01"|"narrator"|null,
   "text":"...","kind":"speech"|"thought"|"caption"|"shout"|"whisper",
   "emotion":{"speed":1.0,"gain_db":0,"pause_after":0.25,"reverb":0.0},
   "audio":"audio/l0001.wav"|null,"dur":1.84}],
 "sfx":[{"id":"x0001","panel_id":"p0003","source":"auto"|"user","sound":"library/sfx/clank.wav"|"synth:clank",
         "at":"panel-start"|0.4,"gain_db":0}],
 "music":[{"id":"m01","from_panel":"p0001","to_panel":"p0040","mood":"tense","track":"...","source":"auto"|"user","gain_db":-14}]}
```

Mixing hand-off: `panelforge/audio/mix.py` exposes
`mix_timeline(chapter_dir: Path, timeline: dict, out_wav: Path) -> Path`
(voices, SFX, music, 48 kHz stereo). render calls it and muxes the result with
ffmpeg. Until it exists, render produces silent video.

### Expression cues for voice acting (added 2026-09-17, Emerson)

Kokoro's delivery is driven by what the page shows. Added fields:

- **bubbles.json** (detect), per bubble:
  `"style":{"outline":"smooth"|"jagged"|"wobbly"|"dashed"|"cloud"|"rect"|"none",
  "text_scale":1.0, "stroke_weight":1.0, "italic":false, "wavy":false,
  "trembling":false, "color":"#000000", "bold_words":["NEVER"]}`.
  `text_scale` is letter height relative to the chapter median, and
  `stroke_weight` is letter thickness relative to the median. Large, heavy
  lettering means loud. Small text in a big balloon means quiet. Wavy or
  trembling lettering means weak or scared. Bold words get emphasis.
- **scene.json** (scene), per character:
  `"expression":{"label":"neutral"|"angry"|"happy"|"sad"|"scared"|"surprised"|"smug"|"pained"|"determined",
  "intensity":0..1,"conf":0..1}`. Per panel:
  `"acoustics":{"space":"small-room"|"hall"|"outdoor"|"vehicle"|"comms"|"void","size":0..1}`.
- **script.json** (audio), per line, `emotion` gains
  `"expression":"angry", "intensity":0.8, "room":"hall", "cues":["jagged outline","angry face"]`.
  Rules combine every cue: face expression, balloon shape, lettering,
  punctuation, scene mood and acoustics. The result maps to Kokoro speed,
  voice-style blending (Kokoro style vectors can be mixed), gain, pauses and
  numpy DSP: pitch shift, tremolo for fear, grit for shouting, breathiness,
  room reverb, and radio EQ for comms. Every cue is listed in `cues`, so the
  editor can show why a line sounds the way it does, and Emerson can
  override any of it.

### timeline.json (render)
```json
{"schema":1,
 "settings":{"aspect":"16:9"|"9:16","height":1080,"fps":30,"style":"motion",
   "bubbles":"keep"|"erase","subtitles":true,"mode":"panel-to-panel"|"page-reveal",
   "pace":1.0,"motion_strength":1.0,"transition":"auto","effects":1.0,
   "backdrop":"auto"|"blur"|"stretch"|"black"},
 "shots":[{"id":"t0001","panel_id":"p0001","start":0.0,"dur":3.2,"style":"motion"|null,
   "camera":{"keys":[{"t":0,"cx":0.5,"cy":0.5,"zoom":1.0,"rot":0}], "shake":0.0, "auto":true},
   "transition_in":{"kind":"cut"|"fade"|"slide"|"whip"|"zoom-through"|"match","dur":0.3,"auto":true},
   "lines":[{"line_id":"l0001","at":0.3}],"sfx":["x0001"],"edited":false}],
 "music":["m01"]}
```

## Endpoints

`{s}` is the series and `{c}` the chapter slug. Long work returns
`{"job_id": ...}`; poll `GET /api/jobs/{id}` (built into web_app.py; state,
progress and log).

- **library** (helper-1, `panelforge/api/library.py`)
  - `GET /api/series`, `GET /api/series/{s}`, `GET /api/series/{s}/chapters`
  - `POST /api/fetch/title {url}` → job, `result = {title, series, chapters:[{number,title,url}]}`
  - `POST /api/fetch/chapters {url | series, chapters:[numbers] | "all", group?}` → job
  - `POST /api/series/{s}/run {first, last | chapters, steps, group?, preview_voice?,
    cast?, render?, timeline?}` → job in lane "batch": fetch/detect/analyze run for
    every chapter first, then (when voice is a step and `cast` is not false) the
    model casts voices, then the remaining steps run chapter by chapter
  - `GET /api/sources` lists registered sites
  - `POST /api/import/path {path, series?, number?}` (folder, cbz, cbr, pdf) → job
  - `POST /api/import/upload` (multipart files) → job
  - `GET /api/mediaforge/downloads`, `POST /api/import/mediaforge {path}` → job
  - `POST /api/export/pdf {series, chapters:[..]|"all", preset:"kindle"|"full"}` → job, `result = {file}`
  - `GET /api/chapters/{s}/{c}/pages/{idx}` returns the image
- **detect** (helper-2, `panelforge/api/detect.py`)
  - `POST /api/chapters/{s}/{c}/detect` → job (strip, panels, bubbles, OCR)
  - `GET|PUT /api/chapters/{s}/{c}/panels`, `GET|PUT /api/chapters/{s}/{c}/bubbles`
  - `GET /api/chapters/{s}/{c}/panels/{pid}/image`
- **scene** (helper-3, `panelforge/api/scene.py`)
  - `POST /api/chapters/{s}/{c}/analyze` → job
  - `GET /api/chapters/{s}/{c}/scene`
  - `GET|PUT /api/series/{s}/cast` (name characters, merge or split clusters; voices set via audio)
  - `GET /api/series/{s}/assets/{kind}`
- **audio** (helper-4, `panelforge/api/audio.py`)
  - `GET /api/voices` lists Kokoro voices
  - `GET|PUT /api/sound {echo: none|comms|scene, sfx, music}` -- the sound
    policy (audio/policy.py): defaults dry voices, no auto sound effects, no
    auto music; hand-placed sound and hand-set rooms always play
  - `POST /api/voices/audition {voice, text, kind, speed}` returns wav bytes
  - `PUT /api/series/{s}/cast/{cast_id}/voice`, `PUT /api/series/{s}/narrator/voice`
  - `POST /api/series/{s}/cast/voices/auto {only?: [cast ids]}` → job (the model
    looks at each character's card pictures -- gender, age, timbre -- and gives
    everyone without a hand-chosen voice a distinct Kokoro voice, leads first;
    such a voice carries `source: "model"` and `why`; result `{described, voices}`)
  - `GET|PUT /api/chapters/{s}/{c}/script`
  - `GET /api/chapters/{s}/{c}/bubbles/{bid}/image` → JPEG of the balloon as
    drawn, cut from the strip with a 14 px margin (the Lines editor's crops)
  - `POST /api/chapters/{s}/{c}/script/build` → job (lines from bubbles, emotion rules)
  - `POST /api/chapters/{s}/{c}/script/llm {vision_only?, vision_all?}` → job (the app's Jan model reads the page:
    speakers where geometry was unsure, expressions where face and words gave none,
    delivery within the DSP limits, small OCR fixes; each verdict recorded on the line
    under `llm`; then the panel picture is shown for unsure speakers where two or
    more characters stand, verdict under `llm.vision_speaker`; starts Jan's router
    when none is running)
  - `POST /api/chapters/{s}/{c}/voice {preview_voice?, only_missing?}` → job (synthesise every
    line; `preview_voice` covers speakers with no voice chosen yet and is never
    written to cast.json)
  - `POST /api/chapters/{s}/{c}/lines/{line_id}/voice {voice?, speed?, pitch?,
    gain_db?, emotion?, text?}` → job (re-speak one line after an edit)
  - `POST /api/chapters/{s}/{c}/script/lines/{line_id}/emotion` (override the
    emotion the rules guessed)
  - `POST /api/chapters/{s}/{c}/audio/auto` → job (auto SFX and mood music)
  - `GET /api/sfx`, `GET /api/music` (library plus synth), `POST /api/sfx/audition`
- **render** (helper-5, `panelforge/api/render.py`)
  - `GET /api/styles`, `GET /api/transitions` (from the registries, with labels and settings schema)
  - `GET|PUT /api/chapters/{s}/{c}/timeline`
  - `POST /api/chapters/{s}/{c}/timeline/auto` → job (intelligent camera and transitions)
  - `POST /api/chapters/{s}/{c}/preview {kind:"styles", panels:[pid x5]}` → job, `result = {videos:{style: url}}`
  - `POST /api/chapters/{s}/{c}/preview {kind:"panel", panel_id, style?}` → job, `result = {video: url}` (about 10 s)
  - `POST /api/chapters/{s}/{c}/render {aspect, bubbles, style?, out_name?,
    height?, fps?, subtitles?, audio?, mode?, pace?, motion_strength?,
    transition?, effects?, backdrop?, shot_ids?, max_seconds?,
    style_settings?: {style: {knob: value}}}` → job,
    `result = {file, url, settings, probe, ...}`.
    `shot_ids` renders only those shots and `max_seconds` only the first so
    many seconds' worth from the start; neither rewrites `timeline.json`.
  - `POST /api/chapters/{s}/{c}/shots/{shot_id}/render {style?, preview?, height?}`
    → job, `result = {video, file, shot_id, probe}` (re-render one shot)
  - `GET /api/renders`
- Files under `~/PanelForgeData` are served at `/data/...`, e.g.
  `/data/series/{s}/chapters/{c}/renders/x.mp4`.

## Registries (one file plus one entry to extend)

- `panelforge/sources/` (helper-1): site fetchers, e.g. `comix.py` and the
  generic Chrome fetcher.
- `panelforge/styles/` (helper-5): `slideshow`, `motion`, `depth3d`,
  `puppet25d`, `inbetween`, with a `model3d` slot for later.
- `panelforge/transitions/` and `panelforge/camera/` (helper-5).
- `panelforge/sfx/` and `panelforge/music/` (helper-4): synth recipes and
  library adapters.

## Ownership

| helper | model | owns |
|---|---|---|
| commander | — | `web_app.py`, `panelforge/{paths,store,jobs,models,api_registry}.py`, `forge_app.json`, `CONTRACTS.md`, `HANDOFF.md`, `README.md`, `tests/test_foundation.py` |
| helper-1 | worker | `panelforge/library/`, `panelforge/sources/`, `panelforge/api/library.py`, `tools/`, `tests/test_library_*`, `~/Forge/shared/forge_mangafetch.py` (new), MediaForge manga section (additive) |
| helper-2 | deep | `panelforge/detect/`, `panelforge/api/detect.py`, `tests/test_detect_*` |
| helper-3 | deep | `panelforge/scene/`, `panelforge/api/scene.py`, `tests/test_scene_*` |
| helper-4 | worker | `panelforge/audio/`, `panelforge/sfx/`, `panelforge/music/`, `panelforge/api/audio.py`, `tests/test_audio_*` |
| helper-5 | deep | `panelforge/render/`, `panelforge/styles/`, `panelforge/camera/`, `panelforge/transitions/`, `panelforge/api/render.py`, `tests/test_render_*` |
| helper-6 | worker | `static/`, `tests/test_ui_*` |
