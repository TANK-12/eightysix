# Codec Lab — manifest

_Written 2026-09-07 for a reader with no conversation history. The machine-
readable version of this is the `manifest` block in `forge_app.json`._

## What this is (and where the code actually lives)

`apps/codec-lab/` is **only a pointer**. The real code is a separate git repo
at **`~/anime-codec-lab`** — its own `.venv`, its own Wine cross-build tooling,
its own history. The `"root"` field in `forge_app.json` tells `forge.py` to
launch it from there, on **port 8431** (`order` 4).

**Codec Lab** is a research harness that races experimental anime-compression
ideas against a real AV1 control on the same clip, judged by the same numbers:
file size, bits/pixel, PSNR, SSIM, encode / decode time. The point isn't to
commit to a format — it's to make trying an idea cheap (one file + one registry
entry) so bad ideas get killed fast.

For deep detail — the file-format spec, every platform-specific build gotcha,
the rebuild checklist — read **`~/anime-codec-lab/README.md`** and
**`~/anime-codec-lab/BUILD_MANIFEST.json`**.

## What the app does

- **Set up a run:** pick or upload a source clip, set trim / scale / fps,
  configure any strategy's parameters via a form built from its schema (nothing
  hardcoded), queue several configs as one batch — a real parameter sweep.
- **Automatic control run:** every batch gets or reuses a fixed AV1 baseline
  (`libsvtav1` crf 30) for that exact clip + trim, so every comparison has a
  real codec to judge against.
- **Results database:** SQLite (`lab.db`) — search by strategy / clip / params
  text, filter by min ratio / PSNR / SSIM, sort any column. Every run ever done
  persists across restarts; each row is tagged `is_control` or not.
- **Three-way comparison:** click a row for original vs control codec vs
  result, each playable with audio; a dropdown swaps in any other completed run
  against the same clip + trim.
- **`.acv` export:** package a run's raw encoded bytes + trimmed passthrough
  audio (WAV) into a standalone `.acv` file (`core/container.py`). Codec Player
  and the shipped `player.py` binary open one with no lab, no ffmpeg and no
  source clip.

## The strategies

Registered in `strategies/registry.py` (label + description + params schema +
`build()` factory):

| Strategy | Idea | Current standing |
|---|---|---|
| `ffmpeg_baseline` | wraps an existing codec as the control group | — |
| `palette_motion` | palette quantization + whole-frame-vectorized motion-compensated block copy / near-match / GOP | good prediction, bottlenecked by zlib entropy coding |
| `downscale_proxy` | downscale + existing codec + sharp upscale | **practical leader** — beats full-res AV1 on size at similar quality, zero custom codec machinery |
| `vector_art` | per-frame vectorization, no motion | weakest on soft/gradient AMV footage; retest on flat cel-shaded source |
| `optical_flow` | dense Farneback motion warp + quantized residual | **best quality** (SSIM up to 0.975), **worst ratio** — per-pixel residuals compress poorly with a byte-oriented compressor |
| `frame_memory` | whole-clip content-addressable block dictionary, no motion search | matches `palette_motion`'s ratio with a simpler mechanism |
| `temporal_skip` | keyframes only + flow-interpolated skip frames | highest variance by design — look at min PSNR, not mean |

Add one: drop a `Strategy` subclass in `strategies/` (`encode(frames) -> bytes`,
`decode(data, shape) -> frames`) and add a `registry.py` entry. It then shows
up as a card with its own form.

**Cross-cutting finding:** the bottleneck in every custom codec here is the
entropy coder (plain zlib), not the prediction idea. Fixing residual / entropy
coding is the top priority in the repo README.

## Where data lives

Resolved by `~/anime-codec-lab/core/paths.py` `data_dir()`:

```
lab.db                     the results store
results/runs/<id>/         decoded.mp4, original.mp4, encoded.bin, audio.wav
clips/                     source clips (drop or symlink a file here to add it permanently)
```

Frozen `.exe` builds put these next to the executable so they survive restarts.

## Dependencies and services

**No networked services.** **Requires `ffmpeg` + `ffprobe` at runtime** —
`core/clip_loader.py` shells out to load / trim / scale video and mux / extract
audio.

**Python:** numpy, opencv (non-headless / T-API), scipy, fastapi, uvicorn, and
`python-pywebview` (system package, for the native `desktop_app.py` window).
Shares `~/anime-codec-lab/.venv`. `intel-compute-runtime` enables the OpenCL /
`cv2.UMat` path in `palette_motion` (though the bigger speed win was
algorithmic — see the repo README's "GPU + speed").

## Memory guard (read before raising `scale`)

Decoding a trim to raw RGB is the largest allocation the app makes and is
driven entirely by numbers the user types. `core/limits.py` projects the peak
from ffprobe's dimensions and refuses a run before allocating anything:

- `POST /api/runs` returns **413** with a suggested `scale`.
- Default ceiling is 4 GiB peak; override with `CODEC_LAB_RUN_BUDGET_BYTES`.
- A `running` row left behind by a killed process is reaped to `interrupted` at
  startup; resuming is an explicit choice (`GET /api/runs/resumable`,
  `POST /api/runs/resume`) and re-checks the budget.

This machine has 31 GiB and **no swap**, so overshooting freezes the laptop.

## Running it

```bash
cd ~/anime-codec-lab
python3 desktop_app.py                                  # native window (primary)
# or:  uvicorn server:app --host 127.0.0.1 --port 8731  # browser tab
# or:  python3 harness.py --source clip.mkv --start 45 --duration 3 --scale 0.25 --fps 24   # scriptable CLI
```

In Forge it runs on **port 8431**, launched from the `root` path. `server.py`
mounts `/shared` from `FORGE_SHARED_DIR` when Forge sets it and skips it
otherwise, so it still runs standalone unchanged.

## API surface

`server.py` — `GET /api/clips`, `POST /api/clips/upload`, `GET /api/strategies`,
`POST /api/runs`, `GET /api/runs/resumable`, `POST /api/runs/resume`,
`GET /api/results`, `GET /api/runs/{id}`, `GET /api/runs/{id}/video/{which}`,
`GET /api/runs/{id}/export.acv`.

## Known gaps

- Custom formats carry **video only** — audio is passthrough (muxed onto
  previews so comparisons are watchable, but no strategy encodes audio, and
  there's no real container bundling a video-plan stream with audio/subtitle
  tracks yet).
- Localhost / no auth — a personal research tool, not meant past `127.0.0.1`.
- Two workers process the queue **sequentially**; a big batch of slow configs
  queues rather than running at once.
- No NVIDIA GPU on this machine, so no CUDA path.

## Also ships as

`AnimeCodecLab` / `AnimeCodecLab.exe` and `AnimeCodecPlayer` /
`AnimeCodecPlayer.exe` — cross-built from this Linux machine via Wine + a
genuine Windows Python + PyInstaller (`winbuild/` holds the Wine prefix). In
`~/anime-codec-lab/release/`. Rebuild after touching `player.py`,
`desktop_app.py`, `server.py` or `static/index.html` — commands in
`BUILD_MANIFEST.json`.
