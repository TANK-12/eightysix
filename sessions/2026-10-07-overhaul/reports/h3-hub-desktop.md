# H3 report: hub, desktop and the shared power tier (helper-3, Yuzu)

date: 2026-10-07 · for: both · crew overhaul · also closes Relay task 60

## Checks
- Tests pass: tests/test_power_tier.py (13 new) plus test_seen, test_desktop_cover, test_forge_gpuload, test_desktop_*, test_speed_detail, test_fullscreen, test_hub_*: 168-174 pass depending on the -k selection. apps/wallpapers tests: 30 pass.
- One test fails, and it failed before my edits too (same result with the backup hub/index.html): test_hub_sliders::test_each_is_a_slider_whose_default_keeps_the_old_behaviour (particle_fps default 30 vs 60). It is not mine.
- black was run on the Python files I touched.
- pyright was run with system python (`--pythonpath /usr/bin/python3`, because forge.py and particles.py need GTK) and with apps/dossier/.venv for the tests. The only errors left are the gi "unknown import symbol" stubs and forge.py:256 in thumb_png, all already there before. No new errors.
- JS: `node --check` on forge_power.js, forge_desktop.js, the extension and the hub's inline scripts.
- Headless Chrome screenshots, looked at: /tmp/h3/shots/ (home at 1920, 1366 and 1100; the Alt+W page before and after the fixes).

## Design decision
I extended the existing easing (shared/forge_power.js levels 0-3, forge_gpuload.py, gpu_heavy.json) instead of adding a second system. There are two new inputs:
- **Visible share.** The Forge GNOME extension measures how much of each Forge window and desktop screen shows and writes it to $XDG_RUNTIME_DIR/forge-desktop-under.json. Under 10 % showing = paused (page unmapped). Under 35 % = reduced (level 3, plus a 15 fps cap).
- **Whole-machine CPU.** forge_gpuload.CpuBusy: enters at 70 % or more held 10 s, leaves under 50 % held 20 s, so it never flickers. It reads /proc/stat once per existing 3-5 s read.

Every effect follows the same tier. `ForgePower.tier()` and the `power_tier` key say why: "reduced: machine busy / GPU busy / battery low / mostly covered" or "paused: hidden". Visible on AC stays full. Nothing was removed.

## Changed files (backups in ~/Forge/backups/2026-10-07-overhaul/hub/)
- shared/forge_power.js: shown, reason, tier(), power_tier, the 15 fps covered cap.
- shared/forge_gpuload.py: cpu_times, CpuBusy, GpuLoad.read() adds cpu and reason.
- shared/forge_seen.py (Momo's new file): pid_shown, watch_shell(on_share).
- forge.py:
  - Momo's Seen moved into forge_seen.
  - on_share -> window.forgeShare, resent when the page finishes loading.
  - "widgets" added to the grab_focus tuple.
  - temps added to the 30 s stats block.
- hub/index.html:
  - powerChange(), forgeShare (clamped), forgeTier, widgetsTheme() carrying power_tier to the widgets, ForgeDepth.set({tier}).
  - No HUD note for cover easing; the note states the real fps.
  - Alt+V no longer forces 60 fps while covered.
  - WidgetsPage (Alt+W, Esc, ends when an app opens, title "Widgets", centred, entrance animation) and Alt+Q close-app.
  - scrollbar-gutter: stable on #home.
- desktop/particles.py: read_shown, per-screen theme["shown"], gpu_reason, temps, the hardened power check, docstring.
- desktop/particles.html and desktop/forge_desktop.js: pass shown and reason; power_tier goes to the widgets.
- desktop/gnome-extension/.../extension.js (Momo's cover work, finished):
  - writes the shares.
  - measures the main "Forge" window, not the pop-out pads.
  - deletes the file on disable.
- New: tests/test_power_tier.py, docs/library/power/2026-10-07-hub-desktop-power.md, a note in apps/wallpapers/WIP.md (nothing changed in Wallpapers: "the Forge desktop" is ~/Forge/desktop), and the State section of Relay task 60.

## Numbers (measured in the scratch rig: a private headless GNOME, A/B in the same sitting; full tables are in the library doc)
- Window over 98 % of Forge, not maximised (Emerson's case):
  - hub: 24.4 % GPU / 46 % CPU -> 0.0 / 0.2 (-100 %)
  - desktop: 17.3 % / 31 % -> 0.0 / 0.2 (-100 %)
- Window over 88 % (reduced tier): hub GPU median 27.6 -> 21.0 (-24 %), CPU 41 -> 25 (-39 %). Desktop: no gain measurable within the noise.
- Visible or 65 % showing: unchanged, so the looks are kept.
- Live Forge (old code): hub 17.8-24 % GPU / 37-55 % CPU with Jan busy. **Live after: not measured** (it needs a restart).
- Not measured: the machine-busy tier, the battery tier and frame times. Umi stopped measuring at 20:15; these belong to the final proper test with Emerson.

## Critic (opus, harsh breaker)
Fixed:
- an app opened from the Alt+W page left home stuck on widgets only
- popout pads hid the hub's cover state
- Alt+V ignored cover
- the HUD note gave the wrong fps
- the desktop power check could die on a bad battery_saver value (my first fix wrongly turned 0 into 20; corrected)
- the extension left a stale file on disable
- forgeShare accepted junk values
- the widgets page was empty-looking and still titled "Home"
- "Edit" jumped when the scrollbar appeared

Rechecked in headless Chrome after the fixes: all hold.

Left:
- The widget cards cut off their sublines at 1366/1100 ("86% of t…"). That is forge_widgets.css, helper-6's file; note posted to them.
- A window spanning two monitors is measured only on its own monitor. Minor.
- Zen, background mode or Alt+V turned on over the widgets page go back to the widgets page when they end. Kept on purpose: it matches "back to where he was".

## Needs Emerson / a restart
- Restart Forge (Python changes) and log out and in to GNOME (the extension). A restart may first need `sudo pacman -Syu` if mesa and llvm-libs are still mismatched (see 2026-10-07-gpu-and-visualiser-lag.md).
- System-level suggestion only, not done: none needed. CPU caps and Hyprland config were not touched.

## PROGRESS.json note for the commander
"2026-10-07 overhaul H3: one shared power tier (shared/forge_power.js): full / reduced (GPU load, whole-machine CPU busy with hysteresis, battery saver, under 35 % visible) / paused (under 10 % visible, minimised, other workspace), with the reason in power_tier. The GNOME extension measures how much of Forge and the desktop shows. Relay task 60 is closed: a window over 98 % of Forge takes the hub from 24 % GPU to 0 and the desktop from 17 % to 0 (rig, verified). Alt+W widgets page and Alt+Q close the app. Live needs a Forge restart and a GNOME re-login; live numbers are not yet measured."

## Scratch left
- /tmp/h3: the harness and shots.
- /tmp/r60: Momo's rig, stopped.
Both are safe to delete after review.
