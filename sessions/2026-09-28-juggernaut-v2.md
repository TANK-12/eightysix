# Session: Juggernaut v2 rebuild from wireframe blueprints (2026-09-28, Mei / ejb-c4)

Project: `~/Models/juggernaut/v2/` (README there is the detailed handoff).

## Emerson's directions
- Use the wireframe set he found (`refs/OneDrive_2026-09-27/86 wire frame and print/`)
  as the main reference, then Phu Huynh's high-poly renders; brighten the dark
  wireframes (done: `bright/`).
- Brand new model, one-to-one, AAA geometry with bolts, nuts and internals; textures
  later. For games, physics simulation and one day a real build: correct front/back,
  proportions, real scale, real joint axes. Better rig bones.
- A very critical critic agent scores the model as the work goes. No heavy renders.
- RAM is fine; kill the Jan session only if it causes trouble (it did not).
- Two sessions on this are fine; he wants a great model at the end.

## State (session end)
- Calibration verified (bone guides land on the reference bone lines in all 4 views).
- Milestones: v2/jg2_m1_blockout, m2_critic1_fixes, m3_legs_pod (current).
- Critic: round 1 3/10, round 2 3.5/10, round 3 (legs only) 4/10; reports in
  v2/critic/roundN/report.md. Pod pass not yet critiqued.
- Rig verified in code: IK exact (ankles within 0.0012 mm in 5 test poses per leg), knee
  rams stay colinear (0.000 degrees) and inside their cylinders.
- All check images kept in v2/images/01..05 (Emerson wants them kept).
- Handoff for the next usage window: v2/NEW-SESSION-PROMPT.md (paste it); it asks for a
  critic after every part pass.
- Separate side session handoff: ~/Models/juggernaut/wire/START-PROMPT.md (an
  independent wire-mesh-faithful build, headless Blender, own folder).
- Emerson's other directions this session: keep every image; batch tool calls hard;
  run the critic more often; asked about max effort (answered: max helps the measuring
  work; the loop count matters more).

## Session 2 (2026-09-28, Daichi / ejb-b5)
- Emerson's directions:
  - The critic runs **only after large batches**, judging the whole model, and in the same
    round it also scores each section from close-up pairs (this corrected "after every part
    pass").
  - The black-and-white wireframe is gold; focus on parts and joints.
  - Materials should follow the reference look and the anime.
  - Work flat out until 95 percent, write the handoff there, and run on to 98 percent only
    to finish something already started.
  - Produce a set of renders next to the old images at handoff.
  - Answers to his questions went into a text file he asked for, opened on screen:
    `v2/notes/answers-2026-09-28.md`.
- Done:
  - Critic round 4 (4/10, whole model plus sections).
  - Legs rebuilt to the wireframe: roller-and-bowl foot, toothed hub caps, shells over dark
    tubes, knee ram stand-off.
  - Open flank bays, D-panels, pod lower side, eye lip.
  - Open-frame gun receiver with gears, a new muzzle and sensor, a mount saddle, and an
    elevation ram rigged on its own bones.
  - Procedural materials (worn white paint, gunmetal).
  - Viewport fix: thin rig bones, helper bones hidden.
  - `render_set.py`.
  - Milestones m4, m5 and m6. Details are in `v2/README.md` Status.
- Verified in code: gun ram and knee rams stay in line (0.000 degrees) across poses, with
  their rods inside the cylinders.
- Critic round 5: `v2/critic/round5/report.md` (if present). Handoff prompt:
  `v2/NEW-SESSION-PROMPT.md`.
- Session 2 end, at 90-95 percent usage:
  - Critic round 5 scored **4.5/10** (round 4: 4/10). Proportions 7.5, receiver 5.5, flanks
    4.5; the weakest areas are materials (3), the foot (3.5) and the knees (4).
  - A final batch after round 5 went into milestone `v2/jg2_m7_weathered.blend`: weathered
    materials v2, fine-knurl caps, magazine ladders and seams, eye rings removed.
  - Render set of m7: `v2/images/16_renders_handoff/`.
  - The foot pad was then rebuilt as a curved rectangle (checked against the top view): `v2/jg2_m8_foot_pad.blend`.
  - Next steps are in `v2/README.md`.

## Session 3 (2026-09-28, Mika / ejb-2a)
- Started from `v2/NEW-SESSION-PROMPT.md`. The work list came from README "Next steps"
  (critic round 5).
- Done (details are in `v2/README.md`, "Status (session 3)"):
  - ankle rebuilt (neck, knuckle, sleeve bearing, yoke, pin caps) and the corrugated hose loop;
  - dark knee drum, dark underside plates, shin ram in a channel, thigh collar rings;
  - flank side plate with a window and housing ring, bigger launcher and bore tube;
  - receiver gears measured off the blueprint, nozzle, domed rear drum, hump handle loop;
  - nose trim and dome bands, a bigger lens, canopy rim rail, raised D-panels, dart plates;
  - khaki weathered materials, and a dark reference-style render look.
- Milestone `v2/jg2_m9_ankle_receiver_materials.blend`. Images in `v2/images/18..25`.
- Critic round 6 scored **5/10** (round 5: 4.5). Its top fixes went into
  `v2/jg2_m10_critic6_fixes.blend`:
  - warm khaki paint with soft grime, and red glass lenses;
  - a one-piece ankle elbow and the crescent pad;
  - flank parts with no blueprint counterpart removed;
  - an octagonal collar and slanted sight on the receiver;
  - a 20 U U-handle, and the muzzle plate and strut.
- Verified in code: the foot pivots on the roller axis (within 0.0011 mm at plus and
  minus 15 degrees), and the knee IK stays within 0.002 mm.
- Render set of m10: `v2/images/28_renders_m10/` (dark reference-style studio).
- Emerson reminded me to keep working to 95 percent before handing off, so I kept going:
  the hip hub and clevis were shrunk to the blueprint's r 27 drum, and a pipe went under
  each hood. Final milestone `v2/jg2_m11_hip_drum.blend`, final render set
  `v2/images/30_renders_m11/`. The handoff was written at about 90 percent.
- Next steps are in `v2/README.md` (hips, gun mount, edge wear, flank leftovers, canopy
  hatch, then critic round 7).

## Session 4 (2026-09-28, Tetsu / ejb-hey)
- Emerson asked for: make it better, run the critic efficiently in one bulk round, render
  walking, running, jumping and more, better textures and materials, and cool pictures.
- Built:
  - knurled hip knuckles, and a banded thigh-root sleeve;
  - stepped double-layer receiver plates;
  - flank fixes and the muzzle lug;
  - rounder leg shells;
  - materials v4: a scanned micro surface from the shared Forge assets, Cycles edge
    wear, and height-masked grime.
- 7 animation clips (`v2/anim.py`: idle, walk, run, turn, strafe, jump, fire, with a
  muzzle flash). Planted feet stay within 0.005 mm (measured).
- Critic round 7 (bulk): **5.5/10** (round 6: 5). Its verified fixes went into
  `v2/jg2_m13_critic7_fixes.blend`. Its hip claim was checked and rejected.
- Later milestones, in order:
  - m14: rounded leg shells;
  - m15: floating parts attached, and the gun-mount side bracket from the blueprints;
  - **m16: the cheek-plate side fix** (knee caps were floating on one side and buried on
    the other). Current file: `v2/jg2_m16_lug_fix.blend`.
- Final job on m16 (`v2/render_final.sh`, detached):
  - `v2/images/48_action_m16/`;
  - `49_renders_m16_cycles/`;
  - `50_anim_m16/`.
- Everything, the STLs included, is also on the Desktop:
  `~/Desktop/Juggernaut/` (Renders/m16 lug fix, 3D printing/m16 lug fix, Reference pictures,
  What is where.txt). It is linked there automatically, one folder per model version.
- A print session (ejb-fc) builds STLs from these milestones in
  `~/Models/juggernaut/print/`.
- Next steps are in `v2/README.md`: grime cavity bake, round leg shells, gun mount,
  knee-ram lug, then critic round 8.


## Session 5 (2026-09-28, Tetsu)
- Emerson asked for: one more full round of refinement (m17), then a handoff carrying his
  new asks: internals (pistons, motors, cockpit, barrel, magazine and shells), a
  brainstorm of assets and parts around the model, anime research and anime-accurate
  walk/run/jump/fight clips, and a render of two Juggernauts fighting. Also: open the
  latest model in Blender for him, explain how to move the render camera (answered in
  chat), EEVEE renders of the current version from the m11 camera positions, and whether
  the magazine should have a front ladder (answered: the rear one is on the blueprint; the
  front one is unprovable, so it is now a switch, `MAG_LADDERS`).
- Built (details in `v2/README.md`, "Status (session 5)"):
  - rounded leg shells, with the underside plate hugging them;
  - knee-ram lug stand-off 54 to 38 U;
  - gear tooth wear, the cradle's 2x2-bolted plate;
  - the eye set back, canopy strap ends, pad seams.
- Found and fixed: `render_look.VIEWS` had been deleted, so the m16 final job never
  rendered its stills. It was restored from the session-4 transcript and matches the
  cameras saved in m16 exactly.
- Verified in code on m17: feet within 0.005 mm and ankles within 0.004 mm in all 7 clips;
  knee-ram rods at least 80.2 U inside their cylinders in every clip.
- Milestone `v2/jg2_m17_round_legs.blend`. Unattended renders: `v2/images/52` (m16 EEVEE,
  20 views), then m17 Cycles stills into `55_renders_m17_cycles` (chained; clips skipped because
  Emerson wants them reworked: the gun must stay with the body, and the gaits must match
  the anime).
- Next: `v2/NEW-SESSION-PROMPT.md` ("New asks", with questions for Emerson), then README
  "Next steps".
- Emerson added: the anime has several Juggernaut build variants (different side arms,
  blades and so on), so references that disagree show variants, not errors. Logged in
  `v2/NEW-SESSION-PROMPT.md` ("New asks" 5: a `VARIANTS` registry, critic briefing).
- Emerson chose rear-only magazine ladders; m17 was rebuilt and resaved with
  `MAG_LADDERS = ("rear",)` before its Cycles stills.
- Emerson set the reference rule: the OneDrive folder's 14 images are basically the only
  reference; others only for special cases. The next session starts with a full review
  against them and expects to redo a fair amount (`v2/NEW-SESSION-PROMPT.md`).
- Emerson's answers (internals scope, base model, liveries, anime clips he will record)
  are in `v2/NEW-SESSION-PROMPT.md`. Game and real-life ideas: `~/Models/juggernaut/IDEAS.md`.
- Long brainstorm for Emerson (game, Godot verdict, real-life calculations, build plan, questions): `~/Models/juggernaut/BRAINSTORM-2026-09-28.md`.

## 2026-09-28 night: split into Model 1 and Model 2 (Tsubaki, ejb-fd)
- Model 1 = v2/ at `jg2_m17_round_legs.blend` (mixed references). The job to finish it
  (gun-aim fix in the clips, small fixes, final render set, saved as m18+, headless
  only) is in `~/Models/juggernaut/v2/FINISH-MODEL-1-PROMPT.md`.
- Model 2 = `~/Models/juggernaut/model2/`, a copy of v2's code (no .blend files),
  reworked against the OneDrive images only. Milestones are `mk2_mNN_<tag>.blend` and
  Desktop folders `Model 2 - mNN <tag>`. It owns the on-screen Blender, the OneDrive
  review and the "New asks".
- Nagi (ejb-6b) exports m17 read-only to Godot; m17 is never overwritten.
- Model 1 finished (Sakura, ejb-f4): `v2/jg2_m18_final.blend`. Gun aim now turns the body (gun yaw +-3 degrees, 7-degree raise, limited by magazine ground clearance), hex boss clash fixed, knee-ram overlap back above 80 U, Desktop folders "Model 1 - ...". Final render set running detached (log /tmp/jug/final_job.log). Details: v2/README.md "Status (Model 1 final)".
- Model 2 session 1 (Tsubaki): m18 `mk2_m18_onedrive_batch1.blend`. Snout and eye moved
  forward to the OneDrive position, sub-arm beak shortened, receiver sides closed, rear
  ladder removed. The index of the set is `refs/ONEDRIVE-INDEX.md`. The next-session
  prompt is `model2/NEW-SESSION-PROMPT.md`.
- Then m19 `mk2_m19_sight_hump.blend`: sight is a tube on a curved yoke, rear hump narrowed
  (front and rear blueprints). Stopped at 63 percent usage with the handoff written.
- Next: brief `sessions/2026-09-28-S27-juggernaut-motion.md` (analyse Emerson's new anime cuts with `refs/anime-motion/cuts.py`, then put the motion into Model 1's clips as m19). The m18 render job is paused (SIGSTOP) at Emerson's request.

- 2026-09-28 late, Ren (ejb-24), S27: analysed Emerson episode cuts (ep 1/2/8/9 = c5-c8), ANALYSIS.md "Batch 2"; Model 1 clips rebuilt to match (walk, run, jump, new skid, old walk kept as creep) and saved as v2/jg2_m19_anime_motion.blend. Checks pass except a 6-micron marginal on the run ankle gap. Full render not run (waiting for CPU go-ahead).
