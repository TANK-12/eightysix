# Why CPU and GPU rise and fall with Emerson's chats

date: 2026-10-07 · for: both · Relay task 71 (Kaede)

## What Emerson saw

In btop: "cpu and gpu go for a bit and then it stops, and then i ask something
and cpu and gpu usage goes back up".

## Short answer

The bursts are Forge's own window drawing while he is looking at it and using
it. When Forge is on screen it animates (particles, wallpaper parallax, the
music pulse); when it is covered by another window it rests (by design, B34).
Asking something means bringing Forge forward and moving the mouse over it, so
the drawing starts again. The model's thinking is remote and costs nothing
here; the local `claude` program of the panel is only 5-10% of one core.

What was waste: moving the mouse over Forge cost up to 78% of a core, because
every mouse frame changed a style value on the whole page. That is fixed (down
to 26%). The rest is the price of the looks he chose, mostly the particles.

## Measured live (verified), 22:37-22:49

Sampled every second from /proc (CPU per process) and the i915 driver's
per-process GPU counters (drm fdinfo). Read only; his Forge was not touched.
"% core" means percent of one CPU core.

- While he chatted in the Forge Claude panel (turns 22:38:25-22:40:38):
  hub page (WebKitWebProcess) 45-75% core and 16-42% GPU; forge.py 14-34%;
  gnome-shell 6-14%.
- Between messages, Forge still on screen: hub 20-37% core, GPU 3-8%.
- Forge covered (from 22:43): hub about 5% core, GPU 0. This is the "it stops".
- Panel `claude` CLI: 5-10% core.
- Whatsie (WhatsApp) renderer swings 3-90% of a core every ~20 s on its own.
  Not Forge; it adds to the up-and-down in btop.

## Measured on a private rig (verified)

A private copy of the real hub on a free port in a headless GNOME, with
Emerson's settings. Each phase about 30 s. Hub page CPU / GPU:

- Home as he has it: 19-20% core, 29-33% GPU, 59-60 fps.
- Particles off: 11% core, 4.5% GPU. Particles are the big steady GPU cost.
- Particles at 12 fps: 15% core, 19.5% GPU.
- Visualiser off, parallax off, glass flat: no further change (11% / 4.3%).
  Glass is not the multiplier.
- Panel busy dots: about +5% GPU. Panel streaming a reply: about +5% core.
  Small.
- Mouse moving over Forge, before the fix: 78% core, 37% GPU.
- Mouse moving, after the fix: 26% core, 37% GPU.
- Mouse moving with parallax off: 18% core.

## Fixes made (committed)

1. hub/index.html: parallax and pulse values are set on the eight layers that
   use them (MOVING_LAYERS + layerVars()), not on the page root. A value on
   the root is inherited by every element, so each mouse frame restyled the
   whole hub. 78% -> 26% of a core with the mouse moving. Browser harnesses
   hub_layers and hub_pulse have new checks for this and pass. Takes effect
   the next time Forge restarts or the hub reloads.
2. shared/forge_music.py: a cava (the system audio meter) that ignores the
   stop signal is now killed and waited for, so it no longer stays behind as
   a dead "[cava] <defunct>" child of forge.py. New test
   test_a_cava_that_ignores_term_is_killed_and_reaped (fails on the old code,
   21 passed with the fix). Needs a Forge restart to load.

The defunct WebKitWebProcess children of forge.py are harmless leftovers of
closed web views (no CPU, no memory); not changed.

## Left as follow-ups (not done)

- Particles: the biggest steady GPU cost (25 points of GPU). Options: draw
  the particle canvas at half resolution, or default it to 30 fps. Both change
  the look, so it is his call.
- Music Web Audio graph never suspends: about 4% of a core always, and an
  audio stream stays open. Suspending it risks silencing his music, so left.
- Whatsie: its renderer spikes on its own; outside Forge.
