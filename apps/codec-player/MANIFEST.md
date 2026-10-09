# Codec Player — manifest

_Written 2026-09-07 for a reader with no conversation history. The machine-
readable version of this is the `manifest` block in `forge_app.json`._

## What this is (and where the code lives)

`apps/codec-player/` is a **pointer**, like `apps/codec-lab/`. The code is at
**`~/anime-codec-lab/web_player.py`**; the `"root"` field in `forge_app.json`
points `forge.py` there. Runs on **port 8432** in Forge (`order` 5).

Codec Player is the in-hub equivalent of the standalone `player.py`: upload a
`.acv` file, and it

1. reads the header for the strategy that produced it (`core/container.py`
   `load_acv()` — strategy id + params + encoded bytes + optional WAV),
2. decodes the frames with that strategy from `strategies/`,
3. serves the reconstructed video at `/video/{play_id}` as an mp4, with the
   audio muxed back in from the file's embedded WAV.

No lab, no source clip, and no ffmpeg-at-runtime dependency to play an existing
`.acv`.

## Features

| Step | What happens |
|---|---|
| **Open a `.acv`** | Drop or upload the file; the header names the strategy and carries its params. |
| **Decode + play** | The named strategy reconstructs the frames; the result plays as an mp4 with the passthrough audio. |

The UI is `~/anime-codec-lab/static/player.html`.

## Where data lives

Nothing is persisted.

## Dependencies and services

**No services.** Reuses `~/anime-codec-lab`'s `core/` + `strategies/` and its
`.venv` (numpy, opencv, fastapi, uvicorn). `web_player.py` mounts `/shared`
from `FORGE_SHARED_DIR` when Forge sets it and skips it otherwise, so it runs
standalone unchanged.

## Running it standalone

```bash
cd ~/anime-codec-lab
uvicorn web_player:app --host 127.0.0.1 --port 8432
```

Then open <http://127.0.0.1:8432>. In Forge it runs on the same port via the
`root` path.

## API surface

`web_player.py` — `GET /` (the page), `POST /api/open` (upload + decode a
`.acv`), `GET /video/{play_id}` (serve the resulting mp4).

## Known gaps

- Playback quality is entirely whatever the source `.acv`'s strategy produced —
  see Codec Lab's findings.
- The **standalone** `player.py` needs non-headless OpenCV for its `cv2.imshow`
  window; the web player here does not.

## Also ships as

`AnimeCodecPlayer` / `AnimeCodecPlayer.exe` (OpenCV-window version, cross-built
via Wine + PyInstaller), in `~/anime-codec-lab/release/` — for sharing `.acv`
files with people who don't have Forge. `AnimeCodecPlayer.desktop` is kept
registered (as `NoDisplay=true`) only so the `.acv` file association still
works.
