# NovelForge — manifest

_Written 2026-09-07 for a reader with no conversation history. The machine-
readable version of this is the `manifest` block in `forge_app.json`._

## What this is

NovelForge writes book- and series-length fiction using a local Jan / llama.cpp
model. The flow: give it a premise (or let **Free-Rein** invent one), it builds
a world and cast, plans a numbered chapter outline, then drafts the book scene
by scene while keeping a structured "world codex" up to date. When the draft is
done it exports to EPUB / PDF / TXT and can read the book aloud as a fully
offline audiobook.

It began as a customtkinter desktop app. The current app is a FastAPI backend
(`web_app.py`) plus a single-page frontend (`static/index.html`); every
business-logic module under `novelforge/` was carried over untouched. `run.py`
still launches the **old desktop app** — the web app is launched by Forge, or
standalone with uvicorn (below).

Runs on **port 8421** in Forge (`order` 1).

## Features (the nine tabs)

| Tab | What it does |
|---|---|
| **Home** | Project list with per-book stats and cover thumbnails. Create or open a project. |
| **Story** | The story bible: title, genre, protagonist, plot, pinned facts (never contradicted), inspiration notes, style directives. **Free-Rein** builds a world + cast + places + factions + open threads in multiple prose passes, scaled by the world-depth setting (Sketch / Standard / Rich / Epic), seeded from whatever fields you filled. **Generate Outline** turns the bible into a numbered chapter list. |
| **Generate** | Drafts the book scene by scene toward a per-chapter word target. A **RAM guard** pauses and, if it can't recover, stops cleanly and resumably when free system memory drops too low (stops Jan's router loading a second multi-GB model and freezing the laptop). A **degeneration guard** aborts and retries a scene that loops. DRY sampling for anti-repetition. Live token stream, soft stop, hard stop. |
| **World Codex** | Structured characters / locations / factions / facts, auto-updated as chapters are written, with periodic contradiction-reconcile sweeps. |
| **References** | A style library built from PDFs: ingest a book, analyse its house style, and fold it into every scene. Also a best-effort research-notes lookup. |
| **Continue a Series** | "Never-ending story" mode. Ingest 1–12 PDFs of an existing series; NovelForge learns the house style, **measures the POV and tense** from the prose, rebuilds the codex, captures how the last book ended, and writes N more chapters at a time with a chosen spin (alternate POV, time-skip, side-character spin-off, genre shift, what-if). |
| **Series** | Multi-book arcs: planned book count, arc synopsis, per-book status. Each book's outline is shaped by the shared arc. |
| **Export** | EPUB (real nav/TOC, Calibre series index), PDF (A4 / Letter), TXT. Whole-series export reuses the per-book path. Cover art: procedural (gradient / duotone / minimal, Pillow only, no network), plus import and light edits. AI cover generation is a deliberate stub behind `diffusers`+`torch`. |
| **Audiobook** (inside Export) | Offline TTS via **Piper** and **Kokoro**. Three modes: single narrator, full cast, or one narrator doing per-character pitch/pace shifts. Regex dialogue attribution, a per-character voice map, an LLM "casting director", and ffmpeg stitching with real chapter markers. |
| **Settings** | Jan API base, models folder, world depth, sampling, RAM-guard threshold, export / cover / audiobook defaults, UI scale and density. |

## Where data lives

`~/NovelMakerData/` — outside this folder, resolved through `Path.home()`:

```
projects/<book>/     bible.json, state.json, codex.json, chapters/, export.json, voices.json
series/<name>/        series arc data
style_library.json   ingested house styles
known_models.json    user-added / hidden model names
novelforge_settings.json
tts_voices/           downloaded Piper/Kokoro ONNX voices
```

## Dependencies

**Required:** fastapi, uvicorn, requests, pypdf, reportlab, psutil, EbookLib,
Pillow (installed by `install.sh` into `.venv`).

**Optional:** `piper-tts` and `kokoro-onnx` (audiobook voices — Kokoro is the
default engine); `diffusers` + `torch` (local AI cover art — stays a stub until
installed, and is minutes-per-image on this CPU-only box).

## External services

**Jan / llama.cpp** at `http://localhost:1337/v1` is required for all
generation. Models are discovered two ways: Jan's live `/v1/models` API, and a
scan of Jan's `llamacpp/models/` folder (each model is a subdirectory with an
optional `model.yml`). Jan only registers a freshly downloaded model at
startup, so a new model needs Jan restarted before it appears.

## Running it standalone

```bash
cd /home/ejb/Forge/apps/novelforge
.venv/bin/python -m uvicorn web_app:app --port 8421
```

Then open <http://127.0.0.1:8421>. (`run.py` launches the legacy desktop app,
not this.)

## API surface

49 routes under `/api/` in `web_app.py`: projects, bible, outline, generate,
free-rein, continuation (spin-presets / ingest / run), series, jobs + SSE
event stream, state, refresh-models, settings, export, cover
(quick / import / edit), style-sources, research, tts
(catalog / installed / preview), voice-map, cast-voices, audiobook.

## Rework (2026-09-28)

A writer and a planner model per role, 14 genre presets (`novelforge/presets/*.json`),
checked outlines that never write filler (`novelforge/outline.py`), BM25 look-ups over
earlier chapters (`novelforge/rag.py`) and delete/reset/rewind with a 409 while a job
runs. Details in the README "Rework" section; the live outline run on the Jan models is
**not yet done**.

## Known gaps (verified vs reasoned)

- **Free-Rein** web endpoint was restored 2026-09-07; the plumbing is verified
  (endpoint registered, job runs, fails cleanly when Jan is down) but it has
  **not yet been run against a live model**.
- **Continuation mode** has not been run end-to-end against real series PDFs —
  the ingest prompts may want tuning once tried.
- `narrator_voices` auto pitch slots are assigned alphabetically, so a
  character can land on a wrong-sounding voice unless set explicitly.
- `research.py` uses DuckDuckGo Instant Answers, which are often empty —
  explicitly best-effort.
- Theme changes need an app restart.

## Other docs

`README.md` (user-facing overview), `WIP.md` (session-by-session change log
with a "known issues" section — the live status).
