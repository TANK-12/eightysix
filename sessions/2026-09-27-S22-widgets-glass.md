# S22: widgets, glass and the media player (next free session)

From S21 (Nene, ejb-c3). Emerson's rule for choices: "go with what you think
i will like and enjoy the most; if you don't know, make both options and make
it a setting".

## Ledger, in order
1. Bug: the Now playing "go to player" button often does nothing. Find why
   (hub/index.html NowPlaying) and fix it, with a browser check.
2. More widgets, each editable (what it shows, size, colour): weather, a full
   media player (art, seek, prev/play/next, volume, go to player), calendar,
   notes, disk, network, Jan, clock/alarms. He has 5 (Clock, Now playing,
   System, Notes, Relax). Widgets live in hub/index.html; settings in the
   Widgets group of shared/forge_theme.py.
3. The visualisers as a widget: style (bars, ring, wave, mirror, aurora,
   orbit, terrain) and size per widget.
4. His widgets on the GNOME desktop through the Forge desktop particles
   extension (desktop/particles.html is the desktop page; move the widget code
   into shared/ so hub and desktop share it). The extension's settings page
   already builds itself from the Widgets group (S21).
5. More glass: liquid glass (bright edges, a slight bend) and frosted, on
   tiles, bar, widgets and app frames, with a strength slider.

## State
Session Asuka (ejb-b2), 2026-09-27 evening.
- 1 DONE, checked off screen. Two causes. (a) A Forge app: zen, background
  mode (Alt+B) or the overview covered the app it switched to; "Go to it" now
  leaves them first (hub/index.html NowPlaying.command). Browser check in
  tests/browser/hub_media_harness.js (2 new PASS). (b) A desktop player
  (Firefox, Qobuz): GNOME on Wayland ignores MPRIS Raise, and many players
  report CanRaise false, so the button did nothing or was greyed out.
  shared/forge_mpris.py now finds the player's process (and its parents) and
  asks the desktop to focus that window: `hyprctl dispatch focuswindow pid:N`
  on Hyprland, or on GNOME the new D-Bus method org.forge.Desktop.Activate
  in the Forge desktop particles extension. MPRIS Raise is the last resort.
  Tests: tests/test_forge_mpris.py (16 pass). **Not verified live:** GNOME
  loads the extension change only after Emerson logs out and back in; the
  hub part needs a Forge restart.
- Also fixed: tests/browser/run.sh did not copy shared/forge_framecap.js and
  forge_power.js beside the hub copies, so the hub harnesses threw at start
  after S21. Full run.sh: 640 PASS, 0 FAIL.
- Extra ask (Emerson, mid-session): the Claude app's tool dropdowns get a
  pink "🖼 picture" tag when a tool result holds a picture (the picture was
  already shown inside). apps/claude/static/claude_common.js + app.css;
  check tests/browser/claude_pic_tag.html (in run.sh); screenshot looked at.
  Needs the Claude page reloaded (Forge restart).
- 2-4: done by S25 (Takumi) and checked/finished by S26 (045f576). 5 glass: done by S26 (79e7fa3): Flat/Frosted/Liquid + strength.
