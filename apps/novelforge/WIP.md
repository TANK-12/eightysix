## U1 sweep (2026-10-08, Relay task 74; done by Relay task 87)

Kept small on purpose: the 2026-09-28 rework below is still uncommitted
(another session's work, never committed or reverted here). Only my hunks
were committed, staged onto HEAD with `git merge-file`; the working tree
holds both.

What changed:
- Break 6: the 15 s state poll runs through `pollState()`, which returns
  false while the server does not answer, so `ForgeIdle.poll` stretches it
  to 30 s (`{ backoff: 2, maxMs: 30000 }`); the header says "Server not
  answering, retrying" and the project list reloads once it is back. A
  failed first `/api/state` no longer kills the page's start-up.
- The committed copy of `static/index.html` was broken: lane H4's commit
  994989b staged the `forge_idle.js` script tag into the middle of
  `loadProjects()` (it would have ended the inline script there). The live
  file on disk was always right; the committed one is now right too.
- Header at narrow widths: project name shortens with an ellipsis and the
  Jan status stays on one line (at 760 px both broke word by word).
  Thin themed scrollbars (`::-webkit-scrollbar` too).
- API: `GET /api/projects/<name>` and `GET /api/series/<name>` for a name
  that is not there are a 404 and create nothing (before, a read made an
  empty project or series folder, which then showed on Home). Project and
  series names over 120 characters are a 400 (a 5000-character name was a
  500); an empty series name is a 400 (it made a series called "").

Verified:
- `pytest -q tests`: 41 passed in the working tree (38 before + 3 new in
  `tests/test_u1_names.py`). The committed variant (HEAD + these hunks,
  exported to /tmp) also passes: 8 passed. black clean on the touched
  .py; pyright: no new errors (2 old ones in the rework's `Job` code).
- Scratch copy on port 9030 (HOME pointed at a temp folder), headless
  Chrome: shots at 760/1100/1500/1920 (`/tmp/u1/G13/shots/after-nf-*`);
  hidden 10 s: 0 fetch / timer / rAF; server killed: 2 fetches in 60 s
  (4 before), calm header line; restarted: back to "Jan online" and the
  project list by itself. Opening a project still goes to Story.
- Bad input battery (curl): empty, wrong types, unicode, path-like names,
  non-JSON bodies all get 4xx with a reason; the two 500/create bugs above
  fixed.

Not verified / left: other routes still build `Project(name)` for unknown
names (PUT bible, generate, export ...): the rework's `_existing()` helper
is the right tool, best finished by whoever lands the rework. Not seen in
the real Forge window. Page changes reach Forge on the next reload; the
`web_app.py` change on the next Forge restart (not restarted here).

### Critic follow-up (2026-10-08, same task)
The critic (`sessions/2026-10-07-overhaul/critics/u1-G13-critic.md`) found
three NovelForge breaks; all fixed, again staged onto HEAD with merge-file:
- `slugify()` strips leading dots: "." and ".." named the projects folder
  itself or its parent, so a read passed the 404 guard and a create wrote
  `bible.json`/`state.json`/`chapters` into `~/NovelMakerData`. Both now
  become "untitled" (same as a name made only of symbols, an older quirk).
- Name length also counts bytes: 100 CJK characters (300 bytes) were a 500,
  now a 400 "name is too long" (slug over 200 bytes).
- Header wraps (`flex-wrap`) and the model pickers narrow below 900 px: in
  Advanced mode at 760 px the status, including the offline line, was off
  screen. Verified headless at 760/900/1100 in Advanced mode: header and
  page exactly window wide, status on the second row at 760 and 900.
- Start-up: a failing `/api/projects` no longer stops the state poll.
Tests: `tests/test_u1_names.py` has two new tests (both failed on the old
commit, pass now); 43 pass in the working tree, 10 on a HEAD export.

# 2026-10-09 - rework UI-checked and committed (Umi, Relay task 123)

Improve-next steps 1, 3 and 4 below are done; step 2 (live outline run on
the 2B and 0.8B) is not: it needs Jan open and the 27B it auto-loads
released, so it waits for Emerson (QUICKSTART question 5). **Verified:**
43 tests pass; black clean; pyright 143 errors, the same 143 as HEAD (old
unbound/optional ones, none new); headless Chrome on a test server with a
copy of ~/NovelMakerData (Jan offline): Home, Story, Generate, World Codex
and Settings in Simple and Advanced render with no page errors; the
Writer/Planner header pickers, the genre-preset picker, the codex list and
Settings > Jan memory all show. Seen, not fixed: the header's "Writer" and
"Planner" labels sit a little above their selects. README has a "Rework"
section.

Critic (opus) on the destructive routes, fixed with tests red first (46
pass): deleting or unlinking a series is refused (409) while a job runs on
one of its books; delete, reset, rewind and codex delete need the exact
folder name ("???" used to trash "untitled", "My Book" hit "My_Book");
rewind also takes chapters past a gap (1, 2, 4) and a second rewind in the
same second gets its own trash folder. Not fixed (low): `add_book` through
the API keeps the name as sent; the bible save route can rewrite state.json
while a job runs (reasoned, not run).

# 2026-09-28 - rework built, stopped before the UI check (Tetsu, ejb-34)

Stopped at Emerson's request ("get to a stopping point, kill everything"). The
code for plan steps 1-8 of `docs/rework-plan-2026-09-28.md` is written and
passes its tests; it has **not been seen in a browser** and **not run against a
live model**. Nothing is committed yet (`git status apps/novelforge`).

**Verified** (`.venv/bin/python -m pytest -q tests`: 38 passed; black run;
pyright clean apart from 3 old errors in untouched lines: `os.startfile`,
`kill.keep_partial`, `Job.thread`). The page script parses (`node --check`).

What exists now:
* **Model per role** (shared `forge_jan`, roles `writer` and `planner`). Header
  pickers on every tab save at once; planner (Advanced) defaults to the writer.
  Outline, Free-Rein, continue-ingest, style analysis and voice casting use the
  planner; prose uses the writer; a run only uses the planner to plan a missing
  outline. Every job holds its models (`JAN.using`) so idle release never
  unloads one mid-job. Settings > Jan memory sets the idle minutes. The stale
  saved `model` (Qwen3_6-27B, not installed) is skipped; **Emerson should pick
  the writer once in the header.**
* **Genre presets** (`novelforge/presets/*.json`, found by folder scan; 14:
  Korean hunter/system, rofan, murim/regression, Japanese isekai and romcom,
  Chinese cultivation, epic fantasy, LitRPG, thriller, romance, mystery,
  sci-fi, horror, general; `_common.json` holds shared voice rules and worn
  phrases). Bible field `preset`; blank = guessed from the genre (F-Ranks
  guesses `kr-hunter`). Picker on the Story tab.
* **Outline pipeline** (`novelforge/outline.py`): code maps the preset's
  structure onto chapters (`presets.chapter_roles`); the model fills batches
  of 3/4/6/10 lines (tiny/small/medium/large) in `Title | what happens | what
  changes | hook`; each line is checked (four parts, length, names a known
  character, not vague, not a near-copy, no example names) and a failed line
  is re-asked alone with the reason (2 retries). No filler ever: it stops and
  saves what it has; "Continue outline" resumes. Optional careful mode (one
  editor pass). A run past the end of the outline stops instead of inventing.
* **Prose prompts**: system prompt from the preset voice + hard rules (names,
  POV/tense, no headings) + worn phrases + a rhythm sample; identical for the
  whole run, and the per-scene parts come after the context, with
  `cache_prompt: true`, so llama.cpp reuses the prefix between scenes. A
  FINAL CHECK line ends every scene request. Worn-phrase count logged per
  chapter.
* **Retrieval** (`novelforge/rag.py`): BM25 over ~200-word passages of earlier
  chapters (minus the verbatim ones) and world-document sections (minus the
  opening already in the prompt), per scene. The world-document opening in
  the prompt now scales with the context budget (1200-6000 tokens).
  Embeddings were not added (they would take a Jan model slot).
* **Delete and reset**: delete project (to `~/NovelMakerData/.trash`), reset
  card (story fields / outline / world doc / codex / chapters / memory),
  rewind from chapter N (chapters to the trash), Clear buttons for outline and
  world doc, editable outline parsed back into chapters on Save (changed
  chapters lose cached beats), codex list with Delete per entry (raw JSON in
  Advanced), delete series, remove a book from a series. Destructive routes
  refuse (409) while a job runs on that project. Pasted labels like "Pinned
  facts:" are stripped on save.
* Fixes: outline progress shows on the Story tab; duplicate
  `streamJobGeneric` removed; "Push to inspiration notes" URL encoded; static
  folder path no longer depends on the working directory.

**Improve next, in order:**
1. UI check (verify skill): test copy on a free port, headless screenshots
   of Home, Story, Generate, World Codex, Settings in both modes. Why: no
   browser has seen the new header pickers, preset picker, reset card or codex
   list.
2. Live outline run on the 2B and 0.8B (Emerson allowed it on 2026-09-28,
   outline only). Recipe: temp copy of F-Ranks with `PROJECTS_DIR` pointed at
   a temp folder, `NovelEngine(...).build_outline(10)`, then
   `forge_jan.release(model)`. **Starting Jan auto-loads the 27B** (it is the
   Local API Server default; ~20 GB, Emerson noticed): release it at once, or
   ask him to change Jan's default model. Tune `check_line` limits (14-110
   words, 0.6 similarity, 2 retries) from what the small models really write.
3. MANIFEST.md, `forge_app.json` manifest block and README for the above.
4. Commit.

# 2026-09-28 - diagnosis, rework plan, Jan 27B entry fixed (Suzu, ejb-0d)

Emerson asked for a big NovelForge rework (better outlines from small models,
genre presets with Korean web novels first, retrieval, delete/reset, shared Jan
hookup) and for the Jan 27B names to line up. Stopped at his request after the
diagnosis. **No NovelForge code changed.** Full diagnosis and ordered plan:
`docs/rework-plan-2026-09-28.md`.

* Jan: the 27B is now one entry, id `qwen3.8-27b-iq4` ("Qwen3.8-27B"), also the
  Local API Server default; the stray `model.gguf` folder is gone. Checked on
  disk and in NovelForge's folder scan; not yet checked in a running Jan.
* Main cause of bad outlines found: Outline / Free-Rein ignore the model
  dropdown and use the saved setting (a model that is not installed) or else
  the first model listed, usually a tiny one; failed batches get filler lines.

# 2026-09-27 - model switch lists only models that are really there (Nagi, ejb-6b)

Emerson (#296): "fix the novel forge model switch, it's seeing models that
aren't there, the folders are empty". Causes: every scan merged the hardcoded
FALLBACK_MODELS (gemma4-opus48, Gemma-4-12B, ... none installed) into the list,
and any folder counted as a model. Also the saved `model` setting was
`Qwen3_6-27B-Q4_K_M`, which is not installed, so jobs asked Jan for it.

* `novelforge/catalog.py`: a folder counts only with weights (a .gguf in it, or
  a model.yml `model_path` that exists, relative to Jan's data folder: that is
  how Forge's `-long` long-context entries work); embedding models
  (`embedding: true`) are left out; a Jan id whose folder is empty is dropped;
  no fallback names ever. The catalog starts empty until the startup scan.
* `web_app.py` `_resolve_model`: the asked/saved model while it is really
  there, else the first real one.
* `static/index.html`: the list rescans when pointed at or focused (at most
  every 5 s) and only rebuilds when it changed; an empty list says "No models:
  is Jan running?".
* Verified: `tests/test_catalog.py` 5 pass (new; pytest installed in the app
  venv); on the real machine the list is the 8 real writing models (was 9 real
  plus 8 made-up, including the embedding model); headless check of the real
  page: dropdown = those 8, no made-up names, pointing at it fires a rescan.
  pyright: only the 2 old errors (web_app.py 149-150). Not seen in the Forge
  window yet (needs the app reopened). The legacy customtkinter app.py still
  uses FALLBACK_MODELS and was left alone.

> Older sections moved verbatim to `WIP-archive.md` on 2026-10-07 (overhaul helper-5): from "NovelForge — work in progress" to "4. Docs".

