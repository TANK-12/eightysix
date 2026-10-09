# Brief: AI Studio gets the 2026 image and video models

date: 2026-10-08 · for: Claude (a fresh session on account "default") ·
from: Tetsu, session that did the research

## Emerson's ask (his words, tidied)

"Look up online the new models for images and videos that fit on 16 GB of
VRAM. Get the compact ones. The big ones: don't actually download them, just
get them connected. Do what you can to rehaul AI Studio to make it work.
Lots of great 3D environment and video generators are out now."

## Read first

1. `~/Forge/docs/library/ai-studio/2026-10-08-new-image-video-3d-models.md`
   is the research: hardware, engine build, candidate table with download
   repos and settings, 3D world generators, sources. Don't redo it, but
   check exact file names and sizes on Hugging Face before wiring.
2. `~/Forge/apps/ai-studio/README.md` and `WIP.md` (top entry, 2026-10-08:
   the Models panel was just made plain, with no sizes, px or jargon on the
   cards; `tests/test_model_picker_text.py` enforces it, so keep new
   labels and descriptions plain).
3. Skills: `forge-session`, `verify`, `safe-shell`.

## How AI Studio works today (verified by reading the code)

- `src/models_catalog.py` `CATALOG`: one dict per model, **single-file
  SD1.5/SDXL checkpoints only** (`url`, `filename`, optional `vae_url`/
  `vae_filename`, sampler/steps/cfg, default size).
- `src/model_manager.py`: downloads (`_download_file`), `is_installed`,
  `catalog_status()` (feeds `/api/models`), delete / delete-all, and
  `ServerManager._launch`, which starts **two `sd-server`s** (Vulkan iGPU +
  CPU) with `-m <checkpoint> [--vae]` plus conv-direct and vae-tiling flags.
- `src/engine.py` calls sd-server's A1111-style API (`/sdapi/v1/txt2img`,
  `/sdapi/v1/img2img`).
- "Video" today is **not a video model**: per-frame img2img with 2D camera
  warps, RIFE interpolation and ffmpeg (`longform.py`, `motion.py`,
  `hybrid.py`).

## What to build (proposed, show Emerson the plan first)

1. **Multi-file models in the catalog.** New entries need
   `diffusion-model` + `llm` (or `t5xxl`/umt5) + `vae` (+ `clip_vision`,
   `high-noise-diffusion-model` for Wan A14B, `audio-vae` for LTX). Make the
   entry a declarative list of parts `{role, url, filename}`, which maps
   roles to sd flags (one table), so adding a model stays one catalog entry.
   Share parts across models by filename (Z-Image and klein-4B both use a
   Qwen3-4B encoder; check whether one file serves both).
   `is_installed`, downloads, delete and delete-all must all walk the parts;
   a shared part stays while any kept model uses it (delete-all already does
   this for VAEs).
2. **"Connected but not downloaded"** big models: catalog entries with a
   flag (e.g. `"tier": "big"`). The card says, in plain words, that it's
   large and probably too heavy for this laptop, and the Download button
   asks for confirmation with the total size. The size can go in the
   confirm dialog, not on the card (Emerson removed tech info from the cards
   today).
3. **Real video models** (Wan2.2 TI2V 5B first). These need `-M vid_gen`.
   Check whether `sd-server` exposes video generation over HTTP; if not,
   run `bin/sd` (CLI) per job. Add a "model video" path next to the existing
   warp-based video, keeping the existing one.
4. **Engine update** only if needed (Qwen-Image 2.1 needs a build newer than
   2026-09-20). The current binary is `master-841-6b3edaa`. Back up `bin/`
   before replacing anything.
5. **3D worlds:** HY-World 2.0 is open but CUDA/PyTorch. Check its README
   for non-NVIDIA support; if none, write that down in the library doc and
   tell Emerson plainly rather than wiring a fake entry. Marble is cloud and
   closed (AI Studio is offline by design).

## Hard constraints

- **Disk: 27 GB free (88% used).** Memory rule: say the download size first
  and let Emerson decide. Rough guess for the compact set (Z-Image-Turbo Q4
  + Qwen3-4B Q4 + ae, klein-4B, Wan2.2 5B + umt5 + vae) is 12-18 GB, which
  would leave about 10 GB. Ask him: all of it, one of them, or plug in AN3
  (`/run/media/ejb/AN3`, not mounted today) and store models there with a
  fallback when it's unplugged.
- **No live GPU test generations without asking** (memory:
  gpu-test-verification-preference). Unit-test the catalog, command building
  and install logic; for real generations, ask Emerson or run one small,
  bounded test he OKs.
- 31 GiB RAM, no swap: a model that over-allocates freezes the laptop. Use
  `--offload-to-cpu` / `--auto-fit` / vae tiling and keep only one big model
  loaded. The CPU sd-server doubles the RAM use, so for big models it should
  probably not run.
- Jan shares the iGPU (memory: igpu-is-shared-between-jan-and-openvino).
- Done means: tests in `apps/ai-studio/tests` pass, black + pyright clean on
  touched files, a headless screenshot of the Models panel, and README/WIP
  updated with what's verified versus only reasoned about.

## State at handoff

Nothing built, nothing downloaded, no files in AI Studio changed by this
research. The earlier plain-cards change is in the working tree,
uncommitted, and recorded in `WIP.md`.

## Update 2026-10-08 (later): Emerson's extra asks, and more models

Read `~/Forge/docs/library/ai-studio/2026-10-08-ai-search-channel-findings.md`
too (AI Search YouTube channel: Qwen-Image 2.1 Q3 GGUF 3.19 GB, MiniMax H3
GGUF 6.7 GB, Ideogram 4, PiD upscaler, LTX 2.5, with HF repos).

His new asks, in his words, tidied:

1. "In AI Studio it was links to download which I press and then they
   download. Make it work like that." Every model, compact or big, is a
   card with a Download button; **nothing downloads until he presses it**.
   That also answers the disk question: show the total size in the confirm
   dialog, check free space before starting, and refuse with a plain message
   if it won't fit.
2. "Rebuild AI Studio to be better, because I made it with poor Opus 5.0."
   and "rebuild everything that doesn't work". This is a real overhaul, not
   just catalog entries: test every feature, write down what's broken in
   WIP.md, and fix or rebuild it. Show him the plan first.
3. He expects video, and especially **2D animated video**, to be the big
   win. 3D worlds are a nice-to-have and very likely NVIDIA-only.
