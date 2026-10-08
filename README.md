# Eighty Six

A physics-driven Juggernaut game, inspired by the anime *86 -Eighty Six-*. Built from scratch in Godot 4.

**Status: early alpha (0.1.1).** It is playable, but rough in places, and the project changes quickly.

You drive a four-legged, 5.4-tonne Juggernaut across rough ground and real-world terrain and fight the Legion
with a 57 mm gun, two 12.7 mm sub-arm guns, a wire anchor and a resonance blade. Everything that moves the
mech is physics: the legs, the motors, gun recoil and the wire all push it. Nothing is a canned animation.

> This is a non-commercial fan project. It is not affiliated with or endorsed by the creators or publishers
> of *86 -Eighty Six-*. The anime's soundtrack is not in this repository.

## Features

- **Procedural legs on real physics** (Jolt, 120 ticks a second). Walk, gallop at up to 70 km/h, slide, take
  charged jumps and flips, and stand back up after a fall.
- **Combat:** a 57 mm gun with AP, heavy AP and HE rounds, sub-arm guns, a resonance blade, ricochets, and
  real blast physics for HE.
- **Wire anchor:** fire it where you look, then swing, reel in, or abseil down cliffs.
- **Legion AI:** Ameise scouts, Grauwolf packs and the Löwe tank, with sight, hearing, flanking, and armour
  you can shoot apart part by part.
- **Your squad:** Spearhead wingmen flown by AI, which you order from the Handler view.
- **Extras:** cockpit and third-person views, photo mode, a Hangar showroom, a scored after-action card, and
  fully searchable settings. Every control can be rebound, and PS5 controllers are supported.

## Maps

| Map | What it is | Mission |
|---|---|---|
| Ashen valley | Hand-made 1 km valley with a ruined town and a river | First contact (three waves) |
| Sector 86 frontier | 4 km streamed frontier with four towns, a river bridge and buildings that break | Frontier sweep |
| Palouse grassland | Real place (USGS lidar), rolling wheat hills, 4 km | Free roam |
| Allegheny forest | Real place, about 100,000 firs on a misty morning, 4 km | Free roam |
| Brilon | Real Sauerland town (6,000 houses) on a gold evening, 2 km | Free roam |
| Test range and test benches | Flat ground for trying moves, and benches that read torque, power and heat | None |

## Running it from source

> **Heads up:** the Juggernaut and Legion 3D models (`assets/models/**/*.glb`) are **not in this repository
> yet**. A fresh clone imports cleanly, but the main menu fails to load the Juggernaut model. Until the models
> are published, a clone is mainly useful for reading the code.

You need **Godot 4.7.2** (the standard build, not .NET) and a GPU that can run Godot's Forward+ renderer
(Vulkan).

```sh
git clone https://github.com/TANK-12/eightysix.git
cd eightysix
godot --headless --path . --import   # first run: import the assets
godot --path .                       # play
godot -e --path .                    # or open it in the editor
```

The game starts from `scenes/boot.tscn`. Its settings are saved to Godot's user folder, not to the project.

## Controls

These are the defaults. You can rebind them under Settings > Controls.

| Action | Keyboard and mouse | PS5 controller |
|---|---|---|
| Walk / sidestep | W A S D | Left stick |
| Turn / aim (the gun is fixed to the body) | Mouse, or Q / E | Right stick |
| Run | Shift | L3 |
| Slide at speed, brake when slow | Ctrl | L2 |
| Jump (hold to charge) | Space | Cross |
| Crouch and brace / tuck in the air | C | Circle |
| Fire the 57 mm gun | Left mouse | R2 |
| Sub-arm guns | Right mouse | R1 |
| Resonance blade (hold to tune, release to strike) | X | Rebindable |
| Reload / next ammo type | R / T | Square / D-pad right |
| Wire anchor: fire or let go / reel in / pay out | F / G / B | L1 / D-pad up / D-pad down |
| Cockpit or third person / free look / zoom | V / Alt / mouse wheel | Triangle / R3 / D-pad left |
| Stand back up after a fall | U | Cross |
| Handler view (squad orders) | Tab, then 1-4 | Touchpad |
| Map / photo mode / pause | M / O / Esc | Create / pause menu / Options |

## Tests

The game has headless tests, one file per system, in `tests/test_*.gd`. Physics in the tests runs at the same
fixed 120 ticks a second as the game.

```sh
tools/run_tests.sh                 # everything (about 10 minutes)
tools/run_tests.sh test_hangar     # one area (matches by name)
python3 -m unittest discover -s tools/tests   # the Python tools
```

`tools/bot_run.sh <name>` plays a scripted run of the real game (the scripts are in `tools/bot/`) and saves
screenshots and measurements to `images/`.

## Exporting builds

Install the official Godot **4.7.2 export templates** first (Editor > Manage Export Templates). Then run:

```sh
tools/export.sh linux      # or windows, macos
```

Builds are written to `build/<platform>/`. Each platform is one entry in `tools/platforms.json`.

## Project layout

| Path | What is there |
|---|---|
| `scenes/`, `scripts/` | The game: core, mech, combat, AI, world, UI |
| `data/*.json` | Registries: missions, maps, music, weapons, tutorial steps and more |
| `assets/` | Textures, sounds, fonts, shaders, maps (sources in `assets/SOURCES.md`) |
| `tests/` | Headless Godot tests |
| `tools/` | Test runner, bot runs, builds and export, map and model tools |
| `DEVLOG.md` | The full development log, one dated entry per work session |
| `PLAYTEST.md` | The playtest guide: missions, tactics and settings worth knowing |

## Credits

- **Music** that ships with the game: "Heartbreaking", "Five Armies" and "Clash Defiant" by Kevin MacLeod
  (incompetech.com), licensed under
  [Creative Commons: By Attribution 4.0](http://creativecommons.org/licenses/by/4.0/). Players can also point the
  game at a folder of their own music.
- **Textures:** ambientCG and Poly Haven (CC0).
- **Real-world maps:** elevation from the U.S. Geological Survey (3DEP), and streets, buildings and land use from
  © OpenStreetMap contributors (ODbL).
- Every outside asset is listed with its source and licence in [`assets/SOURCES.md`](assets/SOURCES.md).
- Built with [Godot Engine](https://godotengine.org) and Jolt Physics.

## Licence

No licence has been chosen for the code yet, so for now all rights are reserved. The third-party assets above
keep their own licences.
