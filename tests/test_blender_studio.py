"""shared/bridges/blender/forge_studio.py helpers inside a real headless Blender."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

STUDIO = Path(__file__).resolve().parents[1] / "shared/bridges/blender"

pytestmark = pytest.mark.skipif(
    not shutil.which("blender"), reason="blender not installed"
)

SCRIPT = r"""
import sys, json, os
sys.path.insert(0, STUDIO)
import bpy, forge_studio as fs
bpy.ops.wm.read_factory_settings(use_empty=True)
out = {}
bpy.ops.mesh.primitive_monkey_add(location=(0, 0, 1)); bpy.context.object.name = "Suzanne"
bpy.ops.mesh.primitive_plane_add(size=6); bpy.context.object.name = "Floor"
bpy.ops.object.shade_smooth()
# tiny HDR sky + texture maps made on the spot, so no network is needed
sky = bpy.data.images.new("sky", 32, 16, float_buffer=True)
sky.pixels.foreach_set([0.6] * (32 * 16 * 4)); sky.filepath_raw = TMP + "/sky.hdr"
sky.file_format = "HDR"; sky.save()
for n in ("t_diff_1k.jpg", "t_rough_1k.jpg", "t_nor_gl_1k.jpg"):
    im = bpy.data.images.new(n, 8, 8); im.filepath_raw = TMP + "/" + n; im.file_format = "JPEG"; im.save()
out["hdri"] = fs.use_hdri(TMP + "/sky.hdr", 1.2, 90)
out["texture"] = fs.texture("Floor", TMP + "/t_diff_1k.jpg", 4)
floor_links = [l.to_socket.name for l in bpy.data.materials[out["texture"]].node_tree.links]
out["floor_inputs"] = sorted(set(floor_links) & {"Base Color", "Roughness", "Normal"})
out["look_studio"] = fs.look("studio")
out["lights"] = sorted(o.name for o in bpy.context.scene.objects if o.type == "LIGHT")
out["camera"] = fs.frame_camera(["Suzanne"], lens=85, yaw_deg=30)
bpy.context.scene.render.resolution_x, bpy.context.scene.render.resolution_y = 160, 120
bpy.context.scene.render.filepath = TMP + "/still.png"; bpy.ops.render.render(write_still=True)
out["look_toon"] = fs.look("toon")
out["outlined"] = sorted(o.name for o in bpy.context.scene.objects if o.modifiers.get("ForgeOutline"))
out["key1"] = fs.keyframe("Suzanne", 1, loc=(0, 0, 1), rot_deg=(0, 0, 0))
out["key2"] = fs.keyframe("Suzanne", 3, loc=(0, 0, 1.3), rot_deg=(0, 0, 45))
out["mp4"] = fs.render_animation(TMP + "/anim", 1, 3, percent=100)
out["glb"] = fs.export_godot(TMP + "/scene", ["Suzanne"])
out["rig"] = fs.rig_human()
out["rig_bones"] = len(bpy.data.objects[out["rig"]].data.bones)
before = {o.name for o in bpy.data.objects}
out["imported"] = fs.import_asset(out["glb"])
print("RESULT" + json.dumps(out))
"""


def test_every_helper_in_headless_blender(tmp_path):
    code = f"STUDIO={str(STUDIO)!r}\nTMP={str(tmp_path)!r}\n" + SCRIPT
    p = subprocess.run(
        ["blender", "-b", "--factory-startup", "--python-expr", code],
        capture_output=True,
        text=True,
        timeout=600,
    )
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT")), None)
    assert line, p.stdout[-3000:] + p.stderr[-3000:]
    r = json.loads(line[6:])
    assert r["hdri"].endswith("sky.hdr")
    assert r["floor_inputs"] == ["Base Color", "Normal", "Roughness"]
    assert r["lights"] == ["LookFill", "LookKey", "LookRim"]
    assert (tmp_path / "still.png").stat().st_size > 1000
    assert r["outlined"] == ["Floor", "Suzanne"] and "LookKey" not in r["outlined"]
    assert Path(r["mp4"]).stat().st_size > 1000
    assert Path(r["glb"]).stat().st_size > 1000
    assert r["rig_bones"] > 100
    assert any(n.startswith("Suzanne") for n in r["imported"])
