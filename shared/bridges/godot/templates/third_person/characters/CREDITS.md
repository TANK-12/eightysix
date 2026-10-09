# Characters and animations (copied in by godot_new_project)

- `HairSample_Female.vrm`: VRoid Studio sample model by pixiv, CC0 1.0
  (listed CC0 at https://vroid.pixiv.help/hc/en-us/articles/4402614652569).
- `AnimationLibrary_Godot_Standard.gltf/.bin`: Universal Animation Library
  (free edition) by Quaternius, CC0 1.0 (https://quaternius.itch.io/universal-animation-library).
- `*.bonemap.tres` and the `.import` files: written by Forge's
  `shared/bridges/godot/humanoid.py`; they retarget both onto Godot's humanoid
  skeleton (%GeneralSkeleton) so the clips play on the model. To use another
  VRoid model, drop its .vrm here and run
  `python3 ~/Forge/shared/bridges/godot/humanoid.py <project> characters/<model>.vrm`.
