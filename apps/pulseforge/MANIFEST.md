# PulseForge — manifest

_Written 2026-09-07 for a reader with no conversation history. The machine-
readable version is the `manifest` block in `forge_app.json`._

## What this is

PulseForge turns songs into YouTube-ready videos. Two things it makes:

**Living stills** (the main one). A background — a still image **or a looping
video clip** — that mostly holds still while the parts you mark move — clouds crossing the sky, water rippling, hair
swaying — under a slow camera drift, with birds, rain, fireflies or your own
sprites drifting through. Several backgrounds and several songs run together as
one long mix with transitions between them and a caption per track. This is the
"lofi radio" format, and it is built in the **Scenery** tab.

**Beat-cut visualisers and AMVs.** Spectrum bars, sprite swarms, or a folder of
video clips cut to the song's beat with motion matched to its energy.

Either way it analyses the music, renders, muxes the song back in
loudness-normalised, and writes an MP4 you upload yourself. No hosting, no
account, just a file.

Runs on **port 8436** in Forge (`order` 9). It began life in this session.

## Architecture

Almost everything is an ffmpeg job. `analyze.py` decodes the audio to numpy and
builds a per-frame feature track (energy, 12 log-spaced bands, sub-bass,
spectral centroid, onset strength, a debounced beat flag) — the band split and
beat picker are ported from Arcade's audio code, no librosa. A **scene** is one
file in `pulseforge/scenes/` that either yields RGB frames from those features
(vectorised numpy / Pillow at an internal ≤1080p buffer, which is why 4K output
stays feasible on a CPU-only laptop) or, for montage, returns an edit decision
list. `render.py` pipes frames to ffmpeg, which scales, muxes, `loudnorm`s and
encodes h264 + AAC + faststart.

**The living pipeline works differently, and the difference is the point.**
Every moving thing in a living shot takes its phase from a `LoopClock`, which
snaps any requested period to a whole number of cycles inside the shot's loop.
A shot is therefore *bit-identical* at `t=0` and `t=loop_seconds`. That means
the renderer computes **one loop** of numpy frames — a few hundred — and lets
ffmpeg repeat that bed for as long as the shot holds. An hour-long mix over four
backgrounds costs four short renders rather than a hundred thousand frames, and
the loops are genuinely seamless rather than approximately so. A shot set to
"live" opts out and renders every frame, for when the picture should react to
that moment in the song.

**Three registries drive everything.** Adding a region effect, an emitter or a
preset is one file (or one entry) plus one line in its registry table — the API,
the editor's pickers and every parameter control are generated from it:

| Registry | Where | What |
|---|---|---|
| Motion effects | `pulseforge/motion/` | What a marked region *does* (13) |
| Emitters | `pulseforge/emitters/` | Particles and creatures drifting through (11) |
| Presets | `pulseforge/presets.py` + `~/PulseForgeData/presets/` | Whole looks, built-in and your own |
| Film grades | `pulseforge/grades.py` | Whole colour looks (9) |
| Ambience | `pulseforge/ambience.py` | Generated sound beds (5) |

**Any numeric parameter can move.** A value may be
`{base, mod, amount, period, shape}` rather than a number; `modulation.py`
resolves it inside `merge_params()`, the one place every effect and emitter
already goes through. An LFO source runs off the `LoopClock` so a modulated
parameter keeps the seam bit-identical; audio sources need the shot in live
mode, and the editor says so on the control.

## The AMV studio (v8)

Four modules, each a registry or a measurement layer, and none of them knows
about the others' internals:

| File | What it is |
|---|---|
| `musicmap.py` | What the song is *doing*: tempo (autocorrelation under a log-normal prior), a phase-locked beat grid (Ellis's dynamic-programming tracker, so the grid survives a quiet bar), bar lines, sections (Foote novelty over a beat-synchronous self-similarity matrix, plus a loudness-step term), drops, hits, vocal presence. |
| `shotdna.py` | What is *in* a clip: one 8 fps decode gives motion, optical-flow direction, brightness, contrast, saturation, warmth, edge detail, subject concentration, sharpness, palette and a close/medium/wide shot scale every half second — plus letterbox bars and internal cuts. Cached on disk. No face detection, deliberately: the stock cascade is trained on photographs and fails on animation. |
| `editstyles.py` | **Eleven editing styles** and **eighteen transitions**, declarative. A style names its pace in bars per section kind, what footage each section wants, which beat effects fire on which events, and what goes between shots. |
| `beatfx.py` | **Seventeen beat-synced effects**, each building an ffmpeg filter from a list of event times. |
| `amvplan.py` | The planner: cut points snapped to the bar grid, then the whole shot assignment solved at once with the Hungarian algorithm rather than greedily, then a repair pass that guarantees no clip repeats back to back. |
| `scenes/amv.py` | The scene; `render._render_amv()` assembles its edit decision list, chunking into passes of 40 shots so a 300-shot edit does not open 300 decoders at once. |
| `palette.py` | Reads a background picture — brightness, warmth, saturation, contrast, light direction — into one of seven moods, and out of that a complete look for the living scene. |

`static/studio.js` draws the plan as a timeline. It is the same
`amvplan.plan()` result the renderer executes, not a preview of it.

## Autopilot (2026-09-24)

A tab (visible in every mode) that turns a folder of songs into upload-ready
packages, and an earnings ledger that shows which channel style actually pays.
It exists because the rest of the app makes one video by hand; a channel needs
dozens.

**How it is built**

| piece | what it does |
|---|---|
| `pulseforge/recipes/` | Declarative registry of channel styles. One file per recipe with a `RECIPE` dict: `id, label, description, scene, format, params, mood, thumb_subtitle` (+ optional `preset`, `minutes`, which are recorded but **not used yet**). Adding a style = one file + one line in `_MODULES` in `recipes/__init__.py`. |
| `pulseforge/autopilot.py` | `plan_run` (scan inbox, pair images, skip done songs), `queue_songs`, `run` (renders sequentially; one bad song does not stop the rest), `make_package`, `package_list`, ledger (`mark_uploaded`, `record_figures`, `ledger`). The renderer is injected (`render_fn`), so tests run without a server. `new_project` is shared with the Album batch route. |
| `web_app.py` | Routes below. One run is **one job** in the existing FIFO queue, so a run of 20 songs never competes with a manual render. |
| `static/index.html` | The Autopilot tab: style cards, inbox and pictures fields (remembered in localStorage), job progress, "Ready to upload" cards, the Earnings form and tables. Search for `autopilot` in the CSS block, the tab bar, the panel, and the `// ---------- autopilot ----------` JS section. |

**Data** lives in `~/PulseForgeData/outputs/autopilot/` (`config.AUTOPILOT_DIR`):
`packages.json` (one record per song+recipe, keyed by slug; status
`queued / rendering / ready / failed / uploaded`), `ledger.json` (entries of
`slug, month, views, revenue`; the same slug+month replaces rather than adds),
and `ready/<slug>/` with `video.mp4` (a hardlink to the project render, so it
takes no extra space), `thumb.jpg`, `upload.txt` and `CHECKLIST.txt`. Each song
is also an ordinary project named `autopilot <recipe> <title>`, so it can be
opened and fine-tuned in the normal editors.

**Routes**: `GET /api/autopilot/recipes` (includes `format_label`),
`POST /api/autopilot/run {inbox, recipe, art?}` → `{job_id, queued, skipped}`
(400 bad folder or recipe, 409 no audio), `GET /api/autopilot/packages`,
`GET /api/autopilot/thumb/{slug}`, `POST /api/autopilot/reveal/{slug}`,
`GET|POST /api/autopilot/ledger` (POST `{slug, action: "uploaded", url}` or
`{slug, action: "figures", month: "YYYY-MM", views, revenue}`).

**Lofi Radio and long videos**: a recipe with `per: "folder"` makes one item
(a mix) from the whole inbox. Its key includes a hash of the song names, so adding
a song makes a new mix. Items are dicts: `{songs, images, slug, title, key}`.
`run()` takes two hooks:
- `prepare_fn(project, recipe)`: `web_app._autopilot_prepare` gives living
  recipes one shot per song (pictures cycled), the `look` preset and grade, and
  the `ambience` bed. It does this through the Simple editor's own route
  functions.
- `chapters_fn(project)`: `get_tracklist`.

With `minutes`, the render is one pass of the playlist, then
`autopilot.repeat_video` loops the finished file with `-stream_loop ... -c copy`.
A 60-minute mix took 126 s instead of about an hour. The project keeps
`target_seconds` at 0 for that reason. Don't set it for Autopilot projects, or
every pass gets encoded. The deep link `#/autopilot` opens the tab without a
project.

**The Autopilot mode (UI)**: a fourth mode (`applyMode("autopilot")`) that hides
the editor tab bar and shows one panel with its own nav, Make / Library /
Earnings (`apShowView`).
- Make is three steps (songs, pictures, look), each live-summarised by
  `/scan`.
- Look cards show `/preview` frames of the first picture.
- Library cards have Upload pack (reveal + copy title, then copy description
  and tags), Open folder, Mark uploaded and Watch.
- The Browse modal uses `/browse`, limited to home. Recent folders are kept
  in localStorage.
- Links: `#/autopilot[/library|/earnings]`, matched exactly by `AP_HASH`.
  Never use `startsWith`: Autopilot projects are named `autopilot-…`.
- Opening a project from Autopilot mode switches to Simple.

Routes added: `GET /api/autopilot/browse`, `/scan`, `/preview` (PNG, cached in
`AUTOPILOT_DIR/previews/`; the hidden `autopilot-preview` project serves living
previews and is filtered from `/api/projects`), and
`/package/{slug}/text`.

**Jan**: `upload_text` calls `jan.write_upload_text` and falls back to a
template on any error. It never loads or unloads a model (Jan is shared).

**Supporting changes**: `render.grab_thumbnail` gained `pop=` (a saturation and
contrast lift, default 0 = unchanged), and its title size is now based on the
shorter side, so 9:16 thumbnails fit (16:9 output is unchanged). `scenes/bars.py`
gained a `soft` style (params `style, bar_count, bar_height, bar_opacity`) and a
`flash` strength. The defaults reproduce the old look exactly.

## Features

### Two editors

The app has grown a lot, and the interface had not kept up: Compose alone had 21
controls across 6 cards with no order implied between them, and the same ~20
scene parameters appeared both there and per-shot in Scenery. So there are now
two views of the same project, switched in the header and remembered in
`ui_mode`:

| Mode | Tabs | For |
|---|---|---|
| **Simple** | Projects · **Make** · Finish | Four numbered steps — music, pictures, look, finish. Picks the defaults you would otherwise have to know about. |
| **Advanced** | Projects · Compose · Scenery · Output · Settings | Everything, unchanged. |

**Nothing is hidden away permanently.** Simple writes the same project fields and
calls the same endpoints — there is no second data model — and *Fine-tune this
→* on any picture drops you into the full Scenery editor **on that shot**. The
one thing Simple does that Advanced does not is apply a look to *every* shot at
once, detecting each picture's own sky and water rather than copying the first
one's regions.

`tests/test_ui.py` asserts the census: every parameter the renderer understands
is still reachable in Advanced. That is the machine-checked form of "nothing was
lost", rather than a claim.

| Tab | What it does |
|---|---|
| **Projects** | One song per project. The chosen scene, its parameters, attached assets and the output format are saved with it. |
| **Make** (simple) | Four steps: add music and even out its volume; add pictures, each becoming a scene; pick a look, a colour grade and an ambient bed, applied to every scene at once; give it a title and a length, then render. A live frame from the real renderer sits beside it. |
| **Finish** (simple) | The pre-flight check and the finished renders. |
| **Compose** | The **playlist** (add several songs, reorder them, give each a caption, set the gap or crossfade between them) → pick a scene → tune its parameters (the form is built from the scene's own schema) → attach images / AI backdrop / sprite pack / clips folder → pick a format and render quality → **Preview** → **Render**. Progress streams into a log with a cancel button. |
| **Scenery** | Where a living still gets built. Pick a background, hit **Find the moving parts** or apply a **preset**, then correct it by hand: paint regions with a brush or click a polygon, choose what each one does, stack transparent PNGs for real parallax, add sprites, and grade it. Every control re-renders one real frame server-side, and **Preview loop** renders the whole loop and plays it round so you can judge the seam. The shot strip along the top is the timeline: each background, how long it holds, and how it hands over to the next. |
| **Output** | Every rendered file with its size; play, download, delete, open-folder; grab a thumbnail PNG at a chosen timestamp. Shows the render queue — what's running and what's waiting. |
| **Projects** | Also hosts **Album batch**: point at a folder of audio files, pick a scene + format, and get one project and one queued render per track. |
| **Settings** | Encoder (CPU x264, or Intel VAAPI/QSV where available), CRF, loudness target, render output folder, AI Studio URL, render quality (draft 540p / standard 720p / high 1080p internal buffer). |

Renders, previews, batches and analyses run through **one FIFO worker** — they
queue and execute one at a time rather than competing for the CPU.

### Scenes

| Scene | Family | Idea |
|---|---|---|
| **Spectrum Bars** | visualizer | Frequency bars + a circular equaliser + a bloom on every beat, over a gradient or your image. |
| **Drifting Scenery** | scenery | A still/AI image with a slow Ken Burns zoom, a parallax haze layer and clouds crossing the frame; breathes with the music. The "lofi study beats" look. |
| **Sprite Swarm** | sprites | Pixel sprites from a `~/ForgeArtData` pack drift across the frame, bob with the bass and burst on beats. |
| **Living Still** | scenery | **The main one.** A still or video background with only the parts you mark moving, stacked transparent PNGs for real parallax, sprites drifting through, a slow camera drift, depth of field and an analogue grade. Multiple backgrounds and songs with transitions. Built in the Scenery tab. |
| **Aurora Field** | visualizer | Ribbons of colour folded by the spectrum; four palettes. Not tuned; the weakest of the set. |
| **Spectrum Tunnel** | visualizer | The spectrum as rings rushing at the viewer; bass sets the ring size, beats fire a bright ring, loudness sets the speed. |
| **Harmonograph Scope** | visualizer | A glowing oscilloscope / Lissajous trace of the audio with phosphor afterglow, colour shifting with brightness and a flash on kicks. |

**Particle effects** (`pulseforge/particles.py`): every visualizer, scenery and
sprites scene gets two extra params, `particles` (none, embers, snow, sparks,
dust, petals) and `particle_amount`. Each preset is one dict in `PRESETS`;
render.py's `_feed` passes every frame scene through `particles.wrap`, so a new
preset is one dict and no scene changes. A preset may add `streak` (seconds of travel) to draw a
fading tail behind each particle; sparks use it. "none" (the default) leaves frames
untouched. Checks: `tests/test_particles.py`, and the browser check
`tests/check_scene_picker.py` (the picker lists both new scenes and a scene's
form offers all six particle choices).

Region effects: `water`, `sway`, `flow`, `sky_clouds`, `shimmer`, `glow_pulse`,
`flicker`, `breathe`, `rays`, `glass_rain`, `reflection`, `fog`, and `frames`
(your own artwork).
Emitters: `particles`, `rain`, `snow`, `dust`, `fireflies`, `bubbles`, `stars`,
`leaves`, `birds`, `fish`, `sprites`.

### Video backgrounds

A shot's background can be a clip rather than a still (`videosource.py`). Frames
are **streamed** out of one ffmpeg pipe — one frame of memory, not a gigabyte —
and because almost nothing loops on its own, the stretch just past the bed is
cross-dissolved into its first frames. On a deliberately non-looping test clip
that took the wrap discontinuity from 2.9× a normal frame step down to 1.5×.
Everything else — camera, regions, emitters, depth of field, grade — applies on
top exactly as it does over a still.

### The look pass

The panel builds itself from the schema and **groups by the `group` each
parameter declares** — Camera, Colour, Analogue, Depth — rather than presenting
one flat grid of twenty sliders. A parameter added later lands in the right
section by saying where it belongs, and a test fails if it declares no group or
one the editor does not render.

Per shot: saturation, warmth, bloom, vignette, grain, **depth of field**
(a focus depth and an aperture, using the depth the layers already carry),
**distance haze**, and the analogue pack — **scanlines**, radial **colour
fringing**, **letterbox bars** and a drifting **light leak**. The leak moves on
the `LoopClock`, so none of it costs the seam.

### The local model

There is **no image generator on this machine** -- only small text models served
by Jan -- so `pulseforge/jan.py` asks them for the two things they are reliably
good at, and the old AI Studio backdrop button is gone:

* **the upload text** -- title, blurb and tags, drafted from the tracklist;
* **"describe a look"** -- you type *"a rainy neon street at night"* and the
  model picks from the app's own registries.

Everything it returns is **validated against what actually exists** and anything
unrecognised is dropped, because a small model will happily invent an effect
called `rainstorm`. Jan not running is a clear message, not a hang.

### Ambient sound

`ambience.py` generates rain, fireplace, vinyl crackle, wind or waves with numpy
— shaped noise plus the right transients — and ffmpeg loops thirty seconds of it
under the whole mix. Nothing is shipped as an audio file, so it costs no disk,
and each bed was tuned against its **energy distribution by band** rather than
by ear-guessing: rain sits mostly in 1–4 kHz, fire in 200 Hz–1 kHz, and so on.

### Drawn over the finished video

`overlays.py`: a **now-playing** line naming the current track, and a **progress
bar**. Both live in the assembly pass rather than in a bed -- a bed is a few
seconds repeated for the length of a song, so anything that changes as the mix
moves on cannot be baked into one. The captions in `sequence.text_filter()` work
the same way.

The progress bar is an `overlay` of a full-width bar slid in from the left, not
a `drawbox` with a width expression: **`drawbox` has no time variable** -- its
`t` is the border thickness -- so such a bar sits at full width forever. That
shipped once and only measuring the rendered frames caught it.

### Title cards

A shot can have `kind: "card"`: leave the image empty, set the two grade
colours, give it a title and a hold. It renders through the ordinary bed path,
so particles and the grade apply to it, and its text is drawn in the assembly
pass over its own time window.

### The tracklist you upload

`tracklist.py` turns the playlist into the description in YouTube's chapter
format, writes it beside the MP4 as `<name>.txt`, and embeds the same marks in
the file as ffmetadata chapters. YouTube's rules -- first mark at `0:00`, at
least three, each at least ten seconds -- are **checked and reported** rather
than assumed. Titles wrap with the playlist, so the fourth play of track one is
still track one.

The thumbnail grabber takes a title, a subtitle, a darkening scrim and a corner,
and writes a 1280x720 PNG.

### Levelling and fades

`sequence.auto_gains()` measures each song with `ebur128` and evens the playlist
out. The levelling is **relative -- to the playlist's own median** -- not to an
absolute target: the final `loudnorm` already sets absolute level, and aiming
every track at a number makes the safety cap fight the goal, leaving a uniformly
quiet playlist exactly as uneven as it started. Fade in and out apply to both
picture and sound.

### Before you upload

`preflight.py` reports what would go wrong: missing audio, shots with no
background, chapter rules, an uneven playlist, loudness off target, an odd
aspect ratio, file size. It is a **report, not a gate** -- nothing refuses to
render. Levels are `stop` / `check` / `fine`.

### Snapshots, and a project as a file

`snapshots.py` stores a named point you can return to, **with copies of its
painted regions** -- a snapshot referencing live masks would change under you.
`projectfile.py` packs a project into one `.pfproj` (an ordinary zip): the JSON
and masks always, the media only if you ask, since that is the difference
between kilobytes and hundreds of megabytes.

### Long videos from few tracks

A project can carry a **target length**: the playlist repeats until it reaches
it, so six tracks become three hours with no new files. The repeat is a
`-stream_loop` over one finished pass rather than a filter graph with twenty
copies of the same input.
| **Beat-Cut Montage (AMV)** | montage | Cuts a folder of video clips to the song's beat. Every cut lands on a detected beat; shots start on scene changes where available. With **match energy** on (default) each slot is filled by the clip segment whose motion best fits the song's energy there — busy footage on the loud parts, calm on the quiet — with a penalty for reusing a clip two shots running. Transitions: cut, crossfade, dip to black, dip to white. |

### Output formats

`YouTube 1080p (16:9)`, `YouTube 4K (16:9)`, `Shorts / Reels (9:16)`, and
`Seamless loop (16:9 1080p)` which renders a short seamless visual bed and
repeats it under the full audio for hour-long "radio" uploads.

## Where data lives

`~/PulseForgeData/`:

```
settings.json
projects/<slug>/
  project.json            name, playlist + captions, shots, scene + params, assets, format
  <song>.mp3, ...         the playlist, in order, copied in
                          (backgrounds may be video clips as well as images)
  assets/                 attached background images and transparent PNG layers
                          (a clips folder is referenced by absolute path, not copied)
  masks/*.png             painted, wand-selected and auto-detected regions
  renders/<name>.txt      the tracklist to paste under the video
  cache/features_<fps>.npz  the analysis, reused across renders
  renders/*.mp4           finished videos
  renders/thumbs/*.png   grabbed thumbnails
cache/motion/*.npy        per-clip motion curves for the AMV scene, keyed by path + mtime
presets/<name>/           a look you saved, with copies of its painted regions
```

Finished MP4s default to `~/Videos/PulseForge` — change it in Settings. Nothing
is written inside the app folder.

## Dependencies

`install.sh` makes the `.venv` with `--system-site-packages`, so the system
**numpy**, **Pillow** and **pycairo** are reused, not re-downloaded (the
machine is short on disk). Into the venv it installs **fastapi**, **uvicorn**,
**python-multipart**, **pytest**, and — added in v8 for the AMV studio —
**scipy** (the Hungarian solver behind shot assignment) and
**opencv-python-headless** (measuring what is in each clip; headless
deliberately, the GUI build drags in Qt for nothing here). **ffmpeg + ffprobe**
(system, already present — ffmpeg 9 with the visualiser filters and VAAPI/QSV)
remain the only hard non-Python requirement. Still no librosa: the beat
tracking, tempo estimate and section detection are written out in numpy.

## External services

- **ffmpeg / ffprobe** — required, does all decode / filtering / encode.
- **Jan** at `http://127.0.0.1:1337/v1` — optional, for the writing assistant and
  "describe a look". Its model id is looked up rather than hardcoded, because it
  changes whenever you swap models in Jan's UI. AI Studio is **no longer used**:
  it was only ever called for image generation, which this machine cannot do.

## Running it standalone

```bash
cd /home/ejb/Forge/apps/pulseforge
.venv/bin/python run.py       # http://127.0.0.1:8436
```

## API surface

`/api/` — `state` (incl. render queue), `scenes`, `formats`, `art-packs`,
`settings`; projects CRUD; `audio` / `asset` / `clips-folder` uploads;
`ai-backdrop`; `analyze`; `preview`; `render`; `render-file` (+ delete,
reveal); `thumbnail` + `thumbnail-file`; `batch`; `jobs/{id}` + SSE `events`;
`autopilot/*` (see the Autopilot section).

v3 adds the registry endpoints `motion-effects`, `emitters`, `transitions` and
`presets` (the editor is generated from these); the playlist (`songs`,
`songs/remove`, `songs/order`); `timeline` (what the finished video will look
like, before rendering it); `asset-file` / `mask-file` / `mask` for the canvas;
**`still`** (one real frame at time *t*, ~200 ms — the editor's live feedback);
**`shot-preview`** (one whole loop as a job); `auto-regions`; `apply-preset`.

v6 adds `jan/status`, `write-upload-text`, `describe-look`, `grades`,
`snapshots` (list/take/restore/delete), `export` / `export-file` /
`projects/import`, `duplicate`, `level-playlist`, `preflight` and `export-all`.

**The `/` static mount must stay last in `web_app.py`** — it matches every path,
so any route declared after it is unreachable.

## Known gaps (verified vs reasoned)

- **New this session.** The pipeline and all five scenes are verified to
  produce valid MP4s from synthetic audio and were inspected frame-by-frame,
  but **the aesthetic quality of each scene is your call** and none is tuned
  against real music yet.
- **Montage / AMV** does beat-synced cutting with motion-to-energy shot
  matching and crossfade / dip transitions. Still missing: **face detection**
  for preferring character shots (needs `opencv-python` ~90 MB or an ONNX model
  — a dependency to review first) and **LLM-assisted edit ordering** from text
  notes. Seams: `clips.motion_curve()`, `clips.scene_cuts()`,
  `montage.build_edl()`. Note: a local text model (Jan) can't literally listen
  to audio; the realistic "AI edits to the music" is the beat/energy analysis
  choosing *when* to cut plus optional model help ordering shots from notes.
- **No draggable clip timeline UI.** The montage is configured by parameters
  and a per-shot motion/energy readout, not a non-linear editor.
- **4K** renders of the Python-drawn scenes upscale from an internal buffer
  (540–1080p depending on render quality). Montage renders natively.
- **Browser checks run through `tools/shot.py`**, not the Chrome extension,
  which isn't connected here. It drives headless Firefox over Marionette
  (stdlib-only) and waits on a JavaScript condition before capturing, because
  `firefox --screenshot` fires on load and would catch the page empty. The app
  has `#/<slug>/<tab>` deep links so a tab can be addressed directly.
- **Auto-detected regions are a suggestion, not segmentation.** Sky, water,
  foliage and lights are found by colour, position, texture and which frame edge
  they connect to. Where a hillside matches the lake below it, the water region
  will climb the hill. Everything it returns is an ordinary brush region you can
  paint over.
- **Region depth is differential drift, not layer separation** — a flat photo
  has nothing behind the region to reveal, so the amount stays small. Stack a
  transparent PNG for parallax that is actually correct.

## Next phase (documented, not built)

Rework or retire `aurora`; drag-to-reorder on the shot strip and playlist;
face-aware shot ranking for the montage (pending a dependency pick); a draggable
clip timeline; LLM-assisted shot ordering from text notes; a fal.ai backdrop
path; optional `moderngl` GPU shader scenes.

## Other docs

`README.md` (user-facing), `WIP.md` (session change log + what's verified).
