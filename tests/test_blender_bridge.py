"""shared/bridges/blender/forge_bridge.py inside a real Blender (background).

Starts `blender -b --factory-startup --python forge_bridge.py` on a spare
port with a throwaway token, then drives it over the socket the way Acchan's
blender tools do. Needs the blender package. Run with any venv that has
pytest, e.g. apps/acchan/.venv.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import struct
import subprocess
import time
from pathlib import Path

import pytest

BRIDGE = Path(__file__).resolve().parents[1] / "shared/bridges/blender/forge_bridge.py"
PORT = 9879

pytestmark = pytest.mark.skipif(
    not shutil.which("blender"), reason="blender not installed"
)


@pytest.fixture(scope="module")
def blender(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("blender")
    token_file = tmp / "token"
    env = dict(
        os.environ, FORGE_BLENDER_PORT=str(PORT), FORGE_BLENDER_TOKEN=str(token_file)
    )
    proc = subprocess.Popen(
        ["blender", "-b", "--factory-startup", "--python", str(BRIDGE)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            socket.create_connection(("127.0.0.1", PORT), timeout=0.5).close()
            break
        except OSError:
            time.sleep(0.2)
    else:
        proc.kill()
        pytest.fail(
            "Blender bridge never started:\n"
            + (proc.stdout.read() if proc.stdout else "")
        )
    yield {"token": token_file.read_text().strip(), "tmp": tmp}
    proc.kill()
    proc.wait()


def send(code: str, token: str) -> dict:
    with socket.create_connection(("127.0.0.1", PORT), timeout=60) as sock:
        sock.sendall((json.dumps({"token": token, "code": code}) + "\n").encode())
        data = b""
        while not data.endswith(b"\n"):
            chunk = sock.recv(65536)
            if not chunk:
                break
            data += chunk
    return json.loads(data)


def test_token_is_private_and_wrong_token_is_refused(blender):
    token_file = blender["tmp"] / "token"
    assert oct(token_file.stat().st_mode & 0o777) == "0o600"
    assert send("result = 1", "nope") == {"ok": False, "error": "Wrong token"}


def test_code_runs_with_output_result_and_errors(blender):
    reply = send("print('hi'); result = {'n': len(bpy.data.objects)}", blender["token"])
    assert reply["ok"] and reply["output"] == "hi\n" and reply["result"]["n"] >= 1
    reply = send("1/0", blender["token"])
    assert not reply["ok"] and "ZeroDivisionError" in reply["error"]


def test_scene_summary(blender):
    reply = send("result = forge.scene_summary()", blender["token"])
    names = {o["name"] for o in reply["result"]["objects"]}
    assert {"Cube", "Camera", "Light"} <= names


def test_print_check_passes_a_cube_and_flags_an_open_plane(blender):
    code = """
bpy.ops.mesh.primitive_plane_add(size=10, location=(30, 0, 0))
bpy.context.active_object.name = 'OpenPlane'
cube = bpy.data.objects['Cube']
cube.scale = (10, 10, 10)
result = forge.print_check('Cube,OpenPlane')
"""
    reply = send(code, blender["token"])
    assert reply["ok"], reply
    cube, plane = reply["result"]["Cube"], reply["result"]["OpenPlane"]
    assert cube["printable"] and cube["problems"] == []
    assert cube["size_mm"] == [20.0, 20.0, 20.0] and cube["volume_mm3"] == 8000.0
    assert not plane["printable"] and "non-manifold" in plane["problems"][0]


def test_export_stl_writes_binary_stl_with_the_check(blender):
    target = blender["tmp"] / "part.stl"
    reply = send(
        f"result = forge.export_stl({str(target)!r}, 'Cube')", blender["token"]
    )
    assert reply["ok"], reply
    assert reply["result"]["check"]["Cube"]["printable"]
    data = target.read_bytes()
    triangles = struct.unpack("<I", data[80:84])[0]
    assert triangles == 12 and len(data) == 84 + 50 * 12


def test_viewport_shot_says_plainly_there_is_no_window(blender):
    reply = send("forge.viewport_shot('/tmp/x.png')", blender["token"])
    assert not reply["ok"] and "No 3D viewport" in reply["error"]
