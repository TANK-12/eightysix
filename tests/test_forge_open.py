"""shared/forge_open.py: asking a running Forge to show one of its apps.

HOW TO RUN
    apps/acchan/.venv/bin/python -m pytest -q tests/test_forge_open.py
    (stdlib only; any python with pytest works)
"""

from __future__ import annotations

import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shared"))
import forge_open  # noqa: E402


def test_open_reaches_the_running_forge(tmp_path):
    sock = tmp_path / "forge.sock"
    opened = []

    def on_open(name):
        if name == "cosmos":
            opened.append(name)
            return True
        return False

    server = forge_open.serve(on_open, path=sock)
    assert server is not None
    try:
        assert forge_open.request_open("cosmos", path=sock) == "ok"
        assert forge_open.request_open("nope", path=sock) == "unknown"
    finally:
        server.close()
    assert opened == ["cosmos"]


def test_nobody_listening_means_none(tmp_path):
    assert forge_open.request_open("cosmos", path=tmp_path / "forge.sock") is None


def test_a_dead_socket_file_is_replaced(tmp_path):
    sock = tmp_path / "forge.sock"
    dead = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    dead.bind(str(sock))
    dead.close()  # the file stays behind, as after a crash
    assert forge_open.request_open("cosmos", path=sock) is None
    server = forge_open.serve(lambda name: True, path=sock)
    assert server is not None
    try:
        assert forge_open.request_open("cosmos", path=sock) == "ok"
    finally:
        server.close()


def test_a_live_forge_is_not_taken_over(tmp_path):
    sock = tmp_path / "forge.sock"
    first = forge_open.serve(lambda name: True, path=sock)
    assert first is not None
    try:
        assert forge_open.serve(lambda name: False, path=sock) is None
        assert forge_open.request_open("cosmos", path=sock) == "ok"
    finally:
        first.close()


def test_forge_apps_are_discovered(tmp_path):
    (tmp_path / "cosmos").mkdir()
    (tmp_path / "cosmos" / "forge_app.json").write_text(
        '{"name": "cosmos", "label": "Cosmos", "tagline": "space"}'
    )
    (tmp_path / "junk").mkdir()
    (tmp_path / "junk" / "forge_app.json").write_text("{not json")
    found = forge_open.forge_apps(tmp_path)
    assert found == [{"name": "cosmos", "label": "Cosmos", "tagline": "space"}]
