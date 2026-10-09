# S25: effect keys, compact Settings, Alt+V controls, widgets, desktop extension

Session Ren/Takumi (ejb-e1), 2026-09-28. Takes over S22 items 2-4 (Asuka,
ejb-b2, stopped after item 1). Emerson's words, tidied:

> make a shortcut that can turn on and off the visualiser and particle effect
> in the Forge app. Also I want more settings, and settings to be more compact
> but still there and better overall, and scrolling to the bottom shouldn't
> mean I need to scroll up to see some of the settings on the sidebar outline.
> Also in the Alt+V mode let me have controls in it by arrow keys, or pressing
> Alt+M to have a new settings popup for the visuals. Also bring over to the
> extension for desktop: particles, the widget, and a way to actually add the
> widgets to the scene; actually make the 5 new widgets that never got made,
> and let me also add visualisers to the desktop extension. Let it be fairly
> separate from Forge so it can run even without Forge running.

## Ledger
1. Keys to turn the visualiser and the particles on and off in Forge
   (HUB_KEYS registry, so Settings > Forge keys can rebind them).
2. More settings; Settings more compact, nothing lost, better overall.
3. Settings' side outline always fully in view while the page scrolls.
4. Alt+V mode: arrow-key controls; Alt+M opens a visuals settings popup.
5. Desktop extension: particles (already there), widgets on the desktop,
   and a way to add, move and remove them there.
6. The widgets that were planned and never made (S22 list): weather, media
   player, calendar, disk, network, Jan, alarms, plus a visualiser widget.
7. Visualisers on the desktop.
8. The desktop part runs without Forge running.
9. (mid-session) "a keybind to turn off animations and particles in that
   order and then back; Alt+P to turn off particles and Alt+M to turn off
   the visualiser". Read as: Alt+E turns the visualiser off, then the
   particles, then both back (the animations setting also stops particles,
   so "animations" here is the visualiser). Alt+M in Alt+V still opens the
   visuals popup, as the first message asked; Alt+Shift+M opens it anywhere.
10. (mid-session) "the visualiser, at least for terrain, like 20 percent
    more sensitive": terrain x1.2, plus a Visualiser sensitivity setting.
11. (mid-session) "do everything in this session", "don't forget the
    widgets", "make the desktop extension work for more than just particles".
12. (mid-session) "as always I have issues with the background media player
    sometimes just not making noise or playing files" (#257, still open).
13. (mid-session) "fix anything else you come across or can think of".
14. (mid-session) "the Forge usage bars are not reliable and keep breaking in
    the Forge app".

## Plan
- Keys: `effects` Alt+E (both), `particles-toggle` Alt+P,
  `visualiser-toggle` Alt+Shift+V, `visuals` Alt+M, all in
  shared/forge_theme.py HUB_KEYS. New bools `particles_shown` and
  `visualiser_shown` are the master switches, so the chosen style survives.
- Alt+V: arrows (visualiser style, pulse strength), Shift+arrows (particle
  kind, amount), 1-9 flip the beat effects, a small on-screen readout.
- Alt+M popup: built from settings marked `quick: "visuals"` in the table,
  handed to the hub in the theme (no hardcoded list in the hub).
- shared/forge_visual.js: the visualiser styles moved out of hub/index.html
  so the hub, the widget and the desktop draw with the same code.
- New widgets in shared/forge_widgets.js, each one `define()` call, with a
  per-widget options panel (colour, what it shows) in edit mode, and a
  storage hook so the desktop keeps its own layout in a file.
- Desktop: desktop/particles.py grows into the desktop host: particles,
  visualiser (its own cava through shared/forge_music.SystemLevels), widgets
  (data from /proc, sysfs, MPRIS via shared/forge_mpris.py, Jan's HTTP API,
  open-meteo for weather). Clicks pass through except on widgets and their
  edit bar; an edit button in a corner adds widgets. It starts when any of
  desktop particles / widgets / visualiser is on. The GNOME extension gets a
  top-bar menu (toggles, edit widgets, settings) and needs no Forge running.

## State
Takumi (ejb-e1) built all of it but stopped without writing this section or
committing. Checked, fixed and committed by Yui (ejb-be, S26) on 2026-09-28;
see sessions/2026-09-28-S26-finish-wave.md.
- 1 done+checked: Alt+E, Alt+P, Alt+M, Alt+Shift+M in HUB_KEYS (rebindable
  in Settings > Forge keys); hub_fx harness in run.sh.
- 2 done+checked: Settings compact by default (two columns, one-line help
  that opens on hover, a dot on changed rows, Reset per page); screenshot
  looked at.
- 3 done+checked: the side outline is sticky and scrolls on its own; checked
  in headless Chrome (outline 81-714 px in a 757 px window).
- 4 done+checked: Alt+V arrows / Shift+arrows / PgUp/PgDn / 1-9, a key hint
  line, and the Alt+M visuals popup built from forge_theme.VISUALS_POPUP;
  screenshot looked at. S26 widened it and named the background-mode
  visualiser row "Visualiser in background mode" (popup_label).
- 5, 7, 8 done+checked off screen, running live but not seen: the desktop
  page carries particles, widgets (✎ Widgets button, Add menu, drag, ⚙
  options, saved to ~/.config/forge/desktop-widgets.json) and a visualiser,
  fed by desktop/particles.py without Forge. desktop_widgets harness 31/31;
  screenshots looked at. S26 restarted the live desktop script on the new
  code (no errors); Forge covered the desktop, so it has not been seen on
  the real screen. The GNOME extension's top-bar menu needs a log out and in.
- 6 done+checked: weather, media player, calendar, disk, network, Jan,
  alarms, visualiser widgets (hub_widgets2 harness); S26 made Add fill the
  first gap and the weather card start from the time zone's city (Perth).
- 9, 10 done+checked (tests); 11: this list.
- 12 (#257 music silent/twice): not done here; S26 ledger item 3.
- 13: S26 fixed a 3 s freeze every 30 s off Wi-Fi (nmcli scan), the cava
  release delay, and two flaky harness checks.
- 14 (usage bars): fixed by S26 in apps/claude/runner.py.
- Needs a Forge restart to be seen in the hub and Settings.
