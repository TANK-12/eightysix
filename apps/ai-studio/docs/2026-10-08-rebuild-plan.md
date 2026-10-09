# AI Studio rebuild plan and shared contract

date: 2026-10-08 · for: both · commander: Rin / Tetsu (session ejb-a6), crew `ai-studio`

## Emerson's asks (his words, tidied)

1. Every new model (compact and big, image, video and 3D world) is a card
   with **Download** and **Delete**. Nothing downloads until he presses it.
2. "Rebuild AI Studio to be better, I made it with poor Opus 5.0", and
   "rebuild everything that doesn't work".
3. He is most interested in **3D world models that build the world as you
   go** (interactive / walk-through), then video, especially 2D animated.

Research to use (don't redo it): `~/Forge/docs/library/ai-studio/2026-10-08-new-image-video-3d-models.md`
and `.../2026-10-08-ai-search-channel-findings.md`. Session brief:
`~/Forge/sessions/2026-10-08-ai-studio-new-models.md`.

## Facts

- Disk 2026-10-08: **81 GB free** (230 GB disk). The iGPU is an Intel Iris
  Xe sharing 31 GiB RAM, no swap. Jan shares the iGPU.
- Engine: stable-diffusion.cpp `bin/sd`, `bin/sd-server`, build
  master-841-6b3edaa (2026-09-04), Vulkan. Qwen-Image 2.1 needs a newer
  build.
- Port 8430 is Emerson's live AI Studio. Helpers use scratch ports
  (9011-9030) and a scratch copy or env-overridden dirs, never his live
  models/outputs.
- **No model downloads by helpers** (test downloads with tiny files or a
  local http server). **No GPU generations** until Emerson OKs them; use a
  fake sd-server stub in tests.

## Catalog schema (one registry, declarative)

`src/catalog/` package: `__init__.py` merges every `catalog/<kind>.py`
`ENTRIES` list into `CATALOG` (id -> entry). Adding a model = one entry in
one file. Kinds: `image`, `video`, `world`. Old SD1.5 entries move into
`catalog/image.py` unchanged in meaning (a single part with role
`checkpoint`, plus `vae` if any).

```python
{
  "id": "z-image-turbo",
  "kind": "image",            # image | video | world
  "label": "Fast and Detailed",   # plain words, no sizes/px/jargon
  "blurb": "...",                 # plain, one or two sentences
  "tier": "compact",          # compact | big ("big" = probably too heavy here)
  "engine": "sd",             # sd | sd-video | world:<runner-id>
  "parts": [                  # every file the model needs
    {"role": "diffusion", "url": "https://huggingface.co/.../resolve/main/x.gguf",
     "filename": "x.gguf", "size_bytes": 3456789012},
    {"role": "llm", "url": "...", "filename": "Qwen3-4B-...gguf", "size_bytes": ...},
    {"role": "vae", "url": "...", "filename": "ae.safetensors", "size_bytes": ...},
  ],
  "settings": {"steps": 8, "cfg_scale": 1.0, "sampler": "euler", "width": 1024, "height": 1024},
  "notes": "technical notes, never shown on a card",
}
```

- Roles for sd: `checkpoint`, `diffusion`, `high_noise_diffusion`, `llm`,
  `t5xxl`, `clip_l`, `clip_g`, `clip_vision`, `vae`, `audio_vae`, `lora`.
  One table in `src/engine_flags.py` maps role -> sd flag. World parts use
  role `weights` (or `code` for a pinned git archive).
- A part is stored once, at `models/parts/<filename>`, and shared by filename
  across models. Delete removes only parts that no other **installed** model
  uses. Old files in `models/sd/` keep working (look there too).
- Every `size_bytes` must be checked against Hugging Face (HEAD request or
  the API) by whoever writes the entry. Never guess.

## HTTP API contract (backend helper-1 owns it, frontend helper-3 uses it)

- `GET /api/models` -> `{"models": [card...], "disk": {"free_bytes": n}}`.
  card = `{id, kind, label, blurb, tier, installed, active, can_run,
  run_note, download: null | {state: "running"|"failed"|"cancelled",
  done_bytes, total_bytes, message}}`. `can_run` false + plain `run_note`
  when the engine/runner can't use it yet (e.g. "Needs an engine update" or
  "Needs the 3D world runtime, not set up yet").
- `GET /api/models/{id}/quote` -> `{total_bytes, needed_bytes, free_bytes,
  fits: bool, message}` (needed = parts not already on disk; fits keeps 5 GB
  spare).
- `POST /api/models/{id}/download` -> starts it (409 if running, 507 with a
  plain message if it won't fit). Resumable (`.part` files + Range).
- `POST /api/models/{id}/cancel`, `DELETE /api/models/{id}` (returns freed
  bytes), `POST /api/models/{id}/activate`, existing delete-all routes stay.
- Generation: existing `/api/generate/image` and `/api/generate/video`
  keep working; new `POST /api/generate/model-video` (prompt, optional
  start image, frames, size) for real video models; worlds:
  `POST /api/worlds/{id}/start` etc. defined by helper-2 in
  `docs/WORLDS.md`, wired into app.py by helper-1.

## Who owns what (crew `ai-studio`)

| Helper | Task | Owns |
|---|---|---|
| helper-1 | backend core: catalog package, parts, download/quote/cancel/delete, engine flags, model-video path, engine update (new build in `bin/next/`, old kept), app.py routes | `src/catalog/` (except `world.py`), `src/models_catalog.py`, `src/model_manager.py`, `src/engine.py`, `src/engine_flags.py`, `src/video_models.py`, `src/config.py`, `src/app.py`, `bin/`, `tests/test_catalog*.py`, `tests/test_parts*.py`, `tests/test_api*.py`, `tests/test_delete*.py` |
| helper-2 | 3D worlds: which world models can be offered, catalog entries, a runner contract | `src/catalog/world.py`, `src/worlds/`, `tests/test_worlds*.py`, `docs/WORLDS.md` |
| helper-3 | frontend rebuild | `static/` (may split into `static/css/`, `static/js/`), `tests/test_model_picker_text.py`, `tests/check_ui*.py` |
| helper-4 | audit and fix the existing features | `src/longform.py`, `src/motion.py`, `src/hybrid.py`, `src/library.py`, `tests/test_u1_robustness.py`, `tests/test_features*.py`, `docs/AUDIT.md` |

Commander only: `README.md`, `WIP.md`, hub docs, this file.
