# MediaForge tools

Standalone command-line companions to the GUI. Run them with the bundled venv:

```bash
cd ~/MediaForge
.venv/bin/python tools/<script>.py ...
```

## anime_sorter.py

Folds a messy, scattered anime collection into one shallow, canonically-named
library.

- `.mkv` / `.mp4` only — nothing else is touched
- **never deletes, never overwrites**; every move is written to a manifest under
  `~/MediaForgeData/manifests/` and is fully revertible
- filename-first parsing, then folder-name aware (a hand-maintained alias +
  canonical-title table covers this collection's shorthand folders), then a
  strict AniList lookup; anything still unresolved is left exactly where it is
  and listed under **NEEDS REVIEW**
- whole-collection de-duplication by quick content hash: any file that collides
  with something already placed — identical content, or a competing encode of
  the same episode/container — is moved to `<library>/_DUPLICATES/<original
  path>` for you to clear by hand
- an `.mkv` and an `.mp4` of the same episode both land in the series folder
  (`Title - S01E05.mkv` + `Title - S01E05.mp4`) — linked but separate
- layout: `<library>/<Title (Year)>/<Title> - S01E05.mkv` (one folder per
  series, files directly inside; movies drop the episode part)

```bash
# dry run — writes a full plan, moves nothing
.venv/bin/python tools/anime_sorter.py \
  --scan DIR [DIR ...] --library ~/Anime

# execute
.venv/bin/python tools/anime_sorter.py \
  --scan DIR [DIR ...] --library ~/Anime --apply

# undo a previous --apply
.venv/bin/python tools/anime_sorter.py --revert ~/MediaForgeData/manifests/XXXX_anime-sort.json
```

`--offline` skips AniList entirely and uses only the built-in title table
(fast, deterministic, no network).

## anime_library.py

Health report for the library the sorter produced: every series with its year,
season/episode counts and size; missing-episode gaps; episodes that still hold
both an `.mkv` and an `.mp4`; files with no `SxxExx`.

```bash
.venv/bin/python tools/anime_library.py [LIBRARY_ROOT]
```

With no argument it reads `library_root` from `~/MediaForgeData/settings.json`.
The same view is in the GUI as the **Anime Library** module.
