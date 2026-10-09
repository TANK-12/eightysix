# Forge consolidation + packaging — end-to-end plan

Status: **DONE 2026-09-06** (Phases 1–4, 6, 7 + Windows Codec Player).
Git and the packaging panel were deferred by the user. Everything that can be
verified without the GTK window or a GPU has been verified; the rest is a short
checklist for you below and in `PROGRESS.json` → `session_4_work.user_to_do`.

Progress log is at the bottom of this file and in `PROGRESS.json`.

## What you asked for (decoded)

1. Make **AI Studio work properly inside the Forge window** — it currently
   behaves better when run standalone.
2. **Only Forge** should appear in the app launcher / Super-key search. The
   other apps get hidden from search but their code stays on disk and runnable.
3. Retire the "old standalone GUIs" as the way you *use* the tools — everything
   is driven through Forge. (Launcher code stays for debugging; you said keep
   as-is.)
4. Pull the **Codec Lab** and **Codec Player** (from `~/anime-codec-lab`) into
   Forge as their own sidebar entries.
5. A **Downloads/Packaging panel inside Forge**: build a shippable file per app
   on demand, download it from the panel, and a **delete button** to reclaim
   the space once you've uploaded it to GitHub.
6. Builds for **Linux and Windows where feasible without large download/disk
   cost**. AI Studio and the Forge shell itself are Linux-only and not shipped
   as downloads. No single combined "whole Forge" bundle.
7. An **efficiency pass** over the code. There is no "nuclear" whole-repo skill;
   the plan uses `/simplify` on every file touched plus a targeted review of
   the genuinely hot paths.

## Decisions locked in from your answers

| Question | Answer |
|---|---|
| First slice | One big plan, approve the full sequence first |
| Windows scope | Player for sure; Codec Lab feasible; Novel/Media only if cheap; **not** AI Studio, **not** the Forge shell |
| Download mechanism | In-Forge packaging panel with per-app build + download + delete |
| Old standalone GUIs | Keep the code as-is on disk |
| App search | **Only Forge** searchable; hide the rest (`NoDisplay=true`) |
| Codec Lab on disk | **Symlink** `~/anime-codec-lab` into `Forge/apps/`, don't move it |
| Whole-Forge bundle | Not shipped — per-app downloads only |

## Root-cause findings (already investigated)

- **AI Studio inside Forge:** its `apps/ai-studio/forge_app.json` uses **port
  8420 — the same port its standalone `app_window.py` binds.**
  `outputs/ai-studio.log` ends with
  `[Errno 98] error while attempting to bind on address ('127.0.0.1', 8420):
  address already in use`. If a standalone AI Studio (or a leftover process)
  is up, Forge's copy can't start, and both would fight over the sd-server
  ports (`1234`/`1235`) and the GPU. This is the leading suspect for "works
  better outside." There may be a second layer of WebKitGTK-iframe quirks
  (file-picker dialogs, `<video>` playback, downloads) — those get checked
  after the port fix, with you testing a real generation.
- **Codec Lab** is already FastAPI + a `static/index.html` with relative
  `/api/...` paths — it fits Forge's "discovered app" model directly. Its
  `.venv` is `--system-site-packages`.
- **Codec Player** (`player.py`) is **not** a web app — it's an OpenCV window.
  The in-Forge version will be a small web player that decodes a `.acv`
  server-side and plays the result in a `<video>`; the standalone `player.py`
  and its `.exe`/binary stay as the shareable artifact.
- **`.acv` double-click:** if the Player is hidden from search, the
  `AnimeCodecPlayer.desktop` entry is kept but marked `NoDisplay=true` so it
  still registers the `application/x-acv` MIME handler.
- **No git in `~/Forge`.** `~/anime-codec-lab` is a git repo with zero commits
  and no remote. Nothing has a remote. `git init` for Forge is offered in
  Phase 0 but not forced.

---

## Phase 0 — Safety net (fast)

- Copy every file about to change into `Forge/backups/2026-09-06-consolidation/`
  (the established pattern — there's no version control).
- **Offer** `git init` in `~/Forge` with a `.gitignore` for `apps/*/.venv`,
  `apps/ai-studio/models`, `apps/ai-studio/bin`, `outputs/`, `backups/`,
  `dist/`, `hub/status.*`. You've deferred this twice; still just an offer.
- No code change ships in this phase.

## Phase 1 — AI Studio works inside Forge + upscale-artifacts bug

1. Change `apps/ai-studio/forge_app.json` `port` from `8420` to a dedicated
   Forge port (`8430`) so a Forge-launched backend and a standalone one never
   collide — matches the convention the README documents. (`outputs/ai-studio.log`
   shows `[Errno 98] address already in use` on `8420`.)
2. Document the sd-server ports (`1234`/`1235`) as still shared — don't run
   standalone AI Studio and Forge's AI Studio at the same time.
3. **Upscale block-artifacts bug:** `engine.upscale()` calls
   `realesrgan-ncnn-vulkan` with no `-t` (tile size), so it attempts one large
   Vulkan allocation and hits the same Iris Xe per-allocation ceiling that the
   sd-server fix (`--*-conv-direct --vae-tiling`) was written for — producing
   coherent rectangular block garbage while the pre-upscale raw image is clean.
   Fix: add a configurable `-t` tile cap (`config.UPSCALE_TILE`, default 200)
   to the Real-ESRGAN command. Apply the same `-t` guard to
   `rife-ncnn-vulkan` in `engine.interpolate()` (identical failure class).
4. Launch Forge, run a **real image generation + upscale** in the AI Studio
   tab. (You verify this — GPU-bound; I can't run it. This and the sd-server
   fix are the two claims that need your eyes on a real high-res generation.)
5. If anything else is off inside the iframe (file dialogs, library grid,
   `<video>` for video-gen, downloads), fix per-symptom.
6. `black` + `pyright` on touched files.

**Deliverable:** AI Studio in Forge behaves like standalone; AI upscale no
longer corrupts a good image.

## Phase 2 — Only Forge in app search

1. In `~/.local/share/applications/`, add `NoDisplay=true` to
   `novelforge.desktop`, `mediaforge.desktop`, `ai-studio.desktop`,
   `AnimeCodecLab.desktop`, and `AnimeCodecPlayer.desktop`.
   - Keep `AnimeCodecPlayer.desktop`'s `MimeType=application/x-acv` line so
     `.acv` files still open on double-click.
   - `forge.desktop` stays visible and is the only launcher entry.
2. `update-desktop-database ~/.local/share/applications/`.
3. Fully reversible (flip `NoDisplay` back). Originals backed up.

**Deliverable:** Super-key search shows only "Forge".

## Phase 3 — Codec Lab as a Forge app

1. `ln -s ~/anime-codec-lab ~/Forge/apps/codec-lab` (keeps the research repo,
   its `.venv`, and its Wine build tooling intact and separate).
2. Add `apps/codec-lab/forge_app.json` (written into the real dir; add it to
   that repo's `.gitignore`): `label "Codec Lab"`, `port 8431`,
   `module "server:app"`, `src_dir "."`, `order 4`, accent hue.
3. In `anime-codec-lab/server.py`: mount `/shared` (the Forge kit) **before**
   the `/static` and `/` routes, skipping it when the directory is absent so
   the lab still runs standalone.
4. In `anime-codec-lab/static/index.html`: adopt the Forge palette tokens and
   `shared/forge.css` / `shared/forge.js` so it reads as one product with the
   other tabs. Keep its own accent.
5. Verify `forge.py` discovers a **symlinked** app dir correctly (it uses
   `os.listdir` + `os.path.isfile` — expected to work; confirmed by launching).
6. Confirm the lab's `--system-site-packages` venv satisfies
   `python -m uvicorn server:app` when launched by Forge. ffmpeg is already on
   the machine.
7. Run a real encode/compare in the tab; screenshot.

**Deliverable:** "Codec Lab" tab runs the full lab UI inside Forge.

## Phase 4 — Codec Player as a Forge app

1. New dir `~/Forge/apps/codec-player/` with `forge_app.json`
   (`label "Codec Player"`, `port 8432`, `order 5`).
2. `web_app.py` (FastAPI, follows the house Job pattern):
   - Bridges `sys.path` to `~/anime-codec-lab` to reuse `core/container.py`,
     `core/frames.py`, `strategies/`.
   - `POST /api/open` — upload a `.acv`, decode via
     `strategies.registry.build(header.strategy_key, header.params)`, render an
     mp4 with the embedded WAV muxed in, return its URL.
   - `GET /video/{id}` — serve it.
   - `/shared` mount + a small `static/index.html`: drop zone + `<video>` on
     the shared kit.
3. `.venv`: a `--system-site-packages` venv (numpy/opencv/fastapi) or a symlink
   to the lab's.
4. Open a real exported `.acv`, confirm picture + sound; screenshot.

**Deliverable:** "Codec Player" tab: open a `.acv`, watch it with audio.

## Phase 5 — SKIPPED (packaging panel), except: Windows Codec Player

Per the user: no in-Forge packaging panel, no per-app downloads. The only
packaging deliverable is a **cross-built Windows `AnimeCodecPlayer.exe`**,
refreshed from the current `player.py` via the documented Wine + Windows-Python
+ PyInstaller recipe in `anime-codec-lab/BUILD_MANIFEST.json`, Wine-smoke-tested,
and left in `anime-codec-lab/release/windows/`. Real-Windows verification is
still out of reach here — flagged for the user.

<details><summary>Original Phase 5 (not being done)</summary>

### In-Forge packaging / downloads panel

1. New Forge app `apps/packager/` (`label "Downloads"`, `order 6`) — a normal
   discovered app, so `forge.py` stays untouched.
2. **Declarative target registry** (one entry per app × platform), e.g.:
   `novelforge-linux`, `mediaforge-linux`, `codec-lab-linux`,
   `codec-lab-windows`, `codec-player-linux`, `codec-player-windows`.
   Adding a target = one registry entry + its builder function.
3. Backend:
   - `GET /api/targets` — each target with build state, artifact size, mtime,
     and a feasibility note.
   - `POST /api/build/{target}` — runs the build as a background Job with a
     live SSE log. Linux → PyInstaller in that app's venv. Windows → PyInstaller
     under Wine, reusing `anime-codec-lab/winbuild/wineprefix` where it applies.
   - `GET /api/download/{target}` — `FileResponse` of the artifact.
   - `DELETE /api/artifact/{target}` — the **delete button**; removes the built
     file(s) after you've uploaded them to GitHub. Confirms in the UI.
   - Artifacts live in `~/Forge/dist/<target>/`; `dist/` is gitignored.
4. Frontend: a card per target — Build / Download / Delete, live log, size,
   total `dist/` size shown so it never balloons silently.
5. **Space discipline** (your constraint): builds are on-demand only, one
   artifact per target (rebuild overwrites), delete button always visible.
6. **Per-target feasibility, shown honestly in the panel:**

   | Target | Linux | Windows |
   |---|---|---|
   | Codec Player | ✅ built already, wire the recipe | ✅ Wine recipe exists |
   | Codec Lab | ✅ PyInstaller + pywebview | ✅ Wine recipe exists |
   | NovelForge | ✅ likely (reportlab/pypdf/requests/fastapi) | ⚠ only if the Wine prefix stays small — else deferred with a note |
   | MediaForge | ⚠ heavier (Pillow, Selenium, imagehash, Whisper) — assess | ✖ deferred (Selenium + browser + size) |
   | AI Studio | ✖ not offered — ~12 GB models + native Vulkan binaries | ✖ |
   | Whole Forge | ✖ not shipped — per-app only | ✖ |

**Deliverable:** a Downloads tab where you build each shippable app, download
it, upload it to GitHub yourself, then delete the local copy.

</details>

## Phase 6 — Efficiency pass

- `/simplify` on every file touched in Phases 1–5 (already part of "done").
- Targeted review, **reported before any change**, of the real hot paths:
  - `forge.py` concurrent startup (already concurrent — verify).
  - The SSE ~120 ms batching in each `web_app.py` (the documented perf fix —
    check it's consistent across all backends).
  - Codec strategies `optical_flow`, `frame_memory`, `temporal_skip` for the
    same "Python loop over tiny ops" shape that `palette_motion` was fixed for
    (9–14× win documented in the lab README).
  - The Phase 4 decode path.
- Optional, flagged for token cost first: a per-app `/code-review`.

## Phase 7 — Docs + verification

- Update `Forge/README.md` (new tabs, packager, the AI Studio port fix),
  `Forge/PROGRESS.json`, `Forge/CLAUDE.md`.
- Update `anime-codec-lab/README.md` + `BUILD_MANIFEST.json` (now
  Forge-integrated; symlinked, not moved).
- Per the definition of done: `black` on touched files, `pyright
  --pythonpath ./.venv/bin/python`, a **real run** of each changed app, and a
  **screenshot** of every new/changed Forge tab via `claude-in-chrome`.

---

## Not doing (unless you say otherwise)

- Windows builds of AI Studio or the Forge shell.
- Moving `~/anime-codec-lab` on disk (symlinked instead).
- Deleting any standalone launcher code.
- Setting up GitHub remotes (you do that; the delete button supports the
  workflow).
- Guardrail hooks (declined, standing).

## Rough sequencing

Phases 1–2 quick. Phase 3 + 4 together. Phase 5 reduced to one Wine build.
Phases 6–7 fold in and get a final pass.

---

## Progress log

### 2026-09-06 — session start (unattended)
- Plan approved with trimmed scope. Starting Phase 1.

### 2026-09-06 — Phases 1–4, 6, 7 + Windows player done (unattended)
All landed in one session. Full detail is in `PROGRESS.json` → `session_4_work`.

- **Phase 1 — AI Studio.** `forge_app.json` port `8420 → 8430` (was colliding
  with standalone). Upscale block artifacts: `config.UPSCALE_TILE = 200` now
  passed as `-t` to `realesrgan-ncnn-vulkan` in `engine.upscale()` (same
  Vulkan per-allocation ceiling as the sd-server bug). `-t 200` validated on a
  test image. **You still need to confirm a real high-res generation + upscale
  looks clean.**
- **Phase 2 — app search.** All 5 non-Forge `.desktop` entries →
  `NoDisplay=true`. Added an `application/x-acv` MIME type so `.acv`
  double-click still opens the Player. Originals backed up.
- **Phase 3 — Codec Lab.** `forge.py` gained a `root` manifest field +
  `FORGE_SHARED_DIR` env. `apps/codec-lab/` is a stub → `~/anime-codec-lab`
  (port 8431). `server.py` mounts `/shared`; frontend palette aligned to Forge.
- **Phase 4 — Codec Player.** New `~/anime-codec-lab/web_player.py` +
  `static/player.html` (port 8432). Decodes a `.acv` → browser-playable mp4.
  Verified end to end on the sample `.acv`.
- **Phase 5 — Windows player.** `release/windows/AnimeCodecPlayer.exe` rebuilt
  under Wine, smoke-tested. Real Windows still unverified.
- **Phase 6 — efficiency.** Codec strategies reviewed, left alone (already
  vectorised / too risky per "if it's too hard don't bother"). Real win: the
  new player encodes `yuv420p` crf20 not lossless `yuv444p` (~5× smaller, and
  444 wouldn't play in WebKitGTK anyway).
- **Phase 7 — docs.** `Forge/README.md`, `CLAUDE.md`, `PROGRESS.json`,
  `anime-codec-lab/README.md`, `BUILD_MANIFEST.json`, `CLAUDE.md` all updated.
- **Verified:** py_compile + black + pyright (per-venv) on every touched file,
  no new errors. mediaforge / codec-lab / codec-player boot-tested through
  `forge.py`'s own `Backend` class — start → ready → respond → clean stop.
- **NOT verified** (needs you): the GTK hub window itself, AI Studio
  generation/upscale, a real `.acv` in the player tab, real Windows.
- **Skipped as agreed:** git, the packaging panel (Phase 5 design kept,
  collapsed, above).

