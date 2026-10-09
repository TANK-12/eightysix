# Media

One place in Forge for playing and getting media.

- **Library**: the mp3, mp4 and other audio/video files in your folders
  (Settings tab; default `~/Music`, `~/Videos`, `~/Downloads/MediaForge/Music`,
  plus the download folder). Click to play; prev/next, shuffle, repeat, a
  volume slider with its number, seek bar. Keys: Space play/pause, ←/→ seek
  10 s, Shift+←/→ previous/next, ↑/↓ volume, `/` search, F full screen.
- **YouTube**: youtube.com as a real page inside the Forge window (a native
  WebKit view, the same mechanism the Browser app uses). Ordinary videos
  play; the Download button hands the open video to the Download tab.
- **Crunchyroll**: crunchyroll.com the same way, for browsing. Episodes need
  Widevine DRM, which WebKitGTK does not have, so **Watch in Firefox** opens
  the same page in Firefox, where the login already is.
- **Download**: paste a channel, playlist or video link, or type a name
  (`Tokyo Echo Sounds`). The list comes from `yt-dlp`; tick what you want,
  save as mp3 (cover and tags embedded) or mp4 into the download folder. The
  library picks the files up when it finishes. Files that already exist are
  skipped, so re-running a channel only fetches what is new.

## Layout

```
apps/media/
  forge_app.json   the manifest (port 8450, fullscreen auto)
  web_app.py       FastAPI: settings, library scan, /api/file, yt-dlp jobs (SSE log)
  media_lib.py     the testable parts: settings, scan, the file guard, yt-dlp
                   command lines and output parsing
  static/          index.html, app.js, app.css (uses /shared/forge.css and
                   forge.js; forge_chrome.js for full screen)
  tests/           pytest, no network, yt-dlp never run
```

Data: `~/.local/share/forge/media/settings.json`. Downloads default to
`~/Music/Forge`.

Run standalone:

```
cd ~/Forge/apps/media
FORGE_SHARED_DIR=~/Forge/shared .venv/bin/python -m uvicorn web_app:app --host 127.0.0.1 --port 8450
```

Standalone there is no page area for YouTube or Crunchyroll (those are hub
views); the library and downloads work anywhere.

## Tools it needs

`yt-dlp` (system package, `/usr/bin/yt-dlp`) and `ffmpeg` for mp3. Firefox is
optional, for Crunchyroll playback. The Settings tab says which are found.
