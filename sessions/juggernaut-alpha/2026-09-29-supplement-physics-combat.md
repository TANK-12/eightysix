# Eighty Six 0.1 alpha: physics and combat supplement

date: 2026-09-29 · for: both (Emerson and every session in the juggernaut-alpha wave) · Emerson's details, written up by Tetsu

Read this alongside `PLAN.md`. **Where the two differ, this file wins.** Emerson's six points first (his
wording, tidied), then what each one changes, lane by lane.

## Emerson's six points

1. **Hitboxes are 1:1 with animation.** No invisible capsule colliders. Every leg segment, chassis part
   and weapon gets its own closely fitted collision shape. Because animation is procedural, moving a leg
   physically moves its hitbox. Dodging mid-air by contorting the mech, or charging a crouch-jump to
   shrink the target profile, is an intentional, supported mechanic.
2. **Mass comes from the rigid bodies; aiming is fixed.** The mech's mass comes strictly from the
   physical properties assigned to the model's rigid bodies (one per part). The 57 mm main gun and the
   sub-arms are hard-mounted facing forward, with no independent tracking. To aim, the player rotates the
   whole heavy chassis. So the anime skid (breaking traction) is not just visual: it is the main combat
   move for whipping the chassis and gun round onto flanking enemies.
3. **Airborne physics and charge jumping.** Zero air control: once the mech leaves the ground it is a
   ballistic rigid body, and its momentum carries fully into the jump. Firing the 57 mm mid-air applies a
   big reverse impulse, so recoil can "rocket dodge" or bend the trajectory. No tap-to-jump: holding
   jump makes the IK crouch and compresses the suspension; releasing it turns hold time, capped by the
   actuator limits, into an upward Jolt impulse.
4. **Supersonic wake and near-misses.** Heavy Legion shells (such as the Löwe's 120 mm) do more than
   direct damage. Each trails an Area3D cylinder standing in for the supersonic overpressure. If the wake
   clips the mech it applies a sideways physics impulse: a near-miss staggers the mech, makes the gait
   generator widen its stance, or spins the mech hard if it is in the air. The wake also pushes loose
   debris.
5. **Test bench reality against game mode.** Game mode: `tuning.json` "magic motors" with huge torque for
   the anime feel. Test bench mode: `parts.json` holds realistic figures for heavy electric linear
   actuators, which are painfully slow, draw huge current and overheat quickly. The point is the brutal
   engineering reality of a heavy walking tank moving under its own weight.
6. **Hardcore manual input mode.** `input.json` gets a hidden hardcore scheme (the "Steel Battalion /
   QWOP" layout): lifting each leg is its own key or trigger, and the mouse or right stick shifts the centre
   of mass by hand. The player has to rhythm-step and keep the centre of mass balanced or the mech tips over.

## What it changes, lane by lane

| Lane | Change |
|---|---|
| A1 | `parts.json` gives every part a mass (or density and volume) and its own collider entry; the mech's total mass and centre of mass are summed from its parts, never typed in. Each actuator carries both a game-mode motor (in `tuning.json`) and test-bench figures (force, speed, current, heat). `input.json` carries the hidden hardcore scheme (per-leg lift actions and centre-of-mass shift axes), off by default. The stand-in test mech is already built from per-part colliders, not one capsule. |
| A2 | Hold-to-charge jump: IK crouch while held, impulse on release from hold time capped by actuator limits. No air control at all. The skid is the combat turn, so it must be controllable and readable. Colliders ride on the procedural leg segments. A wake hit widens the stance or staggers. Hardcore mode drives the legs straight from the per-leg inputs. |
| A3 | The gun has **no** side-to-side traverse (this replaces `PLAN.md`'s "a small traverse at most"); sub-arms are fixed forward too. Mid-air recoil is a real impulse on the body. Damage lands on whichever part collider was hit. |
| A4 | Löwe 120 mm (and any heavy shell) trails the wake Area3D: sideways impulse, stagger, mid-air spin, pushes debris. |
| B1 | Collision shapes fitted per leg segment, chassis part and weapon (no capsules), each with its physical properties so the game can sum mass. |
| B2 | Same per-part colliders for the Legion (read as applying to every mech; the weak points are already named parts). |
| B5 | Debris and loose chunks react to shell wakes. |
| B6 | Test bench runs on the realistic linear-actuator figures from `parts.json`: slow, high current, heat and failure. |

Open with Emerson (asked 2026-09-29): does up/down aiming come only from the body tilting, or may the gun
elevate a little on its own? Default until he answers: the body tilts; the gun only does its raise at rest.
