# PanelForge

Turns English-scanned manga, manhwa and comic chapters into voiced
motion-comic movies inside the Forge hub. Port 8449, data in
`~/PanelForgeData`. Handoff: `HANDOFF.md`. Data formats and endpoints:
`CONTRACTS.md`.

## Pipeline (each stage is a package under `panelforge/`, mounted by `api_registry.py`)

| stage | package | writes | status (2026-09-17) |
|---|---|---|---|
| library | `library/`, `sources/` | `chapter.json`, pages | fetch from comix.to, folder/CBZ/PDF import, Kindle PDF export |
| detect | `detect/` | `strip.json`, `panels.json`, `bubbles.json` (with lettering `style` cues) | verified on chapter 1: 123 panels, 125 bubbles, OCR confidence 0.835 |
| scene | `scene/` | `scene.json`, series `cast.json`, `assets/` | chapter 1 analysed: 123 panels, 21 scenes, 4 locations, 11 cast, 2 extras. The cast finder is improved but still mixes characters -- see HANDOFF section 4 and `tools/cast_sheet.py` |
| audio | `audio/`, `sfx/`, `music/` | `script.json`, `audio/*.wav` | Kokoro voices (picked by hand, or cast by the Jan model from the character pictures on request), the model's page reading (speakers, expressions, delivery, with the panel picture), expression-driven delivery, SFX, music, mixing |
| render | `render/`, `styles/`, `camera/`, `transitions/` | `timeline.json`, `renders/*.mp4` | intelligent camera (text-safe framing), transitions, depth3d layered style, previews, partial renders (`shot_ids`/`max_seconds`); first real film: `renders/lookie-01.mp4` |
| ui | `static/` | | 6 tabs, screenshot-verified with `tools/ui_shots.py`; the Cast & voices tab has a Lines editor (balloon picture per line, click a face to change the speaker, Re-speak) |

## Running

```
cd ~/Forge/apps/panelforge
.venv/bin/python -m pytest -q
.venv/bin/python -m uvicorn web_app:app --host 127.0.0.1 --port 8460   # scratch port; 8449 is Forge's
```

`GET /api/health` lists the API modules that loaded and any that failed.
Long work runs as jobs (`GET /api/jobs/{id}`). Files under `~/PanelForgeData`
are served at `/data/...`.

## Tools

`tools/cast_sheet.py <series> <chapter> [out.jpg] [quantile] [threshold]` --
contact sheet of the cast finder's clusters, one row per character, for
judging it by eye and for trying different clustering settings.
`tools/ui_shots.py --port P --series S --chapter C --out DIR` -- one
screenshot per UI tab, with a chapter actually selected. Point it at a server
started with a temporary `PANELFORGE_DATA`.
`tools/rebuild_chapter.py --port P <series> <chapter> --out NAME [--max-seconds N]
[--from detect|analyze|script|voice|audio|timeline|render]` -- runs the whole
chapter pipeline through a running server, one job after another, and logs
each job's tail. Start it with `setsid -f` and read the log: a full run is
about half an hour when the scene models have to look at changed panels.
`tools/proto_comix_fetch.py` -- the prototype chapter fetcher.
`tools/renormalize.py <series> [chapters]` -- re-cleans every un-edited
bubble's text from `text_raw` with the current cleaner and the learned
series glossary, without OCR.
`tools/replay_llm.py <series> [chapters]` -- re-applies the model's stored
page reading (speakers, expressions) after the take-or-refuse rules change,
without asking the model; changed lines lose their sound so the voice job
(`only_missing`) or the Lines editor can speak them again.
`tools/tilted.py <series> <chapter> [min_degrees]` -- lists the tilted lettering
in a chapter with its angle and whether the reading has it, to find a
slanted caption the reader missed.



Rules that are easy to break: mocks and tests use a temporary
`PANELFORGE_DATA`, never the real folder; a voice chosen by hand is never
changed by the model's casting (only voices marked `source: "model"` are);
never `pkill -f`; AI models download only through `panelforge.models.ensure`
(15 GB budget). Fixed-shape scene models run on the Intel iGPU through
OpenVINO (`PANELFORGE_SCENE_DEVICE=CPU` disables that).
