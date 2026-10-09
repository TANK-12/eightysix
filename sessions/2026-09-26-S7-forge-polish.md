# S7: Forge polish pass (show-my-dad edition) — session "Hub"

Session ejb-47, solo, 2026-09-26. Emerson: "I want you to do all the work...
polish the forge related stuff ... make it really polished before I show my
dad, and embarrassing stuff". Takes over S2's unfinished items (S2 brief:
`2026-09-25-S2-hub-shell.md`; its A15/A16/A13/A11 are done, A12 overview was
built after its last State line).

## Owns
`hub/`, `forge.py`, `forge_views.py`, `shared/`, `apps/settings/`,
the Media button on the hub bar. Backups of every file
before editing: `backups/2026-09-26-forge-polish/`.

## Ledger
- A1 "do all the work, you're Opus max" -> everything in this one session,
  no helper agents. [constraint] Changed by Emerson later: "split the tasks
  and give it to the new claude terminal session" -> A8 and A15 went to S8.
- A2 "polish the forge related stuff ... really polished before I show my
  dad" -> look-and-feel pass over hub, bar, tiles, dialogs, Settings. [core]
- A3 "embarrassing stuff" -> find anything that would embarrass him in a demo
  (broken tiles, dev/debug text, error cards, placeholder text, crude copy)
  and fix it; assumed: hide rather than delete, list what was hidden. [core]
- A4 "start up of the app faster without the UI loading, launch in the
  background on startup" -> Forge starts at login with the window hidden;
  opening Forge shows the already-running window at once; a second launch
  hands over to the running copy. [core]
- A5 "make the UI better and faster" -> S2 A14: measure first, fix the worst,
  before/after numbers. [core]
- A6 "options for hiding / archiving apps" -> Hide: off home and dock, still
  in All apps and search. Archive: off everywhere, backend never started,
  Restore in Settings. From a tile's right-click and from Settings. [core]
- A7 "settings app have more settings and sub menus" -> Settings split into
  sections with sub-pages, plus the new settings this work adds. [core]
- A8 "make the browser load better, it's a bit finicky" -> find what is
  finicky about the Browser app loading and fix it. [core]
  -> handed to S8 (`2026-09-26-S8-claude-enjoy-browser.md`).
- A9 "media button take me where the media is playing, or a popup for more
  media controls" -> bar media button opens a popup: what is playing,
  play/pause/next/prev, seek, volume, and "Go to it" which brings up the app,
  tab or window playing it. [core]
- A10 S2 leftovers: A12 overview (check it), A4 zen mode, A10 home declutter,
  A3 improve-next list. [core]
- A11 closing the window hides Forge instead of quitting; a real Quit stays.
  assumed yes (no objection to the plan). [detail]
- A12 real Forge window is not restarted without asking; Jan untouched.
  [constraint]
- A13 "in the preset size text popup I can't name presets, it just starts
  typing in the app search bar" -> typing in the Aa panel's preset name box
  stays in that box; the home screen's type-to-search ignores keys aimed at
  any text field. [core]
- A14 "I want a zen mode for the forge app and stuff like that" -> S2's A4
  zen mode, promoted: home without tiles/dock/bar (wallpaper, big clock,
  focus timer, one-line intention, optional ambient sound), a bar button and
  a key enter it, Esc leaves; plus calm extras in the same spirit. [core]
- A15 "make a version of the claude app to work and act and look like"
  Enjoy (pasted landing page: "one person, infinite engineers"; each task its
  own conversation with plans and progress together; see what's running and
  what needs you; notes and documents as a knowledge base; repeatable work
  saved as workflows; lowercase, calm, playful look with ↗ links) -> a second
  layout of apps/claude in that style, same backend, switchable; the current
  layout stays. assumed: a switchable version, not a replacement. [core]
  -> handed to S8 (`2026-09-26-S8-claude-enjoy-browser.md`).
- A16 "the full screen is still broken and will un-window the whole forge
  app, or it will leave like a 6th of the screen at the top with just the
  blurry background but no app or bars" -> entering/leaving an app's full
  screen never drops Forge out of its own full screen/maximised state and
  never leaves an empty band; checked in the real window. [core]
- A17-A19 "also build a terminal app and file explorer perfect app and a vs
  code compatible app for forge" -> three new Forge apps; brief written as
  `2026-09-26-S9-terminal-files-code.md` for another session (they touch no
  hub files). A19 needs Emerson's pick of what to install first.
- A20 "also want the alto game to be better, just copy alto or find its
  assets online ... or get alto's music" -> Drift Peaks (S3's app); added to
  `2026-09-25-S3-driftpeaks-audio-media.md` as A20 for the next S3 session;
  counted as the go-ahead for S3's A7 soundtrack download.
- Split (Emerson: "send more tasks off to the new claude code terminal
  session"): S8 = ejb-9e (A8, A15), S9 = ejb-ea (A17-A19).
- A21 "i dont want the live 2d to be active by default" -> the Live2D avatar
  stage (apps/claude, stage.js) is off until turned on; handed to S8.
- A22 "make the forge app work very nicely in many ways across many
  monitors, like Hyprland and stuff like that" -> multi-monitor: Forge shows
  on the monitor you are on, full screen fills the monitor the window is on,
  an app can pop out into its own window to put on another screen, and the
  same works on Hyprland as on GNOME. [core]
- A23 "when I change the size the dock icons at the bottom spill over and
  don't fix themselves or scroll ... I don't really like the dock popping up
  cause it keeps covering UI or input fields ... let me have an option in a
  menu of settings to turn it off" -> the dock fits any size (shrinks or
  scrolls, never spills); the bottom-edge pop-up over apps can be turned off
  in Settings, and never covers the field being typed in. [core]
- A24 "make copy and paste images work in claude terminal and claude forge
  app" -> Forge Claude app: handed to S8. Real terminal: he uses GNOME
  Terminal; wl-paste and xclip are installed; Claude Code pastes images
  with Ctrl+V (Ctrl+Shift+V is GNOME Terminal's text-only paste). Told him;
  S9's terminal app must pass Ctrl+V through. Re-check if he says it still
  fails.
- A25 "when I click out of popups like the text size one I want it to go
  away nicely" -> every hub popup (Aa size, music/media, overview, menus)
  closes on a click outside or Esc, with a short fade. [core]
- A26 "i would prefer that claude sessions have names" -> readable names:
  Hub (S7, ejb-47), Chat (S8, ejb-9e), Tools (S9, ejb-ea); posted on the
  board and in each brief's title.
- A27 "the background music is so quiet even at max, but when I turn it up
  it makes all my other non-quiet stuff too loud" -> the hub's music gets a
  real boost past 100% and evens out quiet tracks, so it sits level with
  everything else at the same system volume. [core]
- A30 "where is the music coming from, because it doesn't pause when I
  press the pause button in the music symbol; make the music interface
  better and make it work" -> found: the Media app was playing
  ~/Music/<lofi playlist>.mp4 (outputs/media.log /api/file requests); the ♫
  button only drives the hub's own background music, a separate player.
  Fix together with A9 + A27: the ♫ button becomes one Now playing popup
  for every player in Forge (shared script in each app reports media and
  takes commands) and on the desktop (MPRIS), with Go to it, seek, volume,
  and a boost past 100% for background music. [core]
- A31 "if you run out, switch the jobs over to the other subscription with
  the important tasks on ultra high and the others on medium" -> when the
  5-hour meter nears the stop point, hand each session's remaining work to
  sessions on the second account (Claude app, account "second"): [core]
  items at the highest effort, the rest at medium. [constraint]
- A32 "the claude usage bars in the app don't update till I actually start
  using them" -> handed to Chat (S8).
- A33 "open a text doc to tell me if you can switch to the other
  subscriptions, and another update in the new text doc" ->
  sessions/STATUS-evening.md, opened in GNOME Text Editor.

## State
- Baseline 2026-09-26: tests/test_hub_*.py and other stdlib tests all pass
  with system python; tests/browser/run.sh ALL PASS. test_blender_*,
  test_forge_accounts, test_forge_assets need pytest (not installed for
  system python; not hub tests).
- A13 done + checked: hub keydown's type-to-search skips any focused text
  field (typingInto()). tests/browser hub_polish block: typing in the preset
  name box stays there; bare home typing still searches.
- A16 part 1 done + checked (unit), real window not seen: forge.FullScreen
  keeps desktop (Start full screen) / app / element wishes apart;
  sync_fullscreen() applies them. App full screen inside Start full screen no
  longer un-windows Forge; bar button works; F11 in an app toggles the app,
  on home the window; Esc leaves the app's only; window manager taking it
  away clears all. tests/test_fullscreen.py 9 PASS. The "empty band at the
  top" symptom not reproduced yet; asked Emerson which app/button.
- A4 done + checked: `forge.py --background` starts hidden (hub loads while
  hidden); plain `forge.py` while one runs sends `show <activation token>`
  over the forge_open socket and exits; closing the window hides it unless
  Settings > Starting and closing says quit; Ctrl+Shift+Q, the page's
  {forge:"quit"} and SIGTERM really quit. Start at login (default on) writes
  ~/.config/autostart/forge.desktop (forge_theme.set_autostart, synced at
  launch and when Settings saves). Checks: tests/test_background_start.py 5
  PASS; live test copy in /tmp with its own socket: socket up 0.26 s, no
  window while hidden (list_windows), show -> window up with the hub fully
  drawn (screenshot), SIGTERM -> exited, socket removed. Close-to-hide itself
  not clicked live yet (needs the real window after a restart).

- A6, A23, A25 done + checked by S7 (from sessions/STATUS-evening.md, S7's last update): right-click Open / Close / Hide from home / Archive with Undo, hidden apps in a folded section, archived never start; dock fits any icon size, waits at the bottom edge, Settings "Dock: Off"; popups fade and close on outside click or Esc. Browser tests in hub_polish. Not seen in the real window (needs a Forge restart).
- A16 band done + checked by S7: the Material look (and Brain) kept its own top edge for the app area; full screen now fills the window in all five looks (hub_polish checks per look).
- A9 + A27 + A30 done + checked (finished by Finisher S10): the ♫ button is Now playing. hub/index.html NowPlaying: app media reported by shared/forge_media.js (every app with forge_chrome.js) and desktop players over MPRIS (shared/forge_mpris.py via forge.py handle_media, polled every 2 s while open; playerctld and Forge's own WebKit players left out). Big card for the newest playing source (play/pause, prev/next, seek, volume, Go to it), rows for the rest (click a name to make it the big one). Clips under 20 s are not listed. Background music: volume to 200% (Settings slider too), Web Audio leveller + limiter (setting "Even out loud and quiet tracks"), steps aside while an app plays (setting "Step aside for other sound") with a note saying so. Checks: tests/test_hub_media.py 4 PASS, test_forge_mpris.py 7 PASS, browser run.sh ALL PASS incl. new forge_media (9), hub_media (40), hub_level (5, measured in WebKit: 26 dB loud/quiet gap -> 7.1 dB, quiet +13.8 dB, 200% loud peak 0.963), hub_polish (S7's own Now playing checks). Screenshot looked at. Not heard with real speakers, not seen in the real window (Forge restart). Gap: pages inside the Browser app are native views, not frames, so they are not listed yet.
- A26 done by S7: sessions named Hub (S7), Chat (S8), Tools (S9) on the board (note 55) and in each brief's title.
- A33 done by S7: sessions/STATUS-evening.md written and opened in GNOME Text Editor; Finisher followed up with sessions/HOW-LONG.md.
- A2 + A3 in progress (Finisher S10, 2026-09-26 18:00, three helpers at Emerson's request "start 3 agents ... do as much polish as possible then stop in 20 mins"): hub CSS/copy sweep, apps copy sweep (found only Arcade's "Phosphor" wordmark, which is its deliberate codename, so it was put back), demo check with sessions/DEMO.md. Results folded into QUICKSTART.md.
- Not done: A5 speed (measure first), A7 Settings sections with sub-pages, A10 S2 leftovers (A12 overview check, home declutter), A14 zen mode, A22 multiple monitors + pop-out. In QUICKSTART.md "Left" for the next session.
