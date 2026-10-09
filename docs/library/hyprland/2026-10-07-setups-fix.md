# Hyprland setups fix (Brain Shell, end4-pC, Caelestia)
date: 2026-10-07 · for: both

## What was broken, and why

| Setup | Fault | Cause |
|---|---|---|
| end4-pC | Default settings, no wallpaper, "Failed to deserialize json: illegal number" | `~/.config/illogical-impulse/config.json` had its first 4096 bytes zeroed (half-written file after a hard power-off; the empty `config.json.tmp` dates from 26 Sep 19:57). |
| end4-pC | Errors in the shell log: `Cannot assign to read-only property "mirrored"` (bar), `filterDuplicatePlayers is not defined` (right sidebar) | Bar set `mirrored` on every widget, including Qt controls where it is read-only; the sidebar called a function that only existed in MediaControls.qml. |
| end4-pC | Game-mode toggle did nothing; lock screen ran a bad command | Used `hyprctl keyword`, which Hyprland refuses in Lua-config mode; Lock.qml also ran `keyword …` as a bare shell command (no `hyprctl`). |
| Brain Shell | Two bars stacked; wallpaper daemon started twice (second one panics); idle, polkit and clipboard watchers doubled | `hyprland.lua` still had the old `BRAIN_SESSION` autostart block, on top of the newer shells registry in `hyprland/execs.lua`. |
| All three | 30 errors at every login: `keyword can't work with non-legacy parsers. Use eval.` | `hyprland/rules.lua` pinned workspaces to monitors with `hyprctl keyword workspace …`; the Lua config mode rejects that, so workspaces were never pinned. |
| All three | `__restore_video_wallpaper.sh: Permission denied` at login | Script not executable. |

Graphics stack: mesa had been held at 26.2.2 while llvm-libs went to 23 (6 Oct), which broke anything GL. It was already fixed at 16:32 today (mesa 26.2.4 installed); no missing libraries now.

## What changed (backups of every original in `~/Forge/backups/2026-10-07-hyprland/`)

- `~/.config/illogical-impulse/config.json`: rebuilt. Lost head (first ~85 lines: ai, appearance, apps, audio, start of background) taken from his preset `presets/Traveler.json` (96% match with the surviving rest); everything after that is his surviving file. The seam line matched exactly. Corrupt copy kept as `illogical-impulse-config.json.corrupt`.
- `~/.config/hypr/hyprland/rules.lua`: workspace pinning now uses `hl.workspace_rule({ workspace, monitor, default })`.
- `~/.config/hypr/hyprland.lua`: legacy Brain autostart block removed; its keybinds line kept.
- `~/.config/hypr/custom/scripts/__restore_video_wallpaper.sh`: `chmod +x`.
- end4-pC (git repo at `~/.config/quickshell/end4-pC`, changes uncommitted): `BarContent.qml` uses one `setMirrored()` helper; `filterDuplicatePlayers` moved into `services/MprisController.qml` and both panels call it there; `GameMode.qml` uses `hyprctl eval 'hl.config({...})'`; `Lock.qml` dead command removed (lock behaviour unchanged, it never worked). `Background.qml` already had uncommitted edits before this session; not touched.
- Caelestia and Brain Shell code: no changes needed; both already use `eval` in Lua mode.

## Verified vs reasoned

Verified:
- `Hyprland --verify-config` passes for all three shells after the edits; a negative probe (bogus field in `hl.workspace_rule`) fails as expected, so the check really validates fields. The game-mode `hl.config` string passes the same check.
- `config.json` parses; wallpaper path present and the image exists.
- `qmllint` finds no syntax errors in the six edited QML files (negative probe with a broken file is flagged).
- Before the fix, nested test runs (Hyprland in a window on GNOME, with GNOME-affecting autostarts blocked) showed: Caelestia bar + wallpaper fine; end4 bar with no wallpaper; Brain with two stacked bars. Screens were captured with grim.

Not verified (needs a real login; Emerson asked for no more windows on his screen):
- The shells after the fix, on real monitors. In particular, **Caelestia looked fine nested**; the only Caelestia fault found was the shared workspace-rule errors. If Caelestia still misbehaves, the cause is something that only shows in a real session.
- The exact on-screen error messages he saw were not captured (Hyprland logs live in RAM and were gone after today's reboot).

## Steps for the next Hyprland login

1. Log out of GNOME, pick each session in turn at the login screen: "Hyprland (end4-pC)", "Hyprland (Brain Shell)", "Hyprland (Caelestia)".
2. Expect: one bar, his wallpaper, no red error bar at the top. end4 settings should look like before (they were rebuilt from the Traveler preset plus the surviving file, so a few early options such as AI or appearance tweaks may be preset values: check them in end4 settings).
3. Press SUPER+1 … on each monitor: workspaces should stay on their own monitor now.
4. If anything still shows an error, run `hyprctl configerrors` and copy `/run/user/1000/hypr/*/hyprland.log` and `/run/user/1000/quickshell/by-id/*/log.qslog` somewhere outside `/run` before logging out (they vanish at reboot), then hand them to Claude.
5. To undo any file: copy it back from `~/Forge/backups/2026-10-07-hyprland/`; for end4-pC, `git -C ~/.config/quickshell/end4-pC diff` shows every change.

Side note: `~/.config/hypr/hyprland.conf` has a typo (`exec-once = kwybars-daemo`) but is not loaded, because `hyprland.lua` takes precedence. Left as is.
