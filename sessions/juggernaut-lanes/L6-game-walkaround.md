# L6: Game, first playable (walk around, great feel, analog controls)
Start line: `Read ~/Forge/sessions/juggernaut-lanes/L6-game-walkaround.md and do it.`
Read MASTER-PLAN.md, then `~/Games/juggernaut/README.md` (Nagi's verified list and next steps). Claim ~/Games/juggernaut.

**First playable = walk around, with far better animation than now.** Nothing else yet.
1. Re-export Model 1 m19 or later (`tools/export_model.py`). Map the new clips `creep` and `skid`,
   and retune speeds to the clips' real ones (walk 2.2 m/s, run 7 m/s, jump 3 m high and 8 m
   long; the game ran at 17 m/s against a guessed RUN_REF of 12).
2. **Controls, both first-class:** PS5-style gamepad and keyboard and mouse, through named
   input actions (so a custom controller later is just one more mapping). Analog is the point:
   stick deflection sets throttle continuously, with response curves and deadzones as settings.
   Keyboard gets a throttle that ramps.
3. **Hard to master, rewarding when you get it right:** mass and momentum, traction that breaks into
   the anime skid when you turn too hard at speed, jump charge by how long you hold, and a landing that punishes a bad angle.
   Tuning values live in one data file.
4. Feet should plant, not slide (procedural foot placement or root motion from the clips),
   with a third-person and a cockpit camera.
5. Verify by playing (godot-forge skill), with a short capture or screenshots; list what's
   verified in the game's README. Leave Star Citizen-level systems for later lanes (MASTER-PLAN L8).
## Result
(write here)
