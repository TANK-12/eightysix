# S11: finish QUICKSTART "Left": session "Kiln"

Session ejb-54, solo, default account, Opus 5.5 high effort, 2026-09-26 late
evening. Emerson: "ok so get to work on the unfinished forge tasks". Works
from `QUICKSTART.md`. Each item's history stays in its own brief (S7, S9,
S3, S4); this file holds the ledger and this session's state.

## Emerson's answers (2026-09-26, verbatim)
- Code Restricted Mode banner: "if you cant find a fix in 3 tries just build
  a thing that will work"
- Pixel Forge -> PixelForge: "Rename to PixelForge"
- S4 A31 Godot character: "3 Both" (VRoid CC0 VRM body + Quaternius
  animations)
- S3 A7 Alto soundtrack: "download it at 128kbps and let me look at it
  cause there shouldn't be that much" (he is right: 127 min at 128 kbps is
  about 122 MB, the 220 MB guess was for best-quality VBR)

## Ledger
1. Hub A7: Settings with sections and sub-pages (S7)
2. Hub A14 leftover: Settings for what zen mode shows
3. Hub A22: multiple monitors + pop-out window
4. Hub A5: speed, measured before and after
5. Polish: cut-off tile taglines (Jan Tune, Board), S2 leftovers (A12, A10)
6. Rename Pixel Forge -> PixelForge
7. Code Restricted Mode: 3 tries, else build a workaround
8. S3 A7: Alto soundtrack at 128 kbps into ~/Music/Alto, Emerson looks first
9. S4 A31: VRM body + Quaternius animations in the Godot template

## State
Resumed 2026-09-27 ~00:45 side by side with Hagane (S12, ejb-72), split by
file: Kiln owns forge.py, forge_views.py, shared/forge_open.py, apps/code,
the PixelForge rename, S4 A31, and Blender + Godot for Claude (board #93).
Hagane owns the hub, Settings, forge_theme, forge.css/js and git commits.
- 1 A7 Settings sections: done+checked (before the pause; see git diff of
  apps/settings/static and tests/browser/settings_sections_harness.js).
- 2 zen settings: done+checked (forge_theme ZEN, hub Zen.draw, hub_zen checks).
- 7 Code: done+checked. Restricted Mode gone (try 1: --disable-workspace-trust);
  "broke" was the page refused with "auth mismatch" after any editor restart
  (token + port now kept); 4 extensions' missing browser files fixed. 12 pytest
  + check_ui ALL PASS. Details: apps/code/WIP.md. Not seen in the Forge window.
- 6 PixelForge rename: done (label, title, h1, crewroom copy, shared comments,
  READMEs). hub/status.js updates on the next Forge start. Hagane has the
  one comment left in shared/forge.js.
- forge.py for Hagane: show_window calls forgeShown(); --background loads the
  hub with ?background=1 (shell_url, test in tests/test_background_start.py,
  6 pass). Live after a Forge restart.
- 8 Alto soundtrack: done, ~/Music/Alto 118 MB at 128 kbps; Emerson to look.
- Board: answered #86 (battery saver), #89 (name Kiln), #95 (tl;dr), #99.
- Found: calendar and jan-tune both use port 8453 (told Hagane, their apps).
- 9 A31 + board #93 (Blender/Godot for Claude): character done+checked
  headless. VRoid HairSample_Female (CC0) + Quaternius UAL (CC0) in
  shared/assets/, new shared/bridges/godot/humanoid.py retargets both onto
  %GeneralSkeleton, template.json assets/retarget, godot_new_project copies
  them. Tests: humanoid 5, acchan test_godot 9 (real headless walk: moved
  5.5 m, blend 1.0, thigh swing 1.66 rad), acchan suite 161 passed; VRM
  imports in headless Blender. Not seen on screen (Emerson's GPU rule).
  Left: textured ground/props in main.tscn, the end-to-end Blender->Godot
  demo. Full state: docs/plans/PLAN-blender-godot-upgrade.md "State 2026-09-27".
- 3 A22 not started in code; stopped ~02:00 2026-09-27 because the usage
  meter answered 429 for 15+ min (last reading 46% at ~01:10, two sessions
  burning it), and a half-done forge.py is worse than none. Findings for the
  next session (reasoned, NOT tested): this session ran on GNOME Wayland,
  where the compositor places a newly mapped window on the monitor with the
  pointer, and Gtk.Window.fullscreen() fills the window's current monitor,
  so "opens where the pointer is" and "full screen fills its monitor" may
  already hold; check on two screens before writing code (Hyprland too).
  The real work is the pop-out: a second Gtk.Window + WebKit2.WebView on
  that app's URL, opened from the hub (postMessage {forge: "popout", name})
  and handled in forge.py next to the other forge messages; the hub side is
  Hagane's (hub/index.html). Emerson's idea of one Forge per monitor with
  linked sub-apps is optional ("do what is best").
- 4 A5 forge.py-side speed: not started.
- Stopped cleanly: no file mid-edit, no scratch server or Godot left running,
  scratch projects deleted. Nothing committed (Hagane commits).
- Backups: backups/2026-09-26-S11/. No commits (Hagane commits).
