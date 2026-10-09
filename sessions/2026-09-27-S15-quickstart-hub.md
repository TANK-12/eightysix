# S15: QUICKSTART top list, session "ejb-35" (Tetsu)

Emerson (2026-09-27): "Read ~/Forge/sessions/QUICKSTART.md and work the top
section in order, starting at item 0." Then: "make sure to coordinate with
other sessions on board".

## Ledger (IDs from QUICKSTART "Left after the 2026-09-27 wave")
0. B34 GPU/CPU while Forge isn't seen (minimised, other workspace; keep
   running on another monitor).
1. B32 Board app: **not mine**. ejb-d3 (S14) holds apps/board (board note 115).
2. B7 background effects: pointer parallax + time-of-day tint, each a setting.
3. B4 Now playing: volume slider and controls on every source row.
4. B20 home widgets and layouts.
5. B18 speed: measure first paint and FPS, pause work that isn't visible.
6. A22 multiple monitors: **Kiln (ejb-54)** posted it's on it (note 103).
7. S14's items: ejb-d3's.

## Files
forge.py (Seen class, window wiring, pause_hidden relay), hub/index.html,
shared/forge_theme.py (SPEED group, pause_when_hidden), tests/test_seen.py.
Backups: backups/2026-09-27-b34/.

## B34 findings (measured 2026-09-27 on a probe window, GNOME 50 / mutter 50.4,
GTK 3.24.52, WebKitGTK 2.52.6)
- Minimise on GNOME Wayland: no window-state change, no unmap, and WebKit's
  `document.hidden` stays false; the page's animation frames kept running at
  24/s while minimised.
- GNOME does send `visibility-notify-event` FULLY_OBSCURED about 4 s after
  the window is minimised (mutter's suspended state), and it held for the
  full 25 s the window stayed minimised.
- Frame callbacks are **not** a usable signal: a queued draw still painted 4
  times a second while minimised (the plan in QUICKSTART guessed they stop).
- `set_child_visible(False)` on the window's child: `document.hidden` true in
  under 0.1 s, animation frames 24/s -> 0, timers slowed to once a second,
  window size unchanged, a playing `<audio>` kept playing; `True` brings it
  all back at once.
- Not measured yet: whether GNOME sends the "visible again" event when the
  window is restored (the probe could not restore itself: GNOME refuses a
  focus-less self-restore), and whether switching workspace sends
  FULLY_OBSCURED. Safety net in the code: focus, a click, a key or the
  pointer entering the window always counts as seen.

## State
- B34 done, checked off screen: tests/test_seen.py 7 pass, hub tests 63 pass,
  Settings tests 34 pass, browser run.sh ALL PASS, a hidden test copy of
  forge.py started and stopped cleanly. **Live check not done**: needs a
  Forge restart plus Emerson minimising / switching workspace / using the
  second monitor while `top` runs (command below). Commit e0d246f.
- B32 not mine (ejb-d3).
- B7 done + checked: WallFx in hub/index.html (pointer parallax via CSS translate/scale, settles and stops asking for frames; time-of-day tint layer #wall-tint, recoloured once a minute). Settings > Home screen: 'Wallpaper follows the pointer' (0-5 %, default 1) and 'Time-of-day tint' (default on). tests/browser/hub_effects_harness.js 13 PASS, run.sh ALL PASS, screenshot /tmp/b34/shot/b7.png (night tint, shifted picture, no edge showing). Commit 277d483.
- Side fix: apps/settings test broken by B37's gsettings read, test pinned to Hyprland (de961a8); Settings tests 34 pass.
- B4 done + checked: every Now playing row has previous / play-pause / next (hidden when the player has none) and its own volume slider + number (to 200% where it can boost); moving a row's volume does not make it the big one. hub_media_harness.js 6 new PASS, run.sh ALL PASS, screenshot /tmp/b34/shot/b4.png. Commit b57fbf4.
- B18 done + checked (hub part): apps behind another app now rest like a background tab. shared/forge_chrome.js pauses their CSS animations and holds their animation frames while the hub says they're off screen, then runs the held frames when they're back; standalone pages are untouched. tests/browser/check_rest.py 8 PASS (real time through cdp_driver: the virtual clock in run.sh gives frames no animation frames). Speed probe tests/browser/hub_speed.py, headless medians of 3: first paint 136-168 ms, soft particles 0.72 ms a frame at 60 fps, ember storm 1.5-1.9 ms at 52-58 fps, visualiser 1.3-1.4 ms at 60 fps. The hub's own JS is cheap; the live cost is WebKit painting and compositing plus the Claude app page (87% of a core measured with it streaming). Commits b6596c0, a8938c8.
- B20 not started: needs Emerson's answers first (questions in the final message of this session).
- Also done for Emerson: crossSessionInbound "accept", permissions.defaultMode bypassPermissions and skipDangerousModePermissionPrompt in ~/.claude/settings.json (backup settings.json.bak-2026-09-27); battery answer on the board (12.8 W, mostly Forge's page process); a run.sh block merge fixed (e2b76e8).
- B38 desktop particles done (d001ad3), checked off screen plus a 5 s live run: desktop/particles.html + particles.py (window mapped at 1536x832, 113 soft particles running, clean exit), GNOME extension desktop/gnome-extension/forge-desktop-particles@forge (API checked against mutter 18's typelib: WaylandClient.new_subprocess(context, launcher, argv), owns_window, Window.set_type/stick/lower/move_resize_frame, signals shown/raised), symlinked into ~/.local/share/gnome-shell/extensions and added to enabled-extensions. **Not checked live: the extension, which loads at Emerson's next log-in.** Setting Home screen > Particles on the desktop (off by default) + Wallpapers toolbar switch; tests/test_desktop_particles.py 4, Wallpapers 29, screenshots /tmp/b34/shot/b38-page.png, b38-wallpapers.png. To try it: log out and in, then tick Particles on the desktop in Wallpapers.
- Particles behind open apps (Emerson: 'even when I have apps open ... particles still work'): done + checked (afb11d5); setting Home screen > Particles behind open apps, default on; hub_effects_harness 4 new PASS, run.sh 453 PASS.
- Side fix: tests/test_hub_ambience.py read KINDS from the hub after they moved to shared/forge_particles.js; hub pytest 68 pass.
- Was next: B38 desktop particles steps 2-6 (plan in sessions/2026-09-27-S16-desktop-particles.md), then B39 frame-rate slider in the Power app (Emerson #194).
- A22 Kiln's. B32 and the board rework ejb-d3's. #185 (Claude app less efficient than the terminal) offered to ejb-d3, who holds apps/claude.

## B20 questions for Emerson (asked 2026-09-27, not answered yet)
1. Which widgets first: clock, now playing, next calendar event, weather, notes, system stats, usage meter, Board "needs you"?
2. Where they live: beside the app tiles, replacing the big clock area, or anywhere on a free grid?
3. Drag and resize on a snapping grid, or fixed slots in small, medium and large?
4. Grid, list and compact layouts for the app tiles: whole home screen or per group?
5. How to edit: an "Edit home" button, Alt plus drag, or a long press?
6. Named layouts to switch between ("Work", "Chill")? Different per monitor?
7. Look: glass cards like the tiles, or bare text on the wallpaper?
8. Fresh start: only the clock and greeting, or a starter set?

## Live check for B34 (after a Forge restart)
`top -b -d2 -p $(pgrep -f "[f]orge.py"),$(pgrep -n -f "[W]ebKitWebProcess")`
then: minimise Forge for 10 s, restore it; switch to another workspace for 10
s, come back; put Forge on the second monitor and focus something on the
first. Expected: the web process falls from ~50% to near 0 about 4 s after
hiding, forge.py drops too, cava stops (`pgrep -c cava`), music keeps
playing, and the page is back instantly on restore. If restoring shows a
blank window, a click or moving the pointer over it brings it back (the
safety net); then GNOME did not send the event and that needs another look.
