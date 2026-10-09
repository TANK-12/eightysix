# novelforge WIP archive

Sections moved verbatim from `WIP.md` on 2026-10-07 (overhaul helper-5) to keep the live WIP short. Nothing was rewritten or deleted; original order kept. The full pre-move file is in `~/Forge/backups/2026-10-07-overhaul/wip/novelforge-WIP.md`.

# NovelForge — work in progress

_Last touched: 2026-09-07._

# 2026-09-07 — web app: Free-Rein restored + model scanning fixed

The customtkinter→web migration (`web_app.py` + `static/index.html`) had left
two things behind. Both are fixed now; no business logic changed
(`engine.build_world`, `catalog.py` untouched).

## 1. Free-Rein was unreachable in the web UI

`NovelEngine.build_world()` (multi-pass world + cast build, scaled by the
`world_depth` setting) was intact but had no web endpoint and no button — the
desktop app's `_free_rein` / `_job_free_rein` were never ported.

* `web_app.py` — new `FreeReinRequest` schema and
  `POST /api/projects/{name}/free-rein`, built exactly like `generate_outline`:
  resolves the model, builds the size profile, runs `engine.build_world(genre,
  protagonist, plot, expand_existing=…)` on the shared background job + SSE
  stream. Seeds come from whatever is saved on the bible; blank is fine.
* `static/index.html` — Story tab gained a "✦ Free-Rein: build world & cast"
  button, an "overwrite filled fields too" checkbox (`expand_existing`), and a
  progress log box. The handler **saves the story bible first** (the endpoint
  reads the bible fresh from disk) via a new `saveBible()` helper shared with
  the Save button, then streams the job into the log box and repopulates every
  Story field + the codex on completion.

Verified: endpoint registered; a job starts, wires the engine, and on a machine
with Jan down fails cleanly with the "Open Jan…" message. **Not yet run
end-to-end against a live model** — left for the user to confirm in the app
(Jan was not running during this session).

## 2. The model dropdown never scanned — only ever showed the fallback list

`AppState` built `Catalog()` (which starts on `config.FALLBACK_MODELS`) but
nothing ever called `catalog.refresh()`, so `/api/state` returned the stale
hardcoded list forever and the user's real installed models never appeared.

* `web_app.py` — `AppState.__init__` now starts a daemon thread that runs
  `catalog.refresh(client, models_path)` once at startup (threaded so a slow
  Jan `/v1/models` can't delay boot). `/api/state` and `/api/refresh-models`
  responses now also carry `scan_count`, `api_count`, `models_path`.
* `static/index.html` — a "Rescan models" button in Settings → Connection
  (calls the existing `/api/refresh-models`), a one-line scan summary under it,
  and a `rescanModels()` call in `init()` so the dropdown fills on load even if
  the backend started before Jan.

Verified live (backend on :8421, Jan down): `/api/state` and
`POST /api/refresh-models` both return the 9 models actually on disk —
`Qwen3_6-27B-Q4_K_M`, `gpt-oss-20b-Q4_K_M`,
`Qwen3_5-9B-Uncensored-HauhauCS-Aggressive-Q4_K_M`, `VibeThinker-3B_Q4_K_M`,
etc. — merged with the fallback list, `scan_count` 9, `models_path` correct.
`black` + `pyright --pythonpath ./.venv/bin/python web_app.py` clean (the two
pre-existing `Job.thread` type errors are unchanged). `node --check` on the
inline script passes. **No browser screenshot** — the Claude-in-Chrome
extension is not connected in this environment; the new markup is served and
the element IDs verified in the response, but a visual pass is still owed.

Pre-edit copies: `~/Forge/backups/2026-09-07-freerein/`.

---

## Done this session

### 1. Jan / RAM crash fix  (the "multiple Jan servers, laptop freezes" bug)

Root cause confirmed: NovelForge never spawns Jan, but Jan's llama.cpp router
(`router.preset.ini`, `--models-max 2`) keeps **one resident `llama-server`
child process per distinct model**, several models configured with 20k–30k
context. Two ways NovelForge made this worse:

* **Concurrent requests.** `_refresh_models`, `_add_pdfs`, `_pdf_action`,
  `_do_research` each spawn a *raw* thread not tracked by `self.worker`.
  "Analyze style" on the References tab makes model calls, so it could run at
  the same time as a chapter generation — two heavy requests at once, and if the
  model dropdown had been changed, a second multi-GB model loading alongside the
  first.
* **No memory headroom check** before firing a run that loads a multi-GB model.

Changes:

* `janclient.py` — every request now goes through one process-wide re-entrant
  gate (`_JAN_GATE`). Only ever one model request in flight. `list_models` /
  `ping` take the gate non-blockingly so the UI never freezes behind a
  generation. Publishes a busy/idle/queue state (`jan_state()`,
  `set_state_callback`).
* `janclient.py` — `ram_status()`, `ram_is_low()`, `free_jan_memory()` helpers.
  `free_jan_memory` is best-effort: this Jan build exposes no unload route
  through the `:1337` proxy (routes are 404; the authed router on `:57469`
  needs Jan's internal key), so it's a no-op here but works if a future Jan adds
  one. The router LRU-evicts past `--models-max` on its own.
* `engine.py` — `_ram_gate()` runs before every chapter. If free RAM is below
  `min_free_ram_gb` (default 2.5) it asks Jan to free idle models, waits up to
  `ram_guard_wait_s` (90 s), and if it still can't recover it **stops cleanly** —
  the run resumes from that chapter on the next Start/Resume.
* `app.py` — header shows `RAM x.x G free · Jan: <state>`, colour-coded.
  `_start_generation` and the continuation writer refuse (with a confirm) when
  RAM is already low. Changing the model in the dropdown fires a best-effort
  `free_jan_memory` for the previous model. Settings tab: RAM-guard switch +
  threshold, and an "⏏ Unload idle Jan models" button.
* `config.py` — new defaults: `ram_guard`, `min_free_ram_gb`,
  `ram_guard_wait_s`. `install.sh` now installs `psutil` (guard degrades to
  off if it's missing).

Verified: 3 concurrent `complete()` calls serialise (queue depth observed, no
overlap). A live 2-chapter generation held RAM flat at ~22 GB free / ~2 GB
llama-server RSS with no second model loading.

**Still worth doing (needs a Jan restart, so left for you):** in
`~/.var/app/ai.jan.Jan/data/Jan/data/llamacpp/router.preset.ini` set
`[*] cache-ram` to a bounded value and drop the per-model `ctx-size = 20000`
lines to ~12000 for the 12B models; consider `--models-max 1`. That's the
Jan-side half of the fix and it's the bigger lever on a truly full machine.

### 2. Continuation / Never-Ending Story mode  (new)

* `continuation.py` — `CorpusIngest`: reads 1–12+ PDFs, learns the house style
  (stored as a StyleLibrary source so `_style_glue` folds it into every scene),
  rebuilds the codex from the corpus, writes a combined "story so far" +
  open-threads, captures the last ~1600 words of the final book as `seed_tail`,
  and infers genre + a next-instalment premise.
* New **"Continue a Series"** tab: add PDFs, pick a spin (Alternate POV /
  Time-skip / Side-character spin-off / Genre shift / What-if — editable text),
  Ingest, then "Write / continue" N chapters at a time. Run it again and again;
  the outline auto-extends (`engine.continue_run`).
* `memory.py` — `continuation_directive()` prepended to the context block:
  "world/cast/voice already established, don't reintroduce", the spin, and how
  the previous book ended. `scope_directive` gives an open-ended brief.
* `engine.py` — `build_outline(keep_existing=)` for extension; a continuation
  branch in the outline prompt; spin folded into `_style_glue`. Ending mode is
  always `book_hook` (never resolves the saga) because `planned_books` is set to
  99 and `book_index` to N+1.

Verified: all views build; the continuation context block renders correctly.
**Not yet run end-to-end against real PDFs** (user has none in the repo) — the
ingest model prompts may want tuning once tried on an actual series.

### 3. Polish

* Header connection indicator now has an explicit online/offline word next to
  the dot.
* `_dispatch` gained a generic `"call"` handler.

## Known small issues not touched

* `research.py` still uses DuckDuckGo Instant Answers (often empty) — fine, it's
  explicitly best-effort.
* Theme changes still need a restart (customtkinter limitation).

---

# 2026-09-04 — Export, cover art & audiobooks (second session, unattended)

Additive throughout: no existing tab, setting, DEFAULTS key or behaviour was
removed or renamed. Two new modules, one new tab, new settings.

## 1. New `novelforge/export.py` — books & covers

* **EPUB** via EbookLib: one XHTML doc per chapter, real nav + NCX TOC, a title
  page, embedded stylesheet, and metadata (title / author / language / genre /
  blurb) plus Calibre `series` + `series_index` so readers shelve a series in
  order. Cover image embedded when one is chosen.
* **PDF** wraps the existing `pdfexport.export_pdf` (untouched) and adds an A4 /
  Letter switch and the cover chosen in the tab.
* **TXT** plain concatenation.
* **Orchestration**: `export_book()` runs every ticked format; `export_series()`
  loops the *same* per-book function over `Series.list_all()`'s books into one
  folder, and honours the kill switch between books.
* **Covers** (Pillow, no ML, no network): `import_cover` copies a chosen file
  into the project; `quick_cover` composes a gradient / duotone / minimal ground
  from the accent colour with fitted title typography, genre line, series line
  and author (the gradient is painted 1px wide and scaled — a per-pixel loop
  over 4M pixels took seconds); `edit_cover` does crop-to-2:3, brightness,
  contrast and a title/author overlay on a legibility scrim, always to a copy.
* **`ai_cover`** is a deliberate stub behind `DIFFUSERS_OK`, same guarded-import
  pattern as reportlab/pypdf. Nothing was pip-installed for it. If the user
  installs `diffusers`+`torch` it lights up; otherwise the UI states the pip
  command and that it's minutes-per-image on this CPU-only box.
* Per-project sidecar `<project>/export.json` holds the chosen cover, so
  `bible.json` / `state.json` / `codex.json` are untouched by any of this.

## 2. New `novelforge/audiobook.py` — offline TTS

* **Piper** (`piper-tts` 1.7.0, installed into `.venv`, added to `install.sh`).
  Genuinely local: ONNX voices download once into `~/NovelMakerData/tts_voices/`
  from a curated 19-voice in-app list, offline forever after.
* **Per-character voices** persisted per project in `<project>/voices.json`;
  names come straight from `codex["characters"]`.
* **Dialogue attribution** (`split_segments`) is best-effort, in the spirit of
  `jsonrepair.py`: reads speech tags around a quote, falls back to the single
  name in the paragraph, alternates the last two speakers across a bare
  exchange, and routes anything it can't place to the narrator. Verified on a
  sample exchange — got all four lines right including two unattributed ones.
* **Rendering**: one WAV per chapter, voices pooled so each ONNX loads once,
  `numpy` linear resample if a character voice differs in sample rate, optional
  spoken chapter announcements. A WAV newer than its source chapter is reused,
  so a cancelled run resumes cheaply.
* **Stitching**: ffmpeg concat demuxer with a silence gap between chapters,
  writing an ffmetadata file so the output carries real **chapter markers** plus
  title/artist tags. m4a / mp3 / wav.
* Cancelable: `render_chapter` never leaves a truncated WAV looking rendered;
  soft stop finishes the chapter and stitches, hard cancel keeps the WAVs and
  skips the stitch.
* **Voice quality**: `-medium` models read flat (user said "too robotic"), so the
  catalogue now leads with the `-high` models — default narrator is
  `en_US-ryan-high` — labelled ★ high quality vs *(fast)*, and there's an
  **expression** slider mapped to Piper's `noise_w_scale`, which is the real
  lever on robotic prosody. Multi-speaker models are supported via a
  `voice#speaker_id` suffix.
  Measured on this box: `-high` ≈ 5× realtime, `-medium` ≈ 20-24× realtime.

## 3. New **Export** tab (`app.py`, sidebar key `"export"`, after Series)

Three cards: book export (target segmented control → this book / whole series,
format checkboxes, output folder), cover art (150×225 live preview + import /
quick generate / edit / remove / AI), audiobook (narrator picker with a ▷
audition button, a scrolling per-character voice list, split/announce toggles,
format, speed, expression, render / soft stop / cancel, progress bar).

Export and TTS run on a **separate** background thread (`self.job`) with their
**own** `KillSwitch` (`self.job_kill`) — cancelling an audiobook can never abort
a generation. Starting one while a generation is running asks first, mirroring
the RAM-guard confirm in `_start_generation`; the audiobook path also runs the
`ram_is_low` confirm.

## 4. UI responsiveness pass (surgical)

* `_hint` and `_labeled_entry` had hardcoded `wraplength=760` / `width=680`.
  They now register with `self._responsive` and resize from the real content
  width on a debounced `<Configure>`, both directions. `_labeled_entry(width=…)`
  still honours an explicit width, so deliberate fixed call sites are unaffected.
  The two other hardcoded `wraplength=740` labels (Continue, Series) joined too.
  30 widgets tracked in the smoke test.
* `_refresh_home` did three file reads per project on the UI thread; it now
  gathers stats on a thread and renders through the bus (`home_stats`).
* Header gained a **busy indicator** (`⏳ Export…`), fed by `_set_busy` and
  rendered alongside the existing RAM / Jan-state label. `_run_worker` marks
  generations busy too, so it covers everything.
* New settings: `ui_scale` (applied live via `ctk.set_widget_scaling`) and
  `ui_density` comfortable/compact, which really does tighten card, entry and
  textbox padding rather than being a decorative toggle.

## 5. Settings

New keys only — nothing removed or renamed. `author_name`, `export_formats`,
`export_dir`, `export_open_after`, `epub_language`, `pdf_page_size`,
`cover_style`, `cover_width`, `cover_height`, `ai_image_backend`, `tts_voice`,
`tts_voices_dir`, `tts_per_character_voices`, `tts_announce_chapter`,
`tts_speed`, `tts_variation`, `tts_format`, `tts_chapter_pause_ms`,
`tts_keep_chapter_wavs`, `ui_scale`, `ui_density`. All wired into a new
"Export, covers & audiobooks" card in the Settings tab.

## Verified

`py_compile` + import of every touched file. A real GUI run on `:0`: all nine
nav tabs build with and without a project open, resized 1600×900 / 1045×730 /
1240×860. Driving the tab's own handlers end to end on a throwaway project
produced a valid EPUB (checked the OPF: cover, series index, nav), PDF and TXT;
a whole-series export of the same book; a quick cover and an edited cover; and a
3-voice audiobook whose `ffprobe` output shows correct chapter markers and
title/artist tags. The throwaway project, series and exports were then deleted.

## Rough edges

* First render of a new voice pauses ~6 s to download it (~60–120 MB).
* Dialogue attribution is regex-only by design. Deep-POV prose with few speech
  tags will mostly fall back to the narrator — correct, but plainer.
* `en_US-libritts_r-medium` has 904 speakers; only speaker 0 is exposed in the
  list. The `voice#id` syntax works if you hand-edit `voices.json`.

---

# 2026-09-05 — follow-up: Kokoro, narration modes, casting, POV fidelity

Driven by live feedback while the first pass was still running.

## "The voice is too robotic"

* Added **Kokoro** (`kokoro-onnx`) as a second engine and made it the default.
  54 voices, 16 curated; one shared 354 MB model instead of one file per voice;
  ~3x realtime on this CPU. Measured against Piper `-high` (~5x) and `-medium`
  (~20x) by playing the same passage through both.
* Voice ids are now `engine:name` with an optional `#speaker` —
  `kokoro:am_michael`, `piper:en_US-libritts-high#40`. `parse_voice()` treats a
  bare id as Piper, so voice maps written earlier today still load.
* Engines sit behind `_PiperAdapter` / `_KokoroAdapter` (both expose `.rate` and
  `.chunks()`), so `_write_segment` doesn't care which one it's feeding.
* VOICEVOX was asked for and **not** added: it's Japanese-only and needs a
  separate ~1 GB engine server. Kokoro's `jf_alpha` / `jm_kumo` cover the same
  ground in-process. Said so rather than shipping a stub.

## Three narration modes

`tts_mode` = `single` | `cast` | `narrator_voices`, resolved by
`narration_mode()` which falls back to the old `tts_per_character_voices`
boolean so nothing written earlier changes behaviour.

`narrator_voices` is the "one narrator doing voices" case: the same model reads
everyone, pitch- and pace-shifted per character. Pitch is done honestly and
cheaply — synthesize `pitch` times slower, then resample by `pitch`, so duration
is unchanged and only the formants move. Per-character choice comes from a
dropdown ("higher", "low and slow", …) or falls back to a stable auto slot.

## LLM casting director

`cast_voices()` hands the codex (names, descs, traits, status) plus the voice
list to the local model and asks for JSON. Everything is filtered against real
character names and real voice ids, an unusable answer leaves the map alone.
Runs through `_run_worker` so it queues behind Jan like every other model call.
Always overridable by hand.

## Voice-model disk management

The user flagged disk use. `installed_report()` / `voice_bytes()` /
`voices_total_bytes()` / `delete_voice()` / `clear_previews()`, surfaced as
"⚙ Manage voice models…": every downloaded model with its size, a running total,
per-row audition and delete. Kokoro's two shared files are reported as one row
because deleting either takes all 54 voices. Deletion is safe — models
re-download on next use. Trimmed 1277 MB -> 453 MB at the end of the session.

## Startup time

The user reported a slow GUI. Profiled it properly:

* **My regression:** importing `novelforge.app` had gone to 0.73 s because
  `audiobook.py` imported piper and kokoro (onnxruntime, phonemizer, csvw) at
  module scope. Now `find_spec()` probes availability and the real import happens
  on first use — back to **0.25 s**.
* **Not my code:** the remaining 2–6 s is customtkinter redrawing every widget on
  each geometry change (`_tkinter.tkapp.call` dominates the profile; raw Tk is
  0.0005 ms/call here, so it isn't XWayland). The shell now paints before Home is
  built (`update_idletasks` + `after_idle`), so the window appears immediately.
  Wall-clock varies 2–6 s with system load — it was measured with Firefox and a
  loaded `llama-server` competing.

## Continuation POV / name fidelity  ← the substantive fix

Reported: *"it often messes up the names, POV especially in the continue story
option — I want it to continue writing exactly as the author did."*

Root cause: `_scene_system()` said only "Immersive, in the POV established so
far" — the model was never told which POV or tense, and the name list wasn't
marked authoritative.

* `continuation.detect_narrative_profile()` **measures** POV and tense from the
  corpus: strips quoted dialogue first (otherwise every spoken "I" reads as
  first-person narration), then counts 1st/2nd/3rd pronouns and past/present verb
  markers. Returns `{}` rather than guessing under 200 words of narration.
  Verified on four fixtures including a third-person passage stuffed with
  first-person dialogue — correctly third person, 0 first-person hits.
* The POV character is asked of the model but only accepted if it matches a codex
  character (exactly or by substring), because small models invent names.
* `memory.continuation_directive()` gained a NARRATIVE VOICE block (absolute POV +
  tense + POV character) and CANONICAL SPELLINGS / CANONICAL PLACES lists.
* `engine._scene_system()` now states the measured voice instead of the vague
  line, widens the name roster 12 -> 24, and calls it "the ONLY correct character
  names, spelled exactly as given — never rename, never invent a variant."
* New **Narrative voice** card on the Continue tab shows the measurement, the raw
  counts and the confidence, and lets POV / tense / POV character be overridden.
* Regression-checked: an ordinary non-continuation project still gets the
  original "POV established so far" wording and no NARRATIVE VOICE block. New
  bible keys (`narrative_profile`, `canon_names`, `canon_places`) are additive.

## Not done

* The `narrator_voices` auto slots are assigned alphabetically, so a 50-year-old
  woman can land on a raised pitch. Set it explicitly per character, or let the
  casting director run in `cast` mode instead.
* POV measurement is corpus-wide. A source series that switches POV per chapter
  gets one profile, which will be wrong for some chapters.

---

_2026-09-04, second unattended session._

## Done this session

### 1. UI responsiveness pass

* `_hint`'s wraplength and `_labeled_entry`'s entry width no longer freeze at
  the pixel constants they were built with — both now bind to their parent's
  `<Configure>` event and recompute against real available width, so the app
  looks right resized well past or under the 1240x860 default (minsize stays
  1040x720).
* Header gained a small busy indicator next to the RAM/Jan-state label, driven
  off the same `Bus` pattern generation already uses, so an Export or
  audiobook job running in the background is visible instead of silent.
* Any export/cover/TTS work found blocking the Tk thread was moved onto its
  own worker thread + kill switch (`_run_bg`, `KillSwitch`), separate from the
  generation worker so the two can't collide silently.

### 2. New **Export** tab  (`novelforge/export.py`, `novelforge/audiobook.py`)

New sidebar entry after Series. Works for **one book or a whole series**
(series mode reuses the exact same per-book path over every book attached to
the series, into one output folder).

* **EPUB** via EbookLib — each chapter its own XHTML document, a real
  nav/TOC, metadata (title, author from Settings, series + book index),
  optional embedded cover. Guarded by `EPUB_OK`; missing EbookLib degrades to
  a pip hint, same pattern as `pdfexport.py`.
* **PDF** — `pdfexport.export_pdf` extended to take the cover chosen on this
  tab; existing PDF export behaviour is unchanged otherwise.
* **TXT** — plain title + manuscript concatenation.
* **Cover art** — import your own image; or an instant procedural "quick
  cover" built with Pillow from the book's title/genre and the app's own
  accent colour (no model, no network, always available); light edits
  (crop-to-cover-ratio, brightness/contrast, title/author text overlay). A
  local Stable Diffusion path exists behind `DIFFUSERS_OK` but is a
  deliberate stub — torch+diffusers is a multi-GB install and minutes per
  image with no GPU on this machine, so it only activates if the user installs
  it themselves; the UI explains this rather than pretending it's fast.
* **Audiobooks** — real offline narration via **Piper** (`piper-tts`, now
  installed in `.venv`; pulls in `onnxruntime`, ~60 MB of wheels). Each World
  Codex character can be assigned its own voice from a small curated list of
  distinct public Piper voices, downloaded once into
  `~/NovelMakerData/tts_voices/` and cached offline after that, plus one
  narrator default. A best-effort regex dialogue attributor (same spirit as
  `jsonrepair`/`textquality` — degrades to "everyone is the narrator" rather
  than guessing wrong) routes quoted lines to the speaking character's voice.
  Chapters render to WAV via Piper, then `ffmpeg` stitches them into one
  tagged, chaptered audiobook file per book under `<project>/audiobook/`.
  Runs on its own cancelable worker thread with progress through the `Bus`;
  starting it while a Jan generation is running prompts a confirm first, the
  same shape as the existing RAM-guard confirms.

### 3. Settings

New `config.DEFAULTS` keys (additive only — nothing existing renamed or
removed): export format/output-dir defaults, author name for EPUB metadata,
narrator default voice + voice cache folder, dialogue-auto-split toggle,
image-gen backend on/off. Settings tab gained an "Export, covers & audiobooks"
section using the existing card layout.

### 4. Docs

* `install.sh` now installs `piper-tts` alongside the rest.
* `README.md` — new "Export & Audiobooks" section, dependency table updated.

Verified: `py_compile` + `import novelforge.app, novelforge.export,
novelforge.audiobook` clean; `piper-tts`/`onnxruntime` actually present in
`.venv`; app launched on the real display for 7s with no exceptions, all
nav tabs including the new Export one build. Not yet run end-to-end against a
real project's chapters/voices (needs the user to click through it once with
a live project).
