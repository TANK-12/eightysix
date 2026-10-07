# Eighty Six: playtest guide

date: 2026-10-01 · for: Emerson · written by lane A4 part 2 (Kenji, relay-12); brought up to date for alpha 0.1
by lane A6 (Asuka, Relay 51) on 2026-10-07

## Launch

- **Forge hub:** the Eighty Six tile, **Play**. Or in a terminal: `~/Games/eightysix/tools/play.sh`
  (rebuilds first if the source changed, a few seconds). A saved version: `tools/play.sh --version NNN`
  (`python3 tools/builds.py list` shows each one's note).
- Main menu, **Deploy**: Ashen valley with its mission, **First contact**. **Select map** has the rest:

| Map | What it is | Mission |
|---|---|---|
| Ashen valley | hand-made 1 km valley, ruined town, river | First contact (below) |
| Sector 86 frontier | 4 km streamed frontier, four towns, the Ash river bridge, buildings that break | Frontier sweep: the last wave crosses the bridge, drop a span under it (HE on an orange-marked bearing) |
| Palouse grassland | real place (USGS lidar), rolling wheat hills, 4 km | free roam |
| Allegheny forest | real place, about 100,000 firs, misty morning, 4 km | free roam |
| Brilon | real Sauerland town (6,000 houses), gold evening, 2 km | free roam |
| Test range | flat ground with boulders and slabs | none |
| Test bench: flat pad / rough field | load a design and read torque, power, heat and failures | none (Settings > Gameplay > Physics > Physics mode: Test bench) |

- **Free roam + Keep exploring:** after a mission ends you can carry on walking the map.

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
| Resonance blade: hold to tune on a Legion unit at the blade tips, release to strike | X | (rebind in Settings > Controls) |
| Reload / next ammo type | R / T | square / d-pad right |
| Wire anchor fire, let go / reel in / pay out | F / G / B | L1 / d-pad up / d-pad down |
| Third person or cockpit / free look / optics zoom | V / Alt / middle mouse | triangle / R3 / d-pad left |
| Park: gun raised / lowered (only when you press it) | P | (rebind in Settings > Controls) |
| Stand back up when on its side or back (jump on the pad does it too while tipped) | U | cross (jump) |
| Photo mode (time freezes, orbit camera, F12 saves a picture) | O | (from the pause menu) |
| Optics zoom (1x to 10x) | mouse wheel or + / - | |
| Handler view (squad map, click to move or attack) / orders 1-4 | Tab / 1 2 3 4 | touchpad / d-pad |
| Map | M | create |
| Frame rate counter / screenshot | F3 / F12 | |
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
- **Your squad:** Settings > Gameplay > Squad sets how many Spearhead wingmen deploy with you (full physics
  Juggernauts with AI pilots). Tab opens the Handler view to order them.
- **The resonance blade (new):** walk up until a Legion unit is at the tips of the two forward blades and
  hold X. A ring fills over 1.2 s (yellow), turns green ("tuned, release") and holds for half a second;
  release then and the blades lunge in for up to 3x damage at 850 mm penetration, enough for a Löwe's front
  plate. Release early and it barely scratches; hold too long and the tune drifts back to half.
- **Final-kill cam (new):** the last Legion of a mission goes down in quarter-speed slow motion with the camera
  swinging round the wreck ("Final kill · Ameise · 451 m"). Enter or Escape skips it. Settings > Gameplay >
  Camera > Final kill cam.
- **Handler radio (new):** the Handler calls the waves (how many, what, which bearing), your kills and long
  shots, the parts you shoot off and what that does, the Löwe ranging you. Top left, typed out. Settings >
  Gameplay > HUD > Handler radio; text size under Accessibility > Subtitles.
- **After-action card (new):** the end card grades the sortie S to D (accuracy, armour left, time, parts shot
  off) and marks your personal bests per mission (score, time, accuracy, longest kill).
- **Shells you can see:** Settings > Graphics > World detail > Combat effects has the shell tracer and the size of
  hits and blasts. Shells ricochet off hard ground at a shallow angle and crack past you on a near miss.

## Settings worth knowing

- **Search (new):** type in the box at the top of Settings (Ctrl+F or / jumps there) and the page becomes the
  list of every setting and key binding that matches, each one working right there; "fog", "jump", "music",
  "squad". Click a "Section › Page" heading to open that page. Escape clears the box.
- **Your music folder (new):** Settings > Audio > Music > Your music folder picks a folder of your own mp3, ogg or
  wav files; set Main menu, Exploring or In combat to "Your music folder" to shuffle it. A copy of the game
  without the 86 soundtrack (the share zips) plays this folder instead, or, with no folder set, three free
  tracks by Kevin MacLeod that ship with the game (CC BY 4.0, credits in assets/SOURCES.md and HOW-TO-RUN.txt).
  Its music lists only offer tracks that are really there.
- Settings > Gameplay > "Damage you take" scales Legion damage (0.25-2x) if the fights are too hard or too easy.
- Settings > Audio has the sound and music pages: a pick and a level for every sound, and the soundtrack in order.
- Settings > Gameplay > Juggernaut: finish (field worn by default), emblem, dirt building up over a sortie, and
  the Legion livery (field worn, night, or the bare export).
- **Tutorial (new, a stub, off by default):** Settings > Gameplay > Menus and theme > Learning > Tutorial. Seven
  steps at the top of the screen (walk, gallop, jump, cockpit view, guns), one at a time. You decide whether it
  stays and what it should teach; the steps are entries in `data/tutorial.json`.
- Settings > Gameplay > Menus and theme: two themes (Handler console, Spearhead field kit) that switch live.

## Your notes

Write them in `~/Games/eightysix/NOTES.md` (any form: one line per thing is fine), or tell any Claude
session "Eighty Six notes: ...". The next session reads them first.

Still waiting on you (from versions 014/015; nothing is built until you answer):
1. Legion accuracy: pick one: ranging/tracking error, aim settling time, a Legion accuracy setting, or measure
   their hit rate first.
2. "Blades go horizontal in a slide": the sub-arm blades swinging level through a slide like the anime's
   slide-and-cut, or something else?
3. Are the spawn-point sparks and the falling through the map gone since 014?
