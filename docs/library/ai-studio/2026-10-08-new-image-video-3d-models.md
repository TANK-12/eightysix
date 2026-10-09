# New image, video and 3D-world models for AI Studio (research, Oct 2026)

date: 2026-10-08 · for: both

Research done by Tetsu (Opus 5.5) for Emerson's ask: "look up online for the
new models for images and videos that fit on 16GB of VRAM, get the compact
ones, connect the big ones without downloading, rehaul AI Studio to make it
work; lots of great 3D environment and video generators are out now."
Nothing has been built or downloaded yet. The build brief is
`~/Forge/sessions/2026-10-08-ai-studio-new-models.md`.

## The hardware, and what "16 GB" means here

- GPU is the **Intel Iris Xe** iGPU (Alder Lake GT2), sharing 31 GiB system
  RAM. "16 GB of VRAM" = the most the iGPU can borrow. No swap: running out of
  RAM freezes the laptop.
- Real speed will be far below the online figures (those are RTX 4090/4080).
  Expect minutes per 1024px image on the bigger models and much longer for
  video. Nothing here has been timed on this laptop yet.
- Disk: **27 GB free of 230 GB (88% used)** on 2026-10-08. AN3 USB drive was
  not mounted.

## The engine AI Studio uses

AI Studio runs everything through **stable-diffusion.cpp** (`bin/sd`,
`bin/sd-server`), build `master-841-6b3edaa` (binary dated 2026-09-04),
Vulkan backend. Its `--help` already has `--diffusion-model`, `--llm`,
`--t5xxl`, `--clip_vision`, `--high-noise-diffusion-model`, `--audio-vae`,
`-M vid_gen`, `--video-frames`, `--offload-to-cpu`, `--auto-fit`.
`strings` on `sd-server` finds z_image, klein, flux2, ltx, minimax, hunyuan,
krea, lens, anima, chroma, so those architectures are compiled in
(reasoned from strings, not tested). **Qwen-Image 2.1 support landed
2026-09-20, after this build**, so that one needs a newer binary.

Upstream supported list (README, fetched 2026-10-08): image: SD1/2, SDXL,
SD3/3.5, FLUX.1, FLUX.2-dev/klein, Lens, Chroma, Chroma1-Radiance,
Qwen-Image (+2.1), PiD, LongCat, Z-Image (+L2P), MiniT2I, SenseNova U1.5,
Ovis, Anima, ERNIE-Image, Boogu, Krea2, Mage-Flow, SeFi, HiDream-O1,
Ideogram4, LLaDA-Image, Ming-Image, PixArt. Edit: FLUX.1-Kontext, Qwen-Image
Edit, LongCat Edit, Boogu Edit, Mage-Flow-Edit, LLaDA Edit. Video:
Wan2.1/2.2, MiniMax-H3, LTX-2.3/2.5, HunyuanVideo 1.5, LingBot-Video.

## Candidates

Compact = small enough to download now and plausible on the iGPU.
Big = list in the catalog ("connected") but do not download.

| Model | Kind | Files (from sd.cpp docs) | Settings | Class |
|---|---|---|---|---|
| **Z-Image-Turbo** (Alibaba, 6B) | image | diffusion `leejet/Z-Image-Turbo-GGUF` (Q3_K/Q4); llm `unsloth/Qwen3-4B-Instruct-2507-GGUF` Q4_K_M; vae `ae.sft` from `black-forest-labs/FLUX.1-schnell` | cfg 1.0, 8 steps | compact, top pick |
| **FLUX.2-klein 4B** (BFL) | image (+edit) | diffusion flux-2-klein-4b (GGUF quants exist on HF); llm Qwen3-4B (same family as Z-Image: check if the same file works); vae `flux2_ae.safetensors` | cfg 1.0, 4 steps | compact |
| **Wan2.2 TI2V 5B** | text/image to video | diffusion 5B GGUF; text encoder umt5_xxl (GGUF); vae `wan2.2_vae` | needs `-M vid_gen`; "Wan vae requires really much VRAM", TAE is the lighter fallback | compact video, top pick |
| Z-Image (base) | image | `unsloth/Z-Image-GGUF` + same llm/vae | cfg 5.0 | big-ish (optional) |
| FLUX.2-klein 9B | image | klein-9b + Qwen3-8B llm + flux2_ae | cfg 1.0, 4 steps | big |
| Qwen-Image / Qwen-Image 2.x | image + edit, 2K | GGUF ~12-13 GB at Q4 (online figure) | needs newer engine for 2.1 | big |
| FLUX.2-dev | image | `city96/FLUX.2-dev-gguf` + Mistral-Small-3.2-24B llm; ~19 GB at Q4_K_S | | too big for 16 GB |
| Wan2.2 A14B T2V/I2V | video | high-noise + low-noise 14B GGUFs, umt5_xxl, wan_2.1_vae (+clip_vision_h for I2V) | | big |
| LTX-2.3 (22B, video + audio) | video | `unsloth/LTX-2.3-GGUF` + `unsloth/gemma-3-12b-it-GGUF` + connectors/vae/audio-vae in the same repo | cfg 6.0, 33 frames, 24 fps | big |
| LTX-2.5 | video + audio | `vantagewithai/LTX-2.5-GGUF` + `Lightricks/LTX-2.5` Gemma4-12B encoder, conv video VAE, audio VAE | cfg 3.0, 121 frames | big |
| HunyuanVideo 1.5 | video | see `docs/hunyuan_video.md`; ~14 GB min with offload (online figure) | | big |
| MiniMax-H3 | video | see `docs/minimax_h3.md` | | not checked |

## 3D environment generators

- **HY-World 2.0** (Tencent, open weights, April 2026): text/image/video to
  navigable 3D Gaussian-splat scenes, meshes and point clouds; exports to
  Blender/Godot-friendly formats. Repo `Tencent-Hunyuan/HY-World-2.0`. A
  PyTorch/CUDA project; not checked whether it can run without an NVIDIA GPU.
  Very likely not runnable on the Iris Xe.
- **Marble** (World Labs): best-in-class but closed and cloud-only; exports
  Gaussian splats (2M or 500k) and meshes. Doesn't fit AI Studio's
  "no cloud" rule.
- None of these run through stable-diffusion.cpp, so "connecting" them to
  AI Studio means a separate runner, not a catalog entry.

## Sources

- stable-diffusion.cpp README and docs (z_image.md, flux2.md, wan.md,
  ltx2.md): https://github.com/leejet/stable-diffusion.cpp
- https://willitrunai.com/image-models/best-for/16gb ,
  https://willitrunai.com/video-models/best-for/16gb
- https://localaimaster.com/blog/best-local-image-models-compared
- https://www.thundercompute.com/blog/best-open-source-ai-video-generation-models
- https://ltx.io/blog/best-open-source-video-generation-models
- https://github.com/Tencent-Hunyuan/HY-World-2.0 ,
  https://www.worldlabs.ai/blog/marble-world-model
