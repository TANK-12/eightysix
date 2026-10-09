# MediaForge — manifest

_Written 2026-09-07 for a reader with no conversation history. The machine-
readable version of this is the `manifest` block in `forge_app.json`._

## What this is

MediaForge rolls up every ad-hoc media script the user had accumulated
(subtitle hardbaking, video enhancement, library sorting, dedupe, manga
scraping, image work, a Japanese tutor) into one local app with a shared
console, progress bar and Kill button. Nothing phones home except the metadata
and translation lookups you switch on yourself.

Like NovelForge it began as a customtkinter app and is now a FastAPI backend
(`web_app.py`) + `static/index.html`. `run.py` launches the legacy desktop app;
Forge / uvicorn launch the web app.

Runs on **port 8422** in Forge (`order` 2).

## Features (the nine modules)

| Module | What it does |
|---|---|
| **Subtitle Studio** | Batch video → MP4 with a burned-in sub track. Sources: an embedded track, an external `.srt`/`.ass`, **translate then burn** (Jan / Google / DeepL), or **Whisper transcribe then burn** so you can subtitle raws without typing a line. Track Inspector via ffprobe, synced across the batch. CPU **or** Intel-GPU (VAAPI / QSV) encoder — CPU by default. |
| **Video Enhancer** | Upscale resolution, motion-interpolate to 60 / 120 fps to de-stutter, tune I-frame / scene-change compression. |
| **Library Organiser** | Point at a messy folder → `anitopy` parses names → AniList / Jikan / TMDB give the canonical title + year → preview a shallow one-folder-per-series tree → **Apply** (move / copy / hardlink). Every run writes a **manifest** so you can **Revert** it later. Hash-check skips already-sorted files and exact dupes. On a name clash the source can be routed to `<library>/_DUPLICATES/<relative path>`. **Never deletes.** |
| **Anime Library** | Read-only health view of the centralised library: every series with year, season / episode counts and size; **missing-episode gaps**; episodes still holding both an `.mkv` and an `.mp4`; a name check. |
| **Duplicate Slayer** | PDF or image folder → perceptual-hash pages → auto-keep-first or manual thumbnail review → rebuild an optimised PDF / CBZ. For scraped manga. |
| **Storage Tools** | A SQLite file index that survives restarts; instant name / size / ext search, largest-first, a duplicate-file finder with one-click extra-copy delete, dead-entry cleanup. |
| **Manga Downloader** | comix.to: whole series listed with its scan groups and every chapter captured by PanelForge's headless-Chrome fetcher (`fetch_cli.py`), two chapters at a time, PDF / CBZ. Other sites: Selenium scrape, pattern-mode pagination, scroll / key navigation (needs a Chrome on PATH, unverified here). See WIP.md. |
| **AI Image Studio** | fal.ai text-to-image / img2img with your key, plus a fully-local Lanczos / bicubic upscaler + unsharp that needs only Pillow. |
| **Japanese Tutor** | Chat backed by your running Jan model, a click-to-type kana keyboard, formal / casual register and persona. |

Plus a **Settings** tab (encoder choice, API keys, paths, optional-dependency
status).

## Command-line tools

- `tools/anime_sorter.py` — consolidate a scattered collection into one
  shallow, canonically-named library. `.mkv` / `.mp4` only, never deletes or
  overwrites, manifest-backed revert, competing encodes / identical files go to
  `<library>/_DUPLICATES/`.
- `tools/anime_library.py` — print the health report.

See `tools/README.md`.

## Where data lives

`~/MediaForgeData/`:

```
settings.json
file_index.db           Storage Tools index
anime_title_cache.json  AniList lookups, cached
manifests/              every organise / sort run — backs Revert, never auto-deleted
```

## Dependencies

**Required:** customtkinter, darkdetect, pillow, pypdf, requests, imagehash,
anitopy, pymupdf, fastapi, uvicorn. **System:** ffmpeg + ffprobe (ffmpeg 9 with
`h264_qsv` / `h264_vaapi` is installed here, so the Intel-GPU toggle works).

**Optional:** `deep-translator` (Google / DeepL subtitle translation),
`faster-whisper` (transcribe raws), `selenium` + a Chromium browser (Manga
Downloader). A missing optional dep just shows an install hint in that tab.

## External services

- **Jan** at `localhost:1337` — subtitle translation and the Japanese tutor
  (no extra key or model download).
- **AniList / Jikan / TMDB** — Library Organiser canonical titles.
- **fal.ai** — AI Image Studio (user API key).
- **Google / DeepL** via `deep-translator` — optional translate backends.

## Running it standalone

```bash
cd /home/ejb/Forge/apps/mediaforge
.venv/bin/python -m uvicorn web_app:app --port 8422
```

Then open <http://127.0.0.1:8422>. (`run.py` launches the legacy desktop app.)

## API surface

38 routes under `/api/` in `web_app.py`: jobs + SSE, thumbnail, settings,
encoders, storage (count / scan / search / duplicates / clean-dead / clear),
anime-library (report / export / namecheck), subtitles (scan-folder / probe /
start), enhance, dedupe (scan / result / thumbnail / finish), organizer
(preview / apply / history / revert), jptutor (status / send), imagestudio
(models / generate / upscale), manga (fetch / download).

## Known gaps (verified vs reasoned)

- **Duplicate Slayer** review thumbnails aren't retained, so they can be
  garbage-collected blank; `_compile` can `IndexError` if every image in a
  group fails to load. Manga-only path, low priority.
- **Anime Library**'s docstring mentions a "Fix names" button that isn't wired
  — only "Name check" exists.
- **Library Organiser** `_edit_row` maps a text click to a row via
  `(line-1)//2`, correct only while every row is exactly two lines (it is
  today).
- The user's **external-drive anime sort is paused**: the NTFS drive
  `14DE4324DE42FD8C` could not be mounted unattended (`ntfsfix` / `ntfs-3g`
  fail, no passwordless sudo). A prior run already sorted 2211 files (391
  parked in `_DUPLICATES/`). Finish it by mounting the drive and running
  `finish_anime_sort.sh` (dry run, then `apply`).

## Other docs

`README.md` (user-facing overview), `WIP.md` (session change log + known
issues), `tools/README.md` (the CLI tools).
