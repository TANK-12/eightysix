# 3D worlds in AI Studio: what can run here, and how

date: 2026-10-08 · for: both · author: Rei (helper-2, crew `ai-studio`)

Emerson's wish: world models that **build the world as you go**: you walk
through and the model draws what comes next. They should be Download/Delete
cards in AI Studio.

**In one line:** no real world model runs on this laptop as shipped. Every
one of them is a PyTorch project made for NVIDIA cards. What runs here today
is an **approximate walk-through** that uses the video engine AI Studio
already has (stable-diffusion.cpp with Wan2.1 VACE 1.3B). It is built and
tested with a fake engine. InSpatio-World 1.5 is the one real world model
that *might* run on the processor after some patching. Its runtime is written
up below for review, but nothing has been installed.

Marking used below:
- **[verified]**: checked on 2026-10-08 against the Hugging Face API, the
  GitHub source, our own `bin/sd --help`, or a test run here.
- **[reasoned]**: worked out from the docs or the code, but not run.

## The laptop

- Intel i5-1245U (12 threads) with **Iris Xe** graphics (Alder Lake). It
  shares the 31 GiB of RAM and there is **no swap**, so running out of
  memory freezes the machine. 81 GB of disk is free. [verified: `lscpu`,
  `free`, `df`]
- **PyTorch on the Intel graphics chip ("XPU") does not cover this chip.**
  PyTorch's validated list is Arc A/B, Core Ultra (Meteor Lake, Arrow Lake,
  Lunar Lake, Panther Lake) and Data Center Max. Alder Lake Iris Xe is not
  on it. [verified: pytorch `docs/source/notes/get_start_xpu.md`] So a
  PyTorch world model here would run on the **processor** (CPU), which is
  very slow. [reasoned]
- **Vulkan:** only stable-diffusion.cpp (and the ncnn tools) use the graphics
  chip here. None of the world-model projects has a Vulkan, GGUF, ONNX or
  OpenVINO path. [verified: no such files or mentions in the repos below]

## Each model, checked

Sizes are the sum of the files a run needs, from the Hugging Face API
(`?blobs=true`, LFS sizes). "Needs CUDA" means the shipped code stops or
breaks without an NVIDIA card.

| Model | What it does | Licence | Download a run needs | Needs CUDA? | Runs here? |
|---|---|---|---|---|---|
| **InSpatio-World 1.5** (`inspatio/world-1.5`) | one picture (or 4, or a video) + a camera path → a walk-through video; a causal, 4-step model that works in blocks of 3 frames | code + weights Apache-2.0 (depth model CC-BY-NC-4.0) | **24.4 GB**: model 5.68 GB + Wan2.1 1.3B text encoder/VAE/tokenizer 11.9 GB + Depth-Anything-3 6.76 GB + code 60 MB [verified] | **Yes, as shipped**: `inference.py` stops with "Scene inference requires a CUDA GPU"; `torch.cuda.current_device()` in `wan/modules/model.py`, `t5.py`, `pipeline/wan_wrapper.py`, `pipeline/memory.py`. But flash-attn is optional (a plain PyTorch attention fallback exists) and there are no custom CUDA kernels [verified by reading the code] | **Maybe, on the processor, after a patch.** Very slow, and memory is a real risk [reasoned] |
| **WorldCrafter-Fast** (`TencentARC/WorldCrafter-Fast`) | image or text → camera-controlled exploration with a 3D-aware memory | repo licence "NOASSERTION" (custom); HF card has none | **147.2 GB** (two 14B-class experts, text encoder 22.7 GB) [verified] | Yes: README says "require an NVIDIA GPU", installs CUDA 12.8 PyTorch, `flash-attn-3`, `xformers` [verified] | No: needs NVIDIA, and bigger than the free disk |
| **SolarWM** (`junchaoh-cs/SolarWM-Wan2.2-5B`) | turns a video model into an interactive world for long sessions | code Apache-2.0; weights **gated** (needs a Hugging Face sign-in) | smallest set: 5B base 34.2 GB + one 40 GB stage checkpoint = **about 74 GB** [verified sizes] | Yes: 50 `.cuda`/`"cuda"` sites, 83 `torch.cuda` calls, flash-attn imports [verified] | No: needs NVIDIA, gated, would nearly fill the disk. **Left out of the catalog** |
| **Evoke** (`AlayaLab/Evoke`, moved from `SII-YuanyangYin`) | joystick-driven world, events added by typing, hour-long sessions | Apache-2.0 | shipped model 57.25 GB + text encoder/VAE 23.2 GB = **80.5 GB** (whole repo 411 GB) [verified] | Yes: README pins torch 2.4 cu124, flash-attn 2.8.3, deepspeed, triton as "load-bearing"; interactive UI quoted on **five H200s** [verified] | No |
| **H3-World** (`DANNY621/H3-World`) | MiniMax-H3 driven by W/A/S/D + I/J/K/L keys | LoRA under the MiniMax-H3 community licence; code Apache-2.0 | add-on 131 MB, but needs the **33B** MiniMax-H3 base [verified] | The model card says loading the add-on in an unmodified H3 pipeline "will not reproduce the reported behavior": it needs their attention patch [verified]. So sd.cpp (which does run H3) cannot use it as a plain LoRA [reasoned] | No. Left out of the catalog |
| **HY-World 2.0** (`tencent/HY-World-2.0`) | text/image → 3D Gaussian-splat worlds and meshes | Tencent custom licence ("other") | **174.7 GB** repo (HY-Pano 32 shards + WorldMirror 5 GB), and the pipeline fetches more on first run [verified] | Yes: bundles `gsplat` CUDA kernels (`.cu` files), `cupy`, flash-attn; README says CUDA 12.8 [verified] | No. Left out of the catalog (its file set can't be pinned) |
| **HY-WorldPlay** (`tencent/HY-WorldPlay`) | Tencent's interactive world model | custom | 189 GB repo, single models 34 to 42 GB [verified] | assumed yes like HY-World [reasoned] | No. Left out |
| **4DAnyone** (`AntResearch/4DAnyone`) | a video of a **person** → multi-view videos → 4D splat. Not a walk-through | mixed, per asset | 21.3 GB (Wan2.2 5B based + human-pose models) [verified] | not checked in code; pose stack (GVHMR, ViTPose, YOLO) is CUDA-first [reasoned] | No, and it is not a world model. Left out |
| **One Video One World** (`yisuanwang/OVOW`) | a video → explorable 3D/4D scene, GLB export | code licence unclear; bundles non-commercial parts (FoundationPose, SpaTrackerV2) | many sub-models; README asks for **≥40 GB of graphics memory** [verified] | Yes: compiles CUDA extensions (`.cu`), needs `nvcc` [verified] | No. Left out (the HF repo `343GltySprk/ovow` is a different project) |

Closed or cloud-only, so never a card: **Atlas** (World Labs), **Marble**
(World Labs), **Runway GWM Worlds 2**.

### Can sd.cpp stand in?

- **InSpatio's weights are Wan2.1 1.3B's layout** with a `model.` prefix and
  a 36-channel input (noise + warped-render latent + mask), fp32. [verified:
  read the safetensors headers of both files, same 825 tensors, same shapes
  except `patch_embedding` (36 vs 16 input channels)]. sd.cpp could probably
  *load* it after renaming, but its causal block-by-block sampling and the
  way it feeds the warped render are not in sd.cpp, so it would not behave
  like InSpatio. [reasoned] Not pursued.
- **Wan2.1 VACE 1.3B runs in sd.cpp** with a control video (`--control-video
  <dir>`), a reference picture (`-i`) and `--vace-strength`. [verified: our
  `bin/sd --help` (build master-841) lists all three; sd.cpp `docs/wan.md`
  shows VACE 1.3B T2V/R2V/V2V commands and links `calcuis/wan-1.3b-gguf`].
  That is what the walk-through below uses.
- Wan2.2 TI2V 5B also runs in sd.cpp (helper-1's "Short Clips" card), but it
  has no control-video input, so it can't follow a camera path. [reasoned
  from docs/wan.md]

## What AI Studio offers (catalog/world.py)

| Card id | Label | Tier | Runner | Download | Can run here |
|---|---|---|---|---|---|
| `world-walk` | Walk Into a Picture | compact | `walk-sd` | 6.28 GB: VACE 1.3B Q8_0 2.37 GB + umt5 Q4_K_M 3.66 GB + Wan2.1 VAE 0.25 GB. The last two are **shared** with helper-1's video cards (same filename, url and size) | yes: our engine has `--control-video` [verified]; speed untimed |
| `inspatio-world-1.5` | Real Walk-Through World | big | `inspatio` | 24.4 GB (11 parts incl. code) | no: "Needs the 3D world runtime, not set up yet" |
| `worldcrafter-fast` | Explorer World | big | `worldcrafter` | 147.2 GB (45 parts) | no: "Needs an NVIDIA graphics card" |
| `evoke` | Steerable World | big | `evoke` | 80.6 GB (32 parts) | no: "Needs an NVIDIA graphics card" |

Notes on the entries:
- Every `size_bytes` came from the HF API, and the code archives were
  downloaded once and their bytes counted. The source revision is in a
  comment above each file list. Downloads use `resolve/main`, like the rest
  of the catalog. [verified]
- World parts carry an extra key, **`dest`**: where the runner links the
  stored file inside its runtime folder, because these projects expect their
  own layout (`checkpoints/Wan2.1-T2V-1.3B/...`). Stored filenames get a
  prefix (`wan2.1-t2v-1.3b--config.json`), because many projects ship files
  with the same name.
- `code` parts are GitHub archives pinned to a commit
  (`codeload.github.com/<repo>/tar.gz/<sha>`). GitHub does not promise that
  archive bytes stay identical forever, so if a size check fails, re-count
  it. [reasoned]
- InSpatio's first run converts the 11.4 GB T5 `.pth` to `.safetensors`
  (another 11.4 GB) unless the patch below drops the `.pth` afterwards.
  [verified in `run_scene_inference.py: ensure_t5_weights`]

## The walk-through runner (`walk-sd`): how it works

**Verified only with a fake engine. No real generation has been run.**

1. The start picture is cropped and resized to the walk's shape (default
   512×288), and becomes frame 1.
2. Each **step** is a list of moves (`forward`, `back`, `left`, `right`,
   `rise`, `sink`, `turn_left`, `turn_right`, `look_up`, `look_down`,
   `stay`). `camera.plan_chunk` turns them into one camera pose per frame
   (17 frames per step by default).
3. Each pose becomes a **flat 2D warp** of the current frame. Walking zooms
   in or out; stepping and turning slide the picture; anything not known yet
   is grey. A sweep test checks every move at 7 headings, and the warps were
   looked at on a grid picture.
4. The sd CLI runs `-M vid_gen` with VACE: the warped frames go in as
   `--control-video`, the current frame as `-i`, plus the prompt. The new
   frames (minus the repeated first one) are added to the session. The last
   frame becomes the start of the next step.
5. The worker then waits for the next step. Stop, or no move for 30
   minutes, ends it.

What it is not: there is no 3D memory and no parallax. Walking back to
where you started will not give the same view. Each step costs one full
Wan 1.3B video run on the Iris Xe; at 512×288, 17 frames and 12 steps, a
guess is **several minutes per step**. Nothing has been timed. [reasoned]
Settings live in the entry (`settings` + `sd_args`) and can be overridden
per session.

It uses the graphics chip like any sd run. **app.py should stop or pause
the image sd-server before starting a world**, and the session must not
overlap a Jan model load (see the igpu memory note). [reasoned]

## Runner contract for helper-1 (app.py)

Import `worlds` (it sits in `src/`, next to `catalog`). Each function returns
a plain dict and raises a `WorldError` subclass that carries a plain message
and an HTTP `status_code`: `WorldError` 400, `WorldNotFound` 404,
`WorldBusy` 409, `WorldCannotRun` 409.

```python
worlds.runner_status(entry) -> (can_run: bool, note: str)  # for card can_run/run_note
worlds.ACTION_LABELS -> {"forward": "Walk forward", ...}   # move buttons
worlds.runtime_plan(runner_id) -> dict | None               # what a PyTorch runtime would install
worlds.start_session(entry, prompt="", image=None, actions=None, settings=None) -> poll dict
worlds.step_session(sid, actions) -> poll dict              # queue the next moves
worlds.poll_session(sid, since=0) -> poll dict
worlds.frame_path(sid, name) -> Path                        # "000001.png"; name is checked
worlds.stop_session(sid) -> poll dict                       # ends the worker's whole process group
worlds.list_sessions() -> [poll dict without frames]        # newest first
worlds.make_clip(sid, fps=None) -> Path                     # walk.mp4 via ffmpeg
```

Poll dict: `{id, model_id, state, message, chunk, frame_count, frames
(names after the first `since`), since, fps, queued_steps, created}`.
`state` is one of `starting`, `working`, `waiting` (ready for a move),
`stopped`, `done`, `failed`. `message` is plain and can be shown as it is.

Suggested routes:

| Route | Calls |
|---|---|
| `POST /api/worlds/{model_id}/start` body `{prompt, image?, actions?, settings?}` (image = an upload or library file the app resolves to a path) | `start_session(CATALOG[model_id], ...)` |
| `GET /api/worlds/sessions` | `list_sessions()` |
| `GET /api/worlds/sessions/{sid}?since=n` | `poll_session` |
| `POST /api/worlds/sessions/{sid}/step` body `{actions: [...]}` | `step_session` |
| `GET /api/worlds/sessions/{sid}/frames/{name}` | `FileResponse(frame_path(...))` |
| `POST /api/worlds/sessions/{sid}/stop` | `stop_session` |
| `POST /api/worlds/sessions/{sid}/clip` | `make_clip` → serve or add to the library |
| `GET /api/worlds` (its `actions` list) | `ACTION_LABELS` |

- Sessions live in `config.OUTPUTS_DIR / "worlds" / <sid>/`, which follows
  `AI_STUDIO_OUTPUTS_DIR`. Runtimes would live in
  `config.MODELS_DIR / "worlds" / "runtime" / <runner>/`.
- Parts are looked up in `config.PARTS_DIR`, then `LEGACY_MODEL_DIR`, then
  `models/sd/` (`runners.PART_DIRS`). A missing part makes `start` raise
  `WorldCannotRun("Download it first")`.
- Only one session runs at a time. Sessions left running when the app
  restarts show as `stopped`.
- The download code should skip the `dest` key; it only matters to world
  runners.

## What the frontend (helper-3) needs

- **World card:** same Download/Delete card as the others, plus `can_run` and
  `run_note` from `runner_status`. When it is installed and can run, show a
  **Play** button.
- **World player:** a start picture (upload or pick from the library), an
  optional prompt, and **move buttons** from the `actions` list in `GET /api/worlds` (arrows /
  WASD feel). Pressing a move calls `step`. Moves pressed while it is busy
  queue up (`queued_steps`). Show frames as they come in (`poll` with
  `since=frame_count`, every 1 to 2 seconds, playing them at `fps`), the
  plain `message`, a **Stop** button, and **Save clip** (`/clip`). Make
  clear that each move takes minutes, with a "drawing the next part" state.
  Fullscreen-friendly (Emerson wants Forge apps usable fullscreen).

## The InSpatio runtime: exactly what installing it would mean (not done)

Nothing is installed. Emerson reviews this first. It is **not** a
press-to-install part, because the shipped code needs CUDA and the CPU path
is untested.

- Folder: `models/worlds/runtime/inspatio/` with `.venv/`, `src/` (the
  pinned code part unpacked), `checkpoints/` (parts linked by `dest`) and
  `aistudio_adapter.py`.
- Python **3.10** (`uv python install 3.10`; uv is at `/usr/bin/uv`). The
  system Python 3.14 has no wheels for the pinned `numpy==1.26.4` and
  `decord==0.6.0`. [reasoned from the pins]
- `uv venv --python 3.10 .venv`, then `pip install --extra-index-url
  https://download.pytorch.org/whl/cpu torch==2.10.0+cpu
  torchvision==0.25.0+cpu` and the rest of `environment.yml` without the
  `+cu126` builds: av 13.1.0, addict, decord 0.6.0, diffusers 0.37.0,
  easydict, einops, evo, ftfy, imageio, moviepy 1.0.3, numpy 1.26.4,
  omegaconf, opencv-python 4.11.0.86, Pillow 12.0.0, plyfile, pycolmap
  4.0.2, regex, safetensors 0.7.0, scipy 1.15.3, tqdm, transformers 4.57.6,
  trimesh. Then `pip install --no-deps depth-anything-3==0.1.1`. (The exact
  list is in `runners.py`, `RuntimeSpec`.)
- Size: the torch CPU wheel is **188.8 MB** and torchvision **1.9 MB**
  [verified: HTTP content-length on download.pytorch.org]. About **2.5 GB**
  installed for the whole runtime [reasoned].
- **CPU patch needed** [verified that these lines exist; the fix itself is
  reasoned]: `inference.py` (drop the CUDA check and `set_device`, use
  `torch.device("cpu")`, skip `torch.cuda.synchronize/empty_cache`);
  `wan/modules/model.py:20` and `wan/modules/t5.py:478`
  (`torch.cuda.current_device()` → the tensor's device); `wan/modules/model.py:66`
  (`autocast('cuda')` → `'cpu'`); `wan/modules/vae.py` (`device="cuda"`
  default, `torch.cuda.amp`); `pipeline/wan_wrapper.py:35` and
  `pipeline/memory.py:44-49` (memory stats → return 0 on CPU); run the DiT in
  bf16 to halve its 5.7 GB fp32 load.
- **Memory risk** [reasoned]: the T5 text encoder alone is 11.4 GB in bf16,
  the DiT is 5.7 GB in fp32, and the depth net is 6.8 GB. Unless the
  adapter encodes the prompt and frees T5 before loading the rest, the peak
  goes past the ~12 GB usually free. With no swap, that freezes the laptop.
  Swapping in the smaller Apache-licensed `depth-anything/DA3-LARGE-1.1`
  (1.64 GB) would help, but it is not known to be compatible.
- Adapter: `aistudio_adapter.py` would speak `worlds/protocol.py`. It would
  turn moves into `target_tcw.txt` with `camera.tcw()` (same OpenCV
  convention InSpatio uses), build a scene folder (picture, depth from DA3,
  intrinsics), run `run_scene_inference.py --scene_dir`, and add `pred.mp4`'s
  frames. A test with a fake adapter already exercises this path.
- Expected speed on the CPU: **minutes to tens of minutes per 5-second
  clip** [reasoned, not measured].

## Files

- `src/catalog/world.py`: the four entries.
- `src/worlds/__init__.py`: front door (above).
- `src/worlds/runners.py`: runner registry, `runner_status`, runtime specs.
- `src/worlds/session.py`: `SessionManager` (subprocess, stop by process group).
- `src/worlds/protocol.py`: the file protocol (stdlib only, copyable into a runtime).
- `src/worlds/camera.py`: moves → poses, `tcw` matrices, 2D warps.
- `src/worlds/walk_sd_worker.py`: the walk-through worker.
- `tests/test_worlds_catalog.py`, `tests/test_worlds_camera.py`,
  `tests/test_worlds_session.py`, `tests/worlds_fakes.py` (fake sd binary).

## Next steps (for Emerson to OK)

1. Download `world-walk` (6.3 GB, of which 3.9 GB is shared with the video
   cards) and run one step at 512×288 with the sd-server stopped. Time it and
   look at it. This is the first real check of the whole idea.
2. If the warps look too flat: add a depth estimate (for example Depth
   Anything V2 Small as ONNX through onnxruntime; that is a new package, so
   it needs review) to get real parallax in the control frames.
3. Only if (1) shows the iGPU is too weak and Emerson wants the real thing:
   review the InSpatio runtime above.
