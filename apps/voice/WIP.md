# Voice: work in progress

date: 2026-10-08 · for: both · built by helper-3 (Yuzu) in crew `voice`, Relay task 113

## Verified (2026-10-08)

- `pytest -q tests`: 77 passed (state machine incl. cancel from every state and
  presses ignored while busy; guard on 11 routes for header and host; CORS for
  5 origins; settings merge, resolve order and 11 rejected patches; app
  discovery from manifests; /api/tts and /api/stt with a fake engine incl. 400
  and 503 cases; unload and idle reaping keeping STT; routing with fake
  Acchan/Claude HTTP servers; end-to-end tap through `FORGE_VOICE_CAPTURE`
  stopped by the silence gate; cancel discards; "say that again" repeats; a tap while a reply is being made stops it from playing, red on the code without that guard).
- Real round trip on a scratch port (18467) with the shared registry: Kokoro
  said "The quick brown fox jumps over the lazy dog. Forge voice is working."
  (4.29 s of audio; 9.2 s first call incl. load, 5.8 s warm) and whisper.cpp
  tiny.en heard back exactly that sentence (9.5 s first call, 2.8 s warm).
- A tap round on the scratch server with `FORGE_VOICE_CAPTURE` and
  `target=text` went listening -> idle in about 4 s with the right text in
  history.
- The real mic path (`pw-record --raw` to a pipe) returned 0.9 s of audio for a
  1 s capture.
- black and pyright clean (0 errors) on every Python file here.

- 21:50, session 6: end to end against the live Acchan: a test instance on
  port 18467 with `FORGE_VOICE_CAPTURE` = Kokoro saying "What time is it?" and
  `FORGE_VOICE_PLAYER=/bin/true`; one `POST /api/ptt/tap` gave history
  `heard "What time is it?"`, target jan, handled_by phrase, reply "It is
  21:50 on Thursday 08 October 2026.", 2907 ms from the tap (recording and the
  1.2 s silence gate included).
- 21:49, session 6: headless Chrome screenshot of the live page on 8467: state,
  both models present and loaded, per-app rows (anywhere, Acchan, Claude),
  readable on the dark theme. "Hear the best voice" now says "Best voice not
  installed" and is disabled while `defaults.tts_best` is null (it used to
  play the fast voice).
- Session 7 (22:06 to 23:55): a press while transcribing or thinking cancels
  the round; a cancelled round's late events cannot move the next one; the CLI
  resends `up` once after 0.3 s on idle (98410bd; the new tests fail on the old
  code). `short_ctx` on the default whisper row: same WER on 10 clips, a 1 s
  command 0.8 s instead of 1.9 s, loop guard re-reads in full (9fde2c1; real
  whisper-cli run checked). 85 pytest here, 18 in tests/test_forge_voice.py.

- Session 8 (22:31, Tsubaki): routing contract (`route()` gives
  (target, text, named), `answer()`): un-named speech goes to Acchan's commands
  with no model first, then Claude ('auto' means Claude), and Jan answers when
  the Claude app is down; a wake name or hotkey target is never redirected. A
  press while a `/api/say` line plays and no round runs only hushes it. The
  Player takes a lock so a hush cannot leave `busy` stuck (a queued line drained
  before it started) or miss a line that is starting. 97 pytest pass; the 18
  new ones fail on the old code (checked on a copy in /tmp). The 'cloud' alias
  was already in the registry wake list.

- Session 9 (22:50, Izumi): Mission Control mic and speak buttons beside
  `#fxAttach` (ab4b723, tests/test_voice_browser.py in apps/mission passes,
  screenshot looked at); tests/cdp_driver.py runs Chrome with
  `--no-documents-portal` (80622ac).
- Session 10 (23:11, Kohaku): Breeze TTS 2 wired in (d0f4ece): engine
  `engines/breeze_cpp.py`, row `breeze-tts-2`, `defaults.tts_best`, heavy
  guard and fallback, a voice belongs to its model, per-row idle time, the
  speech routes in the threadpool. 116 pytest with a fake breeze-server. Real
  runs: Vulkan RTF 5.0 and 4.4, CPU 9.0, whisper heard both lines exactly;
  headless Chrome on a scratch backend: "Hear the best voice" made 2.72 s of
  speech in 24.2 s; no server left after.
- Session 12 (2026-10-09 01:30, Nagi): the critic's findings on 98410bd to
  d0f4ece fixed in 77faebd, each with a test that fails on the old code:
  F1 a load error with several log lines broke the `X-Voice-Fell-Back` header
  and dropped the connection (now `header_text`, one ASCII line, 200 chars);
  F2 un-named speech ran on Claude and Jan both when Claude's reply poll
  failed (Jan only when Claude never got it); F3 a spoken screenshot could
  overwrite any file (Acchan refuses an existing path except the tool's
  default, the model's picks included); F4 a scratch backend killed the live
  backend's breeze-server (one pid file per backend, a live owner's server is
  left); F5 the idle reaper unloaded Breeze right after a long synth
  (re-checked under the model lock); F6 an orphaned server could keep Breeze
  out for good (`clear_stale` before the memory check). F7 (a press while
  thinking drops the reply, not the action) is documented, not changed. 125
  pytest here, whole Acchan suite 321, tests/test_forge_voice.py 18; the
  critic's proof scripts re-run and now pass (the header one against a real
  uvicorn).
- Session 13 (2026-10-09 01:45): a second critic on 77faebd found no high or
  medium bug and three low ones, all fixed with tests: G1 Blender's
  screenshot may save "notes" as notes.png, so from voice that file counts as
  taken too (Acchan `WRITE_TOOLS` maps each tool to the extension it may
  add); G2 a request dropped after it was sent now says "Claude may not have
  got that; check the Voice chat before you say it again" (it pointed at a
  Voice chat that could be empty; Jan still never runs it too); G3 a folder
  is called a folder in the refusal. Acchan 322, voice 125,
  tests/test_forge_voice.py 18 pass; acchan.service restarted, live: 403
  without X-Forge, "what time is it" answered by phrase in 9 ms. The check
  samples and screenshots are kept in `outputs/voice-checks/2026-10-08/`
  (README.txt there, not in git); the task's /tmp scratch is removed.

## Not verified

- Routing to the real Claude app (8445): it still runs its old code (no
  `/api/voice/ask` until it is restarted); only the fake Claude server in the
  tests was used.
- The page's "hear" buttons inside the Forge window. The mic is verified
  since 2026-10-09 (49e7405), but only in a headless WebKitGTK 2.54 window
  with a loopback test mic, not with Emerson's own mic in the real window (see
  the cloning section below).
- Earcons and the desktop notification were not heard or seen (off in tests).
- Hold-to-talk with a real key release (Hyprland) and the GNOME tap hotkey.
- The running backend: Forge started it at 21:34 on 2026-10-08 and it was
  not restarted (Forge stops and starts one app only from its window). All
  the later service code (dd22830, 98410bd, 9fde2c1, 38e2b97, d0f4ece,
  77faebd) loads on its next start: close and reopen Voice in Forge, or
  restart Forge. The registry is read live, so until then the old code sees
  the Breeze row without the memory and Jan check.
- Breeze with a real speaker, and its fallback under a real memory squeeze
  (only faked in tests).
- No `PR_SET_PDEATHSIG` on breeze-server (it would need `preexec_fn`, which
  is not thread-safe): a server outlives a backend killed with SIGKILL until
  the next load or memory check stops it.

## Left to do

- `GET /api/events` (NDJSON stream), model download and delete routes.
- Kokoro is slow-ish on this CPU (about 1.35 s per second of audio warm with
  4 threads while other sessions were busy); worth measuring with the CPU quiet.
- Critic items still open: speech the Claude app or another page plays in the
  browser itself is not known here, so a hotkey press during it opens the mic
  (lines sent through `/api/say` are covered); a cancelled round does not tell
  the Claude app or Acchan, so a command already sent still runs and Claude's
  answer still lands in its Voice conversation (documented in the README).

## Cloning, mood tags and character voices (2026-10-09, Relay task 120)

`git log --grep="Relay task 120"` lists the commits: 49e7405 (mic), c1ee8fe,
ff2ed80, cd95a71, then the critic fixes. The pick and the measurements are in
`docs/library/voice/2026-10-09-voice-cloning-bakeoff.md`; the two critics'
findings and what became of each are in
`docs/library/voice/2026-10-09-cloning-critic-findings.md`.

**First step for Emerson: restart Forge once (Ctrl+Shift+R).** The voice
backend (pid 22968, started 2026-10-08 21:34) and Forge itself (pid 2910) run
older code, so until then the cloned voices, tag handling and pop-out mic fix
are not live. Relay keeps running; it is its own service.

Verified:

- **Speech to text from a page.** In Forge's WebKitGTK 2.54, MediaRecorder
  records 0 bytes from a real mic: the track reports sample rate 0. That is
  why `/api/stt` answered 400 "no audio". `shared/forge_mic.js` captures with
  Web Audio and sends a 16 kHz WAV instead; it is used by Acchan, the Voice
  page and `forge_voice.js` micButton, and pop-out windows now allow the mic.
  `tests/browser/check_mic_webkit.py` passes 8/8 (hub and pop-out, a loopback
  mic playing "What time is it?" is heard exactly; rerun 2026-10-09 03:41
  after the local-page rule below). `tests/test_forge_mic.py` passes 6,
  `tests/test_forge_voice.py` 20, and the node tests for forge_mic and
  forge_voice pass 12 and 11. Pop-outs allow the mic only on a Forge page
  (a file or a server on this laptop), never for the camera or the screen.
- **The cloning rows.** `auk-flash`, `irodori-anime` and `breeze-tts-2` with
  profile voices. On a scratch backend (port 8497) `/api/tts` returned 200 on
  the asked model and voice for every mood tried, SenseVoice heard the right
  words, and no tag was read aloud. Kokoro got its tags taken out.
- **Eighty Six.** `cast.py` rendered 8 real game lines to
  `outputs/voice-cast/eightysix/en/` with Breeze in 7-13 s each. Lena came out
  at 194-206 Hz and Shin at 103-140 Hz, with a voice match of 0.74-0.86 to
  their stand-ins and the right words. Clips made with an older voice clip
  were remade without `--redo`. Japanese through `/api/tts`: 86-shin-ja
  `[angry]` and 86-lena-ja `[worried]` both returned 200 with the right words.
- **Critic fixes (sessions 10-12).** A tag-only line no longer unloads a
  heavy model; a missing profiles folder no longer stops Breeze loading; a
  wrong or unknown voice no longer speaks silently as another one (the header
  names the voice used, Breeze re-saves a lost copy, cast.py checks it); round
  brackets keep ordinary words; a broken tag list keeps the last good one; the
  fall-back respects the language; cast.py remakes a line when the calm clip
  changes, skips "..." lines and never maps two ids to one file; a new calm
  clip moves old mood clips aside; mic error paths close the mic. Each has a
  test that failed on cd95a71 and passes now (`tests/test_cloning_edges.py`
  and the engine, cast, profiles and mic tests).
- **Second critic (session 12).** Ten more fixed, three of them side
  effects of the first fixes: a markdown link whose words are a tag stays a
  link; a cloning row with no voice falls back before loading; a tag line
  keeps the heading or list marker under it; a wrong-shaped tag file no
  longer gives 500; the mic closes within 2 s on failure; pop-outs check
  screen requests with WebKit's own function; only a profile's own clips
  move; `say` prints who spoke and `clip` saves nothing from another voice
  unless `--any-voice`; a loaded Japanese voice speaks while Jan is busy;
  full-width （…） takes every tag. List:
  `docs/library/voice/2026-10-09-cloning-critic-findings.md`.
- **Tests and checks.** The voice suite passes 203, `tests/test_forge_mic.py`
  7, `tests/test_forge_voice.py` 21, node forge_mic 13 and forge_voice 11;
  black is clean, pyright shows 0 errors (GTK import false alarms aside).

Not verified:

- **Whether the moods sound like the mood.** SenseVoice's emotion tag
  mostly said NEUTRAL or UNKNOWN. Ears decide: the samples are in
  `docs/library/voice/samples/`.
- **The live backend.** It is pid 22968, started 2026-10-08 21:34, and still
  runs the old service code, so the profile voices and tag handling load only
  on its next start (restart Forge with Ctrl+Shift+R; reopening only Voice is
  enough for the voices but not for the pop-out mic). It was not restarted
  from here.
- **The real mic.** Speech to text with Emerson's own mic inside the real
  Forge window has not been tried.

Left to do:

- **Real character voices.** Eighty Six needs Emerson's season 1 episodes,
  then this pipeline: extract the audio only, separate the voice
  (bs_roformer), diarize (sortformer), match speakers to characters with
  the subtitles, cut clean clips per emotion, then `profiles.py add --private`.
  Wanted: the English dub and the Japanese audio, no other languages.
- **Eighty Six, how far it is.** 8 of Lena's and Shin's 124 spoken English
  lines are made; the other 116 take roughly 15-25 minutes
  (`cast.py render eightysix --lang en`). 305 lines from Raiden, Theo, Kaie,
  Daiya, Anju, Kujo, Kurena, Lev, the old Handler and small parts have no
  voice yet. The game plays none of these clips; Riku's crew (ejb-6a) decides
  that. Lena's English stand-in is Kokoro's Bella cloned by Breeze, the same
  "Bella (Kokoro)" Acchan offers, so it will not sound like the anime.
- **Japanese game lines.** The game's dialogue has no `text_ja` yet.
  `cast.py render --lang ja` says so and makes nothing.
- **AuK's design mode.** It makes breathy clips with a garbled first second,
  so the English stand-ins are Kokoro presets instead.
- **Not done from the critics.** The `private` flag is a label only (no tool
  refuses to share such clips; no private voice exists yet). No prompt tells
  Jan, Claude or Relay about mood tags, and Acchan cannot pick a voice per
  line (only the Voice page's per-app setting). Ideas worth doing next: a
  "try a voice" box with a mood list on the Voice page; voices for the rest
  of the squad from spare Kokoro presets; a radio filter per game channel.
- **Disk.** Task 120 added about 9.2 GB (AuK 6.1, audio.cpp source and build
  1.8, Irodori 1.1, SenseVoice 0.24). The unused prebuilt audio.cpp (210 MB,
  it crashes on this CPU) and OmniVoice (1.3 GB, ruled out) went to the trash
  on 2026-10-09; emptying the trash frees the space. Swap was 5 of 8 GB in
  use on 2026-10-09 03:40; AuK needs 7.5 GB at peak, so expect the fast voice
  to stand in while Jan holds a big model.
