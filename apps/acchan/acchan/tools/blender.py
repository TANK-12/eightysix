"""Blender, live on screen: start it with the Forge bridge, run Python in it,
check a model is printable, export STL, grab the viewport, render.

The bridge (shared/bridges/blender/forge_bridge.py) runs inside Blender and
takes code over a token-protected local socket; see its docstring. The code
runs with bpy, bmesh, mathutils and `forge` (scene_summary, print_check,
export_stl, viewport_shot, render) in scope; set `result` to return a value.
"""

from __future__ import annotations

import json
import os
import shlex
import socket
import time
from pathlib import Path
from typing import Annotated

from ..desktop import current
from ..registry import ToolError, tool
from ..sysutil import clip
from ..sysutil import path as to_path

TOOLSET = "blender"
TOOLSET_SUMMARY = (
    "Blender live on screen: model (mechs, props), animate, render, check a"
    " model is 3D-printable and export STL"
)
TOOLSET_KEYWORDS = (
    "blender",
    "3d",
    "model",
    "mesh",
    "mech",
    "stl",
    "print",
    "render",
    "animation",
    "rig",
)
TOOLSET_EXAMPLES = [
    ("open blender", "blender_launch", {}),
    ("is my model printable", "blender_print_check", {}),
]

SHARED = Path(os.environ.get("FORGE_SHARED_DIR", Path.home() / "Forge" / "shared"))
BRIDGE = SHARED / "bridges" / "blender" / "forge_bridge.py"
PORT = int(os.environ.get("FORGE_BLENDER_PORT", "9876"))
TOKEN_FILE = Path(
    os.environ.get(
        "FORGE_BLENDER_TOKEN",
        Path.home() / ".local/share/forge/bridges/blender.token",
    )
)


def _up() -> bool:
    try:
        socket.create_connection(("127.0.0.1", PORT), timeout=0.5).close()
        return True
    except OSError:
        return False


def send(code: str, timeout: float = 600) -> dict:
    """Run code in the bridged Blender and return its reply."""
    if not _up():
        raise ToolError(
            "Blender is not running with the Forge bridge. Use blender_launch."
        )
    try:
        token = TOKEN_FILE.read_text().strip()
    except OSError as exc:
        raise ToolError(
            "The bridge token is missing; restart Blender with blender_launch."
        ) from exc
    request = {"token": token, "code": code, "timeout": timeout}
    with socket.create_connection(("127.0.0.1", PORT), timeout=timeout + 10) as sock:
        sock.sendall((json.dumps(request) + "\n").encode())
        data = b""
        while not data.endswith(b"\n"):
            chunk = sock.recv(65536)
            if not chunk:
                break
            data += chunk
    try:
        return json.loads(data)
    except ValueError as exc:
        raise ToolError("Blender closed the connection mid-answer.") from exc


def _call(code: str, timeout: float = 600):
    reply = send(code, timeout)
    if not reply.get("ok"):
        raise ToolError(
            clip((reply.get("output") or "") + (reply.get("error") or ""), 6000)
        )
    return reply


@tool(TOOLSET, example={"file": ""}, voice="ok")
def blender_launch(
    file: Annotated[str, "Optional .blend file to open"] = "",
) -> str:
    """Start Blender on screen with the Forge bridge so the other blender tools can drive it."""
    if _up():
        return "Blender with the bridge is already running."
    command = f"blender --python {shlex.quote(str(BRIDGE))}"
    if file.strip():
        target = to_path(file)
        if not target.exists():
            raise ToolError(f"{target} does not exist.")
        command += f" {shlex.quote(str(target))}"
    current().exec(command)
    for _ in range(120):
        if _up():
            return "Blender is open with the bridge."
        time.sleep(0.5)
    raise ToolError("Blender started but the bridge did not answer within a minute.")


@tool(TOOLSET, risky=True, example={"code": "bpy.ops.mesh.primitive_cube_add(size=20)"})
def blender_run(
    code: Annotated[
        str,
        "Python to run inside Blender; bpy, bmesh, mathutils and forge are imported; set result to return a value",
    ],
) -> str:
    """Run Python inside the open Blender (build or change models, rigs, materials, animation)."""
    reply = _call(code)
    parts = []
    if reply.get("output"):
        parts.append(reply["output"].rstrip())
    if reply.get("result") is not None:
        parts.append(json.dumps(reply["result"], indent=1)[:12000])
    return "\n".join(parts) or "Done."


@tool(TOOLSET, show=True, voice="ok")
def blender_scene() -> str:
    """List what is in the open Blender scene: objects, sizes, materials, animation."""
    return json.dumps(_call("result = forge.scene_summary()")["result"], indent=1)[
        :12000
    ]


@tool(TOOLSET, show=True, voice="ok")
def blender_print_check(
    objects: Annotated[
        str, "Object names, comma separated; empty = selected (or all meshes)"
    ] = "",
) -> str:
    """Check models are 3D-printable: watertight, no loose bits, size and volume in mm."""
    return json.dumps(
        _call(f"result = forge.print_check({objects!r})")["result"], indent=1
    )


@tool(TOOLSET, example={"path": "~/Models/mech_arm.stl"})
def blender_export_stl(
    path: Annotated[str, "Where to write the .stl"],
    objects: Annotated[
        str, "Object names, comma separated; empty = selected (or all meshes)"
    ] = "",
) -> str:
    """Export models from Blender as an STL for 3D printing, with a printability check first."""
    target = str(to_path(path))
    return json.dumps(
        _call(f"result = forge.export_stl({target!r}, {objects!r})")["result"], indent=1
    )


@tool(TOOLSET, example={"path": "~/Pictures/blender_view.png"}, voice="ok")
def blender_viewport_shot(
    path: Annotated[
        str, "Where to save the PNG"
    ] = "~/Pictures/Screenshots/blender_view.png",
) -> str:
    """Save a picture of Blender's 3D viewport as it looks on screen right now."""
    target = str(to_path(path))
    return "Saved " + _call(f"result = forge.viewport_shot({target!r})")["result"]


@tool(TOOLSET, example={"path": "~/Pictures/render.png", "engine": "CYCLES"})
def blender_render(
    path: Annotated[str, "Where to save the PNG"],
    engine: Annotated[
        str,
        "CYCLES (best looking, slow), BLENDER_EEVEE (fast), or empty for the scene's",
    ] = "",
    samples: Annotated[int, "Cycles samples; 0 keeps the scene's"] = 0,
) -> str:
    """Render the scene camera to a picture (film-quality with Cycles)."""
    target = str(to_path(path))
    code = (
        f"result = forge.render({target!r}, {engine.strip().upper()!r}, {int(samples)})"
    )
    return "Rendered " + _call(code, timeout=3600)["result"]
