# helper-3: scene (cast, extras, backgrounds, depth, cutouts, rigs, speakers)

Status: started 2026-09-17. Owned: `panelforge/scene/`, `panelforge/api/scene.py`,
`tests/test_scene_*`, this file.

## Done
- Read CONTRACTS, HANDOFF, foundation modules, forge_jan.
- Candidate models checked on Hugging Face (file lists and sizes read from the HF API).
- Jan is not running right now (`forge_jan.models()` returned `[]`), so the Jan
  mood step must fall back to rules.

## Priority order (commander, budget is tight)
1. scene.json per panel: characters (boxes, faces), saliency, mood/action, speed lines
2. depth maps  3. cast.json clustering + PUT rename/merge + speakers
4. cutouts + inpainted backgrounds  5. rigs, extras, props, SFX lettering

## Written so far (code exists)
- `scene/registry.py` (model list + cached sessions, env PANELFORGE_SCENE_MODELS=off)
- `scene/geom.py`, `scene/cluster.py` (average linkage + cannot-link, purity),
  `scene/speakers.py` (rules), `scene/rig.py` (rig boxes + facing),
  `scene/imaging.py` (saliency, speed lines, colour, grabcut, balloons, inpaint,
  heuristic depth), `scene/detectors.py` (YOLO person/face, anime-seg, CCIP, depth)
- tests: test_scene_cluster.py, test_scene_speakers.py, test_scene_rig.py

## Verified
- 17 unit tests pass (cluster sweep over 40 random worlds, tail-angle sweep,
  3000-shape rig invariant sweep).
- Face detector on every 3rd page (56 pages): 18 faces on 11 pages, all 14 crops
  looked at are real faces (precision good, recall low on this realistic style).
- Timings per 800x1280 page on CPU: face 0.3 s, anime-seg 1.5 s, depth 1.4 s.

## Models (downloaded 2026-09-17 via models.ensure, ~443 MB total)
| key | repo / file | size |
|---|---|---|
| person | deepghs/anime_person_detection person_detect_v1.3_s/model.onnx | 44.6 MB |
| face | deepghs/anime_face_detection face_detect_v1.4_s/model.onnx | 44.6 MB |
| seg | skytnt/anime-seg isnetis.onnx | 176 MB |
| ccip | deepghs/ccip_onnx ccip-caformer-24-randaug-pruned/model_feat.onnx | 150 MB |
| depth | onnx-community/depth-anything-v2-small onnx/model_int8.onnx | 27 MB |

## Next
Build scene package, tests, integration run on 30+ panels, contact sheets.

## Contract additions
(none yet)
