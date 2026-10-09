# apps/codec-player

A pointer, like `apps/codec-lab`. The code lives at `~/anime-codec-lab`; the
`"root"` field in `forge_app.json` points `forge.py` there.

- Backend: `web_player:app` (FastAPI) in `~/anime-codec-lab/web_player.py`,
  port 8432. It decodes an uploaded `.acv` with the strategy that made it and
  serves the result as an mp4 (audio muxed from the `.acv`'s embedded WAV).
- Frontend: `~/anime-codec-lab/static/player.html` (loads `/shared/forge_chrome.js`
  + `/shared/forge_idle.js`; the video pauses while another app is in front).
- Reuses `core/` and `strategies/` from the lab, and the lab's `.venv`.

This is the in-hub equivalent of the standalone `player.py` (OpenCV window),
which still ships as the `AnimeCodecPlayer` / `AnimeCodecPlayer.exe` binary for
sharing `.acv` files outside Forge.
