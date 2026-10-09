# Exo Lab: game first pass (helper brief)

date: 2026-10-08 · for: Claude (a Relay helper session) · from Relay task 102

You build the first pass of the game half of Exo Lab (`~/Forge/apps/exolab`):
exo-suit soldiers after Call of Duty: Advanced Warfare's exo moves and
Crysis's nanosuit modes. Read `docs/2026-10-08-plan.md` sections 2, 7, 9 and
12 first, then `exolab/derive.py` (the stats you play with) and
`data/game/base.json`.

## What to make

`static/game.html` plus `static/game/*` (JS modules, CSS), in three.js r186
from `/shared/vendor/three/` with `@pixiv/three-vrm` 3.5.5 from
`/shared/vendor/three-vrm/` (import map naming `"three"` and
`"three/addons/"`; see `shared/vendor/*/SOURCE.md`). No new dependencies.

- Third person: the VRM character (`/characters/hairsample_female/HairSample_Female.vrm`,
  VRM 0.x: call `VRMUtils.rotateVRM0`; for VRM 0.x flip the x and z of every
  normalised-bone quaternion you set, as three-vrm's own mixamo example does)
  wearing the suit `static/assets/suits/<model>.glb` when it exists. The suit
  is being built now by Relay task #104; until it lands, play with the bare
  character. When it exists: read the sidecar `<model>.json`, attach each
  mesh node to the bone in its glTF extras (`extras.bone`) with
  `Object3D.attach` while the VRM is at rest, and hide the dress faces the
  sidecar's `hide_rule` names.
- Animation: idle, run, sprint, jump, fall, slide, punch from the Quaternius
  Universal Animation Library (CC0, `/shared/assets/animations/universal_animation_library/`,
  read its `manifest.json`), retargeted onto the VRM normalised bones in the
  page (mount the folder: you may add one `app.mount` line for
  `/animations` in `web_app.py` next to `/characters`, nothing else there).
  If retargeting fights you, procedural bone poses for the exo moves are fine
  for a first pass; say which in your doc.
- Moves: sprint (Shift), boost jump (Space again in the air), boost dash (Q
  or double-tap a direction), ground slam (Ctrl in the air), slide (Ctrl while
  sprinting), punch (left click), pick up and throw crates (E, then click).
- Suit modes, Crysis style, keys 1 to 4: Armour (damage taken x
  `armour_mode_damage_mult`), Strength (lift up to `strength_lift_kg`,
  `strength_throw_j`, `strength_punch_j`), Speed (`speed_mode_mps`), Cloak
  (translucent, enemies lose you). Each drains the energy bar at
  `energy.drain_w[mode]` watts; the bar holds `energy.bar_j`, recharges at
  `recharge_w` after `recharge_delay_s`; a boost costs `boost_j`.
- Stats: `GET /api/derive/<model>?profile=<name>` (shape in `exolab/derive.py`;
  `model` and `profile` come from the page URL, default `exo_full` and
  `baseline`). A crate heavier than `lift_kg` (Strength mode:
  `strength_lift_kg`) cannot be lifted; heavier than `break_kg` breaks the
  arms (show it). Keep a stub of the derive JSON in `static/game/stub.json`
  for when the API is down.
- First level: a test range. Poly Haven ground and props from
  `/shared/assets/polyhaven/` (look at what is there; mount it like the
  animations if you use it), a sky, an obstacle course with ledges that need
  the boost jump, crates of labelled weights (5 to 400 kg), targets and
  breakable walls to punch, a lap timer. HUD: energy bar, mode, speed, the
  derived stats in a corner (so Emerson sees his tester edits change the
  game). Escape opens a pause menu with "Back to Exo Lab" (link `/`).
- Light kinematic physics in the page (capsule against boxes, gravity
  9.81 m/s2, jump height and speeds from the derive JSON, not hand-tuned).
- Keep it light: Intel Iris Xe in a WebKit window. Target 60 fps at 1080p.

## Where things go

- Yours: `static/game.html`, `static/game/**`, new files in `data/game/`
  (never `data/game/base.json`, the physics core reads it), `docs/2026-10-08-game.md`
  (what you built, controls, what is verified versus reasoned), and the one
  mount line above. Claim them on the crew board (crew `forge`).
- Not yours: `static/index.html`, `static/tester*`, `static/editor*`,
  `static/app/**`, `static/assets/suits/**` (task #104), `exolab/**`,
  `tests/**`, `WIP.md`, `README.md`. The home menu's Game button (made by
  task 102) opens `game.html?model=<id>&profile=<name>`.

## Checks (done when)

1. `game.html?demo=1` runs a scripted input sequence (walk, sprint, boost
   jump, dash, slam, mode switch, lift a crate, punch) and sets
   `window.__exoDemo = {ok, checks: [...]}`: boost jump apex within 10% of
   `boost_jump_m`, sprint speed within 5% of `sprint_mps`, energy drains in a
   mode, a crate over `lift_kg` refuses to lift.
2. Headless Chrome through Flatpak (the `verify` skill) on a test server
   (port 8496, never Forge's 8466): screenshots of the game and the demo
   result, looked at. Save the check images under `~/Models/exolab/checks/game/`.
3. `black` and `pyright` on `web_app.py` if you touched it; the app's
   `tests/` still pass (`.venv/bin/python -m pytest -q`).
4. Commit only your paths (`git add <paths>`), message ending with the
   attribution lines. Post a board note to `relay-102-work` when done.
