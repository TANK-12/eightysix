# Eighty Six wave: who is doing what, and what is done

date: 2026-09-30 · for: Emerson

Plain-words status of every Claude session in the Juggernaut / Eighty Six wave. Each session adds a dated
line when it stops. Full detail lives in `~/Forge/sessions/juggernaut-alpha/results/` (A1.md, B1.md).
Watch live sessions in Forge › Relay › Live, or `~/.local/bin/relay status` in a terminal.

## The game (lane A1, account hey)
- **Part 1, Sora (stopped at your word, 2026-09-30).** Built the new Godot game `~/Games/eightysix`: 14 data
  registries, menus and settings, a test range with a stand-in walker. Tests: 27 passed, 7 failed.
- **Hub helper (done).** The Eighty Six tile in Forge (`apps/eightysix`, port 8464): 20 of 20 tests pass,
  screenshot checked. Wrote the Godot add-on shortlist; nothing installed, waiting for your pick.
- **Part 2, Yuna (running).** Fixed all 7 failing tests (now all green), built headless bot runs with
  screenshots (29 shots looked at, UI bugs fixed), export presets. Working on: the fps logger, then copying
  the Juggernaut model into the game.

## The Juggernaut model (lane B1, account default)
- **Part 1, Kenji (done 2026-09-29).** Fixed the cockpit shell (canopy and snout) and the gun's rear block;
  made the first game export (rig, colliders, sockets, motor figures).
- **Part 2, Kenji part 2 (done 2026-09-30).** Fixed the hip joints (they sat too low and too far in, and
  were too thin), rounded the rear block, built the back of the pod (cross tube and X-braced frame, with
  the gun's lifting ram on the tube), the left-side stack by the gun, the sensor dimples and the sub-arm
  hood. Game export v2 out; Godot loads it. Every fix has a check image in `model2/images/18-25`.
- **Part 3, Sakura (stopped 2026-09-30, Opus 5.5 xhigh).** Rebuilt the gun's receiver top to match the
  renders (round tubes on top, a middle block with a curved saddle under the sight, lower side plates,
  S-hooks, the hose on the right only and a strut on each side): milestones m30-m32, check images
  `model2/images/26-29`. Export v3 out for the game: a lighter copy at 130k triangles, colliders split into
  pieces, foot sole sockets and leg chains (Yuna's asks). Godot loads both files. Next: small shape fixes
  and a critic round (results/B1.md part 3).
- B1 part 3, second run (Sakura, Relay task 5, ~07:00): measured the small shape fixes, built nothing (meter 93%). Plans for the hood fin, rear block arch and sight housing are in results/B1.md; next: build them as m33.
- **B1 part 4, Sakura (Relay task 5, third run, 2026-09-30 10:41-~11:40).** Built m33-m35: the U-shaped cut at the foot of the gun's rear block, a round sight housing, a bent rod loop on each flank hood, and new feet (a crowned oval pad and a slimmer spike, from the blueprints). A critic round on m34 scored it 6.5/10 (report in `model2/critic/round8/`). Export v4 out from m35; Godot loads both files; v3 kept in `export/archive/v3_m32/`. Next: the legs as round tubes, the snout brow, the gun-mount arch, the dome's rear rim and grille (results/B1.md part 4).
- A Sonnet session (Relay task 4) ran for about 4 minutes by mistake. Stopped; it changed no files.

## Not started yet
A2 walking and physics, B2 Legion models, and the rest of the plan (`PLAN.md`, lanes table).
- **B1 part 5, Sakura (Relay task 5, fourth run, 2026-09-30 ~11:25-11:45).** Made the legs round tubes (m36, m37): grooved round shells, short knee plates, a slim shin tube fitted to the front blueprint. Export v5 out from m37 (mesh only; JSON same as v4; Godot loads both). New measuring tool `model2/legprof.py`. Next: the thigh's knee ram sits 19 U low, then snout brow, gun-mount arch, dome rear (results/B1.md part 5).
- **B3 part 1, Chihiro (2026-09-30, visible session, took over from Relay task 10 at Emerson's word).** Built the small map "Ashen valley" and the asset kit: 116/116 tests, screenshots in `images/097-small_map_check`. Low 75 fps (meets 60), Medium 36 (target 45), High 23 (target 30). Next: Medium frame rate and the town's look (results/B3.md).
- **B3 part 2, Chihiro (2026-09-30).** Fixed holes in the ground at a distance, grapple anchors on ruins that hung in the air, and the town's pale square; four close-up viewpoints. Medium frame rate still not proven at 45 (readings swing 31-45). Next: measure with the desktop idle, the wall at the map edge, bigger outcrops.
- **B4 part 1, Tetsu (ejb-f5, 2026-10-01, visible session, alongside A3 part 4-5).** Look pass: the grainy filter was the upscaler's sharpening (now off by default), ambient occlusion off on Medium and High (it cost 7-10 ms and didn't show), a warm low sun with valley fog and a film colour grade, worn paint on the Juggernaut, real-looking shrubs, mountains instead of a wall around the map, a town street with 21 ruins. Medium runs 50 fps (was 37). Then sound: 24 sounds made from recipes, placed in 3D, far shots heard late at the speed of sound, muffled behind hills, echo that changes in town; a listening page to keep or drop each one. Not done: music (asks you first), Legion sounds (with A4). results/B4.md.
- **B4 part 4, Rika/Tetsu (ejb-6f, 2026-10-02, visible session).** Dirt builds up on the Juggernaut over a sortie (running on dirt, hard landings, skids; Settings > Gameplay > Dirt builds up off washes it); measured live at 0.23 per km at a gallop; 210/210 tests. Rumble still waits for a pad. Then started B5, the big map (results/B5.md).
- **B5 part 1, Rika/Tetsu (ejb-6f, 2026-10-02).** The big map, Sector 86 frontier (4 km), streamed: fine ground with its own colliders built around every mech as you go; river, lake, fords, four towns. Walls and buildings now break under fire (real HE rounds checked) and collapse when their floors lose support. Free roam for now. results/B5.md.
- **A4 part 6, Sora (ejb-ef, 2026-10-02, visible session).** Your ask from track B: bigger 57 mm hits and hit dust, two sliders in Settings > Graphics > World detail > Combat effects (1.6x by default, look only; the default dart now throws dirt, HE gets a fireball). The wire-anchor arc shows as clear dots. Tests pass (test_combat_fx 5/5). Next: the Hangar screen (results/A4.md part 6).
