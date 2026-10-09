# L2: Model 2 critic round A (fix list against the blueprints and the anime, then fixes)
Start line: `Read ~/Forge/sessions/juggernaut-lanes/L2-model2-critic-a.md and do it.`
Read first: MASTER-PLAN.md, `model2/README.md`, `model2/ANIME-SHAPE-NOTES.md` (the brief at its end).
Coordinate with Riku (ejb-ec) on the board: model2/ has one owner at a time.

**Goal:** Emerson says "the angles and sizes of some parts feel off". Find them and fix them.
1. The **OneDrive blueprint set is the base shape** (`refs/OneDrive_2026-09-27/86 wire frame and print/`,
   readable copies in `bright/`). The anime is the second opinion. When they disagree, it's a
   variant: note it, don't "fix" toward the anime.
2. Make one sheet of Model 2 at the blueprint views (front, side, top, rear) overlaid on the
   blueprints, plus crops for each part: pod, eye, gun, mount, magazine, sub-arms, hips, thighs,
   knee rams, shins, feet. Score each part out of 10 and list every angle or size that's off,
   with numbers (degrees, mm).
3. Anime check: crop matching anime frames (`refs/anime-motion/cuts.py detail` or an ffmpeg crop;
   frames listed in ANIME-SHAPE-NOTES.md) and mark each difference "consistent" (two or more CG shots agree) or "one-off".
4. Fix the worst first, as a new milestone (`mk2_mNN_critic_a`), keeping the build's part registry.
   Re-score. Keep every image.
**Done when:** a scored fix list is in `model2/CRITIC-A.md`, the top fixes are in a new milestone, and the L2 line is updated.
## Result
2026-09-29 (Toru / ejb-48), partial: the blueprint half. Gun rebuilt from the blueprints
(m21) and the canopy rear reshaped (m22); honest pair cameras (`model2/camsolve.py`).
Scored fix list: `model2/CRITIC-A.md`. The anime check (step 3) is not done yet.
