"""Files attached to a note on the Board (Relay task 118)."""

import base64

from test_board import client  # noqa: F401  (fixture)


def test_a_note_names_its_attached_files(client, tmp_path, monkeypatch):  # noqa: F811
    c, web_app = client
    monkeypatch.setenv("BOARD_ATTACH_DIR", str(tmp_path / "attachments"))
    data = base64.b64encode(b"%PDF-1").decode()
    got = c.post("/api/attach", json={"name": "../spec.pdf", "data": data}).json()
    assert got["name"] == "spec.pdf" and got["bytes"] == 6
    assert got["path"].startswith(str(tmp_path / "attachments") + "/")
    r = c.post(
        "/api/board/jan/post", json={"text": "read this", "files": [got["path"]]}
    )
    assert r.status_code == 200, r.text
    note = c.get("/api/board/jan").json()["board"]["notes"][-1]
    assert note["text"] == f"read this\n\nAttached files:\n- {got['path']}"
    # a file alone is a note too; a path the Board did not save is not
    assert (
        c.post("/api/board/jan/post", json={"text": "", "files": [got["path"]]})
    ).status_code == 200
    # the same file twice (two clicks on one chip's upload) is named once
    twice = {"text": "again", "files": [got["path"], got["path"]]}
    assert c.post("/api/board/jan/post", json=twice).status_code == 200
    note = c.get("/api/board/jan").json()["board"]["notes"][-1]
    assert note["text"] == f"again\n\nAttached files:\n- {got['path']}"
    r = c.post("/api/board/jan/post", json={"text": "x", "files": ["/etc/passwd"]})
    assert r.status_code == 400
    assert c.post("/api/board/jan/post", json={"text": " "}).status_code == 400


def test_paste_image_needs_json(client):  # noqa: F811
    c, _ = client
    assert c.post("/api/attach/paste-image", data={"x": "1"}).status_code == 415
