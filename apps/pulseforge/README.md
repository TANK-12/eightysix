# PulseForge

Turn songs into videos you can put on YouTube.

The main thing it makes is a **living still**: a background picture that mostly
holds still while the parts you mark move — clouds crossing the sky, the water
rippling, hair or grass swaying — under a slow drift, with birds, rain,
fireflies or your own sprites passing through. Line up several backgrounds and
several songs and it becomes one long mix with transitions between them and a
caption per track. That is the lofi-radio format.

It also still does straight visualisers and beat-cut AMVs.

Either way it analyses the music, renders, muxes the song back in at YouTube's
loudness, and writes an MP4. Nothing is uploaded for you — you get a file.

```bash
cd ~/Forge/apps/pulseforge && bash install.sh     # venv + deps + desktop entry
.venv/bin/python run.py                            # http://127.0.0.1:8436
```

Or open it as the **PulseForge** tab in the Forge hub.

## Three editors

**Simple** is one page and four steps. **Advanced** is the full five-tab editor.
**Studio** is the beat-cut workbench for cutting video clips to music — a
timeline of the whole edit that you plan, look at and change before rendering
anything. They are three views of the same project; nothing is only available in
one of them.

## Cutting clips to music (Studio)

Point it at a folder of video files, pick one of eleven **editing styles**, and
it plans the whole edit:

- shots are held for a number of **bars**, not seconds, and every cut lands on
  the beat grid — so the pacing is right at any tempo;
- the pace changes by **section**: longer through the intro and the breakdown,
  tighter through the chorus, whatever the style asks for;
- each shot is chosen by **what is actually in it** — how busy it is, whether it
  is a close-up or a wide shot, which way the camera is moving, whether it is
  sharp — matched against what that moment of the song wants;
- **beat effects** fire on the events the style names: a zoom punch on the
  downbeat, a flash on the drop, a colour tear on the hit;
- **transitions** vary by moment, and a whip pan is matched to the direction the
  footage was already travelling.

One **intensity** control moves the whole edit at once: up shortens every shot
and pushes every effect harder. Planning takes milliseconds once the clips have
been looked at, so you can try five styles before spending a render.

The timeline draws the real plan: the song's sections, the bar grid, where the
drops are, every shot coloured by which clip it came from, the transitions and a
tick for every effect. Click a shot to see why it was chosen.

## Two editors

There is a switch in the header.

**Simple** is one page and four steps — add music, add pictures, pick a look,
give it a title — with a live frame from the real renderer beside it. It picks
the rest for you. Start here.

**Advanced** is everything: the shot timeline, painted regions, thirteen motion
effects, eleven emitters, modulation, depth of field, the analogue grade.

They are the same project seen at two levels of detail, so nothing you do in one
is lost in the other. *Fine-tune this →* on any picture in Simple opens that
exact scene in the full editor.

## The looks ("scenes")

| Scene | For |
|---|---|
| **Living Still** | **The main one.** A still background with only the parts you mark moving, plus stacked transparent PNGs, sprites and a slow drift. Built in the **Scenery** tab. |
| **Spectrum Bars** | Straight music-visualiser channels. Bars + a ring + a beat bloom over a gradient or your image. |
| **Drifting Scenery** | The older, simpler lofi look: the whole picture zooms and hazes together. Living Still supersedes it. |
| **Sprite Swarm** | Pixel sprites (from your ForgeArtData packs) drifting and pulsing with the bass. |
| **Aurora Field** | Ambient / synthwave / orchestral. Colour ribbons folded by the spectrum. |
| **Beat-Cut Montage (AMV)** | Point it at a folder of video clips and it cuts them to the beat. First version — hard cuts on detected beats, shots start on scene changes. |

## The sizes ("formats")

YouTube 1080p (16:9), YouTube 4K (16:9), Shorts / Reels (9:16), and a
**seamless loop** mode that renders a short bed and repeats it under a long
mix — for hour-long "radio" uploads.

## Making a living still (the full editor)

1. **Projects** → create one, then **Open**. Switch to **Advanced** in the
   header if you are not there already.
2. **Compose** → add your songs. They play in the order listed; drag them about
   with ↑/↓, give each one a caption, and set a gap or a crossfade between them.
   Attach your background images and clips here too. **Level the playlist**
   measures every track and evens them out, and you can set a fade in and out.
3. **Scenery** → this is where the work happens.
   - **Describe a look** in words — "a rainy neon street at night" — and the
     local model picks from the effects, sprites and presets that exist. It only
     ever chooses from what the app offers it, and anything it invents is
     dropped. Needs Jan running.
   - Pick a background for the shot — a still **or a video clip**. A clip is
     decoded a frame at a time and the stretch past the loop is dissolved into
     the start so it repeats without a jump.
   - Hit **Find the moving parts**. It looks at the picture and proposes the
     sky, the water, the foliage and any bright lights, each with the effect
     that usually suits it. Or click a **preset** — *Lofi lake*, *Rainy window*,
     *Night sky*, *Snowfall*, *Underwater* and so on — which does the same thing
     and brings a whole grade and set of particles with it.
   - Or make the shot a **card**: no image, a title and a hold, for an intro
     or an end card.
   - Correct it by hand. **Wand** to click a colour and grow outward from it —
     turn the tolerance up to take more, and untick *just this patch* to take
     every similar area at once. **Brush** to paint, **Erase** to take it back,
     **Polygon** to click a clean outline. Pick what each region does from the
     list and tune it — every control is a slider *and* a number box.
   - Press the small **~** on any slider to make that value move on its own: a
     slow swell, or tied to the loudness, the bass or the hits in the track.
     (Anything tied to the music needs the shot set to `live`; the control tells
     you so.)
   - Add **stacked images**: transparent PNGs over the background, each with its
     own depth. These give real parallax, because a cut-out has actual
     transparency and nothing shows through behind it. A PNG can carry its own
     motion, using its own transparency as the region — drop in a `hair.png`
     with **Sway** on it and there is nothing to paint.
   - Add **sprites and particles** — birds, fish, rain, snow, leaves, petals,
     fireflies, dust, bubbles, stars, or your own PNG frames. Give one a region
     to keep it there: fish in the pond, stars in the sky.
   - Every change re-renders one real frame straight away, so you are always
     looking at the actual renderer. **Preview loop** renders the whole loop and
     plays it round and round — that is how you check the loop is clean.
   - **Focus** and **Aperture** under *Camera & look* blur everything off the
     focus plane, and **Distance haze** fades the far layers — that is what
     makes a stack of cut-outs read as photographed rather than assembled.
   - **+ shot** adds another background, **duplicate** copies the one you are on
     (regions and all). The strip along the top is your timeline: each shot holds
     for one song by default, and the dropdown between two shots is the
     transition.
   - **Take a snapshot** before trying something risky — a named point you can
     come back to, painted regions and all. Ordinary undo is **Ctrl+Z**, and
     works on everything, not just brush strokes.
   - Built something you like? **save this shot** puts it in the preset grid
     next to the built-in ones, painted regions included, ready for the next
     project.
4. Choose a **format** on Compose and hit **Render**.
5. When it is done, the **Output** tab has your description ready to paste —
   the tracklist with timestamps, which YouTube turns into chapters. The chapter
   marks are embedded in the MP4 too. The same tab makes the **thumbnail**: grab
   a frame, put the title on it, darken behind the text.
6. **Check it** before you upload. The pre-flight report says what would go
   wrong — chapters that break YouTube's rules, loudness off target, an uneven
   playlist, an odd shape. It never stops you rendering; it just tells you.
7. **Render everything** queues the 1080p cut, the 9:16 Shorts version and the
   thumbnail in one go.

## Making it feel like one of those videos

Three things on **Compose** do most of the work:

- **Ambient bed** — rain, a fireplace, vinyl crackle, wind or waves mixed low
  under the music. These are generated rather than sampled, so they cost no
  disk and never run out. Press *Hear 6 seconds* to audition one.
- **Show what's playing / progress bar** — the corner label and the bar filling
  across the bottom that these channels all have.
- **Make it this long** — set it to 1 or 3 hours and the playlist repeats to
  reach it. Six tracks becomes three hours without adding a single file, and the
  tracklist and chapters follow automatically.

And on **Scenery**, under *Camera & look*: a **film grade** (nine of them —
faded, teal and orange, warm film, bleach bypass, night, sepia, tape, dream),
plus **scanlines**, **colour fringing**, **letterbox bars** and a drifting
**light leak**. That group changes how the output feels more than anything else
in the app.

Two effects worth knowing about: **Reflection** mirrors whatever is above a
region down into it with a ripple, which is what a still photo of a lake is
usually missing, and **Fog** puts a bank of mist *in* the scene rather than
across the sky.

## Why long videos are quick

Everything that moves is built to come back to exactly where it started at the
end of the loop. So an hour-long mix does not render an hour of frames — it
renders one short loop per background and repeats it underneath. Four
backgrounds is four short renders, however long the mix is. The Scenery tab
tells you how many it will actually do.

If you want the picture reacting to the song moment by moment instead, set a
shot's **Motion** to `live`. That renders every frame, and it is slow.

## Speed

Rendering is CPU-only on this machine.

**Living Still** costs about 48 seconds per 12-second loop at standard quality
— *per background*, not per song. A three-background, ten-song mix is a few
minutes of drawing plus the encode, whether it runs twenty minutes or two hours.

Backgrounds also render several at a time: four beds went from 34 s to 19 s
here. **Settings → Backgrounds rendered at once** controls that, and it is set
low on purpose so a render does not take the whole machine.

The older scenes render every frame. Rough guide for a 3-minute song at 1080p:
Sprite Swarm ~2 min, Aurora ~6 min, Drifting Scenery / Spectrum Bars ~10–15 min,
plus encode. 4K roughly doubles it. Kick off a big render and leave it.

## Taking a project with you

**Export this project** packs it into one `.pfproj` file — the settings, the
shots and your painted regions. The songs and images are left out unless you
tick the box, because those are the hundreds of megabytes and usually not the
part worth keeping. **Duplicate** copies the lot; **use as a template** copies
the look without the songs.

## Where things live

```
~/PulseForgeData/
  settings.json
  projects/<slug>/
    project.json     the playlist, the shots, the scene, params and format
    <song>.mp3 ...   your songs, copied in, in playlist order
    assets/          background images and transparent PNG layers
    masks/           the regions you painted, one greyscale PNG each
    cache/           the audio analysis, reused between renders
    renders/         the finished MP4s
```

Finished files also copy to `~/Videos/PulseForge` by default — change that in
**Settings**.

## Autopilot: a channel on autopilot

For when you have a stack of songs and want a video for each without making
each one by hand.

1. Put the songs in a folder, and some pictures in another if you have them.
2. Press **Autopilot** at the top (next to Simple, Advanced and Studio). Choose
   the two folders with **Browse**. Each look shows your own first picture
   drawn in that style, so pick the one you like:
   - **Lofi Radio**: all your songs as one long mix (an hour), your pictures
     gently alive, soft rain, a chapter per song. Needs pictures. An hour
     renders in about two minutes.
   - **Lofi Drift**: your picture breathing slowly under the music.
   - **Visualiser Bars**: thin mirrored bars under the picture.
   - **Shorts Pulse**: the same, vertical, for Shorts and Reels.
3. Fill in the folders and press **Make**. The videos render one after another.
4. Finished videos appear in **Library**. **Upload pack** opens the video's
   folder and copies the title. Then **Copy description** and **Copy tags**
   give you the rest, in the order YouTube's upload form asks for them. The
   folder also has `thumb.jpg` and a `CHECKLIST.txt`.
5. After uploading, press **Mark uploaded** and paste the link. Each month, type
   the views and revenue from YouTube Studio into **Earnings** and see which
   style earns.

Running Make again on the same folder only does the new songs. Nothing is
ever uploaded for you. Use only music and pictures you have the rights to,
otherwise YouTube's Content ID gives the money to the owner.

## Adding things

Everything extensible here is a registry: one new file, one new line, and it
appears in the app with its own controls. Nothing else changes.

| To add | Put a file in | Register it in |
|---|---|---|
| A **region effect** (what a marked part does) | `pulseforge/motion/` | `motion/registry.py` |
| An **emitter** (particles, creatures) | `pulseforge/emitters/` | `emitters/registry.py` |
| A **preset** (a whole look) | — | `pulseforge/presets.py`, or just hit *save this shot* |
| A **scene** | `pulseforge/scenes/` | `scenes/registry.py` |
| an Autopilot channel style | `pulseforge/recipes/<id>.py` with a `RECIPE` dict | one line in `_MODULES` in `pulseforge/recipes/__init__.py` |

An effect defines `EFFECT` (metadata plus a parameter schema, which *becomes*
the form in the editor) and `apply(frame, mask, box, tl, p, ctx)`. An emitter
defines `EMITTER` and `draw(...)`. A scene defines `SCENE` and `frames(ctx)`,
or `build_edl(ctx)` for the montage family.

Two rules. **Ask `tl` for your phases, never use raw time.** `tl` is a
`LoopClock`, and it snaps every period to a whole number of cycles in the loop.
That is what keeps loops seamless, and the test suite checks it generically — a
new effect is covered the moment you register it. And **take directions from
`imageops.direction_vector()`** rather than calling `sin` yourself: image rows
grow downward, and getting that backwards makes rain fall upward.

## Needs

- **ffmpeg + ffprobe** on PATH (ffmpeg 9 here — required).
- Python: `fastapi`, `uvicorn`, `python-multipart` in the venv; `numpy`,
  `Pillow`, `pycairo` reused from the system.
- Optional: **Jan** on `:1337` for the writing assistant and "describe a look".
  There is no image generation anywhere in this app — the machine has no model
  that can do it.

## Checking the UI

The Chrome extension isn't connected here, so use the bundled screenshotter,
which drives headless Firefox and waits for the page to actually finish loading:

```bash
.venv/bin/python tools/shot.py "http://127.0.0.1:8436/#/my-project/scenery" \
    shot.png --wait "document.body.dataset.ready==='1'" --settle 3
```

Any tab is addressable as `#/<project-slug>/<tab>`.

See `MANIFEST.md` for the full picture and `WIP.md` for what's verified vs
still rough.
