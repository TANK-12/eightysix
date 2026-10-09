# Power — work in progress

## U1 sweep (2026-10-08, Relay task 74)

Swept by Relay task 91 (group G17).
- Rest when hidden: the 5 s `setInterval` (which still polled status and
  history every 30 s behind other apps) is now one `ForgeIdle.poll`
  (`/shared/forge_idle.js`): 5 s while Power is on screen, nothing while
  hidden. The backend samples the graph by itself, so coming back shows the
  last 10 minutes at once (the poll runs straight away on return).
- Server away (break 6): the poll returns false when `/api/status` cannot be
  reached, so its wait doubles 5, 10, 20 to 30 s, and a calm strip at the top
  says "The Power server is not answering ..." instead of "Failed to fetch"
  in the readings card. First loads that failed (modes, autostart, priority,
  frame rate) run again quietly once it answers; the process list refreshes.
- A second click on a mode name while one is still being applied is ignored
  (two helper runs used to start).
- API: a body of `1e999` or `NaN` on any POST was a 500 (FastAPI echoes the
  value and cannot write it as JSON); a `RequestValidationError` handler now
  answers 422 naming the field without the value. `/api/processes?limit=-1`
  listed every process; the limit is kept to 1-100.
- Looks: thin themed scrollbars (`::-webkit-scrollbar`, the hub runs
  WebKitGTK).
- Tests: 145 pass (139 + 6 in `tests/test_api_errors.py`; the 422 cases
  were 500s before, seen on the old code). black, pyright 0 errors on
  `web_app.py` and the new test. httpx added to the venv for `TestClient`.

**Verified** in headless Chrome on a scratch copy (port 9070, temp HOME and
hub folder, so no real settings were written): shown 5 s 11 fetches; hidden
10 s 0 fetches, 0 rAF, 0 timers; shown again 4 fetches at once. Server
killed: API calls at 2 s and 12 s in 30 s, strip shown; restarted: strip gone
and readings back within 1 s of the next try. API failing for the first 6 s
of a page load: slider, autostart list and readings all filled in by
themselves afterwards, no page errors. Screenshots at 760/1100/1500/1920
looked at (`/tmp/u1/G17/shots/`).
**Not verified:** inside the real Forge window. The page change reaches
Forge on the next reload of Power; the `web_app.py` change only on Emerson's
next Forge restart. No mode was applied during testing.

**Critic follow-up** (same day): a second mode clicked while one was being
applied left the slider on a mode that was never applied, and arrow keys on
the slider did the same; the slider and the mode buttons are now disabled
until the apply finishes. With the server away at page load, the Mode card
and a toast still showed a red "Failed to fetch" next to the calm strip; a
network failure on the first loads is now left to the strip. **Verified** in
headless Chrome (port 9070, mode POSTs answered inside the page, nothing
applied): Battery saver then Auto clicked: one POST, slider and label both
on Battery saver; keyboard during an apply: no extra POST, slider matches.
API failing 6 s at load: strip only, no red text, filled itself in.
145 tests pass.

## 2026-09-27 Frame rate on battery (ejb-d1, #199)

- The Frame rate card has a second slider, "On battery" (setting
  `battery_fps`, default 30, 1-60). `/api/fps` GET returns `battery_fps`;
  POST takes either field alone (`FpsBody` fields are optional) and saves
  only what was sent.
- The hub applies min(max_fps, battery_fps) while `stats.plugged` is false
  (forge.py reads the Mains supply's `online`), and the desktop particles do
  the same. 60 means no cap on battery either.
- Verified: 138 tests pass, the hub harness passes 9/9, and the card was
  screenshotted on a spare port (8941). Not verified: the switch while
  actually unplugged.

## 2026-09-24 Battery saver mode (session 52)

Emerson asked for "a very serious battery saver mode". Added:
- `modes/saver.json` ("Battery saver", first on the slider): turbo off, CPU capped at 1.2 GHz, iGPU capped at 600 MHz, firmware `quiet`, keyboard backlight off, USB autosuspend (HID devices skipped), PCI runtime PM, disk writeback every 60 s, Wi-Fi/audio power save, 48 Hz. Wattage limits untouched.
- Helper settings `gpu_max_freq_mhz` ("max" or 100-2000, "max" = gt_RP0), `kbd_backlight` (0-3, clamped to the LED's max), `usb_autosuspend` (flag; mice/keyboards, interface class 03, stay awake). Cool/Auto/Performance now set `gpu_max_freq_mhz: "max"` so leaving saver lifts the GPU cap. Installed to /usr/local/bin/forge-power.
- Optional mode block `background_tasks` {nice, efficiency_cores_only}: in saver the priority watcher puts Background-list tasks at nice 19 on CPUs 4-11 (from /sys/devices/cpu_atom/cpus) and gives them all CPUs back on leaving.
- Watcher no longer re-runs setpriority/ionice on processes already that nice (it used to spawn ionice for every match every 5 s, and failed forever after the slider was raised).
- `display_gnome.py`: 48/60 Hz switching on GNOME via Mutter DisplayConfig (system /usr/bin/python3, which has gi). `display.set_refresh` picks it when XDG_CURRENT_DESKTOP is GNOME and not Hyprland. Emerson is on GNOME at the moment.
- Auto-switch turned on: battery -> saver, charger -> performance. GNOME indexer set not to index on battery (`gsettings ... index-on-battery false`).

Verified on the real machine (on the charger, other sessions' ffmpeg/python running): saver applied 14/14 settings and 48 Hz; read-backs matched (no_turbo 1, 1.2 GHz, epp power, quiet, GPU 600, kbd 0); background tasks at nice 19 with affinity 4-11. Package watts A/B twice: performance 16.06 / 16.28 W, saver 5.74 / 5.74 W. Performance re-applied 11/11 at 60 Hz, GPU back to 1200. 134 tests pass. Screenshot checked.
Not verified: battery draw per mode while unplugged, and the unplug -> saver switch itself (both need the charger pulled).

Notes: power-profiles-daemon is also running (GNOME's own power menu); it reported "performance" throughout and did not override anything during the test, but picking a profile in GNOME's menu will overwrite EPP/platform_profile until the next Forge mode change. On AC, throttled's `HWP_Mode: True` can briefly show EPP as a raw number (32) right after throttled restarts; that setting is Emerson's and was left alone.

Improve next: 1) measure real battery watts per mode unplugged; 2) decide whether to hand GNOME's power menu over to Forge (mask power-profiles-daemon) so the two can't disagree; 3) optional screen dimming in saver (brightness was already 1% when checked, so skipped).

## 2026-09-24 Background tasks now come filled in (session 51)

The card only ever held `claude` and its watcher unit had never been installed, so it did nothing. Now:
- `background_presets.json`: 7 groups, 45 patterns of common annoying background tasks (indexers, thumbnailers, store/update checkers, mail/calendar/account sync, cloud sync, housekeeping helpers, Steam/browser helpers). New configs get them by default; the card shows a "Suggested" list for any not yet added.
- `all_processes()` now lists only the user's own processes (root ones always failed to renice).
- Emerson's live config got all 45 added; `forge-power-priority.service` installed and enabled.

Verified: 112 tests pass; on the real machine 20 processes (evolution-*, goa-*, gvfs volume monitors, bazaar-daemon/dl workers, gsd-housekeeping…) went to nice 6 within one cycle while gsd-media-keys, gvfsd-fuse, Hyprland and firefox stayed at 0; screenshot of the Suggested section checked. Not checked: clicking the Add buttons in a browser (the save route they call was exercised directly).

Improve next: 1) show which listed patterns match a running process right now, so dead patterns are visible; 2) the watcher logs a failure every 5 s if the slider is moved to a *less* nice value than a process already has (unprivileged renice can't go back up) — skip or explain that case.

## 2026-09-20 (hub-wide pass, session 47)

The page polls status and history every 5 s while Power is the app on screen and every 30 s otherwise (`window.ForgeVisible`, from `/shared/forge_chrome.js`). Backend untouched; 93 tests pass.

Approved plan: `/home/ejb/.claude/plans/structured-fluttering-quilt.md`. Parts of it were later changed at the user's direction. Those changes are listed below and take precedence over the plan.

## Sustained-power time window unlocked in Performance (2026-09-15)

Approved plan: `/home/ejb/.claude/plans/stateful-wiggling-metcalfe.md`.

The user was running CPU/GPU-heavy tasks that spiked to 55 W and then stepped
down. Cause: `/etc/throttled.conf`'s `PL1_Duration_s: 28` — after ~28 s at the
PL2 burst limit, `throttled` drops to the lower PL1 sustained limit (45 W
battery; AC was already 60/60 so unaffected there). The user has modified the
laptop's cooling and says it can sustain the higher wattage, and wanted
Performance mode to remove this window the way auto-cpufreq used to.

Added a new, separate setting — `pl1_duration_s` — to `forge_power.py`
(`RANGES`, 1–3600) and generalized `rewrite_throttled()` to take a dict of
overrides instead of fixed `pl1`/`pl2` args, so duration can be rewritten
without touching wattage. **This does not touch `pl1_watts`/`pl2_watts`**; the
existing guard test (`test_shipped_modes_keep_the_users_power_limits`) that
forbids shipped modes from rewriting those wattages is untouched and still
passes — the wattages stay hand-tuned by the user directly.

Performance mode sets `pl1_duration_s: 3600`. Cool and Auto explicitly set it
to `28` (the stock value), so switching modes is deterministic regardless of
what ran before, matching how every other setting in these files already
works.

**Verified live** (not just reasoned): before, `intel-rapl:0/constraint_0_time_window_us`
read ~28,000,000 (28 s). After the user reinstalled the updated
`/usr/local/bin/forge-power` (root-owned; I can't do this myself, needs an
interactive sudo password) and Performance mode was applied, it read
~4,093,640,704 (~4094 s). The hardware quantizes the requested 3600 s to its
nearest representable window rather than hitting it exactly, but the 28 s cap
is gone — a long task now holds the 55/60 W burst limit instead of stepping
down partway through. `throttled.conf` confirmed showing `PL1_Duration_s: 3600`
in both `[BATTERY]` and `[AC]`, wattages unchanged (45/55, 60/60).

Full test suite (71 tests, up from 66) passes, `black` made no changes to the
touched files, `pyright --pythonpath ./.venv/bin/python` reports 0 errors.

**Still to verify:** run the actual heavy workload again and watch
`forge-power measure` or `sensors` over several minutes to confirm sustained
package watts and temperatures hold up under the real load, not just the
short live check done here.

## Changes from the plan (user direction, 2026-09-14)

1. **Throttled limits are deliberate** (45 W / 55 W battery, 60 W AC). No shipped mode sets `pl1_watts` / `pl2_watts`, and a test enforces it.
2. **auto-cpufreq is removed.** The helper writes the governor and turbo directly.
3. **Cool caps frequency at 1.6 GHz** (`max_freq_mhz`).
4. **Extras the user picked:**
   - auto-switch on plug and unplug
   - screen refresh per mode
   - `Super + Alt + P` hotkey
   - 10-minute graph
   - crash-dump cleanup
   - package cache trimmed to 1 version
   - earlyoom plus zram
   - idle PCI devices may sleep
5. **PCIe link power (`aspm`) is removed from all shipped modes.** The firmware refuses changes ("Operation not permitted" in every mode). The helper still supports the setting.

## Installer: the user ran it

Checked afterwards:
- `/usr/local/bin/forge-power` is root-owned, and `sudo -n` works with no password.
- auto-cpufreq is removed, and its service is inactive.
- zram0 is 8 G.
- Crash dumps went from 3.9 GB to 1.5 MB.
- The pacman cache went from 4.3 GB to 3.0 GB.
- `i8kmon` is disabled.
- Auto mode was applied.

**earlyoom failed** (exit 13, start-limit-hit). The `--prefer` pattern contained "Isolated Web Co", and the unit's unquoted `$EARLYOOM_ARGS` split it at the spaces. `install.sh` now uses `Isolated.Web.Co`, and `earlyoom` run by hand with the corrected options starts and prints its thresholds. **The user must re-run `sudo bash ~/Forge/apps/power/helper/install.sh`** (every step checks before acting) to rewrite `/etc/default/earlyoom` and start it.

## Measured on the real hardware (charger plugged in, Firefox and other apps open)

CPU package watts come from `forge-power measure`. The score is the millions of loop iterations per second from a stdlib Python busy loop: one process pinned to CPU 0, or 12 processes. Each measurement lasted 8–10 s. The modes ran in the order Cool, Auto, Performance, so Performance started warmer.

| | Cool | Auto | Performance |
|---|---|---|---|
| Read back | powersave, turbo off, 1600/1600 MHz, epp power, fw cool | powersave, turbo on, 4400/3300 MHz, balance_performance, fw balanced | performance, turbo on, 4400/3300 MHz, epp performance, fw performance, 60.049 Hz |
| Light-use watts | 4.26 W | 6.31 W | 7.45 W |
| 1 core: score / watts | 18.1 / 5.61 W | 49.3 / 22.42 W | 49.0 / 23.56 W |
| 12 processes: score / watts | 195.5 / 32.43 W | 258.7 / 48.24 W | 253.1 / 48.80 W |
| Temperature after | 44 °C | 58 °C | 65 °C |

After removing `aspm`, Cool and Auto each applied 10 of 10 settings with none failed. There is no "before the app" measurement: the helper that reads package watts did not exist before the install, and battery draw can't be read on the charger.

## Verified earlier this session

- **Tests and lint:** `pytest tests -q` gives 66 passed, `black` is clean, and `pyright` reports 0 errors. Forge's discovery and CSS tests pass.
- **Screen refresh:** `hyprctl eval` works on the real panel. `hyprctl keyword` is rejected on this Lua-config Hyprland.
- **Hotkey:** registered (`modmask 72, key P`).
- **Watcher:** `forge-power-watch.service` is active (6.7 MB).
- **Page:** every route works on a running backend, and the headless Chrome screenshot renders.

## Still to verify

1. Re-run the installer, then check `systemctl is-active earlyoom`.
2. **Reasoned, not checked:** the Auto read-back showed 4400/3300 MHz after the 9999999 write, so lifting the cap works. That it keeps following a later turbo toggle is still unverified.
3. Turn auto-switch on, unplug the charger, and confirm the mode changes within 5 s.
4. Press `Super + Alt + P` with the helper installed, and check for the notification and the mode change.
5. Measure battery draw per mode while unplugged.
6. After the next login and reboot: the autostart switches and `forge-power-restore.service`.

## Speed and detail sync (ejb-e3, 2026-09-27, commit 01292cf)

- The mode slider follows changes this page did not make: the 5 s poll (while shown) re-reads `/api/modes`, so the auto-switch watcher on unplugging and `Super + Alt + P` move it. It is left alone while dragged or while a mode is applying.
- The two frame-rate sliders re-read `/api/fps` on the same poll and on the hub's theme message, so a change in Settings > Speed and detail shows here. The cap that applies now (plugged in or battery) is marked "In use now".
- **Verified:** `tests/browser/check_speed_detail.py` (real backends, sandbox HOME), 22 PASS; Power tests 138 passed.
- **Not verified live:** an actual unplug with the watcher on (the mode switch was faked at `/api/modes` in the check).
