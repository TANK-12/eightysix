# Exo Lab: fitted suit build (helper brief)

date: 2026-10-08 · for: Claude (a Relay helper session) · from Relay task 102

You build the fitted exoskeleton parts for Exo Lab (`~/Forge/apps/exolab`)
in Blender, headless. Read `apps/exolab/docs/2026-10-08-plan.md` sections 2,
8 and 12 first. An earlier helper for this was cut off before it saved any
output; only `~/Models/exolab/vrm_body.py` survives (it reads the VRM 0.x body
mesh, positions, triangles and skin weights, into numpy in the page's body
frame). Reuse it if it helps.

## What to make

Two GLBs plus a sidecar JSON each, in `apps/exolab/static/assets/suits/`:

- `exo_full.glb` / `exo_full.json`: every shell in `data/models/exo_full.json`
  (`shells[]`: chest, back, abdomen, pelvis, pauldron, upper_arm_shell,
  gauntlet, hand_guard, thigh_shell, shin_shell, boot, helmet). `mirror: true`
  means a left and a right copy. Cuffs (`cuffs[]`) as thin bands too.
- `exo_lite.glb` / `exo_lite.json`: the shells and cuffs in
  `data/models/exo_lite.json` (back_plate, hip_belt, thigh_cuff, shin_cuff,
  foot_stirrup, plus upper-arm and forearm cuffs). Separate parts with skin
  showing between them.
- Read `fit_gap_mm`, `thickness_mm` and cuff `width_mm`/`gap_mm`/`at` from the
  model JSON in the script; never hardcode them, so the physics and the mesh
  share one number.
- Do NOT model struts, gimbals, motors or links: the page draws the mechanism
  live from the physics layout data.

Character: `~/Forge/shared/assets/characters/hairsample_female` (CC0 VRoid,
VRM 0.x). No organic geometry built from code: shells come from the real body
surface (select faces by skin weight and cut planes, offset outward by the fit
gap, solidify to the thickness, bevel, add panel lines or seams). Look: cool
and close-fitting, sci-fi soldier; matte dark carbon (cfrp parts), light grey
nylon (pa12 parts), small emissive accent lines (one material slot each:
`carbon`, `nylon`, `polycarbonate`, `accent`). Budget about 60k triangles for
the full suit, 25k for the lite (Intel Iris Xe in a WebKit window).

Dress heads-up (from the cut-off helper, board note #1239): the character
wears a dress (flared skirt to y 0.63, bell sleeves; material
`F00_002_01_Tops_01_CLOTH`) and VRoid culled the torso skin under it. Fit arms
and legs to the real skin under the sleeves and skirt, the torso to the tight
bodice. The page will hide the Tops faces whose dominant joint is a skirt or
sleeve joint (`J_Sec_*Skirt*`, `*Sleeve*`) or an arm bone; record the exact
rule you found in the sidecar as `hide_rule`.

## Frame and naming (the page depends on this)

- Export each part in the **body frame at rest pose**: +X the character's
  left, +Y up, +Z forward, metres (VRM 0.x faces -Z in glTF; three-vrm's
  `VRMUtils.rotateVRM0` turns it, as `vrm_body.py` does).
- One mesh node per part and side, named `<shell id>` or `<shell id>_L` /
  `<shell id>_R`, with glTF node extras
  `{"part": "<shell id>", "bone": "<VRM humanoid bone>", "side": "L"|"R"|""}`.
  Bone names are VRM humanoid names: `upperChest`, `hips`, `spine`, `head`,
  `leftUpperArm`, `rightLowerArm`, `leftHand`, `leftUpperLeg`,
  `rightLowerLeg`, `leftFoot` and so on (the model JSON gives `UpperArm` +
  `mirror`, meaning `leftUpperArm` and `rightUpperArm`).
- The page attaches each node to its bone with `Object3D.attach` while the VRM
  is at rest, so world-space rest placement is all that matters.
- Sidecar `<model>.json`: `{"model", "character", "frame", "parts": [{"name",
  "part", "bone", "side", "area_m2" (outer surface), "tris"}], "hide_rule",
  "fit_check": {...}}`. `exolab/parts.py suit_sidecar()` already reads
  `parts[].part` and `area_m2` (summed over sides), so keep those keys.

## Where things go

- Build scripts: `~/Models/exolab/*.py` (run with `blender -b --python`).
- `.blend` saves: `~/Models/exolab/blends/` (new names, never overwrite).
- Check images: `~/Models/exolab/checks/` (Workbench, 640 px, front, side,
  back, three-quarter; look at them).
- Only these app paths are yours: `apps/exolab/static/assets/suits/**` and
  `apps/exolab/docs/2026-10-08-suits.md`. Claim them on the crew board (crew
  `forge`). Do not edit `apps/exolab/exolab/**`, `web_app.py`, other
  `static/` files or `WIP.md` (Relay task 102 owns those).
- Headless Blender only; do not drive Emerson's on-screen Blender.

## Checks (done when)

1. Both GLBs and sidecars exist; a numpy reader (no Blender) loads each GLB
   and prints node names, extras, triangle counts and bounding boxes.
2. Fit check against the skin at rest: per part, the minimum and median gap
   from the shell's inner surface to the body (expect about `fit_gap_mm`, no
   penetration), written into the sidecar's `fit_check`.
3. Sanity: the chest shell sits in front of the chest (+Z), `pauldron_L` at
   +X, the helmet around the head, boots under the feet.
4. Check images looked at; say what they show.
5. `apps/exolab/docs/2026-10-08-suits.md`: what was built, how, the numbers,
   what is verified and what is not, how to rebuild. Commit only your paths
   (`git add <paths>`), and post a short summary on the crew board to
   relay-102-work.
