# Forge: can I switch subscriptions? + update

Written by Hub (S7) at 16:55 on 2026-09-26.

## Can I switch to your other subscription?

Short answer: not this session itself, but the work can move there.

- A running Claude session stays on the account it started with. I can't
  flip Hub (this session) over to "second" halfway through.
- What does work: start new sessions on the account "second", and they
  continue from the briefs in ~/Forge/sessions/ (every session keeps its
  ledger and State there, so a new session loses nothing).
  - In the Forge Claude app: + New conversation, set the account to
    "second", set Effort to "Max" for the important jobs (Hub: full screen,
    media, polish) or "Medium" for the rest, then paste the brief line.
  - Or in a terminal:
    `CLAUDE_CONFIG_DIR=~/.local/share/forge/claude/profiles/second claude --effort max`
    (use `--effort medium` for the lighter jobs).
- I can start those myself by opening a terminal tab and typing that
  command through Acchan's terminal tools. That route is possible but I have
  not tried it in this session yet.
- Right now the usage meter can't be read: the usage check returns "429 Too
  Many Requests" for both accounts (the meter service is rate-limiting, not
  necessarily a sign you're out). Last good reading was 54% of the 5-hour
  window at about 16:30.
- Your rule is saved: when a session runs out, its jobs move to "second",
  important ones at Max effort, the rest at Medium.

## Done and checked since the last update
- Hub: full screen band FIXED. Your screenshot showed it; a probe window
  reproduced it. Cause: the Material look (and Brain) kept its own top
  edge for the app area, which beat "fill the screen", so the bar hid but
  the app stayed 76 px down. Now full screen fills the window in all five
  looks with no frame left round the app (browser checks).
- Hub: hide and archive apps: right-click any tile, dock icon or bar icon
  for Open / Close / Hide from home / Archive, with an Undo notice. Hidden
  apps live in a folded "Hidden" section at the bottom and search still
  finds them; archived apps are gone everywhere and never start.
- Hub: the dock fits at any icon size (your 1.55 size used to push it past
  both edges); it waits a moment at the bottom edge before popping up; new
  Settings choice "Dock: Off".
- Hub: popups (text size, music, the new menu) fade away when you click
  outside them or press Esc.
- Hub: apps can open each other at a place (Files -> "Open terminal here").
- Chat: Browser pages no longer stack; Live2D is off until you click 🎭;
  image paste, thumbnails and copy in the Claude app; replies no longer
  wiped when a tool call follows (that was the "update went away" bug).
- Tools: Files app and Terminal app done (xterm.js, htop/vim work, Ctrl+V
  passes through for Claude image paste).

## Working on now
- Hub: the music. The music you heard was the Media app, not Forge's
  background music, which is why the music button's pause did nothing.
  Building one "Now playing" popup that controls whatever is playing in any
  Forge app (and players like Firefox), with "Go to it", seek, volume and a
  boost past 100% for quiet tracks.
- Chat: Enjoy-style Claude app, then the space-themed roadmap tab, then the
  usage bars updating on their own.
- Tools: Code editor (OpenVSCode Server).

## Next for Hub
Settings with sub-menus and more settings -> zen mode -> multiple monitors
and Hyprland, popping an app out to its own window -> speed, measured before
and after -> polish and the embarrassing-stuff sweep before your dad sees it.

## Needs a Forge restart to see
Everything above. I'll ask before restarting; say "restart forge" whenever
suits you.
