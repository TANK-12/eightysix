# L1: Model 1 side ammo boxes, then freeze Model 1
Start line: `Read ~/Forge/sessions/juggernaut-lanes/L1-model1-ammo-boxes.md and do it.`
Read first: `~/Models/juggernaut/MASTER-PLAN.md`, `v2/README.md` ("Scale and axes", "Files", the last two "Status" sections).

**Goal:** Emerson called Model 1's side ammo boxes the worst part. Rebuild them the way Model 2 did:
its flank bays became solid ammo boxes under the flank hoods (Model 2 milestone `mk2_m20_ammo_box.blend`,
code in `model2/parts_body.py`; read it, don't edit it). Then Model 1 is frozen as a variant.
1. Claim `~/Models/juggernaut/v2` on the board. Compare Model 2's box code and a render of it
   (`model2/images/09_ammo_box/`) with Model 1's flank parts in `v2/parts_body.py`.
2. Port the shape to Model 1 in `v2/parts_body.py`, keeping the `PARTS` registry pattern.
   Keep the boxes attached (no floating pieces) and clear of the legs in every clip.
3. Check headless: `cd v2; SKIP_CYCLE=1 SAVE=jg2_m20_ammo_box.blend blender -b jg2_m19_anime_motion.blend --python anim_checks.py`,
   then read `/tmp/jug/m18_report.json` (print check with no new floating pieces, slip, knee-ram
   overlap at least 80 U). Take small Workbench stills (front, side, 3/4) into `v2/images/61_*`.
4. Add "Status (Model 1, m20 ammo boxes, frozen)" to `v2/README.md`, marking what is verified.
   Tell Nagi (game export) and the print session (ejb-fc) the new file name, and update the L1
   line in MASTER-PLAN.md.
**Done when:** m20 is saved, the checks pass, the stills show the boxes, and the README says frozen.
## Result
(write here)
