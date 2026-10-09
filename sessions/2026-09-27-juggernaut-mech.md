# Session: M1A4 Juggernaut mech build (2026-09-27, Emi / ejb-3d)

Project: `~/Models/juggernaut/` (README there is the detailed handoff).

## State (end of session, about 20:20)
- Milestones 1-3 saved (m3 is current). Rig, IK, knee rams, walk and idle clips done and
  checked in code (foot slip under 0.005 mm).
- Final renders running unattended (render_all.py, log in renders/render_log.txt); not
  yet looked at. Dry run passed.
- .glb exported; Godot test loads it and walks (parked by Emerson).
- Next session: refine toward refs/phu-high-poly-*.jpg, critic pass on the renders.
  Start line: ~/Models/juggernaut/NEW-SESSION-PROMPT.md.

## Emerson's directions this session
- Heavy renders only at the end, unattended (saved to memory).
- Shape should match Phu Huynh's model; textures later.
- He meant online assets when asking "asset or own build": offer the Sketchfab CC-BY mesh.
- Handoff should say: refine it to be much better and much closer to the pictures.

## Downloads
- Poly Haven CC0: blue_metal_plate (1k), meadow_2 HDRI (2k), leafy_grass (1k),
  grass_medium_01 (1k). Reference images into ~/Models/juggernaut/refs (about 4 MB).

## Follow-up (same session, stopped at 95% of the 5-hour window)
- mech-forge skill got a "Faster pipeline" section with this session's lessons.
- Wireframe image hunt: not found; leads tried and next leads in refs/SOURCES.md.
- To do for the pipeline in code (not started): add check-camera stills, the reference
  montage, the ortho overlay and the detached render launcher as forge.* helpers in
  ~/Forge/shared/bridges/blender/forge_studio.py with tests, so any model gets them.
