# Forge work: status for Emerson

Written by Hub (S7), about 16:40 on 2026-09-26. This file stays put, so the
update can't scroll away. Nothing below is live until Forge restarts; Hub
will ask before restarting it.

## Sessions
| Name  | Id     | Job |
|-------|--------|-----|
| Hub   | ejb-47 | forge.py, the hub, Settings: full screen, background start, hide/archive, dock, popups, media, zen, monitors, speed, polish |
| Chat  | ejb-9e | Claude app (Enjoy-style layout, roadmap tab, Live2D off, image paste) and the Browser |
| Tools | ejb-ea | new apps: Terminal, Files, Code (OpenVSCode Server) |

## Done and checked
- Hub: typing a preset name no longer jumps to the app search (browser test).
- Hub: full screen: an app's full screen and Forge's own full screen are kept
  apart, so leaving an app's full screen no longer un-windows Forge; the
  bar's Full screen button works when Forge started full screen (9 tests).
- Hub: background start: Forge starts hidden at login and comes up at once
  when opened; closing the window keeps it in the background (Settings can
  make it quit); Ctrl+Shift+Q quits. Checked live in a test copy.
- Chat: old Browser pages no longer stack up and keep running after closing
  or reloading the Browser.
- Tools: new Files app (32 tests, UI checked in headless Chrome).

## In progress
- Hub: hide and archive apps (right-click menu with Undo), the dock (fits
  at any icon size, waits a moment before popping up, new "Off" option),
  popups that fade away when you click outside or press Esc.
- Chat: Live2D off by default, then the Enjoy-style Claude app.
- Tools: Terminal (xterm.js), then Code (OpenVSCode Server).

## Next
- Hub: background music loudness, media button popup with "go to where
  it's playing", Settings with sub-menus, zen mode, multiple monitors and
  Hyprland plus popping an app out to its own window, speed measured
  before/after, polish and an embarrassing-stuff sweep before your dad sees
  it, S2's leftovers.
- Chat: Enjoy-style app, roadmap tab (space-themed), image paste, and the
  panel losing text when new output arrives.
- Tools: Terminal, then Code.
- Nobody yet: Drift Peaks / Alto (brief ready for another session).

## Waiting on you
- Full screen: which app and which button left the empty band at the top?
