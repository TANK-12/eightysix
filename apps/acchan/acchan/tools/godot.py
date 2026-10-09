"""Godot 4, live on screen: make a project, open the editor with the Forge
bridge, run editor scripts in it, play scenes (and record their frames),
and check a project for script errors.

Scenes (.tscn) and scripts (.gd) are plain text: write them with the file
tools, then godot_check and godot_play. New 3D projects start on the
Forward+ renderer with filmic tonemapping, SDFGI global illumination, SSAO,
glow and soft shadows, so they look good from the first run.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import socket
import subprocess
import time
from pathlib import Path
from typing import Annotated

from ..desktop import current
from ..registry import ToolError, tool
from ..sysutil import clip
from ..sysutil import path as to_path

TOOLSET = "godot"
TOOLSET_SUMMARY = (
    "Godot game engine live on screen: new game projects, editor scripting,"
    " play and record scenes, check scripts"
)
TOOLSET_KEYWORDS = ("godot", "game", "scene", "gdscript", "level", "player", "physics")
TOOLSET_EXAMPLES = [
    (
        "make a new godot game called mechs",
        "godot_new_project",
        {"path": "~/Games/mechs"},
    ),
]

SHARED = Path(os.environ.get("FORGE_SHARED_DIR", Path.home() / "Forge" / "shared"))
ADDON = SHARED / "bridges" / "godot" / "addons" / "forge_bridge"
# Extra add-ons (Phantom Camera, VRM + MToon) copied into every new project.
EXTRA_ADDONS = SHARED / "godot_addons"
# Starter templates: each folder holds files copied over a new project, plus a
# template.json with a one-line "summary". A new template is one new folder.
TEMPLATES = SHARED / "bridges" / "godot" / "templates"
# Big shared files (characters, animation libraries) a template names in its
# template.json "assets" ({project path: path under here}) are copied from
# here, so the template folder itself stays small; "retarget" lists the ones
# to put on Godot's humanoid skeleton (shared/bridges/godot/humanoid.py).
ASSETS = SHARED / "assets"
MODEL_SUFFIXES = (".glb", ".gltf", ".vrm")
PORT = int(os.environ.get("FORGE_GODOT_PORT", "9878"))
TOKEN_FILE = Path(
    os.environ.get(
        "FORGE_GODOT_TOKEN", Path.home() / ".local/share/forge/bridges/godot.token"
    )
)
ERROR_LINE = re.compile(r"(SCRIPT ERROR|Parse Error|ERROR:|Failed to load)", re.I)

PROJECT_GODOT = """; Made by Forge (godot_new_project).
config_version=5

[application]

config/name="{name}"
run/main_scene="res://main.tscn"
config/features=PackedStringArray("4.7", "Forward Plus")

[editor_plugins]

enabled=PackedStringArray({plugins})
{autoloads}
[rendering]

anti_aliasing/quality/msaa_3d=2
anti_aliasing/quality/screen_space_aa=1
lights_and_shadows/directional_shadow/soft_shadow_filter_quality=3
lights_and_shadows/positional_shadow/soft_shadow_filter_quality=3
"""

MAIN_TSCN = """[gd_scene load_steps=5 format=3]

[sub_resource type="ProceduralSkyMaterial" id="sky_mat"]
sky_horizon_color = Color(0.64, 0.66, 0.7, 1)
ground_horizon_color = Color(0.64, 0.66, 0.7, 1)

[sub_resource type="Sky" id="sky"]
sky_material = SubResource("sky_mat")

[sub_resource type="Environment" id="env"]
background_mode = 2
sky = SubResource("sky")
tonemap_mode = 4
ssao_enabled = true
sdfgi_enabled = true
glow_enabled = true
volumetric_fog_enabled = true
volumetric_fog_density = 0.01

[sub_resource type="StandardMaterial3D" id="ground_mat"]
albedo_color = Color(0.22, 0.23, 0.25, 1)
roughness = 0.8

[node name="Main" type="Node3D"]

[node name="WorldEnvironment" type="WorldEnvironment" parent="."]
environment = SubResource("env")

[node name="Sun" type="DirectionalLight3D" parent="."]
transform = Transform3D(0.866, -0.354, 0.354, 0, 0.707, 0.707, -0.5, -0.612, 0.612, 0, 10, 0)
shadow_enabled = true

[node name="Ground" type="CSGBox3D" parent="."]
size = Vector3(40, 1, 40)
transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 0, -0.5, 0)
material = SubResource("ground_mat")
use_collision = true

[node name="Camera3D" type="Camera3D" parent="."]
transform = Transform3D(0.707, -0.3, 0.64, 0, 0.906, 0.423, -0.707, -0.3, 0.64, 8, 6, 8)
"""


def godot_bin() -> str:
    found = shutil.which("godot") or shutil.which("godot4")
    if not found:
        raise ToolError("Godot is not installed (pacman -S godot).")
    return found


def _project(path: str) -> Path:
    root = to_path(path)
    if not (root / "project.godot").is_file():
        raise ToolError(f"{root} is not a Godot project (no project.godot).")
    return root


def _up() -> bool:
    try:
        socket.create_connection(("127.0.0.1", PORT), timeout=0.5).close()
        return True
    except OSError:
        return False


def send(code: str, timeout: float = 120) -> dict:
    if not _up():
        raise ToolError(
            "No Godot editor with the Forge bridge is open. Use godot_open."
        )
    try:
        token = TOKEN_FILE.read_text().strip()
    except OSError as exc:
        raise ToolError("The bridge token is missing; reopen the editor.") from exc
    with socket.create_connection(("127.0.0.1", PORT), timeout=timeout) as sock:
        sock.sendall((json.dumps({"token": token, "code": code}) + "\n").encode())
        data = b""
        while not data.endswith(b"\n"):
            chunk = sock.recv(65536)
            if not chunk:
                break
            data += chunk
    try:
        return json.loads(data)
    except ValueError as exc:
        raise ToolError("Godot closed the connection mid-answer.") from exc


def install_addon(root: Path) -> None:
    target = root / "addons" / "forge_bridge"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(ADDON, target)
    if EXTRA_ADDONS.is_dir():
        for extra in sorted(EXTRA_ADDONS.iterdir()):
            dest = root / "addons" / extra.name
            skip = (extra / ".forge-disabled").exists()
            if extra.is_dir() and not skip and not dest.exists():
                shutil.copytree(extra, dest)


def autoload_section(root: Path) -> str:
    """[autoload] lines declared by add-ons in a .forge-autoload file (Name=res://path)."""
    lines = []
    for f in sorted((root / "addons").glob("*/.forge-autoload")):
        for line in f.read_text().splitlines():
            if "=" in line:
                name, res = line.split("=", 1)
                lines.append(f'{name.strip()}="*{res.strip()}"')
    return "\n[autoload]\n\n" + "\n".join(lines) + "\n" if lines else ""


def plugin_list(root: Path) -> str:
    cfgs = sorted((root / "addons").glob("*/plugin.cfg"))
    return ", ".join(f'"res://addons/{c.parent.name}/plugin.cfg"' for c in cfgs)


def _humanoid():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "forge_humanoid", SHARED / "bridges" / "godot" / "humanoid.py"
    )
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def template_assets(source: Path, root: Path) -> list[str]:
    """Copy a template's shared assets into the project and write the
    retargeting files for its humanoids. Returns the project paths copied."""
    meta = json.loads((source / "template.json").read_text())
    copied = []
    for dest, src in (meta.get("assets") or {}).items():
        origin = ASSETS / src
        if not origin.is_file():
            raise ToolError(f"The template needs {origin}, which is missing.")
        target = root / dest
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origin, target)
        copied.append(dest)
    if meta.get("retarget"):
        humanoid = _humanoid()
        for item in meta["retarget"]:
            humanoid.write_retarget(root, root / item)
    return copied


def templates() -> dict[str, str]:
    """Template name -> one-line summary, from the folders in TEMPLATES."""
    found = {}
    for meta in sorted(TEMPLATES.glob("*/template.json")):
        try:
            summary = json.loads(meta.read_text()).get("summary", "")
        except ValueError:
            summary = ""
        found[meta.parent.name] = summary
    return found


def import_problems(root: Path, log_lines: list[str]) -> list[str]:
    """Problems with the project's .glb/.gltf/.vrm files after a headless import."""
    problems = []
    for model in sorted(root.rglob("*")):
        rel = model.relative_to(root)
        if model.suffix.lower() not in MODEL_SUFFIXES or rel.parts[0] in (
            ".godot",
            "addons",
        ):
            continue
        meta = model.with_name(model.name + ".import")
        hint = (
            " (is the vrm add-on enabled in project.godot?)"
            if model.suffix.lower() == ".vrm"
            else ""
        )
        if not meta.is_file():
            problems.append(f"{rel}: not imported, no .import file{hint}")
            continue
        text = meta.read_text(errors="replace")
        if "valid=false" in text:
            problems.append(f"{rel}: import failed (valid=false in {meta.name})")
            continue
        imported = re.search(r'^path(?:\.\w+)?="res://(.+?)"', text, re.M)
        if imported and not (root / imported.group(1)).exists():
            problems.append(f"{rel}: imported file {imported.group(1)} is missing")
        problems += [
            f"{rel}: {line.strip()}"
            for line in log_lines
            if model.name in line and "WARNING" in line
        ]
    return problems


@tool(TOOLSET, example={"path": "~/Games/mechs", "name": "Mechs"})
def godot_new_project(
    path: Annotated[str, "Folder for the new project"],
    name: Annotated[str, "Game name"] = "",
    template: Annotated[
        str,
        "Starter template; empty = a plain scene, third_person = WASD player with a Phantom Camera and AnimationTree",
    ] = "",
) -> str:
    """Create a new good-looking 3D Godot project (sky, sun, shadows, global illumination, glow) with the Forge bridge, optionally from a starter template."""
    root = to_path(path)
    if (root / "project.godot").exists():
        raise ToolError(f"{root} already has a Godot project.")
    template = template.strip()
    known = templates()
    if template and template not in known:
        raise ToolError(
            f"No template {template!r}. Known: {', '.join(known) or 'none'}."
        )
    root.mkdir(parents=True, exist_ok=True)
    title = name.strip() or root.name
    install_addon(root)
    (root / "project.godot").write_text(
        PROJECT_GODOT.format(
            name=title.replace('"', ""),
            plugins=plugin_list(root),
            autoloads=autoload_section(root),
        )
    )
    (root / "main.tscn").write_text(MAIN_TSCN)
    (root / ".gitignore").write_text(".godot/\n")
    if template:
        source = TEMPLATES / template
        for item in sorted(source.rglob("*")):
            if item.is_file() and item.name != "template.json":
                dest = root / item.relative_to(source)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, dest)
        template_assets(source, root)
        return (
            f"Made {title} at {root} from the {template} template: {known[template]}."
        )
    return f"Made {title} at {root}: main.tscn has a sky, sun, ground and camera."


@tool(TOOLSET, example={"path": "~/Games/mechs"}, voice="ok")
def godot_open(path: Annotated[str, "Project folder"]) -> str:
    """Open a Godot project in the editor on screen, with the Forge bridge for godot_editor."""
    root = _project(path)
    install_addon(root)  # keeps the bridge current
    if _up():
        return "A Godot editor with the bridge is already open; close it to switch projects."
    current().exec(f"{shlex.quote(godot_bin())} -e --path {shlex.quote(str(root))}")
    for _ in range(180):
        if _up():
            return f"Godot is open on {root.name} with the bridge."
        time.sleep(0.5)
    raise ToolError(
        "Godot opened but the bridge did not answer in 90 s (first import can be slow)."
    )


@tool(TOOLSET, risky=True, example={"code": "return editor.get_open_scenes()"})
def godot_editor(
    code: Annotated[
        str,
        "GDScript body of func run(editor); editor is EditorInterface; return a value to get it back",
    ],
) -> str:
    """Run GDScript inside the open Godot editor (reload or open scenes, add nodes, save)."""
    reply = send(code)
    if not reply.get("ok"):
        raise ToolError(reply.get("error", "failed"))
    return json.dumps(reply.get("result"), indent=1)[:12000]


@tool(TOOLSET, show=True, voice="ok")
def godot_check(path: Annotated[str, "Project folder"]) -> str:
    """Check a Godot project for script and scene errors and for .glb/.gltf/.vrm import problems (imports everything once)."""
    root = _project(path)
    proc = subprocess.run(
        [godot_bin(), "--headless", "--path", str(root), "--editor", "--quit"],
        capture_output=True,
        text=True,
        timeout=300,
    )
    lines = (proc.stdout + proc.stderr).splitlines()
    errors = [line for line in lines if ERROR_LINE.search(line)]
    models = import_problems(root, lines)
    if not errors and not models:
        return "No script, scene or model import errors."
    report = errors + (["Model import problems:"] + models if models else [])
    return clip("\n".join(report), 8000)


@tool(TOOLSET, example={"path": "~/Games/mechs", "seconds": 5}, voice="ok")
def godot_play(
    path: Annotated[str, "Project folder"],
    scene: Annotated[
        str, "Scene to run, like res://level.tscn; empty = the main scene"
    ] = "",
    seconds: Annotated[int, "How long to run before closing"] = 6,
    record: Annotated[
        bool, "Save frames (PNG) of the run and return the last one"
    ] = True,
) -> str:
    """Run a Godot scene on screen for a few seconds, recording frames so the result can be looked at."""
    root = _project(path)
    fps = 30
    frames = max(1, int(seconds)) * fps
    argv = [godot_bin(), "--path", str(root), "--quit-after", str(frames)]
    out_dir = root / ".forge_frames"
    if record:
        shutil.rmtree(out_dir, ignore_errors=True)
        out_dir.mkdir()
        argv += ["--write-movie", str(out_dir / "frame.png"), "--fixed-fps", str(fps)]
    if scene.strip():
        argv.append(scene.strip())
    # Recording writes a PNG per frame at window size: about 1.5 frames a
    # second on the Iris Xe with SDFGI on, so allow a second per frame.
    limit = 60 + (frames if record else seconds * 3)
    proc = subprocess.Popen(
        argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    try:
        output, _ = proc.communicate(timeout=limit)
        report = [f"Ran {scene.strip() or 'the main scene'} for {frames} frames."]
    except subprocess.TimeoutExpired:
        proc.kill()
        output, _ = proc.communicate()
        report = [f"Stopped after {limit} s before all {frames} frames were done."]
    errors = [line for line in output.splitlines() if ERROR_LINE.search(line)]
    if record:
        shots = sorted(out_dir.glob("frame*.png"))
        if shots:
            report.append(f"{len(shots)} frames in {out_dir}; last: {shots[-1]}")
        else:
            report.append("No frames were written.")
    if errors:
        report.append("Errors:\n" + clip("\n".join(errors), 6000))
    return "\n".join(report)
