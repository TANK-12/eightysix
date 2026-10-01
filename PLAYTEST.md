# Eighty Six: playtest guide

date: 2026-10-01 · for: Emerson · written by lane A4 part 2 (Kenji, relay-12)

## Launch

- **Forge hub:** the Eighty Six tile, **Play**. Or in a terminal: `~/Games/eightysix/tools/play.sh`
  (rebuilds first if the source changed, a few seconds). A saved version: `tools/play.sh --version NNN`
  (`python3 tools/builds.py list` shows each one's note).
- Main menu, **Deploy**: Ashen valley with its mission, **First contact**. The test range has no mission.

## The mission: First contact

1. **Two Ameise scouts** patrol the craters about 200 m ahead of where you start. When one sees you it calls
   every Legion unit within 600 m, then keeps 150-250 m away, circles and fires bursts at you.
2. **A Grauwolf pack (three)** comes in from the town, called in by the scouts, so it knows roughly where you
   are. The pack spreads to flank you, fires unguided rockets in pairs, then charges in for the blades.
3. **The last push:** a Löwe holds 180-500 m off and lets its 120 mm turret do the work (it lays the gun,
   ranges in, fires every 6 s; HE at a moving or far target, the dart at a still one), with two Grauwolf
   and an Ameise.

Clear all three waves to win. Lose your Juggernaut and it's over. Both end screens offer **Restart mission**
and **Main menu**. The objective and how many Legion are left show at the top left.

## Controls (defaults; rebind under Settings > Controls)

| What | Keyboard and mouse | PS5 pad |
|---|---|---|
| Walk / sidestep | W A S D | left stick |
| Turn the chassis (the gun is fixed to it) | mouse, or Q / E | right stick left-right |
| Tilt the body to aim up and down | mouse | right stick up-down |
| Run (also sideways and backwards) | Shift | L3 |
| Slide at speed, brake when slow | Ctrl | L2 |
| Jump (hold to charge) | Space | cross |
| Crouch and brace (during a charged jump: flip, about one turn with the stick fully pushed; in the air: tuck) | C | circle |
| Fire 57 mm gun | left mouse | R2 |
| Sub-arm guns | right mouse | R1 |
| Reload / next ammo type | R / T | square / d-pad right |
| Wire anchor fire, let go / reel in / pay out | F / G / B | L1 / d-pad up / d-pad down |
| Third person or cockpit / free look / optics zoom | V / Alt / middle mouse | triangle / R3 / d-pad left |
| Park: gun raised / lowered (only when you press it) | P | (rebind in Settings > Controls) |
| Photo mode (time freezes, orbit camera, F12 saves a picture) | O | (from the pause menu) |
| Pause | Esc | options |

## What to try

- **Don't stand still under the Löwe.** Its first round ranges in and the next lands. Keep moving and jink,
  because it leads your smoothed speed and a change of direction beats the lead. Its HE bursts shove you
  (about 1.1 m/s at 2 m, 0.5 m/s at 5 m, real blast physics). In the air the shove also spins you.
- **Break line of sight.** Ruins and ridges hide you from sight, but not from hearing: a 57 mm shot carries
  three times as far as a footstep. Units remember where they last saw or heard you.
- **The Löwe's hull is 240 mm,** past the 57 mm dart's 180. Flank it for the turret ring and the rear deck,
  or shoot its legs out at the knees.
- **Grauwolves:** shoot the rocket pod and it stops firing rockets. Shoot the optic and it sees a third as far.
- **Heavy AP (T to cycle):** more kick and more damage. Fire it in the air to dodge.
- Everything from earlier lanes still works: flips, the wire-anchor arc, sprint any way, the slide, photo mode.

## Settings worth knowing

- Settings > Gameplay > "Damage you take" scales Legion damage (0.25-2x) if the fights are too hard or too easy.
- Settings > Audio has the sound and music pages (lane B4).

## Your notes

Write them in `~/Games/eightysix/NOTES.md` (any form: one line per thing is fine), or tell any Claude
session "Eighty Six notes: ...". The next track-A session (A5) reads them first.
