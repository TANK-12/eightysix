# Power

A Forge app for this laptop (Dell Latitude 5430, i5-1245U). It gives you:

- **A slider** that switches between **Cool**, **Auto** and **Performance** in one click, with no password prompt.
- **Automatic switching** when the charger is plugged in or pulled out.
- **A hotkey** (`Super + Alt + P`) that steps through the modes.
- **A 10-minute graph** of temperature, battery draw and CPU speed.
- **On/off switches** for the programs that start at login.
- **A live list** of what is using the CPU.

Port **8440**. Forge finds it automatically from `forge_app.json`.

auto-cpufreq is **not used and is removed by the installer**. The user asked for it gone. Everything it did (forcing the governor, switching turbo) is done directly by the helper here.

## The modes

Each mode is one JSON file in `modes/`. The slider is built from whatever files are there.

| | Cool | Auto | Performance |
|---|---|---|---|
| governor | powersave | powersave (the CPU scales itself) | performance |
| turbo | off | on | on |
| frequency cap | 1600 MHz, every core | none | none |
| energy preference | power | balance_performance | performance |
| Dell firmware fan table | cool | balanced | performance |
| idle devices may sleep | yes | yes | left as they are |
| NMI watchdog | off | off | off |
| disk write-back | 15 s | 5 s | 5 s |
| audio / Wi-Fi power save | on / on | on / on | off / off |
| screen refresh | 48 Hz | left as it is | 60 Hz |
| sustained-power window | 28 s (stock) | 28 s (stock) | 3600 s (effectively unlocked) |

**Your throttled wattage limits are never changed by these modes.** They stay at 45 W sustained and 55 W burst on battery, and 60 W on AC. The values are deliberate, and a test fails if any shipped mode sets `pl1_watts` / `pl2_watts`. What Performance *does* change is `pl1_duration_s`, the window `throttled` averages over before stepping down from the burst limit to the sustained one — stretched to an hour so a long task can hold the burst wattage instead of dropping after 28 s. This assumes the laptop's cooling can take it; it does not raise or bypass the thermal trip temperature in `/etc/throttled.conf`.

### Adding or tuning a mode

Copy a file in `modes/` and change `name`, `label`, `order`, `description` and whichever settings you want. A setting you leave out is left untouched. The optional `"display": {"refresh_hz": N}` block (a whole number from 30 to 240) sets the laptop panel's refresh rate. It uses the panel's closest supported rate and skips anything the panel can't do.

The only settings the helper accepts:

| setting | allowed values |
|---|---|
| `governor` | `powersave`, `performance` |
| `turbo` | `on`, `off` |
| `max_freq_mhz` | whole number 400–5000, or `"max"` for no cap |
| `epp` | `default`, `performance`, `balance_performance`, `balance_power`, `power` |
| `platform_profile` | `cool`, `quiet`, `balanced`, `performance` |
| `pl1_watts` + `pl2_watts` | whole watts 5–55, set together, burst ≥ sustained. Rewrites `/etc/throttled.conf`. |
| `pl1_duration_s` | whole seconds 1–3600: the sustained-power averaging window before `throttled` steps down from burst to sustained. Rewrites `/etc/throttled.conf`. |
| `aspm` | `default`, `performance`, `powersave`, `powersupersave` |
| `pci_runtime_pm` | `auto` (idle devices may sleep), `on` (never sleep) |
| `nmi_watchdog`, `wifi_power_save` | `true` / `false` |
| `dirty_writeback_cs` | 100–6000 (hundredths of a second) |
| `audio_power_save` | 0–60 |

A mode file with anything else in it is refused, and the page shows which file is at fault.

## How switching works without a password

- The page, the hotkey and the auto-switch watcher all call `modes.apply_mode()`. It runs `sudo -n /usr/local/bin/forge-power apply --mode <name>` with the mode's settings on stdin, then sets the screen refresh through `hyprctl eval`. This Hyprland uses a Lua config, which rejects `hyprctl keyword`.
- `/usr/local/bin/forge-power` is a **root-owned copy** of `helper/forge_power.py`. `/etc/sudoers.d/forge-power` lets your user run that one file, and nothing else, without a password. The copy lives outside `~/Forge` on purpose: a passwordless rule on a file your user can edit would let any program running as you become root.
- The helper checks every value against the table above before changing anything, and never runs a shell. It never creates a missing system file; a missing control is reported as a failed setting.
- The last mode applied is saved to `/var/lib/forge-power/last.json`. `forge-power-restore.service` re-applies it at boot. The screen refresh is not restored at boot; your `~/.config/hypr/monitors.lua` sets that.

**After editing `helper/forge_power.py`, re-run the installer.** The running copy is the installed one, not the file in this folder.

## Switch automatically

The "Switch automatically" card picks one mode for battery and one for the charger. The choice lives in `~/.config/forge-power/auto.json`.

`forge-power-watch.service` is a **user** service, so it needs no root and runs with Forge closed. It reads `/sys/class/power_supply/AC/online` every 5 seconds and applies the matching mode only when that value changes. While auto-switch is off it does nothing. Picking a mode with the slider is overridden at the next plug or unplug.

```
systemctl --user status forge-power-watch.service
systemctl --user disable --now forge-power-watch.service   # stop it entirely
```

## Background tasks

The "Background tasks" card lowers the CPU and disk priority (`nice`/`ionice`)
of processes matching a name pattern you add, so they lose out first under
contention, while patterns in "Protected" are never touched even if they'd
otherwise match. The list, and the how-much-lower slider, live in
`~/.config/forge-power/priority.json`. It ships with `claude` plus about 45
common background-task patterns pre-listed under Background (file indexers,
thumbnailers, app-store download workers, calendar/mail/account sync, cloud
sync, desktop housekeeping helpers). Those suggestions live in
`background_presets.json`, grouped with a one-line reason each; the card's
"Suggested" section offers any group not yet in your list, one at a time or
with "Add all". Adding a group is one new entry in that file. Only processes you
own are considered, since the unprivileged watcher cannot renice anyone
else's.

The user service is installed by copying `helper/forge-power-priority.service`
to `~/.config/systemd/user/` and running
`systemctl --user enable --now forge-power-priority.service`.

`forge-power-priority.service` is a **user** service, like the auto-switch
watcher, so it needs no root: lowering your own process's niceness doesn't
require privilege. It reads the config fresh every 5 seconds and reapplies it,
so a new process matching a pattern (e.g. a fresh Claude Code session) gets
picked up without restarting anything, and an edit from the page takes effect
on its own without waiting for the watcher.

```
systemctl --user status forge-power-priority.service
systemctl --user disable --now forge-power-priority.service   # stop it entirely
```

## Hotkey

`Super + Alt + P` runs `cycle.py`. It steps Cool → Auto → Performance → Cool and shows a notification. The bind line was added to `~/.config/hypr/custom/keybinds.lua`, so it also appears in the Keymap app. The file as it was before is in `~/Forge/backups/hypr-custom-keybinds.lua.pre-power`.

## Graph

While the backend is running, it takes a reading every 5 seconds: temperature, average CPU speed, laptop draw on battery, and the active mode. The last 120 readings (10 minutes) stay in memory. The three small charts share one crosshair and tooltip; arrow keys work too. "Show readings as a table" lists the same numbers. Battery draw only exists on battery, because the charger hides it.

## Install and undo

```
sudo bash ~/Forge/apps/power/helper/install.sh                 # everything below
sudo bash ~/Forge/apps/power/helper/install.sh --no-cleanup    # same, but leave the services alone
sudo bash ~/Forge/apps/power/helper/uninstall.sh               # remove the helper, rule, boot service, earlyoom/zram setup
sudo bash ~/Forge/apps/power/helper/uninstall.sh --restore-services   # also turn the cleaned-up services back on
```

The installer:

1. Installs the helper, the sudoers rule and the boot service.
2. **Removes auto-cpufreq** with plain `pacman -R`, not `-Rns`, so Python libraries other tools use stay installed. It also deletes its leftover override files in `/opt/auto-cpufreq`, unblocks `power-profiles-daemon` (auto-cpufreq's setup had masked it; it isn't installed, so nothing starts), and applies Auto mode so the CPU is back to normal.
3. Turns off services that do nothing useful here. They stay installed:
   - `i8kmon`: it crash-looped because its sensor doesn't exist on this model.
   - `pacman-init`: it re-initialised the package keyring on every boot.
   - `grub-btrfsd`: it failed because the disk isn't btrfs.
   - `choose-mirror`, `livecd-alsa-unmuter`, `livecd-talk`, `vboxservice`: Arch installer leftovers.
   - `ModemManager`: mobile broadband isn't used.
   - `NetworkManager-wait-online`: it only slowed boot.
   - `haveged`: not needed on modern kernels.

   Bluetooth, CUPS, Avahi, `lactd` and throttled are kept.
4. Clears crash dumps (3.9 GB, all from `llama-server`) and caps future ones at 500 MB.
5. Trims the package cache to the newest version of each installed package and drops cached files of uninstalled packages. The measured dry run freed about 1.35 GB.
6. Installs **zram-generator** (compressed swap in RAM, half of RAM up to 8 GB, no disk) and **earlyoom**.
   - earlyoom closes the biggest program at 4% free memory and 10% free swap, preferring `llama-server` and browser tabs and never touching Hyprland or the shell.
   - systemd-oomd was rejected: Firefox, Hyprland and the shell share one cgroup here, so it would close the whole desktop.

The uninstaller cannot give back deleted crash dumps or cached packages, and it does not reinstall auto-cpufreq (`sudo pacman -S auto-cpufreq`).

Backups made before any system change:
- `~/Forge/backups/throttled.conf.pre-power`
- `~/Forge/backups/enabled-services.pre-power.txt`, which lists the exact re-enable commands
- `~/Forge/backups/hypr-custom-keybinds.lua.pre-power`

## Starts at login

The switches list every `.desktop` file in `~/.config/autostart`. Off adds `Hidden=true`; on removes it. No root is needed. The change takes effect at the next login, and nothing that is already running is closed.

## Files

| file | what |
|---|---|
| `web_app.py` | Routes: `/api/modes`, `POST /api/modes/{name}`, `/api/status`, `/api/history`, `/api/watts`, `/api/processes`, `GET/POST /api/autoswitch`, `GET/POST /api/priority`, `/api/autostart`, `POST /api/autostart/{file}`; the 5-second sampler |
| `modes.py` | Loads and checks `modes/*.json`, calls the helper, sets the screen refresh |
| `helper/forge_power.py` | The root helper (source of the installed copy) |
| `helper/install.sh`, `helper/uninstall.sh` | One-time setup and undo |
| `helper/forge-power-restore.service` | Boot restore (system service) |
| `helper/forge-power-watch.service` | Auto-switch watcher (user service, copied to `~/.config/systemd/user/`) |
| `helper/forge-power-priority.service` | Background-task priority watcher (user service, copied to `~/.config/systemd/user/`) |
| `display.py` | Laptop panel refresh rate via `hyprctl eval` |
| `autoswitch.py`, `watch.py` | Auto-switch settings and the watcher loop |
| `priority.py`, `priority_watch.py`, `background_presets.json` | Background-task list, suggested patterns, matching and renice logic, and the watcher loop |
| `cycle.py` | The hotkey |
| `history.py` | The graph's rolling buffer |
| `status.py` | Password-free readings |
| `autostart.py` | The login switches |
| `static/index.html` | The page |
| `tests/` | `.venv/bin/python -m pytest tests -q` |

## Checks

```
cd ~/Forge/apps/power
.venv/bin/python -m pytest tests -q
F="helper/forge_power.py modes.py display.py autoswitch.py history.py cycle.py watch.py status.py autostart.py priority.py priority_watch.py web_app.py tests/*.py"
black --check $F && pyright --pythonpath ./.venv/bin/python $F
```

What is verified and what is still pending is tracked in `WIP.md`.

## Battery saver

`modes/saver.json` is the most frugal mode: turbo off, 1.2 GHz CPU cap, 600 MHz
graphics cap, firmware `quiet`, keyboard backlight off, USB and PCI devices
allowed to sleep (mice and keyboards excepted), disk writes batched each minute
and a 48 Hz screen. Its `background_tasks` block makes the priority watcher put
every Background-list task at nice 19 on the efficiency cores only. Measured on
the charger with the same apps open: 16 W package in Performance, 5.7 W in
Battery saver. Screen refresh switching works on Hyprland (`hyprctl`) and on
GNOME (`display_gnome.py`, via Mutter's D-Bus API).
