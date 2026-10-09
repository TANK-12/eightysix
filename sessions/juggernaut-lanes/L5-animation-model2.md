# L5: Animation on Model 2, plus foot sparks and dust
Start line: `Read ~/Forge/sessions/juggernaut-lanes/L5-animation-model2.md and do it.`
Waits for L2 (a stable Model 2 rig). Read MASTER-PLAN.md, ANALYSIS.md "Batch 2" (and "Batch 3" if it exists), `v2/anim.py`.
1. Port the m19 clip set (idle, walk, creep, run, skid, turn, strafe, jump, fire; the `CLIPS`
   registry and named constants) to Model 2's rig. Model 2 can do what Model 1 couldn't: a
   **wide run splay** and the **40 deg parked gun** (add a `park` clip).
2. **Effects:** sparks and dust at the feet on run, skid and landing (as a registry of effects
   keyed to foot events, reusable in the game). Add the ambush crouch-and-rise (ep 2, c6 95-99 s),
   firing on the move, and about 1.75 s between shots.
3. Checks like `v2/anim_checks.py` (slip, ram overlap, clearances). Smoke render and mid-clip
   stills, then ask Emerson before any full render (one heavy render machine-wide).
Goal: the walk and run look like the anime. Emerson's complaint was that the old ones looked terrible.
## Result
(write here)
