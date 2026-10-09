# pulseforge WIP archive

Sections moved verbatim from `WIP.md` on 2026-10-07 (overhaul helper-5) to keep the live WIP short. Nothing was rewritten or deleted; original order kept. The full pre-move file is in `~/Forge/backups/2026-10-07-overhaul/wip/pulseforge-WIP.md`.

## v8 (2026-09-08) — the AMV studio

The beat-cut side had been the thin part since v1: it cut on detected beats and
matched busy footage to loud passages, and that was all it knew. This pass
rebuilt it on three new layers and gave it a timeline to work in.

### What the app can now hear

`musicmap.py` sits on top of `analyze.py` and works out what the song is
*doing*, not just how loud it is:

| | how |
|---|---|
| **tempo** | autocorrelation of the onset envelope under a log-normal prior around 120 BPM. Without the prior, half- and double-time score identically and the answer flips between songs. |
| **beats** | Ellis's dynamic-programming tracker: the set of times maximising onset strength minus a penalty for spacing that is not the tempo period, solved exactly. This is why the grid **keeps going through a quiet bar**, where peak-picking drops out and a montage stalls. |
| **bars** | the beat phase whose sub-bass and harmonic change are consistently heaviest. |
| **sections** | Foote novelty — a checkerboard kernel down the diagonal of a beat-synchronous self-similarity matrix — plus a loudness-step term, then named by loudness and repetition. |
| **drops, hits, vocal** | energy jumps across a moving boundary; onset peaks; the mid-band energy ratio. |

Measured against a synthetic song built with a known tempo and layout:
**128.57 BPM against a true 128**, meter 4, downbeats a mean **45 ms** off the
real bar lines, and **all six section boundaries found within 0.03 s** and
correctly named intro / verse / chorus / verse / chorus / outro.

### What the app can now see

`shotdna.py` streams each clip once at 8 fps and 256×144 and measures, every
half second: motion, **optical-flow direction**, brightness, contrast,
saturation, warmth, edge detail, how centred the interest is, sharpness, the
dominant colours, and a close/medium/wide **shot scale**. Also letterbox bars
and internal scene cuts, off the same pass.

**There is deliberately no face detection.** OpenCV's stock cascade is trained
on photographs and is close to useless on animation, which is what this is
mostly for, and the anime-trained cascades are third-party model files. Shot
scale is estimated from the picture's own structure instead, which works on
live action and animation alike and needs no model.

### How it decides

- `editstyles.py` — **eleven editing styles**, declarative. Each names a pace in
  *bars* per section kind, what footage each section wants, which beat effects
  fire on which musical events, and what goes between shots. A new style is one
  dict.
- `beatfx.py` — **seventeen beat-synced effects**, each returning an ffmpeg
  filter: zoom punch, shake, flash, colour tear, invert hit, blur hit, strobe,
  cinema bars, and so on. Plus **eighteen transitions**.
- `amvplan.py` — the planner. Cuts are placed in **bars, not seconds**, and
  snapped to the grid; at 128 BPM a "two second" shot is 4.27 beats and is
  wrong every time, while two bars is right at any tempo.

**Shot choice is solved globally, not greedily.** Every slot is scored against
every candidate stretch of footage and the whole assignment is solved at once
with the Hungarian algorithm (`scipy.optimize.linear_sum_assignment`). A greedy
pass gives slot one its best shot and leaves slot two with the leftovers;
solving it globally will hand slot one its *second* best when that frees the
right shot for slot two. The candidate list is repeated with a rising reuse
penalty, which is what lets a nine-clip folder fill a two-hundred-shot edit
without reuse ever being free.

### The Studio

A third mode beside Simple and Advanced, with a canvas timeline showing the
actual plan: sections, the bar grid, a novelty curve, drops, every shot coloured
by which clip it came from, transition markers, and a tick for every beat effect.
Drag to pan, scroll to zoom, click a shot to see why it was chosen. Changing the
style or the intensity **replans in milliseconds** — you decide before spending
an encode.

Simple and Advanced are untouched, the `montage` scene is untouched, and the
parameter form is built from `scenes/amv.py`'s own schema, so a control added
there appears in the Studio with a slider and a number box and no UI change.

### Also this pass

- **A look taken from the artwork** (`palette.py`). A background image is
  measured — brightness, warmth, saturation, contrast, where the light comes
  from — and read as one of seven moods, which sets the grade, vignette, bloom,
  grain, haze and light leak. The leak's colour comes from the picture's own
  highlights, which is what stops it reading as a filter laid on top, and it is
  dropped entirely when the light has no direction. Verified: a night scene, a
  golden-hour scene, an overcast scene and a bright day are each read correctly,
  with the light direction right in all four.
- **`aurora` was rewritten**, three passes after it was first called not good.
  It drew horizontal sine ribbons, which is not what an aurora looks like from
  any angle. It now draws vertical curtains: a crisp lower edge, a diffuse top,
  fine rays from two beating frequencies, folding as they climb, and colour
  changing with height because the height is the physics. All four original
  parameters keep their names and defaults, so existing projects open unchanged.

### Three real bugs

**A 28-shot edit rendered six seconds long.** A shot longer than the footage
left in its clip leaves `xfade` with no material at its offset, and the whole
chain silently stops there — the container still reported the full duration,
because the *audio* was the full length. Fixed in both places: the planner now
prices a footage shortfall steeply and reports `shots_short_of_footage`, and
every shot stream is `tpad`-padded so an offset can never fall past the end.

**`rgbashift` accepts an expression and then fails.** Its shifts are integer
options, so `rh='4*t'` errors with "undefined constant t" — and the neighbouring
`eq` and `hue` take the same expression happily. The colour tear is gated with
`enable` instead, which is the look anyway. Every one of the seventeen effects
was rendered through ffmpeg and checked to (a) change the picture and (b) peak
at the event, because an effect whose expression is read once and held produces
no error anywhere.

**The studio insisted no project was open when one was.** The page declares
`PROJECT` with `let`, and a top-level `let` never becomes a property of
`window` — only `function` declarations do. `window.PROJECT` is permanently
undefined while the binding is perfectly visible by name.

Also found and fixed: the shared stylesheet caps every `.panel` at 960px, so
widening `.wrap` for a workbench tab did nothing — this had been quietly
squeezing the Scenery editor too; and a deep link to a tab in another mode
landed on the wrong tab.

### Verified this pass

- **`pytest`: 304 pass, 1 skipped** (was 260). `test_v8.py` adds 34.
  The ones that matter: every cut in **all eleven styles** lands within 20 ms of
  the beat grid; the chorus is cut faster than the verse; **no style repeats a
  clip back to back** (226 back-to-back repeats across the styles before the
  repair pass, 0 after); the shots tile the song with no gaps or overlaps;
  intensity up more than doubles the shot count; and a footage shortfall is
  reported rather than hidden.
- **End-to-end renders** at 1080p in two styles: 28 shots / 16 effects, and 76
  shots / 112 effects over two passes. Both come out **2475 frames = 82.50 s
  against an 82.50 s song**, with 48 kHz AAC. Shot content was confirmed against
  the plan by motion signature — shots assigned the moving clip render at 28.7
  motion, shots assigned the still clips at ~0.
- **The Studio was driven in a real browser**: the plan built, the timeline drew
  its sections, drops, shots, transitions and effect ticks, and the stats and
  clip list filled in.
- `black`, `pyright` (still only the pre-existing `forge_art` warning), JS
  syntax checks, and `test_inventory.py` extended to guard the three new
  registries.

### Still not done

- **The timeline is read-only.** You can see and inspect every cut, but not drag
  one. Editing a single shot by hand is the obvious next step.
- **The `montage` scene still has the v6 xfade-offset shape.** The new AMV path
  does not; the old one was left alone rather than changed without a way to
  verify it.
- The `frames` effect and `sprites` emitter still have not been driven with real
  hand-drawn animation.
- Shot choice has no idea what a *character* is — only what a close-up looks
  like structurally. Everything above about face detection still applies.

## v7 (2026-09-08) — two editors

Four feature passes had left the interface behind the app. Compose alone had 21
controls across 6 cards with nothing implying an order between them; the same
~20 scene parameters appeared both there and per-shot in Scenery with no
indication which won; and *Camera & look* was one flat grid of about twenty
sliders mixing the camera, the grade, the film effects and the depth of field.

There are now **two views of the same project**, switched in the header and
remembered in `ui_mode`:

- **Simple** — `Projects · Make · Finish`. One page, four numbered steps: music,
  pictures, look, finish. It picks the things you would otherwise have to know
  about (a 1.5 s crossfade, one shot per picture, the living scene) and shows a
  live frame from the real renderer beside it.
- **Advanced** — the five tabs as they were, tidied.

### Nothing is hidden away permanently

Simple writes the **same project fields** and calls the **same endpoints** —
there is no second data model — and *Fine-tune this →* on any picture drops you
into the full Scenery editor **on that shot**. The one thing Simple does that
Advanced does not is apply a look to *every* shot at once, detecting each
picture's own sky and water rather than copying the first one's regions.

`tests/test_ui.py` asserts the census: every parameter the renderer understands
is still reachable in Advanced, read out of the actual markup. That is the
machine-checked form of "nothing was lost".

### What was tidied

- **The look panel groups itself.** Each parameter in `scenes/living.py` now
  declares a `group` — camera, colour, analogue, depth — and the panel builds
  its sections from that. A parameter added later lands in the right place by
  saying where it belongs, and a test fails if it declares no group or one the
  editor does not render.
- **Compose's scene parameters** moved into a collapsed *Scene* section labelled
  as the fallback for shots that do not set their own, which is what they always
  were, unlabelled.
- **The inspector is in working order**: Background → Preset → Describe →
  Regions → Images → Sprites → Camera & look.

### Two things this pass found

**The screenshot tool never reported page errors.** `tools/shot.py` read
`window.__shotErrors` and printed whatever it found, but nothing ever populated
it — so every run reported a clean page whether or not the page had thrown. It
now installs listeners for `error`, `unhandledrejection` and `console.error`
before waiting. That is worse than no report, and it had been that way since the
tool was written.

**The Make button started enabled.** It was clickable before the page had
decided whether the project was ready, so a click could land before the handler
was attached. It starts disabled and is enabled by the readiness check — which
is both correct and what made the automated click-through meaningful.

### Verified this pass

- **`pytest`: 260 pass, 1 skipped** (was 235). `tests/test_ui.py` adds 23,
  reading the real markup: every parameter reachable, both modes' tabs correct,
  the four steps present, Simple not a dead end, no inline `display` fighting a
  `hidden` attribute, and the static mount still last in `web_app.py`.
- **A real click-through in Simple**, driven through the browser: clicking
  *Forest light* applied the preset to both shots, detected the `foliage` region
  in the photograph on its own, added the `dust` emitter, and left each shot its
  own picture. Pressing *Make the video* started a render.
- **Both modes screenshotted** in a real browser.
- `black`, `pyright` (still only the pre-existing `forge_art` warning), JS syntax
  checks on all three modules and the inline script.

## v6 (2026-09-08) — fifteen more, and the AI Studio path repurposed

### The one deliberate removal

The **AI backdrop button is gone**. It posted a prompt to AI Studio expecting an
image generator; there is none on this machine, only small text models through
Jan, so it could never work. It was flagged and agreed before removal rather
than deleted quietly, and replaced with two things a small text model *is*
reliably good at (below). `pulseforge/aistudio.py` and the `ai-backdrop`
endpoint are the only things this pass removed.

### The fifteen

| # | What | Where |
|---|---|---|
| 1 | **Jan writes the upload text** — title, blurb, tags | `jan.py` |
| 2 | **Describe a look** — words in, a configured shot out | `jan.py` |
| 3 | **Undo/redo across the editor**, not just brush strokes | `scenery.js` |
| 4 | **Drag to reorder** shots | `scenery.js` |
| 5 | **Keyboard shortcuts** — B/E/P/W, `[`/`]`, arrows, space, Ctrl+Z | `scenery.js` |
| 6 | **Snapshots** — a named point you can return to | `snapshots.py` |
| 7 | **Duplicate a project**, or use one as a template | `web_app.py` |
| 8 | **Export / import a project** as one `.pfproj` | `projectfile.py` |
| 9 | **Render everything** — 1080p + Shorts + thumbnail in one action | `web_app.py` |
| 10 | **Reflection** — what is above the waterline, mirrored into it | `motion/reflection.py` |
| 11 | **Fog** — a bank of mist sitting in the scene | `motion/fog.py` |
| 12 | **Film grades** — nine whole colour looks | `grades.py` |
| 13 | **Per-song levelling** | `sequence.py` |
| 14 | **Fade in and out** on picture and sound | `render.py` |
| 15 | **Pre-flight check** — what would go wrong if you uploaded this | `preflight.py` |

### The bug this pass actually found

**With any transition, the video ended before the audio and froze.** The xfade
offsets accumulated `previous duration - transition`, which overlaps the shots,
so the picture came out shorter than the music by the total of every transition
added together — two transitions meant two seconds of frozen last shot with the
mix still playing. It had been there since transitions shipped in v3 and nothing
caught it, because a frozen last shot looks like a deliberately still shot.

It surfaced only because the new fade-out gave something measurable at the end
of the video that never fired. Offsets now use each shot's own `start`.
`test_v6.py` asserts both the offsets and that the picture lasts as long as the
music.

### Two things worth writing down

**The local model is never trusted.** Everything it returns is checked against
the real registries and anything unrecognised is dropped — it will invent an
effect called `rainstorm` and mean it. The tests cover that path without needing
Jan running, which is the case that matters.

**Levelling is relative, not absolute.** The first version aimed every track at
−14 LUFS and capped corrections at 12 dB, which meant a uniformly quiet playlist
had every track clamped and stayed exactly as uneven as it started. It now
levels to the playlist's own median — the final `loudnorm` handles absolute
level — and an 18.3 dB spread closes to 0.3 dB.

### Verified this pass

- **`pytest`: 235 pass, 1 skipped** (was 189). `test_v6.py` adds 39.
  `test_inventory.py` now also guards the grades.
- **Jan was not running**, so what was verified is the *graceful* path: status
  reports it cleanly, and the reply-parsing and validation are tested directly —
  invented names dropped, out-of-range values clamped, prose-wrapped JSON found,
  a non-JSON reply reported. The live call is written but untested against a
  real model.
- **End-to-end**: a title card, reflection on the lake, fog, two film grades,
  a 1.5 s fade in and 2.5 s out, fire ambience, and an 18 dB playlist levelled.
  Decoded every frame: first frame 0.00, peak 94.0, last 1.01 — both fades land
  and the picture now runs the full 10.5 s.
- **Reflection and fog were tuned by measurement.** Fog was invisible at any
  sane density until the noise field was measured: smooth noise sits in a narrow
  band around its mean and blurring narrows it further, so it peaked at 0.7 and
  averaged 0.44. It is stretched to fill 0..1 now.
- `black`, `pyright` (still only the pre-existing `forge_art` warning), and a
  browser screenshot of the editor with snapshots, undo/redo and the shortcut
  hints.

### Still not done

`aurora` remains untouched and still not good. The `frames` effect and `sprites`
emitter have still not been driven with real hand-drawn animation. The montage
path has the same xfade-offset shape as the bug fixed above, but its shots have
no independent timeline position, so it was left alone rather than changed
without a way to verify it.

## v5 (2026-09-07) — what real background-music videos actually have

Not more effects: the specific things those channels do that PulseForge could
not.

| # | What | Where |
|---|---|---|
| 1 | **Video backgrounds** — loop a clip instead of a still | `videosource.py`, `layers.py` |
| 2 | **Ambient sound** — rain, fire, vinyl, wind, waves, generated | `ambience.py` |
| 3 | **The analogue look** — scanlines, colour fringing, letterbox, light leak | `scenes/living.py` |
| 4 | **Now playing + progress bar** | `overlays.py` |
| 5 | **Title cards** | `scenes/living.py`, `render._card_text()` |
| 6 | **Make it an hour** — the playlist repeats to a target length | `sequence.py` |
| 7 | **One shot per image** — a slideshow from the existing machinery | `web_app.py` |
| 8 | **Thumbnail with the title on it** | `render.grab_thumbnail()` |

### The ones that needed real care

**Video backgrounds keep the loop economy.** Frames are streamed out of one
ffmpeg pipe — one frame of memory, not a gigabyte — and because almost nothing
loops on its own, the stretch just past the bed is decoded separately and
cross-dissolved into its first frames. On a deliberately non-looping test clip
that took the wrap from **2.9× a normal frame step down to 1.5×**.

**The ambience is generated, and tuned against measurements.** Shaped noise plus
the right transients, no audio files, so it costs no disk. The first version
measured a spectral centroid of ~11 kHz for everything, which is thin hiss, not
rain — and the honest metric turned out to be **energy by band**, which showed
99.95% of the "wind" bed sitting below 200 Hz. It was a tilt with no high-pass.
Each bed is now band-limited and asserted to sit where its name says: rain in
1–4 kHz, fire in 200 Hz–1 kHz, and so on.

### Three real bugs, all found by measuring rather than looking

1. **The progress bar never moved.** `drawbox` has no time variable — its `t` is
   the border *thickness* — so `w='iw*t/duration'` read a constant and the bar
   sat at full width for the whole video. It looks plausible in a still frame.
   Rebuilt as an `overlay` of a full-width bar slid in from the left, and now
   measured at 11.1 / 33.3 / 55.6 / 77.8% against expected at four timestamps.
2. **`ambience.generate()` returned the wrong length** — the loop-blend guard
   bailed instead of trimming, so a "3 second" bed was 4.5 seconds. Caught by a
   test asserting the sample count, not by listening.
3. **A silent patch failure.** A `str.replace` that no longer matched after
   `black` reformatted a signature printed success anyway, so a fix I believed
   was in was not — the ♪ prefix kept rendering as a tofu box. Patch scripts now
   assert the replacement happened.

Also fixed: the tracklist said "Track 7" for the fourth play of track one
(titles now wrap with the playlist), and `/api/timeline` ignored the target
length, so the editor said "0m 23s / 2 placements" for a video that renders 90 s
with 6 placements.

### Nothing was lost

`tests/test_inventory.py` now asserts the full inventory — every scene, format,
effect, emitter, preset, transition and ambience bed that has ever shipped, plus
the public helper names. Adding is expected; removing should take a deliberate
decision rather than a passing rename.

### Verified this pass

- **`pytest`: 189 pass, 1 skipped** (was 137). `tests/test_v5.py` adds 41 and
  `test_inventory.py` 9. Each ambience bed is asserted to sit in the right part
  of the spectrum; the analogue pack is asserted **not to break the loop seam**;
  the video wrap is measured as a ratio against a normal frame step, because a
  cross-dissolve is not an identity and asserting zero there would be wrong.
- **End-to-end**: an intro card, a video-clip shot and a living still, rain
  under the music, the analogue grade, now-playing and a progress bar, repeated
  4× to 90 s. `ffprobe` confirms 8 chapters, 48 kHz audio, and the progress bar
  measured correct at four timestamps.
- `black`, `pyright` (still only the pre-existing `forge_art` warning), and both
  tabs screenshotted in a real browser.

## v4 (2026-09-07) — eight more

Three that make the picture better, two that make the work faster, one that
makes the renderer faster, one that improves what gets uploaded, one for reuse.

| # | What | Where |
|---|---|---|
| 1 | **Magic wand** — click a colour, grow a region | `wand.py`, a fourth canvas tool |
| 2 | **Modulation** — any parameter can move on a slow cycle or ride the music | `modulation.py` |
| 3 | **Light rays** | `motion/rays.py` |
| 4 | **Rain on glass** — droplets that actually refract | `motion/glass_rain.py` |
| 5 | **Depth of field + distance haze** | `layers.py`, `scenes/living.py` |
| 6 | **Parallel bed rendering** | `bedworker.py`, `render.py` |
| 7 | **Tracklist & YouTube chapters** | `tracklist.py` |
| 8 | **Reuse** — duplicate shots, copy regions, save your own presets | `presets.py`, `web_app.py` |

### The two that needed care

**Modulation lands in one place.** A parameter value may be
`{base, mod, amount, period, shape}` instead of a number, and it is unpacked in
`merge_params()` — the single choke point every effect and emitter already
resolves through. So it works for all 11 effects and 11 emitters, and for
anything added later, with no per-effect code. LFO modulation goes through the
`LoopClock`, so **a modulated parameter still leaves the seam bit-identical**;
audio sources are flagged in the UI as needing live mode, because a repeated
loop bed has no position in the song to read.

**Parallel beds are subprocesses, not a pool.** `fork` from the web app's render
thread is the deadlock-prone path Python now warns about, and `spawn` /
`forkserver` both re-import `__main__`, which fails outright depending on how
the parent was started (it failed immediately when driven from a heredoc). A
plain subprocess taking a JSON job has none of that, is trivially cancellable,
and behaves the same from the app, a test or a shell. Only loop beds go to
workers — a live bed needs megabytes of numpy analysis and is the length of the
whole song anyway. Any failure falls back to the sequential path, so this can
only make a render faster or leave it unchanged.

### Fixed along the way

**Rain, snow and leaves were falling upward.** The emitters treated angles as
though the y-axis pointed up, but image rows grow downward, so every "falling"
default was inverted — and `flow` scrolled the wrong way with it. There is now
one `imageops.direction_vector()` with an intuitive compass (0 right, 90 up,
270 down) used by every effect and emitter, and a regression test that asserts
rain moves down and bubbles move up. Nothing visible caught this: a still frame
of drifting particles looks the same either way.

**A JSON payload quietly disabled the fast path.** The bed job dict carried the
numpy analysis the worker never reads, so serialisation failed and every render
fell back to sequential. The fallback did exactly its job — the render still
succeeded — which is also why it would have gone unnoticed without reading the
log.

### Verified this pass

- **`pytest`: 137 pass, 1 skipped** (was 102). `tests/test_v4.py` adds 29.
  Notable: a **modulated effect is still bit-identical at the loop seam**;
  parallel and sequential beds are **byte-identical hashes** given the same
  encoder settings; wand tolerance grows the selection and contiguous mode stops
  at the edge; focus decides what is sharp and haze fades the distance; chapter
  metadata is well-formed and escaped; a saved preset carries its painted
  regions into another project under a new name.
- **Parallel: 33.9 s → 18.8 s for four beds, 1.80× faster.** Byte-identical to
  sequential when the encoder thread count matches; across thread counts the
  pictures differ by a mean of 0.25 levels, which is x264 threading, not
  rendering.
- **End-to-end**: rays, glass rain, depth of field, distance haze and a
  modulated cloud amount in one render. `ffprobe` confirms the embedded
  chapters (`0.00→12.50 First Track`, `12.50→22.50 Second Track`), and
  `v4.txt` was written beside the MP4 with matching timestamps.
- **Refraction proven on a checkerboard** — the squares visibly bend inside each
  droplet, which a flat test image could never have shown.
- `black` clean; `pyright` — still only the pre-existing `forge_art` warning.
- **Browser-checked**: the wand tool with its tolerance control, the duplicate
  and save-this-shot buttons, copy-to on every region, and an open modulation
  row on a live parameter.

### Still rough

- Auto-detection and the wand are both suggestions; neither is segmentation.
- The `frames` effect and `sprites` emitter still have not been driven with real
  hand-drawn animation.
- `aurora` remains untouched and still not good.

## v3 (2026-09-07) — the living-still workflow

The point of this pass: a background video is **mostly a still image with a few
parts of it moving** — clouds crossing the sky, water rippling, hair swaying —
under a slow camera drift, with simple sprites added on top, running long over
several backgrounds and several songs. The old `drift` scene animated the whole
picture at once, which is not the same thing and never looks right.

### The shape of it

A project is now a **playlist of songs** plus a **list of shots**. A shot is one
background image plus:

- **regions** — parts of the picture marked by hand (brush or polygon) or found
  automatically, each running one motion effect;
- **stacked images** — transparent PNGs laid over the background, each with its
  own depth, placement and optional motion. These give *real* parallax: a
  cut-out moves against the background with nothing showing through;
- **emitters** — particles and creatures drifting through, at their own depths;
- **camera** and **look** — a slow push and drift, then grade, bloom, vignette,
  grain;
- a **hold** (one song, or N seconds) and an **out-transition**.

### Loop-exactness, and why it is the whole design

Everything that moves asks a `LoopClock` for its phase, and the clock snaps
every requested period to a whole number of cycles inside the shot's loop.
Nothing is allowed to use raw time. That means a shot is **identical at t=0 and
t=loop_seconds**, which buys two things at once:

1. the loops are clean, which is what the user asked for;
2. the renderer only has to compute **one loop** of numpy frames and let ffmpeg
   repeat it. An hour-long mix over four backgrounds costs four short renders
   instead of 108,000 frames.

`test_a_whole_shot_loops_seamlessly` asserts the seam is **bit-identical**, not
merely close — anything else accumulates into a visible pulse when the bed is
repeated dozens of times.

### New modules

| File | What it is |
|---|---|
| `looping.py` | `LoopClock` — snapped periods and wrapping phases. Every effect and emitter goes through it. |
| `imageops.py` | The pixel maths: bilinear `sample`/`displace`, `box_blur`, `periodic_noise`. |
| `masks.py` | Regions (polygon points or a brush PNG) → feathered float masks, cached, plus `bbox`. |
| `layers.py` | `Camera` and the shot's `Backdrop`: background + stacked transparent images. |
| `motion/` | **Registry** of 9 region effects. One file + one line each. |
| `emitters/` | **Registry** of 11 particle/sprite emitters. Same pattern. |
| `scenes/living.py` | The flagship scene: composes everything in depth order, then grades. |
| `sequence.py` | The timeline: joins the playlist, places shots, builds per-song captions. |
| `autoregions.py` | Guesses where the sky, water, foliage and lights are. |
| `presets.py` | **Registry** of 11 complete looks. |
| `artsource.py` | Loads the user's own frames — a folder of PNGs, a GIF, or a sprite strip. |
| `tools/shot.py` | Headless-Firefox screenshots over Marionette (see "Browser checks"). |

Effects: `water`, `sway`, `flow`, `sky_clouds`, `shimmer`, `glow_pulse`,
`flicker`, `breathe`, `frames` (your own artwork in a region).
Emitters: `particles` (fully configurable), `rain`, `snow`, `dust`, `fireflies`,
`bubbles`, `stars`, `leaves` (leaf/petal), `birds`, `fish`, `sprites` (your own
artwork or a ForgeArtData pack).

Adding either is **one file plus one line in its registry** — the API, the
picker and the whole parameter form are generated from the table.

### Verified this pass

- **`pytest`: 102 pass, 1 skipped** (was 11). `tests/test_living.py` adds 91.
  The important ones are generic over the registries, so a new effect is
  covered the moment it is registered:
  - every effect and every emitter is **bit-identical at t=0 and t=loop**;
  - every effect changes pixels **only inside its mask** (`glow_pulse` is
    skipped — its bloom spills on purpose);
  - every emitter is a pure function of time, not carried state;
  - every registered thing declares a schema whose defaults sit inside its own
    min/max;
  - a whole shot loops with a **max channel difference of 0**;
  - `still()` agrees with the rendered frame at the same time, so what the
    editor's scrubber shows is what renders;
  - a broken layer or emitter costs that layer, not the render.
- **End-to-end render**: 2 songs (1.5 s crossfade) × 2 shots (auto-detected sky
  and water, a stacked foreground PNG with `sway`, birds, snow, a `fade_black`
  between them). `ffprobe` confirms 1920×1080, 22.5 s, muxed AAC. Frames dumped
  either side of the transition and eyeballed — the crossfade, the per-song
  caption change and the blurred second shot are all correct.
- **The encoded loop**: the change across the loop point of a rendered bed is
  **1.33× a normal frame-to-frame step** — the remainder is h264 quantisation,
  not motion. Measured, not assumed.
- **`black`** clean. **`pyright --pythonpath ./.venv/bin/python`** — one
  pre-existing dynamic-import warning (`forge_art`), no new errors.
- **The UI was actually looked at** (see below): both tabs screenshotted, the
  live still rendering in the canvas, region overlays, all controls present.

### Speed

Optimised from 230 → **135 ms/frame** at 720p standard, measured on a shot with
two region effects, a stacked image with its own effect, and three emitters:

- `sample()` gained a fast path for constant offsets that slices instead of
  gathering (5.4× on that path) and a flat-linear-index path for varying fields;
- `sky_clouds` shapes its cloud field **once** — thresholding and blurring both
  commute with a whole-pixel roll of a tiling field, so per frame there is
  nothing left but the roll;
- the look pass grades in place, takes luminance through a matmul, and blooms at
  quarter resolution.

In loop mode this is bounded by the loop length, not the song. A 12 s bed at
720p is about 48 s of work regardless of whether the video is 3 minutes or an
hour.

### Fixed along the way

**Every render was producing 96 kHz AAC.** `loudnorm` works internally at
192 kHz and leaves the stream there, which ffmpeg then handed to the AAC
encoder. `_audio_filter()` now appends `aresample=48000`. This affected *all*
scenes, not just the new ones.

### Browser checks

The Chrome extension is not connected on this machine, and `firefox
--screenshot` alone is useless here — it fires on the load event, so a page that
fetches its data afterwards captures empty. `tools/shot.py` drives headless
Firefox over **Marionette** (length-prefixed JSON over TCP, so it is stdlib-only
and adds no dependency) and polls a JavaScript condition before capturing:

    ./.venv/bin/python tools/shot.py "http://127.0.0.1:8436/#/my-project/scenery" \
        out.png --wait "document.body.dataset.ready==='1'" --settle 3

The app grew `#/<slug>/<tab>` deep links to make this work, which is worth
having anyway.

## Earlier passes

### v2 (2026-09-07) — speed, AMV editor, studio polish

`render_quality` tiers; `overlay.glow_dots()` kernel-paste rewrite; aurora at
half-res. `clips.motion_curve()` and energy-matched montage EDLs with
`xfade` transitions. Project text fields → one `drawtext` pass; thumbnail
exporter; a real FIFO render queue; album batch. Verified by 11 passing tests
and an end-to-end montage render.

### v1 (2026-09-07) — first build

`analyze.py` (numpy feature track, no librosa), the scene registry with `bars` /
`drift` / `swarm` / `aurora` / `montage`, `overlay.py`, `formats.py`,
`render.py`, `clips.py`, `aistudio.py`, `project.py`.
