# 2026-09-28 NovelForge rework (Suzu, ejb-0d)

Emerson: "fix novel forge and make it work... make the jan server for the 27b
model work (names don't line up)... be able to delete the outline, bible and
stuff... small models make really bad outlines, make the system prompt and the
whole thing better, hook into Jan better, add a RAG... make it work to make
indistinguishable Korean light novels or other novels." Do not run tests on the
models (no live generation); everything else is allowed.

## Ask ledger
1. Jan 27B: one entry with matching names (folder, Jan id, Local API Server default).
2. NovelForge works: model choice actually used by every job, bugs fixed.
3. Delete / reset: outline, bible, world doc, codex entries, chapters, projects, series.
4. Better outlines, even from small models.
5. Better system prompts and pipeline for prose.
6. Hook into Jan better (shared forge_jan: per-app roles, idle release).
7. RAG: retrieve relevant earlier passages / world notes while writing.
8. Genre presets, Korean web novel / light novel first, others too.
9. Handoff docs.

## Owns
apps/novelforge/** ; Jan model folder qwen3.8-27b-iq4 + Jan settings.json ids.

## State
- Session 2: Tetsu (ejb-34) built plan steps 1-8, then stopped at Emerson's request. Details: apps/novelforge/WIP.md top section.
- 1 Jan 27B names: done + checked in a running Jan (/v1/models lists qwen3.8-27b-iq4, no model.gguf). Note: Jan auto-loads the 27B on start (it is the Local API Server default, ~20 GB).
- 2 NovelForge works (model per job, bugs): done, tested with a fake client; not seen in a browser.
- 3 Delete / reset: done, tested through the API; UI not seen.
- 4 Better outlines: done, tested with a fake client; live run on the 2B was stopped before its first reply (not verified live).
- 5 Better prose prompts: done, prompt shape tested; not run live.
- 6 Jan hookup via forge_jan: done, role fallback tested; idle release not checked live.
- 7 RAG: done (BM25), tested; embeddings deliberately not added.
- 8 Genre presets: done (14, Korean first), tested.
- 9 Handoff: done. Not done: UI screenshots, live outline test, MANIFEST/README/forge_app.json, commit.
- Jan closed again, nothing left running. Board claims released.
