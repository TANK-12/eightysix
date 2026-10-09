# MediaForge

One local app that rolls up every media utility from the `download/` scripts —
rebuilt properly, combined under one dark GUI with a shared console, progress bar
and Kill button. Nothing phones home except optional metadata / translation
lookups you turn on yourself.

```bash
cd ~/MediaForge && bash install.sh      # venv + deps + desktop entry
# then search "MediaForge" in your app menu, or:
.venv/bin/python run.py
```

## Modules

| | Module | What it does | From your scripts |
|---|---|---|---|
| 📝 | **Subtitle Studio** | Batch video → MP4. Burn an **embedded** sub track, or an **external .srt/.ass**, or **translate → burn** (your local Jan model / Google / DeepL), or **transcribe with Whisper → burn** so you can subtitle raws without typing a line. Track Inspector (ffprobe, synced across the batch). CPU **or** Intel-GPU (VAAPI/QSV) encoder — CPU default. Live progress + Kill. | `new5`, `hardbake`, `subtitle_hardbake*`, `jap` |
| ✨ | **Video Enhancer** | Upscale resolution, motion-interpolate to 60/120 fps (de-stutter), I-frame / scene-change compression tuning. | `vid`, `vid2`, `vid3` |
| 🗂️ | **Library Organiser** | Point at a messy anime/TV folder → `anitopy` parses names → **AniList / Jikan / TMDB** gives canonical title + year → preview a shallow one-folder-per-series tree → **Apply** (move/copy/hardlink) → every run writes a **manifest** so you can **Revert** it later. Hash-check skips already-sorted files and exact dupes. Never deletes. | the "sort my animes" idea + `new14/15` search |
| 📺 | **Anime Library** | Health view of the centralised library: every series with year, season/episode counts and size; **missing-episode gaps**; episodes still holding both an `.mkv` and an `.mp4`; a name check. Read-only. | companion to the sorter |
| 🧹 | **Duplicate Slayer** | PDF or image folder → perceptual-hash pages → auto-keep-first or manual thumbnail review → rebuild an optimised PDF/CBZ. Great for scraped manga. | `dupe`, `dupe1`, `dupe2` |
| 💾 | **Storage Tools** | SQLite file index (survives restarts), instant name/size/ext search, largest-first, duplicate-file finder with one-click extra-copy delete, dead-entry cleanup. | `new11`, `new14`, `new15`, `multi_tool_explorer` |
| 📚 | **Manga Downloader** | Selenium scrape (comix.to / manhuaus / generic), pattern-mode pagination, parallel chapters, PDF/CBZ. **Fixed the missing-pages bug**: incremental scroll with real patience + height-growth check + retried image fetches instead of one big scroll. | `manga*`, `chill*`, `final*` |
| 🎨 | **AI Image Studio** | fal.ai text-to-image / img2img (your key), plus a fully-local Lanczos/bicubic upscaler + unsharp that needs only Pillow. | `ai_image_studio*`, `local_image_studio*` |
| 🇯🇵 | **Japanese Tutor** | Chat backed by your running **Jan** model, click-to-type kana keyboard, formal/casual + persona. | `jap`, `jap1`, `jap2` |

## Where things live

```
~/MediaForgeData/
  settings.json
  file_index.db          Storage Tools index
  anime_title_cache.json AniList lookups, cached
  manifests/             every organise / anime-sort run — used for Revert, never auto-deleted
```

## Command-line tools

`tools/anime_sorter.py` consolidates a scattered anime collection into one
shallow, canonically-named library (never deletes, manifest-backed revert,
parks duplicates in `_DUPLICATES/`). `tools/anime_library.py` prints a health
report. See `tools/README.md`.

## Notes for this machine

- **ffmpeg 9** with `h264_qsv` / `h264_vaapi` is installed, so the GPU toggle
  actually works here via VAAPI/QSV (Intel iGPU). It's still **CPU by default** —
  flip it per job once you've confirmed a file encodes cleanly.
- Optional deps (`selenium`, `faster-whisper`, `deep-translator`, a Chromium
  browser) light up the Manga / Whisper / Google-translate paths. Missing ones
  just show an install hint in that tab.
- Translation and the Japanese tutor reuse your **Jan** server (localhost:1337) —
  no extra key, no extra model download.
