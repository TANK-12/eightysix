# GPU use of the hub and desktop, and the visualiser lag (Relay task 56)

date: 2026-10-07 · for: both

Emerson asked for three things: smoke in Eighty Six too costly (part 1), the
music visualiser trailing the music (part 2), and Forge and the desktop
using a lot of GPU (part 3). All three are done: parts 2 and 3 below, part
1 at the end (smoke costs 55-58 % less GPU, a heavy barrage runs 22 -> 37
fps).

Laptop: Intel Iris Xe (Alder Lake GT2), 1920x1080. The GPU clock floats
between 100 and 1200 MHz, so a bare "busy %" flatters a light load run at a
low clock. The figures below are "page at full clock": the page's render
busy time times the mean clock over 1200 MHz. That figure repeats within a
few points between runs; busy % alone jumped 19-60% for the same page.

## How it was measured (tools, all in ~/Forge/tools)

- `gpu_use.py [seconds]`: GPU render % and CPU % per process, from
  /proc/<pid>/fdinfo, no root needed.
- `web_gpu_bench.py --visible [--root DIR] [--levels] [--no-count] [--js ...]`:
  loads a page in WebKitGTK 4.1 full screen and measures its web process,
  the whole GPU's awake share (RC6) and the mean clock. `--root` points at a
  copy of the files from before a change, for an A/B in the same sitting.
  With the monitors off mutter draws at 10 fps, so wake them first.
- `vis_latency.py [--fps N --nr N]`: a silent PulseAudio null sink, cava on
  its monitor, tone bursts in; times sound to half height for cava alone and
  for cava plus the old and new page easing. The sink is removed after.

Environment note: on 2026-10-07 mesa 26.2.2 needed libLLVM.so.22.1 but
llvm-libs was 23 (a partial upgrade on 2026-10-06), so any new GL process
fails ("Could not create default EGL display"), a restarted Forge included.
The benches ran with libLLVM 22 from the pacman cache in /tmp. Fix:
`sudo pacman -Syu` (the repo has mesa 26.2.4).

## Part 3: why the hub used so much GPU (verified)

- The running Forge hub web process: 52.7% GPU render with the screen on
  (gpu_use.py, 10 s). The desktop particles page: about 3.5% at full clock.
  The hub is the hog; the desktop page is not.
- No single layer is the cost. Any change on screen makes WebKitGTK
  recomposite the whole hub (wallpaper, depth canvas, particles, glass), and
  one such frame costs a lot on this GPU. A 3 px spinning square alone kept
  the full hub at about 15-20% at full clock. Hiding layer groups one at a
  time took a few points each; the wallpaper group the most (about 7).
- So the cost is the frame rate. Smooth CSS animations were forcing 60
  frames a second all the time: the clock's shimmer (11 s, infinite), the
  breathing widget's orb (in the default widget set), the zen clock's
  shimmer while zen mode was hidden (opacity 0 still animates), and the
  background-mode Ken Burns drift on the full-screen wallpaper. The 3D
  depth wallpaper's slow drift ran its full-screen ray walk at 60 fps for
  movement under a pixel a frame, and the visualiser redrew its full-screen
  canvas 60 times a second in silence.
- WebKit honours `steps()`: it sleeps between steps. Measured with nothing
  else moving: clock shimmer 25% -> 8.5%, breathing orb 19.6% -> 2.9%.

### What changed

- hub/index.html: clock shimmer `steps(66)` (12 a second); home and zen
  animations paused while those screens are hidden (in an app, zen,
  background mode); background-mode drift in `steps()` at 6 a second.
- shared/forge_widgets.css: breathing orb `steps(48)` (12 a second).
- shared/forge_depth.js: the drift alone draws at 24 fps (`DRIFT_FPS`);
  the pointer and the beat still draw at full rate and wake it at once.
- Visualiser (hub and desktop): in silence, a style that looks the same
  every frame (bars, ring, wave, mirror, not rainbow) redraws 10 times a
  second instead of 60, and the first sound wakes it at once.

### Before and after (verified, same sitting, alternating runs)

Hub as loaded with Emerson's settings (particles 25 fps, bars visualiser,
3D wallpaper on), no frame counter, page at full clock:

- home screen: 34.3% and 31.4% before; 18.4% and 18.1% after (about -45%).
  Web process CPU 42-49% -> 30-31%.
- background mode (Ambient.toggle): 24.5% and 26.0% before; 12.8% and
  12.0% after (about -50%).
- after, with the 3D drift off: 13.5%; with particles off: 13.3%. Those two
  are what still draws now; each is a setting Emerson already has.
- desktop particles page: 3.1-4.0% before and 3.1-3.6% after (no change; it
  was already cheap).

## Part 2: the visualiser lag (verified for the cava and easing part)

Sources found, in order of size:

1. cava's `noise_reduction = 77` (its default) at 30 fps held each level
   back by roughly 70-100 ms.
2. The pages then eased the bars a fixed 35% per frame (two or three frames
   to reach half height), and the music-path analyser had
   `smoothingTimeConstant 0.8` on top.
3. The hub asked cava for 30 levels a second.

The output device's own delay works the other way (the monitor gets the
sound before the speakers play it), so it does not add lag.

Fix: cava `noise_reduction = 30` (the Alt+V pulse keeps 15), the hub asks 60
levels a second, the analyser smoothing is 0.5, and both pages ease with
`ForgeVisual.follow` (shared/forge_visual.js): a rise lands within a frame
and a fall eases out over about 0.16 s, the same at any frame rate.

vis_latency.py, median of 7 bursts, ms behind the raw sound on the monitor
(the rig's own playback buffer, about 330 ms, is taken off):

- before (30 fps, nr 77, old easing): 109 ms (156 ms in an earlier run of 5)
- after, hub (60 fps, nr 30, new easing): 77 ms
- after, desktop (40 fps, its setting, nr 30, new easing): 76 ms

Not measured: the last step from canvas to the screen (WebKit compositing,
about one frame). Watching it with music is the check left for Emerson.

## To take effect

Forge and the desktop particles have to restart (shared/forge_music.py is
Python, loaded once), and a restart needs the mesa fix above first. Never
restarted here.

## Part 1 (Eighty Six smoke): done (session 3, Momo)

The game Emerson calls "Alpha" is Eighty Six (~/Games/eightysix, alpha 0.1).
All shell, hit and wreck smoke goes through CombatFx.smoke_emitter
(scripts/combat/combat_fx.gd): big see-through quads (an HE hit at the
default 1.6x Hit dust makes about 72 puffs, 4-7 m across, alive 3-4.5 s).
On the Iris Xe the cost is fill: every layer is blended over every pixel it
covers. When the frame time climbs past 1/15 s the 120 Hz physics runs out
of its 8 steps a frame and the world itself slows down, which is the "slows
the simulation" Emerson saw.

Fix (look kept, simulation untouched):
- each cloud draws half the puffs it asks for (SMOKE_THIN 0.5), each 1.25x
  bigger and more opaque by the stacking rule (n puffs of alpha a cover
  1-(1-a)^n, so half as many need 1-(1-a)^2), capped at 0.95;
- past 260 live puffs in the scene (SMOKE_BUDGET), new clouds thin further,
  down to a quarter;
- smoke is lit per vertex instead of per pixel.

Bench: tools/bot/smoke_cost.json (test range, third person, an HE hit
10-30 m ahead every 0.5 s, then 5-16 m ahead with the camera in the
cloud), tools/bot_run.sh smoke_cost --preset=medium, 1920x1080, quiet GPU,
two runs each, old and new in the same sitting (images/613, 616 old;
619, 620 new). GPU ms per frame, and what the smoke adds over the empty
range in the same run:

- empty range: 14.5-18.9 ms (clock noise)
- barrage, old: 41.5 / 39.1 ms (+22.6 / +24.3), 21.7 / 23.2 fps
- barrage, new: 24.7 / 24.5 ms (+9.8 / +10.0), 37.0 / 37.3 fps
- in the cloud, old: 60.7 / 56.1 ms (+41.8 / +41.3), 16.1 / 17.0 fps
- in the cloud, new: 33.3 / 33.6 ms (+18.4 / +19.1), 27.3 / 27.1 fps
- main-thread CPU, barrage 8.3 -> 5.7 ms, in the cloud 10.7 -> 6.7 ms

So smoke costs 55-58 % less GPU, frames are 1.6-1.7x faster in a heavy
barrage, and the worst case stays well above the 15 fps where the world
slowed. Tried on the way (one run each): per-vertex alone, barrage 40 ->
35 ms and in the cloud no change (fill, not shading, is the cost); half
the puffs at 1.1x size, a thinner, patchier cloud; at 1.2x with a 200
budget, cheaper again (+7 / +14 ms) but visibly smaller clouds, so 1.25x
and 260 won. Screenshots side by side looked at: the new clouds read the
same, a touch lumpier up close.

Not done, on purpose: no new quality setting (the thinning helps every
preset, and Settings > Graphics > Combat effects > Hit dust already sizes
the smoke); no fixed_fps on the emitters (CPUParticles3D has no
interpolation in Godot 4.7, so 30 Hz updates would step, and the CPU was
never the bound). Bot runs need LD_LIBRARY_PATH=/tmp/r56-llvm22/usr/lib
until `sudo pacman -Syu` fixes mesa vs llvm-libs (the off-screen mutter
fails to start otherwise).

Tests: tests/test_smoke_cost.gd 4/4 (thinning keeps density, the budget,
live puffs counted in and out, per-vertex), test_combat_fx 12/12.
