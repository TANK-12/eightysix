# NovelForge rework: diagnosis and plan (2026-09-28)

Written for a fresh session with no conversation history. Session brief:
`~/Forge/sessions/2026-09-28-novelforge-rework.md`. Backups of every NovelForge
file as it was before this work: `~/Forge/backups/2026-09-28-novelforge/`.

## What Emerson asked for

"fix novel forge and make it work ... make the jan server for the 27b model
work (the model names don't line up) ... be able to delete the outline, bible
and stuff ... small models make really bad outlines, make the system prompt and
the whole thing better and hook into Jan better, add a RAG or something ...
make it actually work to make indistinguishable Korean light novels or other
novels." Also: **do not run tests on the models** (no live generation through
Jan). Everything else (unit tests with a fake client, screenshots) is allowed.
He said "get on with it": work unattended, don't stop for questions.

## Done so far

**Jan 27B entry fixed on disk (done, not yet checked in a running Jan).**
The cause: the 27B had been imported through a stray folder literally named
`model.gguf` whose `model.yml` pointed at `qwen3.8-27b-iq4/model.gguf`. Jan
therefore served it under the id `model.gguf` (that was the only name in the
Local API Server's model picker), while the real folder `qwen3.8-27b-iq4` had
only an old-format `model.json` that Jan ignores. NovelForge's folder scan
listed both names. Changes, all under `~/.var/app/ai.jan.Jan/data/Jan/data/`:

- wrote `llamacpp/models/qwen3.8-27b-iq4/model.yml` (same settings as before:
  ctx_size 50000, n_gpu_layers 100, mtp on, name "Qwen3.8-27B");
- removed the `llamacpp/models/model.gguf/` folder (it held only a model.yml)
  and the stale `qwen3.8-27b-iq4/model.json` (said ctx 4096);
- `settings.json`: the 5 references to the id `model.gguf` now say
  `qwen3.8-27b-iq4` (the llama.cpp provider's model list, the selected chat
  model, and the Local API Server default model);
- `llamacpp/router.preset.ini`: section renamed to `[qwen3.8-27b-iq4]` (Jan
  rewrites this file from model.yml on start anyway).

Checked: settings.json still parses and shows the new id in all three places;
NovelForge's `scan_models_folder` now lists `qwen3.8-27b-iq4` (ctx 50000,
weights found, "large" profile) and no `model.gguf`.
**Not checked:** Jan has not been started since. To check without loading the
model: start Jan, `curl -s http://127.0.0.1:1337/v1/models`, expect
`qwen3.8-27b-iq4` and no `model.gguf`. One old Jan chat thread
(`threads/5ed1ad5e-...`) still names `model.gguf`; that chat needs the model
picked again. Undo: copies of the old folder, model.json, settings.json and
preset are in `~/Forge/backups/2026-09-28-novelforge/jan/`.

Update 2026-09-28 (Tetsu, ejb-34): steps 1-8 are now built and tested with a
fake client; the Jan 27B id was checked in a running Jan (`/v1/models` lists
`qwen3.8-27b-iq4`, no `model.gguf`). Step 9 and a live outline run remain.
Current state and next steps: the top section of `../WIP.md`.

## Diagnosis (found by reading the code and the saved data, not by running)

1. **Outlines are written by the wrong model.** `web_app.py` `_resolve_model(None)`
   is used by Generate Outline, Free-Rein, Continue-ingest and style analysis.
   It ignores the model dropdown and takes the saved `model` setting, which is
   only saved when Generate starts, else the first model in the list. The saved
   value is `Qwen3_6-27B-Q4_K_M`, which is not installed, so these jobs fall to
   the first listed model (likely a 0.8B-2B; which one depends on Jan's list
   order, not checked). This is the main reason outlines are bad.
2. **Filler outline lines.** When an outline batch fails, `engine.build_outline`
   pads it with "Advance the central conflict; a setback forces {protagonist}
   to change tactics". With an empty protagonist it reads "forces the to change
   tactics" (seen in the saved project `cintinue`). These lines then drive
   whole chapters.
3. **The outline cannot be edited.** The Outline box on the Story tab is
   `readonly`, `saveBible` never sends it, and `chapter_list` (what generation
   actually uses) is only ever written by the engine.
4. **Outline progress is invisible.** The outline job streams into the Generate
   tab's box while the user is on the Story tab.
5. **Nothing can be deleted** from the UI: no delete for projects, series,
   outline, world document, codex entries or chapters.
6. **Most of a long world document is never seen.** `memory.py` puts only the
   first ~2200 tokens of `world_doc` into every prompt.
7. **The Codex tab is a raw JSON dump.**
8. **NovelForge does not use the shared `~/Forge/shared/forge_jan.py`**, so it
   has no per-app model roles and never releases idle models (Emerson's
   standing rule for every Forge app that uses Jan).
9. Small frontend bugs in `static/index.html`: `streamJobGeneric` is defined
   twice (the second silently replaces the first); the "Push to inspiration
   notes" button builds its URL from an unencoded project name.

## Plan, in order

Each step is independent enough to land and check on its own.

1. **Model choice that sticks.** Mount `forge_jan.mount(app, "novelforge",
   roles=("writer", "planner"))`. A model picker in the header (visible on every
   tab) saves at once; "planner" (outline, Free-Rein, codex, summaries) is shown
   in Advanced mode and defaults to the writer. Every job resolves its model
   through the role, falling back to `settings["model"]`, and runs inside
   `with jan.using(model):` so the idle release never pulls a model mid-job.
   Migrate the stale saved `Qwen3_6-27B-Q4_K_M` to `qwen3.8-27b-iq4`.
2. **Genre presets as a registry.** One JSON file per preset in
   `novelforge/presets/`, loaded by discovery (no hardcoded list). Fields: id,
   label, description, voice rules, structure template (chapter roles by
   percentage of the book), outline guidance, scene guidance, worldbuilding
   cues, naming conventions, clichés to avoid, default words per chapter, and a
   short original sample paragraph. Korean first: Korean hunter/system web
   novel, Korean romance fantasy (rofan), Korean murim/regression; then Japanese
   isekai light novel, Japanese romcom light novel, Chinese cultivation, Western
   epic fantasy, LitRPG/progression, thriller, romance, mystery, sci-fi, horror,
   general. New bible field `preset`, chosen on the Story tab.
3. **Outline pipeline that small models can follow.** Code, not the model,
   decides the structure: each chapter gets a role from the preset's template
   (hook, inciting incident, arc boss, midpoint reversal, climax, and so on).
   The model fills small batches (3-5 chapters for small models) in a fixed
   line format `Title | what happens, with names | what changes | hook`, with
   one good and one bad example in the prompt. Each line is checked: names a
   known character, is not a near-duplicate of another line (word overlap), is
   within length bounds, is not vague. Failed lines are retried one by one with
   the reason. No filler is ever written: if retries fail, keep the partial
   outline, report it, and offer "Continue outline". Optional "careful" mode:
   one critique pass that rewrites the weakest chapters.
4. **Better prose prompts.** System prompt built from the preset's voice rules,
   a clichés-to-avoid list and the hard rules (names, POV, tense, no headings).
   Repeat the key instructions at the end of the user message (small models
   follow the last thing they read). Keep a stable prefix (system prompt + canon
   block) ahead of the per-scene parts and send `cache_prompt: true`, so
   llama.cpp reuses its cache between scenes. This matters a lot for the 27B on
   the iGPU, where reading a 10k-token prompt takes minutes. Log a cliché count
   per chapter.
5. **Retrieval ("RAG").** New `novelforge/rag.py`: pure-Python BM25 (a
   keyword-ranking formula) over ~200-word chunks of earlier chapters and over
   the world document's sections. The query is the scene beat plus the chapter
   goal plus the names in it. The chapters already included word for word are
   left out. Results go after the stable prefix. Optional embeddings through
   Jan's `sentence-transformer-mini` behind a setting, off by default: loading
   it takes one of the router's model slots and could push the 27B out.
6. **Delete and reset.** Delete a project from Home (moves it to
   `~/NovelMakerData/.trash/`, not a hard delete). Clear buttons for outline and
   world document. A reset card with checkboxes: bible fields, outline, codex,
   chapters, memory (summaries, story-so-far). An editable outline that is
   parsed back into `chapter_list` on save. A codex list with a delete button
   per entry. Rewind to chapter N (delete N onward). Delete a series or remove
   a book from one.
7. **UI fixes:** outline progress box on the Story tab, the duplicate
   `streamJobGeneric`, the unencoded URL.
8. **Tests with a fake Jan client** (no live model): preset loading, chapter
   role mapping, outline validation and retry, BM25 ranking, delete/reset
   endpoints through FastAPI's TestClient with `novelforge.project.PROJECTS_DIR`
   and `SERIES_DIR` pointed at a temp folder. The app venv already has pytest
   and httpx. Existing suite: `tests/test_catalog.py` (5 tests).
9. **Checks before calling it done:** black and
   `pyright --pythonpath ./.venv/bin/python` on touched files, a headless
   screenshot of the Story, Codex and Home tabs (verify skill), then update
   MANIFEST.md, forge_app.json's manifest block, README.md and WIP.md.

## Useful facts

- The legacy customtkinter `novelforge/app.py` (2707 lines) is not what Forge
  runs; leave it alone. Forge runs `web_app.py` + `static/index.html` on 8421.
- Test copy: `.venv/bin/python -m uvicorn web_app:app --port <free port>` from
  the app folder, with a PID file; never touch the running Forge copy.
- Jan is shared: check `pgrep -a -x llama-server` before loading anything, and
  never restart Jan while it's in use. Qwen models need thinking switched off per
  request (already done in `janclient.py`).
- Emerson's target project is `~/NovelMakerData/projects/The_F-Ranks_Solo_System`
  (Korean power fantasy, protagonist Kang Jin-Woo). Its `plot` field has pasted
  "Protagonist: ... Scope: One-shot" lines mixed in.
