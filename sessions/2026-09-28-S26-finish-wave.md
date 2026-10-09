# S26: finish every unfinished Forge task, the desktop, widgets and extensions

Session Yui/Tetsu (ejb-be), 2026-09-28. Emerson's words:

> finish up all the unfinished forge tasks and desktop and make the widgets
> and extensions and stuff, leave novel forge alone
> (mid-session) don't ask questions, just do what I would enjoy

NovelForge (apps/novelforge, its uncommitted rework) is not touched.

## Ledger, in order
1. S25 (Takumi, ejb-e1, stopped with ~1,900 lines uncommitted and no State):
   check it, fix what fails, see it on screen, commit. Its own ledger is in
   sessions/2026-09-28-S25-effects-keys-widgets-desktop.md.
2. S25 item 14: "the Forge usage bars are not reliable and keep breaking".
3. #257 left over: the hub music reaches the speakers twice / sometimes
   silent (S20 brief).
4. S22 item 5: liquid glass and frosted glass with a strength slider.
5. S24: one Forge window per screen (A22 part b).
6. S23: 2.5D wallpapers (rembg isnet-anime + Depth Anything V2 Small, both
   approved by Emerson on 2026-09-27).

## State
- 1 done+checked, committed 045f576: S25 checked (pytest, run.sh, headless
  screenshots looked at), fixed (Wi-Fi scan freeze, cava release, gap-fill
  Add, weather from the time zone, popup labels, flaky harness checks). The
  live desktop script was restarted on the new code (running, no errors) but
  is not seen on screen yet: Forge covered the desktop.
- 2 done+checked, committed 6736908: usage bars. A rate_limit_event with no
  numbers replaced the stored usage and wiped the bars; now merged. 138
  Claude app tests pass. Needs the Claude app restarted (Forge restart).
- 3 done+checked, committed 5001cbf: #257 silence. WirePlumber had saved
  0% for "Forge" and the live Forge stream was at 0% (measured). The paused
  hub music no longer rests at volume 0, and starting it asks forge.py to
  unmute/lift Forge's streams. Fixed live on this laptop at 09:36. "Music
  heard twice" was not reproduced and is not fixed. A test left one harmless
  line "forge-s26-voltest" in ~/.local/state/wireplumber/stream-properties.
- 4 done+checked, committed 79e7fa3: glass kinds Flat/Frosted/Liquid +
  strength, on hub and desktop; run.sh 768 PASS 0 FAIL; screenshots looked at.
- 5 done+checked off screen, committed 0ce67d3: S24 as one desktop window
  per monitor (desktop/particles.py + the GNOME extension), each screen with
  its own widgets: the scenery that pop-outs land on. Setting On the
  desktop > On every screen. Only one monitor here, so more than one is
  reasoned, not seen. The "full hub on every screen" option is NOT built
  (a forge.py rework into several hub windows).
  Found on the way and fixed: S25's --edit took SIGUSR1, which WebKit's JS
  engine uses for GC; the live desktop window deadlocked at 100% of a core
  for 14 min (gdb: main thread in JSC::Heap::acquireAccessSlow). Now a
  watched file; a test guards it. The fixed script ran idle (0.4% CPU).
- 6 done+checked, committed 77100ab: 2.5D wallpapers. shared/forge_layers.py
  (no install, no download: PanelForge's isnetis.onnx + Depth Anything V2
  Base + panelforge's venv). Run live on sky2: 7.5 s, subject "near" (tree,
  girl, hill); layers looked at; hub screenshots at two pointer positions
  looked at. Turned ON in Emerson's settings (wall_3d); his layers are made.
- Checks at the end: run.sh 780 PASS 0 FAIL; pytest tests/ 274 passed;
  Claude app 138 passed; black run; pyright no new errors.
- Needs from Emerson: a Forge restart (Ctrl+Shift+R) for the hub, Settings
  and the Claude app; a log out and in for the GNOME extension (top bar
  menu, one window per screen).
- Scratch left: none in the tree; one harmless test line
  "forge-s26-voltest" in ~/.local/state/wireplumber/stream-properties.

## Follow-up ask (Emerson, 2026-09-28 ~10:05)
> keep working, make sure the background music works properly and the
> desktop widgets and visualiser and particles work and have settings

7. Desktop widgets / visualiser / particles work: done+checked LIVE at
   10:12 on an empty workspace: particles, clock, weather (Perth 18°C), the
   player card and ✎ Widgets drawn on the real desktop (screenshot looked
   at). The visualiser drew nothing because no sound was playing.
8. Settings on the desktop: done+checked, committed 545a343. A ⚙ button
   beside ✎ Widgets opens the GNOME extension's own settings page (seen to
   open live from `gnome-extensions prefs`; works without Forge and without
   logging out), Forge's Settings on Hyprland. Harness 34/34.
9. Background music: **fixed, root cause measured (2026-10-01 22:40, Hina
   ejb-d6); not yet heard in the running Forge (needs a restart).**
   Cause: WebKitGTK's default autoplay policy (allow without sound) refuses
   play() on an element with sound until the page has been clicked. The hub
   starts its music with no click, so it sat paused (and its AudioContext
   suspended) unless a click happened to land on the hub itself: "sometimes
   silent". Fix: forge.hub_webview() builds the hub's WebView with
   WebsitePolicies(autoplay=ALLOW). Checks: tests/test_hub_autoplay.py, and
   tests/browser/check_music_webkit.py (step b below, built smaller: a real
   WebKitGTK window plays a -40 dB tone from forge_music.MusicServer through
   Web Audio like Music.graph; plain WebView: rms 0.0, paused, ctx suspended;
   hub_webview(): rms 28.9, playing, ctx running, routed; both PASS).
   **Measuring tool was wrong before:** `parec --monitor-stream=<id>` returns
   zero samples on this PipeWire even for Eighty Six playing loud, so the
   "RMS 0" readings below said nothing. What works: start
   `pw-record -P '{ node.autoconnect=false node.name=cap }' ... out.wav`, then
   `pw-link "Forge:output_FL" cap:input_FL` (and FR). Live at 22:27 that gave
   Eighty Six rms 11563 and Forge rms 0.0 (stream running, all zeros).
   Still open: "music heard twice" not reproduced; the check saw two
   same-named output nodes for one routed page (element + AudioContext), the
   live Forge showed one. Older notes, kept: At 10:08 music was on
   with 30 tracks, but Forge's only sound stream (Web Audio, #177, now at
   100%) and the speakers were pure silence (parec RMS 0). All 30 tracks
   decode (gst-discoverer). The live Forge still runs the old hub (needs a
   restart for 5001cbf). Next session, in order:
   **2026-10-01 22:20 (Mei, ejb-c6), measured:** Forge restarted 20:21 today
   (`forge.py --background`, after 5001cbf). Settings: music on, volume 100.
   Forge has one sink input (#92, not corked, 100%); `parec --monitor-stream=92`
   for 2 s gave RMS 0.0, peak 0, so it is still pure silence. **Not known:** whether
   the hub believed it was playing at that moment (the window was in background
   mode and forge.sock has no state query). Next: Emerson opens Now playing,
   presses play, and the same parec line is run again; if it is still 0, do b.
   a. After Emerson restarts Forge, measure again: `pactl list sink-inputs`
      (Forge streams, volumes) and `parec --monitor-stream=<id> | head -c
      352800` for RMS while the hub says it is playing.
   b. Build tests/browser/check_music_webkit.py: a real WebKitGTK window
      (Gtk.Window kept below, app name "forge-music-check", not off-screen:
      off-screen WebKit never plays media) loading the real hub with a fixture
      theme whose tracks are two -50 dB tone files served by
      forge_music.MusicServer, wiring {"music": ...} to forge_music.handle.
      Assert: exactly one playing stream with signal (not two = "twice"),
      silence after pause, signal again after play, a new track after next.
   c. If the element + Web Audio route is at fault in WebKitGTK, fall back
      to the plain element (no createMediaElementSource) and let the
      visualiser use cava (visualiser_source "system" already does).
- Also seen: the screen locked at ~10:14 and GNOME turned every extension
  off (ours and dash-to-dock: INACTIVE), which stops the desktop layer; it
  comes back on unlock. Not a fault.
- Stopped at 92% of the 5-hour window (Emerson's pacing rule).
- 2026-10-01: item 9 fixed (above). Needs from Emerson: Ctrl+Shift+R to
  restart Forge, then music should start by itself. The S26 ledger is done
  apart from the unbuilt "full hub on every screen" option and the
  unreproduced "heard twice".
