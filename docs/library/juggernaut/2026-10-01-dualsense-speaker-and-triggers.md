# DualSense speaker, haptics and adaptive triggers in Eighty Six: what could work

date: 2026-10-01 · for: both · lane B4 (Tetsu, ejb-f5) · research only, as the plan asks

**Nothing here is verified.** No DualSense was connected on 2026-10-01 (none in `/dev/input/by-id`, PipeWire sinks
or paired Bluetooth devices), so this is reasoned from how the pieces work, to be checked with the pad in hand.
The game's rumble already works through Godot (`Input.start_joy_vibration`, `scripts/core/rumble.gd`, patterns in
`data/rumble.json`).

## What Godot 4.7 reaches
- **Rumble (the two classic motors): yes.** Already used. On a DualSense the "motors" are emulated by its voice-coil
  haptics, so it feels softer and buzzier than a DualShock.
- **Adaptive triggers: no, not from GDScript.** Trigger resistance is set by writing DualSense output reports. Godot
  exposes no call for that. Two ways round it:
  1. A small helper process that writes those reports straight to the pad's `/dev/hidraw*` node (needs a udev rule
     so the user can write to it). The game would tell the helper "trigger effect X" over a pipe. Hidraw allows
     several openers, so Godot keeps reading the pad as normal (reasoned, to check).
  2. A GDExtension around SDL3's `SDL_SendGamepadEffect` (SDL3 passes raw DualSense effect packets). More work, and it
     would be a second copy of SDL next to Godot's own joypad code.
  Candidate tool to try first, **not installed (needs your pick):** `dualsensectl` (Arch AUR, github.com/nowrep/dualsensectl),
  a CLI for lightbar, LEDs, microphone and speaker volume; check whether the current version also sets trigger effects.
- **Speaker and full haptics: USB only.** Plugged in by USB, the DualSense shows up as a sound card with 4 channels
  (1-2 the speaker/headset jack, 3-4 the two haptic actuators). Over Bluetooth that audio path is not available on
  Linux. Godot plays to one output device at a time (Settings > Audio > Output device), so sending a few sounds to
  the pad while the rest plays on the laptop needs a second output: a small helper that plays a sound file on the
  pad's sink when the game asks (reasoned), or Godot's audio routed through a PipeWire virtual device that splits
  channels (reasoned, fiddly).

## Suggested next steps (when the pad is plugged in)
1. `pactl list short sinks` with the pad on USB: confirm the 4-channel sink. Play a test tone on channels 3-4 to feel the haptics.
2. `ls -l /dev/hidraw*` and try one trigger effect from a tiny script (effect bytes from the SDL3 source's PS5 driver).
3. If both work, lane B6 or A6 can add a helper `tools/pad_helper.py` (stdlib only) and a `data/pad_effects.json`
   registry: trigger feel per weapon (the 57 mm trigger with a hard wall, the MG with a pulse) and speaker sounds
   (reload clunk, low ammo).
