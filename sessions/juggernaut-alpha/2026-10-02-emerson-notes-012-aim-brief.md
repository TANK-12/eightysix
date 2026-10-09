# Brief: Emerson's notes after playing 012: aiming, first person, shell effects, MG lag
date: 2026-10-02 · for: Claude (next track-A session, hey account, Opus high) · written by Minato/Tetsu (ejb-42)

Start line: `Read ~/Forge/sessions/juggernaut-alpha/PLAN.md and this brief, then do it.` Work on version 013
(`~/Games/eightysix`, tree clean at e6ec8ef). Emerson's notes come first; save version 014 at the end.

## His notes (2026-10-02, after playing 012), close to his words
1. **Main gun aiming is bad in third person**, a bit better in first person (where you see less, as expected).
2. **The aim mark locks onto the hills.** "I don't want no lock-on, I want aim-at-mouse kind of stuff."
3. **The shell never lands where I was aiming.**
4. The **machine guns at least go where the body points**, but that mostly works in first person only; he thinks it
   does not work in third person.
5. **The first-person model is trash and its shadows are bad**; the guns look bad in first person.
6. **A landing shell makes nowhere near enough explosion**, so he can never tell where he hit. Wants: an **option for
   shell tracers**, and **HE makes big explosions**.
7. Wants **skidding** (shells skipping/ricocheting off the ground at shallow angles) and **better near-miss wind physics**
   (the blast/pressure of a shell passing close).
8. **MG rounds hitting the ground make smoke that causes huge lag spikes.**
9. (Earlier in the same chat) The Legion hit almost every shot. Answer given: by design they have spread, an aim cone
   and lead on smoothed velocity, but they aim at the target's exact centre of mass while they see it (no ranging or
   tracking error), and their spread (Ameise 4 mrad, Löwe 0.4 mrad) is tiny next to a 3-4 m Juggernaut. Offered:
   ranging and tracking error, an aim settling time after a target jinks, a Legion accuracy setting, and a bot that
   measures hit percentage per enemy per range. **He has not picked yet: ask him, or do the measurement first.**

10. **He could move and shoot the Juggernaut in the main menu.** Fixed 2026-10-02 (Minato): the menu/Hangar mech
    (`scripts/ui/hangar_stage.gd`) was built with `is_player` true; now false. Check in a bot run that the menu
    Juggernaut ignores keys.
11. **Sparks and smoke also appear at the map's spawn point** when he fires (main menu, test world, maybe other
    maps), as well as at the muzzle and the impact. Reasoned suspect: an effect (muzzle, casing, tracer or impact)
    placed before it is in the tree or at a default (0,0,0) position, e.g. `global_position` set on a node not yet
    added, or a projectile's first frame at the origin. Find it with a bot that fires once and lists every
    CPUParticles3D/Decal/OmniLight3D position.
12. **The 12.7 mm rounds often start outside the body** (muzzle placement off the sub-arm guns). Check
    `MechCombat.sub_muzzle_local()` against the model's sockets with a screenshot of tracers at the muzzles.
13. **In first person the teammates' models look broken ("cooked").** Strong lead (reasoned, not checked): every
    Juggernaut's `MechCombat._tag_mech_layer` puts the hull parts not in "cockpit_show" on
    `CombatFx.COCKPIT_SHELL_LAYER`, and the first-person camera culls that layer (`chase_camera.gd` cull_mask), so
    the *wingmen* lose those parts too, not only the player's own shell. Fix: tag only the player's mech, or give the
    player's shell its own layer. Check with a cockpit screenshot looking at Werewolf.
14. **His own muzzle flashes look super bad and weak** (57 mm and 12.7 mm, first person at least). `CombatFx.muzzle()`:
    make the flash, smoke and light read at real size from the cockpit and the chase camera, without a lag cost.
15. **Blades go horizontal in a slide**, maybe pointing along the direction of travel. Reasoned reading: the
    high-frequency blades on the sub-arms (`juggernaut_m2_blades`, and any loadout with blades) swing out level while
    skidding, like the anime's slide-and-cut. Ask him in one line if he means something else (e.g. the feet).
16. **Mouse wheel: zoom in, or "power of shot" so shells can arc.** Physics check first: the 57 mm fires at one muzzle
    velocity (a fixed charge), so the honest version of "power" is a **range setting**: the wheel sets a range and the
    body tilts up to the elevation that lobs the round there (HE over cover), with the mark showing the arc's landing
    point. Zoom is the other option (`zoom_optics` already exists, middle mouse). Offer both as a setting (wheel =
    zoom / range). In the field the wheel is free: squad selection only takes the wheel inside the Handler view.

17. **High priority: the Juggernaut falls through the map when damaged.** Reasoned suspects: a lost part or leg
    (`MechCombat._on_part_lost`, `DamageModel` detachable parts) removes or disables collision shapes so the body is
    left with too little hull collider, or the limp (`_limp`) drives the body down faster than Jolt's contact holds.
    Reproduce with a test that takes off each detachable part and each leg in turn on flat ground and on a slope and
    checks the body stays above the ground for 10 s; then fix.
18. **The camera often goes into the ground (and through Legion).** `scripts/camera/chase_camera.gd` has no
    collision: add a camera-to-target ray (world layer, plus a small sphere margin) that pulls the camera in front of
    terrain and buildings, and decide whether Legion bodies count (probably fade or pass rather than snap).

19. **Free roam:** he wants to go to any map with **no enemies** (a "Free roam" / "No Legion" choice when deploying,
    e.g. mission = none in Select map), and to **keep playing after beating every wave** (the win screen offers
    "Keep exploring" as well as Restart / Main menu; the map stays live with the squad).
20. **A zoom scope on the mouse wheel**, with its own HUD (optics view with range marks), to spot the Legion far
    off. This settles note 16: **wheel = zoom by default** (steps, e.g. 1x / 3x / 6x / 10x, the gunner's optics);
    the range-setting idea stays an option. `zoom_optics` (middle mouse) already exists: look at what it does and
    build the scope on it.

**Update (Emerson, after playing 013):** "v13 does have OK 3rd person main gun aiming, but could still be better;
it's fine." So notes 1-4 are a polish item for 013, not a rebuild: keep 013's aiming as the base, measure it with
the crosshair-landing bot first, and only change what the numbers show is off. Lower priority than the lag (note 8),
the menu/spawn-point effects (10-11) and the first-person fixes (13-14).

## How to read note 2-4 (reasoned; confirm with Emerson in one line if unsure)
The 57 mm stays **fixed to the body** (standing rule, PLAN notes 2026-09-30 and 2026-10-01: never any movement on
the 57 mm, no recoil lessening). "Aim at mouse" then means: the mouse/camera sets an **aim point in the world** (the
screen crosshair), and the body turns and tilts (yaw by leg torque, pitch by the existing body-tilt aim) to bring the
bore onto it, so the round lands where the crosshair was. Today the third-person crosshair and the bore line differ
(camera offset = parallax), and the main gun mark is the bore line's own impact point, which jumps along the terrain
("locks onto the hills"). Likely fix: a camera-aim mode where the crosshair is the target, the body servos to it
within its real turn/tilt rates, and a second small mark shows where the gun points now (converging on the
crosshair). The sub-arm 12.7 mm guns in "fixed" mode should use the same aim point in third person.
Check the existing aim modes first (`gameplay.aim_mode` rate/angle, `gameplay.sub_guns_aim`, `_pitch_aim` in
`scripts/mech/standin_mech.gd`, the reticle in `scripts/ui/combat_hud.gd`). Prove it with a bot: fire at marked
targets at 100/300/600 m in third and first person and report how far each round landed from the crosshair point.

## Effects (notes 6-8)
- Tracers: `scripts/combat/projectile.gd` already builds a tracer per round (`tracer_len_m`); add a setting
  (Graphics > World detail or Gameplay > HUD) to show 57 mm tracers big and bright, with a short trail.
- Impacts: `scripts/combat/combat_fx.gd` `impact()`, `fireball()`, `clods()`, scaled by the "Combat effects"
  sliders (A4 part 6, default 1.6x). Make APFSDS ground hits read clearly (dust column, flash) and HE much bigger,
  still physically sized from the round's `tnt_kg` (`scripts/combat/blast.gd`) with the slider as a look multiplier.
- Ricochet/skip: a real APFSDS or HE round skips off ground at shallow angles; decide by impact angle and ground
  hardness, keep the energy honest, test it.
- Near-miss: the passing shell's shock wave (`blast.gd` has the overpressure fit) as camera shake, sound crack and a
  small push only if the numbers say so; no invented forces.
- **MG ground-hit lag (start here, likely quick):** every hit calls `CombatFx.impact` which makes **new**
  `CPUParticles3D` nodes, a `Decal` and an `OmniLight3D` per round (`sparks`, `smoke`, `flash_light`); the 12.7 mm
  pair fires many rounds a second. Reasoned suspects: node churn, many lights at once, particle material setup.
  Measure first (a bot firing the sub-guns at the ground with `measure`, frame time p1 low), then pool the particle
  nodes or use one shared emitter per type, skip the light for small rounds, cap live decals.

## First person (note 5)
`gameplay.default_view` cockpit; `cockpit_show` parts list in mechs.json and `CombatFx.COCKPIT_SHELL_LAYER`
(A4 part 5). The near hull/gun pieces seen from inside look bad and their shadows are poor: look at it in screenshots
first (bot `a4p5_cockpit`), then improve what is in view (which parts show, materials, shadow settings for the
camera-near geometry). A proper cockpit is a later job; this is about the current view not looking broken.

## Done means
Each note answered in results/A4.md (or a new results file) with before/after numbers or screenshots; tests for the
aim math and the ricochet rule; full suite green; scoreboard row; version 014 saved with a "try this" note.
Also still open from A5: the scoreboard air-turn change (results/A5.md "Open").
