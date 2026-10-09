"""Forge bridge for Blender: lets Claude (through Acchan's blender_* tools)
run Python inside the Blender window you are looking at.

Start Blender with it:   blender --python ~/Forge/shared/bridges/blender/forge_bridge.py [file.blend]
(Acchan's blender_launch does exactly that.)

Protocol: one JSON object per line over TCP on 127.0.0.1:FORGE_BLENDER_PORT
(default 9876):  {"token": "...", "code": "..."}  ->  {"ok": bool, "output":
"printed text", "result": <value of `result` if the code set it>, "error": "..."}.
The token lives in ~/.local/share/forge/bridges/blender.token (mode 600), so
only this user's processes can drive Blender. The socket thread only queues
requests; a bpy.app.timers callback runs them on Blender's main thread, which
is the only thread bpy is safe on.

The code runs with `bpy`, `bmesh`, `mathutils` and `forge` (the helpers
below) already imported. The helpers are the tested, reusable part: mechs
and printable parts go through `forge.print_check` and `forge.export_stl`.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import queue
import secrets
import socketserver
import sys
import threading
import traceback
import types
from pathlib import Path

import bmesh
import bpy
import mathutils

PORT = int(os.environ.get("FORGE_BLENDER_PORT", "9876"))
TOKEN_FILE = Path(
    os.environ.get(
        "FORGE_BLENDER_TOKEN",
        Path.home() / ".local/share/forge/bridges/blender.token",
    )
)


# --- helpers the code can call as forge.<name> ----------------------------------


def _objects(names=None):
    """Mesh objects by name ('' or None = the selected ones, else all meshes)."""
    if names:
        wanted = (
            [n.strip() for n in names.split(",")]
            if isinstance(names, str)
            else list(names)
        )
        found = [bpy.data.objects.get(n) for n in wanted]
        missing = [n for n, o in zip(wanted, found) if o is None]
        if missing:
            raise ValueError(f"No object called {', '.join(missing)}")
        return [o for o in found if o.type == "MESH"]
    selected = [o for o in bpy.context.selected_objects if o.type == "MESH"]
    return selected or [o for o in bpy.context.scene.objects if o.type == "MESH"]


def scene_summary() -> dict:
    scene = bpy.context.scene
    rows = []
    for obj in scene.objects:
        row = {
            "name": obj.name,
            "type": obj.type,
            "location": [round(v, 3) for v in obj.location],
            "dimensions": [round(v, 3) for v in obj.dimensions],
        }
        if obj.parent:
            row["parent"] = obj.parent.name
        if obj.type == "MESH":
            row["faces"] = len(obj.data.polygons)
            row["materials"] = [m.name for m in obj.data.materials if m]
        if obj.animation_data and obj.animation_data.action:
            row["action"] = obj.animation_data.action.name
        rows.append(row)
    return {
        "file": bpy.data.filepath or "(unsaved)",
        "engine": scene.render.engine,
        "frames": [scene.frame_start, scene.frame_end],
        "unit_scale": scene.unit_settings.scale_length,
        "objects": rows,
    }


def _evaluated_bmesh(obj):
    """The object's mesh with modifiers applied, in world space."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    mesh = obj.evaluated_get(depsgraph).to_mesh()
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.transform(obj.matrix_world)
    obj.evaluated_get(depsgraph).to_mesh_clear()
    return bm


def print_check(names=None, min_wall_mm: float = 0.8) -> dict:
    """Is each object printable? Watertight (no non-manifold edges), no loose
    geometry, no degenerate faces, volume and size in mm (1 Blender unit =
    1 mm unless the scene's unit scale says otherwise), and edges shorter
    than min_wall_mm as a rough thin-feature warning."""
    scale_mm = bpy.context.scene.unit_settings.scale_length * 1000
    if bpy.context.scene.unit_settings.system == "NONE" or scale_mm == 1000:
        scale_mm = 1.0  # plain units are treated as millimetres, as slicers do
    report = {}
    for obj in _objects(names):
        bm = _evaluated_bmesh(obj)
        try:
            non_manifold = sum(1 for e in bm.edges if not e.is_manifold)
            loose_verts = sum(1 for v in bm.verts if not v.link_edges)
            loose_edges = sum(1 for e in bm.edges if not e.link_faces)
            degenerate = sum(1 for f in bm.faces if f.calc_area() < 1e-8)
            thin = sum(
                1 for e in bm.edges if e.calc_length() * scale_mm < min_wall_mm * 0.25
            )
            bm.normal_update()
            volume = abs(bm.calc_volume(signed=True)) * scale_mm**3
            lo = (
                [min(v.co[i] for v in bm.verts) for i in range(3)]
                if bm.verts
                else [0, 0, 0]
            )
            hi = (
                [max(v.co[i] for v in bm.verts) for i in range(3)]
                if bm.verts
                else [0, 0, 0]
            )
        finally:
            bm.free()
        problems = []
        if non_manifold:
            problems.append(
                f"{non_manifold} non-manifold edges (holes or internal faces)"
            )
        if loose_verts or loose_edges:
            problems.append(f"{loose_verts} loose vertices, {loose_edges} loose edges")
        if degenerate:
            problems.append(f"{degenerate} zero-area faces")
        if thin:
            problems.append(
                f"{thin} very short edges (features may be too thin to print)"
            )
        report[obj.name] = {
            "printable": not (non_manifold or loose_verts or loose_edges or degenerate),
            "problems": problems,
            "volume_mm3": round(volume, 2),
            "size_mm": [round((h - l) * scale_mm, 2) for l, h in zip(lo, hi)],
        }
    return report


def export_stl(path: str, names=None, check: bool = True) -> dict:
    """Write the objects (modifiers applied) as one binary STL, after a
    print_check unless check=False. Returns the check and the file."""
    target = Path(os.path.expanduser(path))
    if target.suffix.lower() != ".stl":
        target = target.with_suffix(".stl")
    target.parent.mkdir(parents=True, exist_ok=True)
    objs = _objects(names)
    if not objs:
        raise ValueError("No mesh objects to export")
    result: dict = {"check": print_check([o.name for o in objs]) if check else {}}
    previous = list(bpy.context.selected_objects)
    for o in bpy.context.view_layer.objects:
        o.select_set(o in objs)
    try:
        bpy.ops.wm.stl_export(
            filepath=str(target), export_selected_objects=True, apply_modifiers=True
        )
    finally:
        for o in bpy.context.view_layer.objects:
            o.select_set(o in previous)
    result["file"] = str(target)
    result["bytes"] = target.stat().st_size
    return result


def viewport_shot(path: str) -> str:
    """Save a picture of the largest 3D viewport, as it looks on screen."""
    if bpy.app.background:
        raise RuntimeError("No 3D viewport: Blender is running without a window")
    target = Path(os.path.expanduser(path))
    target.parent.mkdir(parents=True, exist_ok=True)
    for window in bpy.context.window_manager.windows:
        areas = [a for a in window.screen.areas if a.type == "VIEW_3D"]
        if not areas:
            continue
        area = max(areas, key=lambda a: a.width * a.height)
        with bpy.context.temp_override(window=window, area=area):
            bpy.ops.screen.screenshot_area(filepath=str(target))
        return str(target)
    raise RuntimeError("No 3D viewport is open (Blender running without a window?)")


def render(
    path: str, engine: str = "", samples: int = 0, frame: int | None = None
) -> str:
    """Render the scene camera to a PNG. engine: CYCLES, BLENDER_EEVEE or ''
    for the scene's own; samples 0 keeps the scene's setting."""
    scene = bpy.context.scene
    if scene.camera is None:
        raise RuntimeError("The scene has no camera; add one and point it at the model")
    if engine:
        scene.render.engine = engine
    if samples and scene.render.engine == "CYCLES":
        scene.cycles.samples = samples
    if frame is not None:
        scene.frame_set(frame)
    target = Path(os.path.expanduser(path)).with_suffix(".png")
    target.parent.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(target)
    scene.render.image_settings.file_format = "PNG"
    bpy.ops.render.render(write_still=True)
    return str(target)


sys.path.insert(0, str(Path(__file__).resolve().parent))
import forge_studio  # noqa: E402  # pyright: ignore[reportMissingImports]

forge = types.SimpleNamespace(
    scene_summary=scene_summary,
    print_check=print_check,
    export_stl=export_stl,
    viewport_shot=viewport_shot,
    render=render,
    **forge_studio.HELPERS,
)


# --- running code ---------------------------------------------------------------


def run_code(code: str) -> dict:
    """Run code on the current thread with the helpers in scope."""
    scope = {
        "bpy": bpy,
        "bmesh": bmesh,
        "mathutils": mathutils,
        "forge": forge,
        "__name__": "forge_bridge_call",
    }
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            exec(compile(code, "<forge>", "exec"), scope)
        result = scope.get("result")
        try:
            json.dumps(result)
        except (TypeError, ValueError):
            result = repr(result)
        return {"ok": True, "output": out.getvalue()[-20000:], "result": result}
    except Exception:
        return {
            "ok": False,
            "output": out.getvalue()[-20000:],
            "error": traceback.format_exc(limit=6)[-6000:],
        }


def load_token() -> str:
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    if TOKEN_FILE.is_file() and TOKEN_FILE.read_text().strip():
        return TOKEN_FILE.read_text().strip()
    token = secrets.token_hex(16)
    TOKEN_FILE.write_text(token)
    TOKEN_FILE.chmod(0o600)
    return token


class Bridge:
    """Socket thread in, main thread out."""

    def __init__(self, port: int = PORT):
        self.token = load_token()
        self.jobs: queue.Queue = queue.Queue()
        bridge = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                for raw in self.rfile:
                    try:
                        msg = json.loads(raw)
                    except ValueError:
                        reply = {"ok": False, "error": "Send one JSON object per line"}
                    else:
                        if not secrets.compare_digest(
                            str(msg.get("token", "")), bridge.token
                        ):
                            reply = {"ok": False, "error": "Wrong token"}
                        else:
                            done = threading.Event()
                            box: dict = {}
                            bridge.jobs.put((str(msg.get("code", "")), box, done))
                            if not done.wait(float(msg.get("timeout", 600))):
                                reply = {
                                    "ok": False,
                                    "error": "Blender did not finish in time (busy rendering?)",
                                }
                            else:
                                reply = box["reply"]
                    self.wfile.write((json.dumps(reply) + "\n").encode())
                    self.wfile.flush()

        class Server(socketserver.ThreadingTCPServer):
            daemon_threads = True
            allow_reuse_address = True

        self.server = Server(("127.0.0.1", port), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def drain(self) -> None:
        while True:
            try:
                code, box, done = self.jobs.get_nowait()
            except queue.Empty:
                return
            box["reply"] = run_code(code)
            done.set()

    def tick(self) -> float:
        self.drain()
        return 0.1  # run again in 0.1 s

    def serve_blocking(self) -> None:
        """For `blender -b` (tests): no timers run there, so loop here."""
        import time

        while True:
            self.drain()
            time.sleep(0.05)


def start() -> Bridge | None:
    existing = getattr(sys.modules[__name__], "_bridge", None)
    if existing:
        return existing
    try:
        bridge = Bridge()
    except OSError as exc:
        print(
            f"Forge bridge: port {PORT} is taken ({exc}); is another Blender running it?"
        )
        return None
    bridge.start()
    sys.modules[__name__]._bridge = bridge  # type: ignore[attr-defined]
    if bpy.app.background:
        print(f"Forge bridge listening on 127.0.0.1:{PORT} (background)", flush=True)
        bridge.serve_blocking()
    else:
        bpy.app.timers.register(bridge.tick, persistent=True)
        print(f"Forge bridge listening on 127.0.0.1:{PORT}")
    return bridge


if __name__ == "__main__":
    start()
