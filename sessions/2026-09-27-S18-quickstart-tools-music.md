# S18: QUICKSTART share, music speed, sliders, desktop particles (session "ejb-55", Tetsu)

Emerson (2026-09-27): "read the quick start and all the other stuff that
needs to get done ... mostly focus on the quickstart and unfinished work",
then "coordinate with the other guy". Split agreed with ejb-94 (board name
ejb-a1, brief `2026-09-27-S17-board-fps-aistudio-acchan.md`): it has B32
Board, B39 FPS slider (`max_fps`, forge_framecap.js), ai-studio resizing,
Acchan terminals/docs. Mine below. "godot stuff in another session".

## Ledger
1. A7 Settings sub-pages (QUICKSTART Hub (S7) Left 1).
2. B27 a distinct persona name per session: waiting on Emerson's pick of
   name style.
3. Tools "Improve next" (apps/terminal, files, code): waiting on his answers
   (xterm search add-on OK?, which items, Code's Restricted Mode banner).
4. Godot leftovers: moved to its own session (Emerson).
5. New: "make the auto pause for music background and also the normal pause
   for the background music way faster, it takes too long".
6. New: "make basically everything have a slider like fps and level of power
   used for particles and stuff in settings, but don't change or remove
   anything or function I have now". fps is ejb-94's `max_fps`.
7. New: "the extension for the particles in desktop should also have
   settings and only on when visible".

## Files
hub/index.html (Music.sync), forge_views.py (MEDIA_AGENT, _media_changed),
shared/forge_theme.py (music_fade), tests/test_views.py,
tests/test_hub_media.py, tests/browser/hub_music_fix_harness.js,
tests/browser/forge_media_parent.html. Backups: backups/2026-09-27-S18/.

## State
- A7 already done by earlier sessions (one page per group on the left,
  search, B36 layouts): checked, apps/settings tests 34 pass, run.sh
  settings_sections all PASS. Nothing to build.
- Side fix: forge_media_parent's "with its length" check was flaky on a busy
  machine (1 fail in 3); it now waits for the length. run.sh 454 PASS (30eaf49).
- 5 music speed done + checked (ea5b75d): fade timed by the clock, setting
  Music > Music fade (0-2000 ms, default 150; was a fixed ~1.5 s); Browser
  app pages report play/pause at once instead of the hub's 3 s question.
  test_views 7 pass (new push test, direct and cross-origin frame),
  test_hub_media 5, run.sh 456 PASS. **Needs a Forge restart to be felt.**
- 7 desktop particles done + checked (8b8f1e5, settings entries in
  1344f6a): Settings > Desktop particles (kind or "same", amount, frame rate
  1-60 default 30 under Speed's max_fps, "Only while the desktop shows"
  default on); GNOME extension prefs.js (gear in Extensions) opens Forge
  Settings. test_desktop_particles 6 pass, run.sh desktop_particles 7 PASS,
  run.sh 462 PASS overall, prefs page built in gjs/Adw, screenshots
  /tmp/s18shot/*.png. Not checked live: needs the log out/in from B38.
- Tools "Improve next" handed to ejb-94 (rebalance, Emerson: "equal work").
- 6 sliders done + checked (git log "More sliders"): Home screen > Particle
  size, Particle speed, Particle frame rate (5-60, draws are skipped between),
  Tint strength; Background mode > Drift length; plus Music fade and the
  Desktop particles sliders from earlier. Defaults keep today's look; nothing
  removed. test_hub_sliders 2, run.sh 469 PASS, screenshot
  /tmp/s18shot/home-sliders.png. Next slider ideas: visualiser sensitivity,
  glass blur, shadow strength.
- 8 Acchan voice done + checked (see git log "Acchan voice"): acchan/voice.py
  (Kokoro via nyarch/forge_tts.py, Piper fallback, whisper.cpp tiny.en from
  ~/.var/app/moe.nyarchlinux.assistant/.../whisper.cpp + ffmpeg; nothing
  downloaded), /api/voice/status|speak|listen, 🎤/🔈 beside Send, Voice
  picker in Settings. forge.py: microphone allowed, camera never
  (media_request_ok), hub frames allow="fullscreen; microphone". acchan 166
  pass (real round trip), test_forge_mic 2, run.sh 463 PASS, screenshot
  /tmp/s18shot/acchan.png. **Not checked live:** speaking into a real mic
  inside Forge (needs a Forge restart for the permission) and hearing a
  reply; the live acchan.service needs a restart to load the new routes.
- 9 B20 widgets + Relax done + checked (git log "B20 home widgets"). Emerson
  left the choices to Claude ("just do what is cool, like MD3, or like 5 made
  by you"); picked: Material 3 tonal cards (glass as an option), 5 widgets
  (Clock, Now playing for every player on the laptop, System rings, Notes,
  Relax), pages with dots/swipe, Edit mode with drag/resize/add/remove on a
  12-column snapping grid, localStorage layout, Relax = full-screen box
  breathing (Esc leaves), Settings > Widgets (on, look, size, breathing
  pace). hub_widgets harness 29 PASS, run.sh 498 PASS, screenshots
  /tmp/s18shot/widgets-*.png. Improve next: weather and calendar widgets,
  per-monitor layouts, a widget for the Board's "needs you".
- 2 B27 names: done by Sakura (ejb-55), commit bf9e727; see apps/board/WIP.md "B27 persona names".
- Usage: 0% -> 51% by the first handoff (with ejb-94); Emerson said keep going, batched from then on.
