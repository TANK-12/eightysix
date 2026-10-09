# AI Studio: work in progress

## Rebuild (2026-10-08, crew ai-studio)

What and why: see README "Rebuild (2026-10-08)". Files: `src/catalog/`,
`src/engine_flags.py`, `src/video_models.py`, `src/worlds/`, rewritten
`src/model_manager.py`, `src/app.py`, `src/motion.py`, `src/longform.py`,
`src/hybrid.py`, `src/library.py`, new `static/` (index.html, css, js), `bin/next/`,
`docs/` (plan, WORLDS.md, AUDIT.md), tests (`test_catalog*`, `test_parts`,
`test_api*`, `test_engine_checks`, `test_worlds_*`, `test_features_*`,
`check_ui.py`).

Verified: full suite 323 passed, 128 skipped (opt-in live HF size checks; run
once live: 128/128 sizes match); pyright 0 errors on touched src files
(`tests/check_ui.py` reports only the path-injected `cdp_driver` import);
check_ui 174 passed at 760/1100/1920 px, screenshots looked at.

Open:
- No GPU run of anything new: `bin/next` engine, the new image models, model
  video, edit, world moves. Waiting for Emerson's OK.
- Emerson's running AI Studio (port 8430) still runs the old backend until he
  presses Close app and opens it again; the new page needs the new backend.
- The draggable panels (B41) were dropped for the fixed layout: ask Emerson.
- Move model files to the shared Forge model home `~/Forge/models/diffusion/`
  (FORGE_MODELS_DIR, agreed with Relay 113's voice work 2026-10-08), keeping
  `models/sd/catalog/` as a fallback.
- PiD upscaler left out (gated Gemma tokenizer + new route needed).
- InSpatio-World 1.5 runtime is specified in docs/WORLDS.md, not installed
  (needs review; ~11 GB text encoder in RAM, no swap).
- outputs/ holds 3 folders from failed jobs (bb6e723a6f35, 8bbf525ee384,
  29c5f0445927); `library.orphans()` lists them, nothing deletes them.

## Plain model picker (2026-10-08)

Emerson asked for the Models panel to drop the technical details. The
cards no longer show the "anime · 3.5GB" line (CSS rule gone too), and
`/api/models` no longer sends `style`/`size_gb`. The Vega entry is now
"Realistic -- High Detail" with a blurb that has no pixel sizes
(`src/models_catalog.py`, which black reformatted; the internal
`description` field keeps the technical notes). Sizes still show in
"Delete all models". **Verified:** `tests/test_model_picker_text.py`
(no px/GB/SDXL/VAE-style terms in any card), full suite 50 passed,
pyright 0 errors, headless screenshot of the open Models panel.

## U1 sweep (2026-10-08, Relay task 74)

Group G11, Relay task 86. Backups of the edited files are in
`backups/2026-10-07-overhaul/sweep/ai-studio/`.

What changed:
- Library search no longer 500s on FTS5 syntax (`"`, `AND`, `NEAR(`, `:(`):
  every typed word is a quoted phrase, the last one still a prefix; only
  punctuation finds nothing (`src/library.py`).
- Request bounds (pydantic `Field`): sizes 64-2048, steps 1-150, cfg 0-30,
  seed -1 or more, upscale 2-4, jpg/png only, keyframes and scene frames
  1-60, fps and hold frames 1-60, strengths 0-1, at most 20 scenes, prompts
  up to 4000 characters, motion one of `motion.PRESETS`. Bad values get a 422
  instead of an hours-long or crashing job. `/api/jobs/{id}/state` refuses
  odd ids (400).
- Page: the newest library search wins (an older answer arriving late is
  dropped); when the server is down the gallery and the Models panel say so
  calmly and retry by themselves (2 s growing to 30 s, resting while
  hidden), no request storm and no uncaught errors; the models poll skips
  rebuilding the cards when nothing changed; Activate / Delete / Download
  send one request per click and stay busy until the answer, and a refusal
  is shown in words; field errors read "seed: Input should be ..." instead
  of "[object Object]"; empty or junk number fields send the default
  (clamped to the field's min/max), never null or NaN.
- The looping preview video pauses while AI Studio is hidden and carries on
  when shown (not if it was paused by hand); library thumbnails load lazily
  (`loading=lazy`, videos `preload=metadata`).
- Looks: thin themed scrollbars (incl. `::-webkit-scrollbar` for the hub),
  the Models dialog fades in, thumbnails lift slightly on hover, and the
  Settings and Library panels leave room under the hub's floating Close app /
  Full screen buttons.

Verified:
- `tests/test_u1_robustness.py` (37 cases) plus the old tests: 46 passed.
  The tests call the handlers and request models directly: this venv's
  starlette 1.6 test client wants an extra `httpx2` package, which was not
  installed (needs review first).
- Headless Chrome on a scratch copy (port 9011, empty models so no
  sd-server): hidden page makes 0 fetches / timers / frames in 10 s (hub
  signal and document hidden); stage video paused on hide, playing again on
  show; API down: calm lines, 5 requests in 12 s (was 10), recovers to 5
  model cards and 14 thumbnails; slow-then-fast search race keeps the newest;
  double-click Download is one request; screenshots at 760, 1100, 1500 and
  1920 px (main, models, video) in `/tmp/u1/G11/shots/as-*`.
- Live on the scratch server: width 51200 is a 422, an unknown motion a 422
  naming the allowed ones, `/api/jobs/a.b/state` a 400.

### Critic follow-up (G11 critic, 2026-10-08)
Report: `sessions/2026-10-07-overhaul/critics/u1-G11-critic.md`. Fixed:
- NaN / Infinity in a request is a 422 ("Input should be a finite number"),
  not a 500; the 422 reply no longer echoes the rejected value back.
- A search the server refuses (4xx, e.g. far too long) says so once and
  does not retry; the search box takes at most 500 characters.
- A video that finishes while AI Studio is hidden starts when it is shown.
- Video thumbnails are back on the default preload (the critic suspected
  `preload=metadata` paints black tiles in WebKitGTK); images stay lazy.
Verified: 49 tests passed (3 new); live curl NaN gives 422; headless Chrome:
video landed hidden is paused, playing once shown; 4xx search shows its
line and makes 0 requests in the next 8 s.

Not verified / notes:
- No real generation was run (no GPU jobs in the sweep).
- Static changes reach Emerson's Forge on the next page reload; the backend
  (`src/app.py`, `src/library.py`) only on his next Forge restart.
