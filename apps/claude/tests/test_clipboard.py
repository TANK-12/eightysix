"""A24: images through the desktop clipboard (wl-paste / wl-copy), with fake
binaries standing in so the real clipboard is never touched."""

import base64
import os
import stat
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import clipboard
import runner
import web_app

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)
FORGE = {"X-Forge": "1"}


def fake_bin(path: Path, body: str) -> Path:
    path.write_text(f"#!{sys.executable}\n{body}")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


@pytest.fixture
def board(tmp_path, monkeypatch):
    """A fake clipboard: types listed in types.txt, the image in image.bin,
    and whatever wl-copy is handed lands in copied.bin with its type."""
    (tmp_path / "types.txt").write_text("text/html\nimage/png\n")
    (tmp_path / "image.bin").write_bytes(PNG)
    paste = fake_bin(
        tmp_path / "wl-paste",
        f"""import sys
d = {str(tmp_path)!r}
if "--list-types" in sys.argv:
    sys.stdout.write(open(d + "/types.txt").read())
else:
    sys.stdout.buffer.write(open(d + "/image.bin", "rb").read())
""",
    )
    copy = fake_bin(
        tmp_path / "wl-copy",
        f"""import sys
d = {str(tmp_path)!r}
open(d + "/copied.bin", "wb").write(sys.stdin.buffer.read())
open(d + "/copied.type", "w").write(sys.argv[sys.argv.index("--type") + 1])
""",
    )
    monkeypatch.setenv("FORGE_WL_PASTE", str(paste))
    monkeypatch.setenv("FORGE_WL_COPY", str(copy))
    return tmp_path


def test_an_image_on_the_clipboard_is_read_with_its_type(board):
    assert clipboard.read_image() == (PNG, "image/png")


def test_text_only_on_the_clipboard_gives_no_image(board):
    (board / "types.txt").write_text("text/plain\nSTRING\n")
    assert clipboard.read_image() is None


def test_no_clipboard_tool_gives_no_image(board, monkeypatch):
    monkeypatch.setenv("FORGE_WL_PASTE", str(board / "missing"))
    assert clipboard.read_image() is None


def test_an_image_is_copied_with_its_type(board):
    clipboard.write_image(PNG, "image/png")
    assert (board / "copied.bin").read_bytes() == PNG
    assert (board / "copied.type").read_text() == "image/png"


def test_copying_something_that_is_not_an_image_is_refused(board):
    with pytest.raises(ValueError):
        clipboard.write_image(b"hello", "text/plain")


@pytest.fixture
def client(board, monkeypatch):
    monkeypatch.setenv(
        "FORGE_CLAUDE_BIN",
        f"{sys.executable} {Path(__file__).with_name('fake_claude.py')}",
    )
    monkeypatch.setattr(web_app, "conversations", runner.Registry(board / "data"))
    return TestClient(web_app.app)


def new_conversation(client) -> str:
    return client.post("/api/conversations", json={}, headers=FORGE).json()["id"]


def test_pasting_attaches_the_clipboard_image_and_it_can_be_shown(client):
    cid = new_conversation(client)
    saved = client.post(f"/api/conversations/{cid}/paste-image", headers=FORGE).json()
    assert saved["name"].endswith(".png") and saved["bytes"] == len(PNG)
    shown = client.get(f"/api/conversations/{cid}/files/{saved['name']}")
    assert shown.status_code == 200 and shown.content == PNG
    assert shown.headers["content-type"] == "image/png"


def test_pasting_with_no_image_says_so(client, board):
    (board / "types.txt").write_text("text/plain\n")
    cid = new_conversation(client)
    assert (
        client.post(f"/api/conversations/{cid}/paste-image", headers=FORGE).status_code
        == 404
    )


def test_only_a_conversations_own_images_are_served(client):
    cid = new_conversation(client)
    client.post(
        f"/api/conversations/{cid}/files",
        json={"name": "notes.txt", "data": base64.b64encode(b"secret").decode()},
        headers=FORGE,
    )
    assert client.get(f"/api/conversations/{cid}/files/notes.txt").status_code == 404
    assert (
        client.get(f"/api/conversations/{cid}/files/..%2F..%2Fx.png").status_code == 404
    )


def test_copy_route_puts_an_image_on_the_clipboard(client, board):
    body = {"data": base64.b64encode(PNG).decode(), "media": "image/png"}
    assert client.post("/api/clipboard/image", json=body).status_code == 403
    assert (
        client.post("/api/clipboard/image", json=body, headers=FORGE).status_code == 200
    )
    assert (board / "copied.bin").read_bytes() == PNG
