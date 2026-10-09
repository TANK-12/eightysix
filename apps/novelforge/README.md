# NovelForge

A local, single-machine studio for writing **long** novels (and whole series)
with the models you already run in [Jan](https://jan.ai/). Nothing leaves your
computer except optional DuckDuckGo idea lookups.

It's the successor to the `novelN.py` scripts: it keeps everything that worked
in *novel4* (World Codex, memory manager, PDF style learning, add/remove model
list) and folds in the good parts of *novel5* (live token streaming, a real
kill switch, styled PDF export, directly-editable outline) — then adds the
pieces that were missing.

## What's new vs. the old scripts

| Area | Before | NovelForge |
|---|---|---|
| **Stopping** | "stop after chapter" only | Soft stop **and** a hard KILL that aborts the HTTP stream mid-token, with *keep / discard partial* |
| **Length** | one model call per chapter → hits the output cap at ~2–4k tokens | each chapter is planned into **scene beats**, each beat streamed, and **continued** until it reaches your words-per-chapter target |
| **Weird model output** | `json.loads` + one regex; tiny models broke it (you got 0-word chapters) | `jsonrepair.py`: strips `<think>` blocks, markdown fences, single quotes, trailing commas, unquoted keys; accepts **lists where dicts were asked for** and vice-versa; loose `KEY: value` fallback format for small models |
| **Model awareness** | one prompt for every model | reads each model's real `ctx_size` from `model.yml`, clamps the context budget to it, and picks a **size profile** (tiny / small / medium / large) that changes prompt length, retry counts and JSON strictness |
| **Empty output** | saved silently | retried, then reported loudly — never writes a 0-word chapter |
| **Series** | none | group books, inherit the earlier books' codex + a synopsis as canon, "Start next book" |
| **UI** | tk notebook | customtkinter, dark/light, nav rail, live stream pane, Simple vs Advanced controls |
| **App** | `python novel5.py` | shows up in your app launcher as **NovelForge** |
| **Output** | manuscript.md + a PDF | **Export tab**: EPUB / PDF / TXT for one book *or* a whole series, cover art, and a fully offline **audiobook** with a different voice per character |

## Rework (2026-09-28, committed 2026-10-09)

- **A model per role.** Header pickers on every tab: the writer writes prose,
  the planner (Advanced; "Same as writer" by default) writes outlines,
  Free-Rein, style analysis and voice casting. Settings > Jan memory sets how
  many idle minutes before NovelForge unloads a model it loaded.
- **Genre presets** (`novelforge/presets/*.json`, found by folder scan, 14 of
  them, Korean hunter/system first; `_common.json` holds shared voice rules and
  worn phrases). Picked on the Story tab; "Auto" guesses from the genre. A new
  preset is one new JSON file.
- **Checked outlines** (`novelforge/outline.py`): the preset's structure is
  mapped onto chapters, the model fills small batches of
  `Title | what happens | what changes | hook` lines, and each line is checked
  and re-asked alone if it fails. It never writes filler: it stops and saves,
  and "Continue outline" resumes.
- **Prose prompts** built from the preset voice plus hard rules, kept identical
  for a whole run so llama.cpp reuses the cached prefix between scenes.
- **Look-ups** (`novelforge/rag.py`): BM25 word search over earlier chapters and
  world-document sections, per scene (Settings: "Passages looked up per scene").
- **Delete and reset everywhere:** delete a project (to
  `~/NovelMakerData/.trash`), reset parts of it, rewind from chapter N, clear
  outline or world doc, edit the outline in place, delete codex entries.
  Destructive actions are refused while a job runs on that project.

Not yet done: a live outline run on the small Jan models to tune the line
checks (see WIP.md).

## Setup

```bash
cd ~/NovelForge
bash install.sh
```

That creates `.venv` (sharing your system `tkinter` / `requests` / `pypdf` /
`reportlab`), adds `customtkinter`, generates an icon, and installs a
`novelforge.desktop` entry. Then just search **NovelForge** in your app menu.

Run without installing:

```bash
python3 run.py          # re-execs into .venv automatically if it exists
```

### Dependencies

Everything optional is guarded: if a library is missing the app still runs and
the feature that needs it explains the `pip` command instead of crashing.

| Package | Needed for | Missing → |
|---|---|---|
| `customtkinter`, `tkinter` | the GUI | required |
| `requests` | talking to Jan | required |
| `psutil` | RAM guard | guard off |
| `pypdf` | reading reference PDFs, Continue-a-Series | PDF learning off |
| `reportlab` | PDF export | PDF export off |
| **`EbookLib`** | **EPUB export** | EPUB off |
| **`Pillow`** | **cover art (import, quick generate, edit)** | covers off |
| **`kokoro-onnx`** | **the realistic audiobook voices (default engine)** | falls back to Piper |
| **`piper-tts`** | **offline audiobook narration, multi-speaker models** | audiobooks off |
| **`ffmpeg`** (system) | **stitching audiobook chapters** | audiobooks off |
| `diffusers` + `torch` *(not installed)* | optional AI cover generation | AI cover off — the quick cover needs nothing |

## Using it

1. **Home** — create a project (one project = one book).
2. **Story** —
   - **Scope**: *One-shot* (a single self-contained story) or *Series* of N books
     (shared world + an overarching arc; each book resolves its own arc and,
     except the last, ends on a hook). This changes the outline, the endings,
     and how books are saved and chained.
   - **World depth**: Sketch → Standard → Rich → Epic. Higher = Free-Rein writes
     far more (a multi-pass *World Document*: foundation → cast dossiers →
     places/factions/history → myth/culture), scaled to dozens of characters.
   - Genre / protagonist / plot / pinned facts, then **✦ Free-Rein** invents the
     rest and fills the World Document + Codex. Everything is editable.
   - For a series: **Plan series arc** (or Free-Rein does it) writes the
     multi-book plot; each book's outline is shaped by it.
3. **References** *(optional)* — add your own novel PDFs. *Analyze style* is
   auto-used every scene; *Summarize content* is kept only as your reference.
4. **Generate** — target chapters and words/chapter (defaults lean long:
   30 × 3500). *Generate outline*, then *Start / Resume*. Watch it stream.
   *Soft stop* finishes the chapter; **KILL NOW** aborts mid-token.
5. **World Codex** — auto-maintained, with the rolling **Story-so-far synopsis**
   and **Open threads** the engine keeps updated so a long book doesn't forget
   or contradict itself. Hand-editable as raw JSON.
6. **Series** — attach the book to a series, import earlier books as canon,
   or **Start next book** (carries the world doc, arc, codex and ending state).
7. **Export** — EPUB / PDF / TXT, cover art and audiobooks. See below.
8. **Output** — `manuscript.md` is rewritten after every chapter in the project
   folder; export a styled PDF from there too.

## Export & Audiobooks

The **Export** tab does three things, for a single book *or* every book in a
series (same code path, just looped):

**Books.** Tick EPUB / PDF / TXT and hit Export.
- *EPUB* is a real one: each chapter is its own XHTML document, with a proper
  nav/TOC, a title page, and metadata — title, author (from Settings), genre,
  blurb, plus Calibre-style `series` / `series_index` so a reader app shelves
  book 2 after book 1. Your cover is embedded.
- *PDF* is the existing styled export, now taking the cover you chose here.
- *TXT* is a plain concatenation, for when you just want the words.

Output goes to `<project>/export/` unless you set a folder; a whole-series
export lands in `~/NovelMakerData/exports/<series>/`.

**Cover art.** No ML, nothing over the network:
- **Import image…** copies your own file into the project folder.
- **✦ Quick generate** builds a cover instantly from the title, genre, series
  line and your accent colour — gradient, duotone or minimal.
- **Edit cover…** does the three things people actually want: crop to the 2:3
  cover ratio, brightness/contrast, and a title/author overlay on a legibility
  scrim. It always writes a copy; your original is untouched.
- **✧ AI generate** is a stub, off by default. It lights up only if you install
  `diffusers`+`torch` yourself — on this CPU-only machine that's a multi-GB
  install and minutes per image, which is why the procedural cover is the real
  feature.

**Audiobooks — local, offline, per-character voices.** Two engines behind one
list, both fully offline once their model is downloaded into
`~/NovelMakerData/tts_voices/`:

| Engine | Voices | Speed on this CPU | Notes |
|---|---|---|---|
| **Kokoro** ★★ *(default)* | 16 curated of 54 | ~3× realtime | Clearly the most human. One shared 354 MB model covers every voice |
| **Piper** ★ | 20 curated | ~5× realtime (`-high`), ~20× (`-medium`) | 60–120 MB per voice. Includes `en_US-libritts-high`, 904 speakers in one file |

Voice ids are `engine:name` — `kokoro:am_michael`, `piper:en_US-ryan-high`,
`piper:en_US-libritts-high#40` for a speaker inside a multi-speaker model. A bare
id still means Piper, so older voice maps keep working.

**Three narration modes:**
- **Single narrator** — one voice reads everything.
- **Full cast** — a different voice *model* per character.
- **One narrator doing voices** — the narrator reads everyone, pitch- and
  pace-shifted per character (pick "higher", "low and slow", … per name, or leave
  it on auto). One model, several apparent voices — the audiobook-actor approach.

- **✦ Auto-cast with the model** hands your codex — names, descriptions, traits —
  to the local LLM and asks it to cast every character by apparent gender, age,
  accent and temperament. Everything it picks is overridable by hand.
- A best-effort regex attributor routes quoted dialogue to the speaking
  character's voice — it reads speech tags (`"…," Elena said`), falls back to the
  only name in the paragraph, and alternates speakers across a bare exchange.
  Anything it can't place stays with the narrator, which is the honest failure
  mode rather than a wrong voice.
- Chapters render to WAV and are stitched by `ffmpeg` into one tagged file with
  **chapter markers**, under `<project>/audiobook/`. The map lives in
  `<project>/voices.json`.
- **⚙ Manage voice models…** lists everything downloaded with its size and a
  running total, and deletes any of it — models re-download automatically the
  next time they're used, so pruning is always safe.
- Runs on a cancelable worker thread with its own kill switch, separate from
  generation, plus a header busy indicator; it warns before competing with a
  running generation for RAM and CPU, and re-uses already-rendered chapters if
  you restart it.

Use ▷ to audition any voice — or any character's pitch — before committing to a
ten-hour render. For Piper voices the **expression** slider (`noise_w_scale`) is
the cure for a flat, robotic read; Kokoro needs no such help.

## Continuing an existing series in the author's voice

The **Continue a Series** tab's biggest failure mode was the continuation
drifting out of the source author's voice — names quietly mutating, and the POV
or tense sliding between chapters. The scene prompt used to say only *"in the POV
established so far"*, which tells a local model nothing it can act on.

Ingest now **measures** the narrative voice instead of hoping:

- Quoted dialogue is stripped first, then first/second/third-person pronouns and
  past/present verb markers are counted across the whole corpus. A character
  saying "I know what I saw" no longer makes a third-person book look
  first-person. Too little narration to be sure and it declines to guess rather
  than guessing wrong.
- The POV character's name is asked of the model but only accepted if it matches
  someone already in the codex.
- The result is pinned into **every** scene prompt as an absolute rule —
  *"first person, past tense · narrated by Elena Marsh. Every sentence of
  narration must stay in this person and this tense."*
- The codex's exact spellings go in as **canonical names and places**: *"use
  these exactly; never rename, never invent a variant."*

The **Narrative voice** card on the Continue tab shows what was measured, with
the raw pronoun and verb counts and a confidence figure, and lets you override
POV, tense and POV character by hand. Ordinary (non-continuation) projects are
untouched by this.

## Quality guards (why the old runs collapsed)

Small local models fall into repetition loops and abstract "prose-poem" drift,
and earlier versions saved the results and poisoned every later chapter. Now:

- Every prose call carries **DRY sampling + light repetition penalties** (the
  single biggest fix — a looping 14B becomes coherent).
- Output is checked for **degeneration** (sentence / trigram / compression
  repeat) and **prompt-scaffolding leakage**; a looping scene is retried once
  hotter, then trimmed to its healthy prefix; a chapter that still reads as a
  loop is **not saved**.
- Scenes are forced to use **real character names**, make **something happen**,
  and include **dialogue**; abstract drift is detected and retried.
- Tune anti-repeat strength and toggle the guard in **Settings → Advanced**.

## Where things live

```
~/NovelMakerData/
  projects/<book>/  bible.json  state.json  codex.json  chapters/  manuscript.md
                    cover.png  export.json  voices.json
                    export/    <title>.epub | .pdf | .txt
                    audiobook/ <title>.m4a | .mp3 | .wav
  series/<name>/     series.json
  exports/<series>/  whole-series exports
  tts_voices/        downloaded Piper voice models (offline after first fetch)
  style_library.json     known_models.json     novelforge_settings.json
```

## Model notes (this machine — Intel iGPU, CPU inference, ~13 GB free RAM)

**Use a dense, instruction-tuned model — not a small MoE and not an RP/"vibes"
finetune.** Those loop and drift, which is what wrecked the early runs.

| Model | Why | Size (Q4_K_M) |
|---|---|---|
| **Mistral-Nemo-Instruct-2407** *(downloaded for you)* | 12B dense, 128k context, follows the bible, doesn't loop — best default here | ~7.1 GB |
| `Gemma-4-12B-OBLITERATED` *(you have it)* | dense 12B, uncensored; solid with the DRY guard on | ~7 GB |
| `Llama-3.2-3B` / `Qwen3_5-4B` *(you have them)* | fast, coherent, less rich — fine for drafting | ~3 GB |

**Avoid for prose:**
- `Qwen3_6-14B-A3B-FableVibes` — MoE with only ~3B active params + a "vibes"
  finetune; loops and writes purple abstraction. This is what produced the
  58k-word repetition in `My_first_romcom`.
- `VibeThinker-3B` — reasoning-tuned; `<think>` is stripped but it's not a
  prose model.
- The `*-Uncensored-HauhauCS-Aggressive` finetunes — RP-tuned, loop-prone.

Whatever you pick, keep the **degeneration guard** on and **DRY ≥ 0.6**.
