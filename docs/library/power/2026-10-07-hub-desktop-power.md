# Forge hub and desktop power: hidden, covered and busy (Relay task 60 + overhaul H3)

date: 2026-10-07 · for: both · by Yuzu (overhaul helper-3), finishing Relay task 60 started by Momo

## What Emerson asked

- "Forge desktop and hub keep using the GPU when they are hidden" (Relay task 60,
  WhatsApp 15:43: an app covering almost the whole screen, btop still shows the GPU busy).
- "more intelligent power on and off of GPU-using stuff" and "be smart with the
  fact that a lot of stuff is happening on GPU and CPU": one shared tier from
  plug, charge, visibility, other programs' GPU load and whole-machine CPU load.
- Keep the looks when visible, do not remove features.

## The rule now (one place: shared/forge_power.js)

| tier | when | what draws |
|---|---|---|
| full | plugged in or charged, visible, machine quiet | everything as set |
| reduced | other programs' GPU load (levels 1-3, forge_gpuload.py), whole-machine CPU busy (>= 70 % for 10 s, until < 50 % for 20 s), battery at the saver mark, or **less than 35 % of the window/screen showing** | Emerson's steps: visualiser off, half the particles, 25 fps (particles never under 20); mostly covered also caps frame rates at 15 (only a sliver shows) |
| paused | under 10 % showing, minimised, on another workspace, fully covered | nothing: the page is unmapped (forge.py / desktop/particles.py) |

`ForgePower.tier()` says why ("reduced: machine busy", "reduced: GPU busy",
"reduced: battery low", "reduced: mostly covered", "paused: hidden");
`values()/apply()` carry it as `power_tier`, which helper-6's particles,
widgets and 3D wallpaper read. The hub exposes `window.forgeTier()`.

How much shows comes from the Forge GNOME extension (it sees every window):
it writes `$XDG_RUNTIME_DIR/forge-desktop-under.json` with each desktop
screen's and each Forge process's visible share. Before this, the hub rested
only on GNOME's fully-obscured event (every pixel covered, about 4 s late) and
the desktop only under a maximised or full-screen window.

## Measurements (verified, scratch rig, same sitting, alternating runs)

Rig: a private headless GNOME Shell 51 (1920x1080 virtual monitor, own
runtime dir, dconf and session bus, /tmp/r60), the Forge extension (old copy
for "before", the repo copy for "after"), the real desktop/particles.py with
Emerson's settings, and the hub page in a window named Forge wired like
forge.py (Seen + watch_shell). Figures: that process's own render-engine busy %
and CPU % (DRM fdinfo, /proc), 8 s per phase. The machine was busy (Jan on
the GPU at about 64 %, other sessions; load average 5-7), so absolute numbers
float; compare within a row.

Hub web process, GPU render % / CPU %:

| case | before | after | change |
|---|---|---|---|
| window over 98 % of Forge, not maximised (Emerson's case) | 24.4 / 46.0 and 25.0 / 48.7 | 0.0 / 0.2 | GPU -100 %, CPU -100 % |
| window over 88 % (12 % shows), reduced tier | 24.0 / 43, 31.1 / 39 (median 27.6 / 41) | 20.2 / 26, 21.7 / 24 (median 21.0 / 25) | GPU -24 %, CPU -39 % |
| window over 35 % (65 % shows) | 25.9 / 64, 30.7 / 48 | 26.7 / 44, 29.3 / 45 | full tier, no change wanted |
| maximised window over it, minimised, other workspace | 0.0 | 0.0 | already paused before (B34) |
| visible, nothing over it | 29.9 / 57, 28.7 / 57 | 29.1 / 50, 27.8 / 43 | unchanged (looks kept) |

Desktop page (desktop/particles.py's web process):

| case | before | after | change |
|---|---|---|---|
| window over 98 % of the screen, not maximised | 17.3 / 31.1 | 0.0 / 0.2 | GPU -100 %, CPU -99 % |
| window over 88 %, reduced tier | 11.6 / 12, 14.4 / 14 | 15.3 / 11, 18.4 / 12 | no gain measurable in the noise |
| desktop fully showing | 17-28 | 17-28 | unchanged |

The reduced tier helps the hub but not measurably the desktop page: per
task 56 the cost here is each recomposited frame of a full-screen window,
and the desktop's widgets and clock still wake it. The paused tier is the
big win for both.

Live, Emerson's running Forge (old code, before any of this; Jan busy):
hub web process 17.8 % GPU / 55 % CPU at 19:49 and 24.1 % / 37.5 % at
20:21; his desktop page was resting (its screen counted as hidden).
**Live after: not measured** — it needs a Forge restart and a GNOME
log-out/in (the extension is loaded at login). Smoothness (frame times) and the
machine-busy tier were not measured: Umi (commander) stopped measuring runs
at 20:15; one proper test with Emerson (AC and unplugged) comes at the end,
and `tools/quiet_window.py` can freeze other sessions for it.

## Verified by tests

tests/test_power_tier.py (13): a sweep of 21 shares x 4 GPU levels x plug x
charge (the share only ever raises the level, fully shown is exactly the old
rule), tier reasons, the 15 fps covered cap, CpuBusy hysteresis (enter/leave
timing, spikes and dips reset, and a sweep of every load 0-100 % wobbling
0/5/15 points for 10 minutes: at most one change), GpuLoad reading a fake
/proc/stat, the extension file parsers, and the hub wiring. With
test_seen, test_forge_gpuload, test_desktop_*, test_speed_detail,
test_fullscreen and test_hub_*: 174 pass; test_hub_sliders fails the same
way before these edits (particle_fps default 30 vs 60, not this work).

## To take effect

Restart Forge (forge.py, forge_seen.py, forge_gpuload.py are Python) and log
out and in to GNOME (the extension). Until then the old behaviour runs.
Per the 2026-10-07 GPU doc, a restart may need `sudo pacman -Syu` first if
mesa and llvm-libs are still mismatched.
