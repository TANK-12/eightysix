"""Files attached in the Relay chat and transcript chats (Relay task 118):
saved by /api/attach, handed over as "Attached files:" lines, and only files
this app saved can be named."""

from __future__ import annotations

import base64
import os
import sys

from test_relay_chat import H, client, fake_cli  # noqa: F401  (fixtures)

SID = "11111111-aaaa-bbbb-cccc-000000000003"


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def upload(client, name, data):
    r = client.post("/api/attach", json={"name": name, "data": b64(data)}, headers=H)
    assert r.status_code == 200, r.text
    return r.json()


def test_upload_saves_in_a_day_folder_without_overwriting(client):
    import web_app

    first = upload(client, "../../shot.png", b"PNG1")
    second = upload(client, "shot.png", b"PNG2")
    assert first["name"] == "shot.png" and second["name"] == "shot (1).png"
    assert first["path"].startswith(str(web_app.ATTACH.root()) + os.sep)
    assert open(first["path"], "rb").read() == b"PNG1" and first["bytes"] == 4
    assert (
        client.post("/api/attach", json={"name": "a", "data": "x"}).status_code == 403
    )
    bad = client.post("/api/attach", json={"name": "a", "data": "!!"}, headers=H)
    assert bad.status_code == 400 and "base64" in bad.json()["detail"]


def test_upload_size_cap(client, monkeypatch):
    import web_app

    monkeypatch.setattr(web_app.ATTACH, "max_bytes", 3)
    r = client.post("/api/attach", json={"name": "a", "data": b64(b"1234")}, headers=H)
    assert r.status_code == 413


def test_relay_chat_sends_the_paths(client, fake_cli):
    got = upload(client, "plan.pdf", b"%PDF")
    r = client.post(
        "/api/relay-chat/say",
        json={"text": "read this", "files": [got["path"]]},
        headers=H,
    )
    assert r.status_code == 200, r.text
    assert fake_cli.read_text() == f"read this\n\nAttached files:\n- {got['path']}"
    # a file alone is a message too
    client.post(
        "/api/relay-chat/say", json={"text": "", "files": [got["path"]]}, headers=H
    )
    assert fake_cli.read_text() == f"Attached files:\n- {got['path']}"
    # nothing at all still is not
    r = client.post("/api/relay-chat/say", json={"text": " ", "files": []}, headers=H)
    assert r.status_code == 400


def test_the_file_list_does_not_count_against_the_text_limit(client, fake_cli):
    got = [upload(client, f"{'n' * 100}-{i}.png", b"P") for i in range(20)]
    r = client.post(
        "/api/relay-chat/say",
        json={"text": "x" * 3990, "files": [g["path"] for g in got]},
        headers=H,
    )
    assert r.status_code == 200, r.text
    assert fake_cli.read_text().count("\n- ") == 20
    r = client.post(
        "/api/relay-chat/say", json={"text": "x" * 4001, "files": []}, headers=H
    )
    assert r.status_code == 400


def test_only_files_this_app_saved_can_be_named(client, fake_cli, tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("no")
    for path in (str(secret), "/etc/passwd", "relative.txt"):
        r = client.post(
            "/api/relay-chat/say", json={"text": "hi", "files": [path]}, headers=H
        )
        assert r.status_code == 400 and "attach it again" in r.json()["detail"]
    got = upload(client, "a.txt", b"a")
    r = client.post(
        "/api/relay-chat/say",
        json={"text": "hi", "files": [got["path"]] * 21},
        headers=H,
    )
    assert r.status_code == 400


def test_session_say_appends_the_paths(client, monkeypatch):
    from mc import actions

    seen = {}

    def say(session_id, text, **kw):
        seen["text"] = text
        return {"via": "board", "id": 7}

    monkeypatch.setattr(actions, "say", say)
    got = upload(client, "pasted.png", b"PNG")
    r = client.post(
        f"/api/sessions/{SID}/say", json={"text": "", "files": [got["path"]]}, headers=H
    )
    assert r.status_code == 200, r.text
    assert seen["text"] == f"Attached files:\n- {got['path']}"


def test_paste_image_reads_the_desktop_clipboard(client, tmp_path, monkeypatch):
    fake = tmp_path / "wl-paste"
    png = b"\x89PNG\r\n\x1a\nfake"
    fake.write_text(
        f"#!{sys.executable}\n"
        "import sys\n"
        "if '--list-types' in sys.argv: print('image/png'); sys.exit()\n"
        f"sys.stdout.buffer.write({png!r})\n"
    )
    fake.chmod(0o755)
    monkeypatch.setenv("FORGE_WL_PASTE", str(fake))
    r = client.post("/api/attach/paste-image", json={}, headers=H)
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "pasted.png"
    assert open(r.json()["path"], "rb").read() == png
    empty = tmp_path / "wl-empty"
    empty.write_text(f"#!{sys.executable}\nprint('text/plain')\n")
    empty.chmod(0o755)
    monkeypatch.setenv("FORGE_WL_PASTE", str(empty))
    assert client.post("/api/attach/paste-image", json={}, headers=H).status_code == 404
