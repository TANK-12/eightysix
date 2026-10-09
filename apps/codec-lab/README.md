# apps/codec-lab

This folder is **only a pointer**. The real code is a separate git repo at
`~/anime-codec-lab` (kept separate on purpose — it has its own `.venv`, its own
Wine cross-build tooling, and its own history). The `"root"` field in
`forge_app.json` tells `forge.py` to launch it from there.

- Backend: `server:app` (FastAPI), run from `~/anime-codec-lab` on port 8431.
- Frontend: `~/anime-codec-lab/static/index.html`. It keeps its own copy of the
  Forge palette (not `/shared/forge.css`, whose classes collide with its own) and
  loads `/shared/forge_chrome.js` + `/shared/forge_idle.js` so its poll and
  videos rest while another app is in front.
- The `/shared` mount in `~/anime-codec-lab/server.py` resolves via the
  `FORGE_SHARED_DIR` env var that `forge.py` sets; standalone it falls back to
  a sibling `shared/` if present, and is simply skipped if neither exists.

To work on the lab itself, go to `~/anime-codec-lab` — see its `README.md` and
`BUILD_MANIFEST.json`.
