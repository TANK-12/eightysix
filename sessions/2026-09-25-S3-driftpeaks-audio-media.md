# S3: Drift Peaks, audio everywhere, Media downloader

Part of the 2026-09-25 wave; read `~/Forge/sessions/README.md` first.
Suggested model: Opus, medium effort.

## Owns
- `apps/driftpeaks/`, `apps/media/`
- The hub's visualiser and background-music code (claim the hub files for
  each edit; S2 owns the rest of `hub/`; agree on the board)
- A new backend audio source for the visualiser (a small endpoint or
  helper; put it where the hub's other backend lives)

## Ledger

- **A8** "the youtube downloader in the media thing is not working" ->
  reproduce with one short public video, find the cause (often an outdated
  `yt-dlp` in the app's venv, or a changed option), fix, test with a mocked
  downloader plus one real tiny download. Do this first: A7 and A21 reuse it.
  [core]
- **A5** "framerate doesn't show up in zen mode for the slopes game, I want
  it to show up" -> Drift Peaks' zen mode hides the FPS counter; show it
  there too (keep the rest of zen's clean look). [core]
- **A6** "there are box rocks or models or coins or whatever, so keep
  working on the game" -> rocks, props and coins look boxy. Give them proper
  low-poly shapes in the Alto style (faceted rocks, round coins that spin
  and glint, trees, cabins, flags), via the shared `shapes` content type so
  Emerson can edit them. Then keep improving the game down its "Improve next
  (ranked)" list in `apps/driftpeaks/WIP.md`. [core]
- **A7** "I want suitable music; I wouldn't mind you getting the youtube for
  the Alto game music" -> in-game music: let Drift Peaks play a playlist,
  and fetch the Alto's Adventure / Alto's Odyssey soundtrack audio from
  YouTube with the fixed downloader into Forge's shared music place (for
  Emerson's own local use). Post the chosen video links on the board before
  downloading and state the disk size. [core]
- **A9** "I want the visualiser for forge to work with any audio from
  system or qbz or forge or whatever" + "make sure the visualiser works for
  all music" -> the hub visualiser should react to whatever is playing on
  the laptop, not only audio inside a Forge page. Reasoned approach (not
  checked): capture the PipeWire/PulseAudio monitor of the default output
  (`pw-record` / `parec` on `<sink>.monitor`) in a backend, compute a few
  band levels, stream them to the hub (server-sent events or WebSocket);
  fall back to in-page Web Audio. Low CPU; stop capturing when the
  visualiser is off. Check with QBZ, a browser tab and a Forge app playing.
  [core]
- **A21** "fix the music folder for background music; maybe just access a
  set youtube video and skip the ads, or download the audio of the video"
  -> the hub's background music from a folder is broken; fix it, and add
  "play from a YouTube link": download the audio once with the fixed
  downloader (no ads that way) and play it from the folder. [core]

- **A20** (2026-09-26, via S7) "also want the alto game to be better, just
  copy alto or find its assets online and make music or get alto's music" ->
  (a) this is Emerson's go-ahead for A7: fetch the two soundtrack links posted
  on the board (note 30) with the Media downloader into ~/Music/Alto and play
  them in Drift Peaks; (b) make Drift Peaks look and feel much closer to Alto's
  Adventure/Odyssey: silhouetted layered parallax hills, soft gradient skies
  through the day, dusk and night, weather, the snowboarder's trick flow,
  llamas/props, rope grinds, chasms, the menu and zen feel. Recreate the look
  with original art in that style (S7's reading: no ripped game sprites; the
  style itself is fair game); keep everything editable through the shared
  `shapes` type (A6). [core]

## Order
A8 -> A5 -> A21 -> A7 -> A9 -> A6 and further game polish.

## Checks
pytest for media and driftpeaks (write tests for the downloader wrapper,
playlist and settings); black and pyright; headless screenshots of the game
(zen mode with FPS visible) and of Media. Frame rate, sound and the
visualiser with real system audio cannot be judged headless: write down how
Emerson checks each, in one line.

## State
- **A8 done + checked** (2026-09-25). yt-dlp and backend were fine; Media's
  page was broken (called a helper that does not exist, crashed when opened
  at `#download`, had no toast box). Details in `apps/media/WIP.md`.
  Checks: 14 pytest pass; `apps/media/tests/browser/run_download_flow.sh`
  all PASS with a fake yt-dlp and with `--real` (19 s video saved as mp3).
- **A5 done, checked headless** (2026-09-25). The counter was never hidden
  in Zen: it was near-white 12px text at 70% opacity over white snow.
  Now a dark pill under the distance (top-left), shows "… fps" until the
  first reading, measures real frame time (it used the step capped at
  1/30 s, so anything under 30 fps read as 30), and "Show frame rate" is in
  simple Settings. Checked: headless Zen screenshot with Emerson's save
  shows the pill; 14 pytest + 11 Node pass. Emerson checks the number:
  Forge > Drift Peaks > Zen > Ride, top-left reads like "58 fps · 3 ms".
- **A21 done, checked headless; A9 done, checked in parts** (2026-09-25):
  - Cause of "music folder broken": `~/Music/Forge` did not exist, and the
    only music Emerson has is a lo-fi playlist **video** in `~/Music`
    (.mp4, a type the hub refused), so the hub got an empty track list.
  - Fixed: music folder takes .mp4/.webm/.aac too; default folder and
    Emerson's saved setting are now `~/Music` (one level down counts, so
    Media's `~/Music/Forge` downloads play); the note button's tooltip and
    panel say why there is nothing. Backup of his settings:
    `backups/2026-09-25-S3-media/settings.json.bak`.
  - New: the note button opens a panel: play/pause, skip, and "paste a
    YouTube link": forge.py saves that video's audio into the music folder
    (shared/forge_music.py + shared/forge_ytdlp.py, the same downloader as
    Media) and plays it. API for S2's zen mode: `Music.play()`,
    `Music.pause()`, `Music.playing`.
  - A9: new setting "Visualiser listens to" (default: anything playing on
    the laptop). forge.py runs cava on the default output's monitor only
    while the home-screen visualiser draws, pushes 32 bar levels to the
    hub, and cava stops by itself if the page stops asking (5 s keep-alive,
    15 s timeout). Wave style is rebuilt from the levels. Falls back to the
    in-page music without cava or outside Forge.
  - Checked: tests/test_forge_music.py 11 pass; Settings 33 pass; Media 14
    pass; tests/browser/run.sh ALL PASS (134, new hub_music block with 28
    checks: levels asked for / stopped in apps, pushed levels draw, panel,
    add flow, API, cava fallback); screenshot of the panel looked at; real
    cava via forge_music on this laptop: 63 frames in 3 s, 61 with sound,
    stopped cleanly; GStreamer decodes the lo-fi mp4's AAC audio; pyright 0
    new errors; forge.py test scripts pass.
  - Not checked (needs a Forge restart, Emerson's call): inside the real
    window. Emerson: restart Forge, play something in QBZ or a browser tab,
    look at the home screen (the wave should move); click the note button,
    paste a YouTube link, press Add (it should play within a minute).
- **A7 started**: soundtrack links + size posted on the board for Emerson
  (Alto's Adventure OST https://youtu.be/vVZUZgwXJxQ 62 min, Alto's Odyssey
  OST https://youtu.be/XTAHy7L5wAw 65 min, ~220 MB mp3, into ~/Music/Alto).
  Not downloaded. Next: check the board for a "no"; if none, fetch with
  `shared/forge_ytdlp.download_command([...], Path('~/Music/Alto'), 'audio')`
  (or Media's Download tab), then give Drift Peaks a playlist: a setting
  "Music folder" (default `~/Music/Alto`), a backend route listing and
  serving the files (guard like Media's `/api/file`), shuffle, volume
  slider + number field, fade on pause, tests for the list/serve route.
- **A6 not started**: rocks/coins/props through the shared `shapes` type,
  then `apps/driftpeaks/WIP.md` "Improve next".

## Next session (S3 continued)
Usage was 76% at the checkpoint (one task per 15 min rule). Start with:
`Read ~/Forge/sessions/README.md, then continue ~/Forge/sessions/2026-09-25-S3-driftpeaks-audio-media.md from its State`.
Order: A7 download + Drift Peaks playlist (A20a) -> A6 shapes -> A20b Alto look and feel -> game polish.
