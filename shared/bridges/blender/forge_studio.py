"""Look, asset, rigging, animation and export helpers for the Blender bridge.

Exposed to bridge code as forge.<name>. Every helper works headless
(blender -b) too, which is how tests/test_blender_studio.py checks them.

    forge.look("studio" | "toon" | "hdri:<polyhaven id or .hdr path>")
    forge.use_hdri(id_or_path, strength, rotation_deg)
    forge.import_asset(id_or_path)      -> new object names (glTF/glb/fbx/obj/vrm)
    forge.texture(obj, id, scale)        -> PBR material from Poly Haven maps
    forge.frame_camera(names, lens, yaw_deg, pitch_deg)
    forge.rig_human()                    -> Rigify human rig
    forge.keyframe(obj, frame, loc=, rot_deg=, scale=, bone=)
    forge.render_animation(path, start, end, percent)  -> .mp4
    forge.export_godot(path, names)      -> .glb for Godot
"""

from __future__ import annotations

import math
import os
import sys
from pathlib import Path

import bpy
from mathutils import Vector

SHARED = Path(__file__).resolve().parents[2]
if str(SHARED) not in sys.path:
    sys.path.insert(0, str(SHARED))


def _asset(id_or_path: str, res: str = "1k") -> dict:
    """A local file path, or a Poly Haven id fetched through forge_assets."""
    p = Path(os.path.expanduser(id_or_path))
    if p.exists():
        sibs = sorted(f.name for f in p.parent.iterdir() if f.is_file())
        return {"main": str(p), "dir": str(p.parent), "files": sibs}
    import forge_assets  # pyright: ignore[reportMissingImports]

    return forge_assets.get(id_or_path, res)


def _world_nodes():
    scene = bpy.context.scene
    if scene.world is None:
        scene.world = bpy.data.worlds.new("World")
    world = scene.world
    world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    nt.links.new(bg.outputs[0], out.inputs[0])
    return nt, bg


def use_hdri(
    id_or_path: str, strength: float = 1.0, rotation_deg: float = 0.0, res: str = "1k"
) -> str:
    """Light the scene with a 360-degree HDRI sky (Poly Haven id or .hdr/.exr path)."""
    a = _asset(id_or_path, res)
    nt, bg = _world_nodes()
    env = nt.nodes.new("ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(a["main"], check_existing=True)
    coord = nt.nodes.new("ShaderNodeTexCoord")
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.inputs["Rotation"].default_value[2] = math.radians(rotation_deg)
    nt.links.new(coord.outputs["Generated"], mapping.inputs[0])
    nt.links.new(mapping.outputs[0], env.inputs[0])
    nt.links.new(env.outputs[0], bg.inputs[0])
    bg.inputs[1].default_value = strength
    bpy.context.scene.view_settings.view_transform = "AgX"
    return a["main"]


def _new_objects(before: set) -> list[str]:
    return sorted(o.name for o in bpy.data.objects if o.name not in before)


def import_asset(id_or_path: str, res: str = "1k") -> list[str]:
    """Import a model (Poly Haven id, or a .gltf/.glb/.fbx/.obj/.vrm path).
    Returns the names of the new objects."""
    a = _asset(id_or_path, res)
    path = a["main"]
    ext = Path(path).suffix.lower()
    before = {o.name for o in bpy.data.objects}
    if ext in (".gltf", ".glb"):
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=path)
    elif ext == ".vrm":
        if not hasattr(bpy.ops.import_scene, "vrm"):
            raise RuntimeError("The VRM add-on is not enabled in this Blender")
        bpy.ops.import_scene.vrm(filepath=path)
    else:
        raise ValueError(f"Cannot import {ext} files")
    return _new_objects(before)


def texture(obj: str, id_or_path: str, scale: float = 1.0, res: str = "1k") -> str:
    """Give an object a photo-real PBR material from a Poly Haven texture id."""
    a = _asset(id_or_path, res)
    files = {Path(f).name.lower(): Path(a["dir"]) / f for f in a["files"]}

    def find(*keys):
        return next((p for n, p in files.items() if any(k in n for k in keys)), None)

    m = bpy.data.materials.new(Path(a["main"]).stem)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    coord = nt.nodes.new("ShaderNodeTexCoord")
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (scale, scale, scale)
    nt.links.new(coord.outputs["UV"], mapping.inputs[0])

    def img(path, colour):
        t = nt.nodes.new("ShaderNodeTexImage")
        t.image = bpy.data.images.load(str(path), check_existing=True)
        if not colour:
            t.image.colorspace_settings.name = "Non-Color"
        nt.links.new(mapping.outputs[0], t.inputs[0])
        return t

    if p := find("diff", "col"):
        nt.links.new(img(p, True).outputs[0], bsdf.inputs["Base Color"])
    if p := find("rough"):
        nt.links.new(img(p, False).outputs[0], bsdf.inputs["Roughness"])
    if p := find("metal"):
        nt.links.new(img(p, False).outputs[0], bsdf.inputs["Metallic"])
    if p := find("nor_gl"):
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nt.links.new(img(p, False).outputs[0], nm.inputs["Color"])
        nt.links.new(nm.outputs[0], bsdf.inputs["Normal"])
    o = bpy.data.objects[obj]
    o.data.materials.clear()
    o.data.materials.append(m)
    return m.name


def _bounds(names=None):
    objs = (
        [bpy.data.objects[n] for n in names]
        if names
        else [o for o in bpy.context.scene.objects if o.type == "MESH"]
    )
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    if not pts:
        raise RuntimeError("Nothing to frame: no mesh objects")
    lo = Vector(tuple(min(p[i] for p in pts) for i in range(3)))
    hi = Vector(tuple(max(p[i] for p in pts) for i in range(3)))
    return lo, hi


def frame_camera(
    names=None,
    lens: float = 50.0,
    yaw_deg: float = 25.0,
    pitch_deg: float = 10.0,
    margin: float = 1.15,
) -> str:
    """Point the scene camera (made if missing) so the objects fill the frame.
    yaw 0 looks from the front (-Y); pitch > 0 looks down, < 0 looks up."""
    scene = bpy.context.scene
    cam = scene.camera
    if cam is None:
        cam = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
        scene.collection.objects.link(cam)
        scene.camera = cam
    cam.data.lens = lens
    lo, hi = _bounds(names)
    centre, radius = (lo + hi) / 2, (hi - lo).length / 2
    fov = cam.data.angle
    dist = radius * margin / math.sin(fov / 2)
    yaw, pitch = math.radians(yaw_deg), math.radians(pitch_deg)
    d = Vector(
        (
            math.sin(yaw) * math.cos(pitch),
            -math.cos(yaw) * math.cos(pitch),
            math.sin(pitch),
        )
    )
    cam.location = centre + d * dist
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    cam.data.clip_end = max(cam.data.clip_end, dist * 4)
    return cam.name


def _area(name, loc, energy, size, colour):
    light = bpy.data.lights.new(name, "AREA")
    light.energy, light.size, light.color = energy, size, colour
    o = bpy.data.objects.new(name, light)
    bpy.context.scene.collection.objects.link(o)
    o.location = loc
    o.rotation_euler = (-Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return o


def _clear_lights():
    for o in [
        o
        for o in bpy.context.scene.objects
        if o.type == "LIGHT" and o.name.startswith("Look")
    ]:
        bpy.data.objects.remove(o)


def _toon_material(src):
    colour = (0.8, 0.8, 0.8, 1.0)
    if src and src.use_nodes and "Principled BSDF" in src.node_tree.nodes:
        colour = tuple(
            src.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value
        )
    elif src:
        colour = tuple(src.diffuse_color)
    m = bpy.data.materials.new(f"Toon_{src.name if src else 'Default'}")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    dif = nt.nodes.new("ShaderNodeBsdfDiffuse")
    s2r = nt.nodes.new("ShaderNodeShaderToRGB")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.interpolation = "CONSTANT"
    ramp.color_ramp.elements[0].color = tuple(c * 0.55 for c in colour[:3]) + (1,)
    ramp.color_ramp.elements[1].position = 0.3
    ramp.color_ramp.elements[1].color = colour
    em = nt.nodes.new("ShaderNodeEmission")
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(dif.outputs[0], s2r.inputs[0])
    nt.links.new(s2r.outputs[0], ramp.inputs[0])
    nt.links.new(ramp.outputs[0], em.inputs[0])
    nt.links.new(em.outputs[0], out.inputs[0])
    return m


def _outline_material():
    m = bpy.data.materials.get("ForgeOutline") or bpy.data.materials.new("ForgeOutline")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs[0].default_value = (0.02, 0.015, 0.03, 1)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(em.outputs[0], out.inputs[0])
    m.use_backface_culling = True
    return m


def look(preset: str = "studio", outline_mm: float = 1.5) -> str:
    """One-call looks. studio: warm key, cool rim, soft fill, AgX, EEVEE.
    toon: cel shading + ink outlines on every mesh, one sun, Standard view.
    hdri:<id or path>: realistic sky lighting (Cycles recommended for finals)."""
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    _clear_lights()
    if preset.startswith("hdri:"):
        return use_hdri(preset[5:])
    if preset == "studio":
        scene.view_settings.view_transform = "AgX"
        lo, hi = (
            _bounds()
            if any(o.type == "MESH" for o in scene.objects)
            else (Vector((-1,) * 3), Vector((1,) * 3))
        )
        r = max((hi - lo).length, 1.0)
        c = (lo + hi) / 2
        _area(
            "LookKey",
            c + Vector((-1.2, -1.5, 1.4)) * r,
            400 * r * r,
            r,
            (1.0, 0.9, 0.8),
        )
        _area(
            "LookRim",
            c + Vector((1.3, 1.4, 1.0)) * r,
            300 * r * r,
            r * 0.5,
            (0.7, 0.8, 1.0),
        )
        _area(
            "LookFill",
            c + Vector((1.5, -1.2, 0.3)) * r,
            80 * r * r,
            r * 2,
            (1.0, 1.0, 1.0),
        )
        _, bg = _world_nodes()
        bg.inputs[0].default_value = (0.02, 0.02, 0.025, 1)
        return "studio"
    if preset == "toon":
        scene.view_settings.view_transform = "Standard"
        sun = bpy.data.objects.new("LookSun", bpy.data.lights.new("LookSun", "SUN"))
        scene.collection.objects.link(sun)
        sun.data.energy = 3.0
        sun.rotation_euler = (math.radians(50), math.radians(-20), math.radians(-30))
        outline = _outline_material()
        done = {}
        for o in [o for o in scene.objects if o.type == "MESH"]:
            mats = [s.material for s in o.material_slots] or [None]
            o.data.materials.clear()
            for src in mats:
                key = src.name if src else ""
                done.setdefault(key, _toon_material(src))
                o.data.materials.append(done[key])
            o.data.materials.append(outline)
            md = o.modifiers.get("ForgeOutline") or o.modifiers.new(
                "ForgeOutline", "SOLIDIFY"
            )
            md.thickness = outline_mm / 1000 / max(o.scale)
            md.offset, md.use_flip_normals, md.use_rim = 1.0, True, False
            md.material_offset = len(o.data.materials) - 1
        return "toon"
    raise ValueError("preset must be studio, toon or hdri:<id or path>")


def rig_human(name: str = "Rig") -> str:
    """Add and generate a Rigify human rig (1.8 m; scale it to the model).
    Bind a mesh with: mesh.select, rig active, bpy.ops.object.parent_set(type='ARMATURE_AUTO').
    """
    import addon_utils

    addon_utils.enable("rigify", default_set=True)
    bpy.ops.object.armature_human_metarig_add()
    meta = bpy.context.active_object
    bpy.ops.pose.rigify_generate()
    rig = bpy.context.active_object
    rig.name = name
    bpy.data.objects.remove(meta)
    return rig.name


def keyframe(
    obj: str, frame: int, loc=None, rot_deg=None, scale=None, bone: str = ""
) -> str:
    """Key location / rotation (degrees, XYZ Euler) / scale of an object or a pose bone."""
    o = bpy.data.objects[obj]
    target = o.pose.bones[bone] if bone else o
    if rot_deg is not None:
        target.rotation_mode = "XYZ"
        target.rotation_euler = [math.radians(a) for a in rot_deg]
        target.keyframe_insert("rotation_euler", frame=frame)
    if loc is not None:
        target.location = loc
        target.keyframe_insert("location", frame=frame)
    if scale is not None:
        target.scale = scale
        target.keyframe_insert("scale", frame=frame)
    return f"{obj}{'/' + bone if bone else ''}@{frame}"


def render_animation(
    path: str, start: int = 1, end: int = 0, percent: int = 50, fps: int = 24
) -> str:
    """Render frames start..end (end 0 = scene end) to an H.264 .mp4 for checking."""
    scene = bpy.context.scene
    if scene.camera is None:
        raise RuntimeError("The scene has no camera; call forge.frame_camera() first")
    scene.frame_start, scene.frame_end = start, end or scene.frame_end
    scene.render.fps = fps
    scene.render.resolution_percentage = percent
    s = scene.render.image_settings
    if hasattr(s, "media_type"):
        s.media_type = "VIDEO"
    s.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    target = Path(os.path.expanduser(path)).with_suffix(".mp4")
    target.parent.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(target)
    scene.render.use_file_extension = False
    bpy.ops.render.render(animation=True)
    return str(target)


def export_godot(path: str, names=None) -> str:
    """Export objects (default: all) with their animations to a .glb for Godot."""
    target = Path(os.path.expanduser(path)).with_suffix(".glb")
    target.parent.mkdir(parents=True, exist_ok=True)
    for o in bpy.context.scene.objects:
        o.select_set(not names or o.name in names)
    bpy.ops.export_scene.gltf(
        filepath=str(target),
        export_format="GLB",
        use_selection=bool(names),
        export_animations=True,
    )
    return str(target)


HELPERS = {
    f.__name__: f
    for f in (
        use_hdri,
        import_asset,
        texture,
        frame_camera,
        look,
        rig_human,
        keyframe,
        render_animation,
        export_godot,
    )
}
