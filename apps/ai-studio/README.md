# AI Studio

A local, offline image/video generator with a searchable, deletable history
and a built-in model manager. No cloud calls, no accounts, no content
filter or safety-checker layered on top of the models -- it's your machine,
your weights, your outputs.

## Rebuild (2026-10-08)

Rebuilt by crew `ai-studio` (commander Rin/Tetsu, 4 Opus 5.5 helpers) at
Emerson's ask: every model is a press-to-download card, the app rebuilt
properly, broken things fixed, 3D world models offered. Plan and contract:
`docs/2026-10-08-rebuild-plan.md`; worlds: `docs/WORLDS.md`; feature audit
with evidence: `docs/AUDIT.md`. Pre-rebuild copy:
`~/Forge/backups/2026-10-08-ai-studio-rebuild/`.

- **One model list built from files**, in `src/catalog/` (`image.py`, `video.py`,
  `world.py`). Adding a model is one entry in one file. Each entry lists its
  *parts* (files); a part is stored once in `models/parts/` and shared by
  filename; old checkpoints in `models/sd/catalog/` still count. Every
  `size_bytes` matches Hugging Face (`tests/test_catalog_sizes_live.py`, opt-in
  live check).
- **Press to download:** quote (size, free space, keeps 5 GB spare), then a
  resumable download with progress and Cancel; Delete keeps parts another
  installed model uses. Nothing downloads until pressed. Gated repos
  (Ideogram 4, LTX 2.5) need `HF_TOKEN` and say so on the card.
- **Two engine builds:** `bin/` (master-841, unchanged; the SD1.5 models use it)
  and `bin/next/` (master-945-a1ded76, 2026-10-06; new models use it;
  `AI_STUDIO_SD_BUILD=next` switches everything). Role -> flag table in
  `src/engine_flags.py`. New models run with `--offload-to-cpu --diffusion-fa
  --vae-tiling` and without the second CPU sd-server.
- **Real video models** (`src/video_models.py`, `POST /api/generate/model-video`):
  `sd -M vid_gen` per job as a cancellable background process; the image
  servers stop for it and come back on the next image.
- **Warp video** (`/api/generate/video`) now runs as a background job: answers
  `{id, status: "running"}` at once, follow `/api/jobs/{id}/state`, stop with
  `POST /api/jobs/{id}/cancel` (`wait: true` keeps the old blocking reply).
  Audit fixes in motion/longform/hybrid/library are listed in `docs/AUDIT.md`.
- **Edit an image:** `POST /api/generate/edit` (prompt + picture, active model).
- **3D worlds** (`src/worlds/`, `/api/worlds/...`): "Walk Into a Picture" is an
  approximate walk-through on the sd.cpp Wan 2.1 VACE model (each move warps
  the last frame, the model paints in the new view). Real world models
  (InSpatio-World 1.5, WorldCrafter-Fast, Evoke) are listed but need NVIDIA or
  a reviewed runtime install; see `docs/WORLDS.md`.
- **New page:** sections Make an image / Edit an image / Make a video / 3D
  worlds / Library; Models panel with Images / Video / 3D worlds tabs.
  `static/index.html` + `static/css/studio.css` + `static/js/*.js` (one `AS`
  object). Checked by `tests/check_ui.py` (headless Chrome, contrast >= 4.5:1,
  no text under 14 px, no all-caps).

**Verified:** 323 tests pass, 128 opt-in live tests skipped; `check_ui.py` 174
checks at 760/1100/1920 px against a stand-in backend; the real backend on a
scratch port served cards, tabs and the download quote. **Not verified:** no
new model has been downloaded or run on the Iris Xe (engine `bin/next` has
only passed `--help`); real downloads, edits, model video and world moves are
untested until Emerson OKs GPU runs.

## Models

Nothing is hardcoded -- open the **Models** button in the header to
download, delete, or switch between checkpoints. Only one is installed by
default (to save disk space); grab others any time.

The panel shows each model only by its friendly label ("Anime -- General")
and a short description. The "Show technical details" link, which revealed
the real checkpoint name, full description, steps and CFG, was removed at
Emerson's request (2026-09-27), and `/api/models` no longer sends `name` or
`full_description`; the real names stay in `src/models_catalog.py`.

| Model | Style | Notes |
|---|---|---|
| **MeinaMix V10** (default) | anime | Versatile general-purpose anime checkpoint. No filter, handles NSFW. |
| MeinaHentai | anime | Same lineage, tuned toward explicit content specifically. |
| Counterfeit V3 | anime | Vibrant, illustrative, strong linework. |
| Realistic Vision V6.0 B1 | realistic | Photorealistic, not anime-styled. |

Switching models stops and restarts `sd-server` with the new checkpoint (a
few seconds) -- no need to restart the app.

**Per-model tuning matters and isn't uniform.** Each catalog entry carries
its own sampler/steps/cfg, because a technique that works great on one
checkpoint can quietly wreck another. Concretely: an LCM-LoRA (which cuts
SD1.5's usual ~25 steps down to ~6) works well on Realistic Vision but
produces a uniform haze on the Meina-lineage anime checkpoints *no matter
how many steps you give it* -- confirmed by testing both 6 and 10 LCM steps
and getting the same blur. The fix isn't more steps, it's the right sampler
for that checkpoint: the anime models use `dpm++2m` at 16 steps / cfg 7
instead, which actually converges. If you add a model to the catalog
yourself, don't assume LCM settings will transfer -- check.

## How it stays fast anyway

1. Generate at 512x512, not at final resolution.
2. Feed that through **Real-ESRGAN** (GPU, Vulkan, ~1-2s) to upscale 4x to
   2048x2048, recovering sharp detail cheaply instead of paying for it at
   generation time.
3. For video: motion (pan/zoom/orbit) is a real, deterministic 2D warp
   applied to the scene's anchor frame -- not something the model has to
   invent -- which also happens to make every frame's img2img "healing"
   pass independent of its neighbors. That independence is what lets frames
   be farmed out across **both the iGPU and the CPU** concurrently.

## Hybrid GPU+CPU dispatch

`hybrid.py` runs one `sd-server` pinned to the iGPU and one pinned to CPU,
each pulling the next frame off a shared queue as soon as it's free. This
naturally biases toward the GPU (it's normally faster, so it finishes and
grabs the next frame sooner) while keeping the CPU genuinely busy in
parallel rather than idle -- no artificial fixed split, no forced 50/50
that would just slow the whole job down to the CPU's pace. Both `sd-server`
instances default to using all physical CPU cores/the full iGPU already
(`-t -1`), so nothing extra is needed to "max out" either one.

If something else on your machine is using the iGPU (another local LLM,
etc.), GPU-backend generation will simply be slower since it's sharing
hardware -- the CPU backend picks up proportionally more of the queue
automatically when that happens, since it's timing-based, not hardcoded.

## Longform video

The video tab supports a multi-scene storyboard: each scene is its own
prompt + frame count + camera motion (static/pan/zoom/orbit) + strength.
Scene transitions are handled explicitly -- the next scene's first frame is
generated via img2img *from the previous scene's last frame* (a
content-aware transition, not a hard cut), and a short cross-fade is
blended across the boundary before the final encode. Every frame's
completion is checkpointed to `outputs/<job>/state.json` (backend used,
timing) as it happens.

Simple mode (single prompt + one motion direction) still works exactly as
before -- longform is opt-in via a checkbox in the UI.

## Deleting things

Every thumbnail in the library has a small × button; deleting removes both
the database entry and the on-disk job folder permanently. Models can be
deleted from the Models panel too.

Any installed model can be deleted from the Models panel, including the
active one (2026-09-24; this used to be refused). Deleting the active model
stops its sd-servers, deletes the files, and switches to the first other
installed model, or leaves none active. The next Generate starts the servers
for whichever model is active (`model_manager.ensure_running`). Tests:
`.venv/bin/python -m pytest -q tests`.

**Delete all models** (2026-09-25, top of the Models panel) lists every model
file in AI Studio's own `models/` folder, one row per image model (with its
VAE) plus the LCM-LoRA, leftover files in `models/sd/catalog`, the upscale
models and the RIFE model, each with its size and file names. Image models,
the LoRA and leftovers are ticked; upscale and RIFE are not, because nothing
in AI Studio downloads them again. The button shows the space the ticked rows
free. Symlinked files are never listed, so a file shared from Jan or another
Forge folder cannot be deleted from here; a VAE still used by a kept model
stays. The list is `model_manager.EXTRA_MODELS` plus the catalog
(`delete_all_plan`, `delete_all`; routes `GET`/`POST /api/models/delete-all`).
Verified 2026-09-25: 9 tests pass; headless screenshot of the panel against
the real folder (2.30 GB model, 128 MB LoRA ticked; 33 MB upscale and 10 MB
RIFE unticked; "frees 2.42 GB"). Nothing was deleted in that check.

## Output format

Final images save as JPEG (quality 92) by default to avoid multi-megabyte
uncompressed files; pass `"output_format": "png"` in the API for lossless.
Video is already efficiently compressed via H.264.

## Requirements

- Linux with Vulkan (works on Intel/AMD/NVIDIA GPUs, integrated or discrete)
- Already set up for you: `bin/sd`, `bin/sd-server`,
  `bin/realesrgan-ncnn-vulkan`, `bin/rife-ncnn-vulkan`
- Python venv in `.venv/` with fastapi + uvicorn

## Run it

```bash
./run.sh
```

`sd-server`'s lifecycle is now owned by the FastAPI app itself (started on
app startup, stopped on shutdown, restarted on model switch) -- `run.sh`
just starts the web app. Open http://127.0.0.1:8420, or launch **AI Studio**
from your desktop's app search, which does the same thing in a native
window and shuts everything down when you close it.

## Layout

```
bin/                native engines, build master-841 (sd, sd-server, realesrgan, rife)
bin/next/           newer sd.cpp build (master-945) used by the new models
models/parts/       downloaded model files, stored once, shared by filename
models/sd/catalog/  older single-file checkpoints (still found)
models/sd/lora/     LoRAs (sd-server loads them by name from here)
models/upscale/     Real-ESRGAN ncnn weights
models/interp/      RIFE ncnn weights
src/
  app.py            routes
  catalog/          the model list: image.py, video.py, world.py (+ merge in __init__)
  models_catalog.py thin shim over catalog/
  model_manager.py  quote/download/cancel/delete parts; owns the sd-server processes
  engine_flags.py   part role -> sd flag table
  engine.py         talks to sd-server + upscale/interpolate/encode (checks outputs)
  video_models.py   real video models via sd -M vid_gen (background jobs)
  worlds/           3D world runners, sessions, camera moves
  motion.py         camera warps (mirror-filled edges, colour matching)
  hybrid.py         GPU+CPU frame dispatch with retry and cancel
  longform.py       multi-scene storyboard, blocks re-based on the newest frame
  library.py        sqlite-backed searchable, deletable history with thumbnails
static/             index.html, css/studio.css, js/*.js
docs/               rebuild plan, WORLDS.md, AUDIT.md
outputs/            generated images/videos (one folder per job) + library.db
```

## Panels (B41, 2026-09-27)

**Replaced 2026-10-08** by the rebuilt page (fixed sections that stack below
900 px); the draggable cards are no longer used by AI Studio. Kept below as
history.

The page is three cards, Settings, Preview and Library, that you drag by
their title bar and resize from the bottom-right grip; double-click a title to
fill the window and again to put it back. The layout is saved per app in the
browser (localStorage key `forge-panels:ai-studio`), and **Reset layout** in
the header restores the default. Below 760 px wide the cards stack in one
scrolling column. The cards come from the shared module
`shared/forge_panels.js` (any Forge app can mount it on a container whose
children carry `data-panel`); its browser test is
`tests/browser/forge_panels.html`, run by `tests/browser/run.sh`.
Verified 2026-09-27: 16/16 panel checks pass, full run.sh 567 PASS, and
headless screenshots at 1400 and 700 px wide look right.

## Notes

- No prompt filtering, no safety checker, no refusal logic anywhere in this
  stack, by design. Use it responsibly; you're the only thing between the
  model and the output.
- If you add a checkpoint to `models_catalog.py` yourself, test its actual
  sampler/steps/cfg rather than copying another entry's -- see the LCM note
  above for why that matters.

## Errors from the sd-server (2026-09-20)

`engine.EngineError` (the sd-server said no, or is not running) used to escape
as a bare 500 with a traceback in `outputs/ai-studio.log`. `src/app.py` now
has an exception handler that answers 502 with the message, so the page can
show it. Nothing else in the app changed that session.
