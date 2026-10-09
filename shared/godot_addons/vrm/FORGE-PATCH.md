# Local patch for Godot 4.7

godot-vrm v2.1.0 does not compile on Godot 4.7.2: 4.7 made the
GLTFDocumentExtension hooks `_import_post` and `_export_post` return an
`Error`, and four overrides here ended without a return
("Parse Error: Not all code paths return a value").

Patched 2026-09-25 by adding `return OK` at the end of:

- `1.0/VRMC_springBone.gd` `_export_post`
- `1.0/VRMC_materials_mtoon.gd` `_import_post`
- `1.0/VRMC_materials_hdr_emissiveMultiplier.gd` `_import_post` and `_export_post`

The unpatched copy is in `~/Forge/backups/2026-09-25-blender-studio/godot-vrm-before-4.7-patch/`.
Drop this patch when upstream godot-vrm ships a 4.7-compatible release.
