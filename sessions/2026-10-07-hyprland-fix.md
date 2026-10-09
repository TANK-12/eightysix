# Hyprland setups fix
date: 2026-10-07 · for: Claude · model: Opus 5.5, high (Emerson's pick)

## Emerson's words
"also make new one to fix my hyprland setups i noticed that they broke" (2026-10-07). No detail yet on what breaks: find out, and ask him one short question only if the cause can't be found from logs and a test run.

## What is known
- Emerson adds: 2 of the 3 setups are broken, the last two (end4-pC and Caelestia), and all 3 (Brain Shell too) show error messages. Fix the two broken ones and clear the error messages on all three.
- He is on GNOME right now (gnome-shell, Wayland). Hyprland is his other session; nothing has been checked in it this week.
- Config: ~/.config/hypr (hyprland.conf 242 B pointing at the setup, hyprland.lua, variables.lua, caelestia-keybinds.lua, hyprland-brain.conf, custom/, hyprland/, scheme/, shaders/, utils/, hypridle/hyprlock). Three shells: Brain Shell (source ~/.local/src/Brain_Shell), end4-pC (Material Design 3) and Caelestia; likely Quickshell-based.
- Likely cause to check first: a system update (kernel is now 7.2.9). Read /var/log/pacman.log for hyprland, hyprutils, hyprlang, aquamarine, quickshell, qt6 and related upgrades since mid-September, then run each setup's config check (e.g. `Hyprland --verify-config` or the version's equivalent) and look for errors from the shells.
- ~/hypr-for-windows is the Windows port for a friend: out of scope unless the break is there.

## How
- Back up every file before editing it (copy to ~/Forge/backups/2026-10-07-hyprland/), never delete; Emerson's rule is be super careful deleting, prefer gio trash.
- Do not log out or crash his GNOME session. Headless only (Emerson, 2026-10-07: nothing that opens on his screen, no nested windows): config checks, headless backend, logs; if a real login is needed, write exact steps for him instead.
- Never touch CPU power caps (Power app). Don't edit ~/Forge files claimed on the `overhaul` crew (`python3 ~/.claude/skills/crew/crew.py status overhaul`).
- Fix all three setups if they're broken, so each starts cleanly with its bar/widgets, keybinds and wallpaper as before. Don't change what works.
- Finish: a dated doc in ~/Forge/docs/library/hyprland/2026-10-07-setups-fix.md (what broke, why, what changed, what is verified vs only reasoned about, steps he should try on next Hyprland login) and a board note on crew `forge`.
