# S16: B38 particles on the normal desktop (ejb-fd, Tetsu)

Emerson: "an option for particles on the normal desktop in the same way Forge
does"; "make it part of settings and wallpaper app"; he uses GNOME, GNOME
Classic and sometimes Hyprland. Design pick (asked 2026-09-27): **Forge-made
helper GNOME extension**, nothing downloaded.

## Plan (next session starts at step 2)
1. DONE: Particles moved to `shared/forge_particles.js` (commit 1232b29). The hub
   sets `Particles.look/showing/boost`; `tests/browser/run.sh` copies the script
   beside its hub copies. Result: 440 PASS before and after, and no Chrome left
   running.
2. `desktop/particles.html`: a transparent page with `<canvas id="particles">`,
   `../hub/theme.js` and `../shared/forge_particles.js`; showing() is always true.
3. `desktop/particles.py` (system python3, GTK3 + WebKit2 4.1, like forge.py): a
   borderless, see-through, fullscreen window with an empty input region, so
   clicks pass through. It watches `hub/theme.js` (Settings and Wallpapers
   rewrite it on every change) with a Gio.FileMonitor, calls
   `Particles.apply()` with the new theme, and exits when `desktop_particles` is
   off. It rests when fully obscured (the same trick as B34 in forge.py). On
   Hyprland it uses a GtkLayerShell background layer (the typelib is
   installed).
4. `desktop/gnome-extension/forge-desktop-particles@forge/`: launches the
   script through `Meta.WaylandClient.new_subprocess` while the setting is on
   (the extension watches `~/.config/forge/settings.json`). For its own window
   it calls `set_type(Meta.WindowType.DESKTOP)` plus `stick()`, the way
   ding@rastersoft.com's `emulateX11WindowType.js` does. Install is a symlink
   into `~/.local/share/gnome-shell/extensions/` plus
   `gnome-extensions enable`; it needs one log out and back in on Wayland.
5. The setting `desktop_particles` (bool, off by default) goes in
   `shared/forge_theme.py` SETTINGS. Settings shows it automatically. The
   Wallpapers app gets a toggle beside "Desktop only"
   (apps/wallpapers/static/index.html:74, app.js), which saves through its
   backend. Turning it on also starts the script on Hyprland (like
   set_autostart).
6. Checks: pytest for the setting and the start/stop helper; a headless
   screenshot of desktop/particles.html; the Wallpapers app's tests plus a
   screenshot; the extension is checked live by Emerson after he logs back in.

## State
- B38 step 1 done and checked: run.sh 440 PASS, 0 headless Chrome left. It
  hasn't been run yet: `tests/test_hub_*.py` (system python has no pytest, so
  use a venv that has it) and `tests/browser/hub_speed.py` (it copies the hub
  on its own, so it may need `shared/forge_particles.js` beside the copy).
- Steps 2-6 done by S15 (ejb-35), commit d001ad3; details in sessions/2026-09-27-S15-quickstart-hub.md. Only the extension's live check is left (after a log out and in). Hyprland: add `exec-once = python3 ~/Forge/desktop/particles.py` to hyprland.conf (not done: his Hyprland config is his). Backups are in backups/2026-09-27-desktop-particles/.
