"""Files Emerson sends (Relay task 118): shared/forge_attach.py and the
WhatsApp intake (media rows found, saved, their paths put in the message).
The live page grab was checked by hand (WIP.md); these never open Whatsie."""

import base64
from contextlib import contextmanager
from typing import Any

import chat
import forge_attach
import pytest
import store
from channels import Incoming, whatsapp

# ---- shared/forge_attach.py ---------------------------------------------------------


def test_safe_name_keeps_names_inside_the_folder():
    assert forge_attach.safe_name("../../etc/passwd") == "passwd"
    assert forge_attach.safe_name("..\\..\\boot.ini") == "boot.ini"
    assert forge_attach.safe_name("") == "file"
    assert forge_attach.safe_name("...") == "file"
    assert forge_attach.safe_name(".bashrc") == "bashrc"
    assert forge_attach.safe_name("my pic (2).png") == "my pic (2).png"
    assert forge_attach.safe_name("a$b|c.txt") == "a_b_c.txt"
    long = forge_attach.safe_name("x" * 300 + ".jpeg")
    assert len(long) == 120 and long.endswith(".jpeg")


def test_long_names_fit_the_file_system_in_bytes(tmp_path):
    name = forge_attach.safe_name("日本語" * 50 + ".pdf")
    assert name.endswith(".pdf") and len(name.encode()) <= 120
    saved = forge_attach.save(tmp_path, "日本語" * 50 + ".pdf", b"x")
    again = forge_attach.save(tmp_path, "日本語" * 50 + ".pdf", b"y")
    assert saved.read_bytes() == b"x" and again.name.endswith(" (1).pdf")
    assert forge_attach.safe_name("日本語" * 50).encode().__len__() <= 120


def test_save_never_overwrites(tmp_path):
    first = forge_attach.save(tmp_path / "new", "pasted.png", b"one")
    second = forge_attach.save(tmp_path / "new", "pasted.png", b"two")
    third = forge_attach.save(tmp_path / "new", "pasted.png", b"three")
    assert [first.name, second.name, third.name] == [
        "pasted.png",
        "pasted (1).png",
        "pasted (2).png",
    ]
    assert first.read_bytes() == b"one" and third.read_bytes() == b"three"


def test_save_refuses_big_files_and_bad_base64(tmp_path):
    with pytest.raises(ValueError, match="larger"):
        forge_attach.save(tmp_path, "big.bin", b"x" * 11, max_bytes=10)
    with pytest.raises(ValueError, match="not base64"):
        forge_attach.save_base64(tmp_path, "a.txt", "not base64!!")
    with pytest.raises(ValueError, match="larger"):
        forge_attach.save_base64(tmp_path, "a.txt", "QUFB" * 100, max_bytes=10)
    got = forge_attach.save_base64(tmp_path, "a.txt", base64.b64encode(b"hi").decode())
    assert got.read_bytes() == b"hi"
    assert not (tmp_path / "big.bin").exists()


def test_note_and_has_files():
    assert forge_attach.with_note("look", []) == "look"
    text = forge_attach.with_note(" look at this ", ["/a/b.png", "/a/c.pdf"])
    assert text == "look at this\n\nAttached files:\n- /a/b.png\n- /a/c.pdf"
    assert forge_attach.has_files(text)
    assert forge_attach.with_note("", ["/a/b.png"]) == "Attached files:\n- /a/b.png"
    assert not forge_attach.has_files("Attached files: none, just chatting")


def test_inside_only_names_uploaded_files(tmp_path):
    root = tmp_path / "up"
    mine = forge_attach.save(root, "a.txt", b"a")
    (tmp_path / "secret.txt").write_text("no")
    assert forge_attach.inside(root, str(mine)) == mine.resolve()
    assert forge_attach.inside(root, str(root / ".." / "secret.txt")) is None
    assert forge_attach.inside(root, str(tmp_path / "secret.txt")) is None
    assert forge_attach.inside(root, str(root / "missing.txt")) is None
    assert forge_attach.inside(root, str(root)) is None


def test_day_folder_and_types(tmp_path):
    assert forge_attach.day_folder(tmp_path, 0).parent == tmp_path
    assert forge_attach.ext_for("image/jpeg") == ".jpg"
    assert forge_attach.ext_for("text/markdown; charset=utf-8") == ".md"
    assert forge_attach.ext_for("application/x-nope") == ""


# ---- WhatsApp: which rows are files from Emerson ------------------------------------------


def test_media_rows_from_emerson_are_new_but_relays_own_files_are_not():
    state = {}
    whatsapp.pick_new([{"id": "old", "me": True, "text": "hi"}], state)
    found = [
        {"id": "old", "me": True, "text": "hi"},
        {"id": "pic", "me": True, "text": "", "kind": "image"},
        {"id": "cap", "me": True, "text": "this one", "kind": "image"},
        {"id": "sent", "me": True, "text": "", "kind": "document", "file": "x.md"},
        {"id": "them", "me": False, "text": "", "kind": "image"},
        {"id": "blank", "me": True, "text": "", "kind": ""},
    ]
    new = whatsapp.pick_new(found, state, {"sent"})
    assert [m.message_id for m in new] == ["wa:pic", "wa:cap"]
    assert new[1].text == "this one"


class GrabPage:
    """Stands in for WhatsApp Web: a caught Blob of `data`, read in slices."""

    def __init__(self, data: bytes, name="", kind="image/jpeg", how="button"):
        self.data, self.name, self.kind, self.how = data, name, kind, how
        self.disarmed = 0

    def js(self, script):
        if script == whatsapp.GRAB_HOOK:
            return True
        if script == whatsapp.DISARM:
            self.disarmed += 1
            return True
        if script == whatsapp.GRABBED:
            return {"name": self.name, "size": len(self.data), "type": self.kind}
        if script.startswith("(async (id, kind)"):
            return self.how
        if script.startswith("new Promise"):
            start, end = (
                int(n) for n in script.split("slice(")[1].split(")")[0].split(",")
            )
            return base64.b64encode(self.data[start:end]).decode()
        raise AssertionError(script[:60])


def test_grab_reads_the_blob_in_slices(monkeypatch):
    monkeypatch.setattr(whatsapp, "SLICE", 4)
    data = bytes(range(10)) * 3  # 30 bytes: 8 slices
    p: Any = GrabPage(data, name="notes.md", kind="text/markdown")
    assert whatsapp.grab(p, {"id": "x"}) == (data, "notes.md", "text/markdown")
    assert p.disarmed == 1
    with pytest.raises(LookupError):
        gone: Any = GrabPage(b"", how="gone")
        whatsapp.grab(gone, {"id": "x"})


def test_grab_refuses_files_over_the_limit(monkeypatch):
    monkeypatch.setattr(forge_attach, "MAX_BYTES", 5)
    p: Any = GrabPage(b"123456")
    with pytest.raises(ValueError, match="over Relay's limit"):
        whatsapp.grab(p, {"id": "x"})
    assert p.disarmed == 1  # disarmed even when it fails


def test_file_names():
    at = 1791467000.0
    assert (
        whatsapp.file_name({"kind": "document", "file": "plan.pdf"}, "", "")
        == "plan.pdf"
    )
    assert whatsapp.file_name({"kind": "document"}, "given.md", "") == "given.md"
    pic = whatsapp.file_name({"kind": "image"}, "", "image/png", now=at)
    assert pic.startswith("whatsapp-picture-") and pic.endswith(".png")
    assert whatsapp.file_name({"kind": "audio"}, "", "", now=at).endswith(".ogg")
    assert whatsapp.file_name({"kind": "video"}, "", "video/mp4", now=at).endswith(
        ".mp4"
    )


@contextmanager
def no_page(settings):
    yield None


def test_receive_saves_files_and_names_them_in_the_message(monkeypatch):
    monkeypatch.setattr(whatsapp, "page", no_page)
    monkeypatch.setattr(whatsapp, "open_chat", lambda p, name: None)
    pic = Incoming("whatsapp", "me", "", "", message_id="wa:pic")
    doc = Incoming("whatsapp", "me", "", "what is in this", message_id="wa:doc")
    bad = Incoming("whatsapp", "me", "", "", message_id="wa:bad")
    got = {"pic": (b"JPEG", "", "image/jpeg"), "doc": (b"# hi", "plan.md", "")}

    def grabber(p, row):
        if row["id"] == "bad":
            raise TimeoutError("WhatsApp did not hand the file over in time")
        return got[row["id"]]

    whatsapp.receive(
        {"whatsapp_chat": "Indeed"},
        [
            (pic, {"id": "pic", "kind": "image"}),
            (doc, {"id": "doc", "kind": "document", "file": "plan.md"}),
            (bad, {"id": "bad", "kind": "video"}),
        ],
        grabber,
    )
    folder = forge_attach.day_folder(store.path("attachments"))
    assert pic.files and pic.files[0].startswith(str(folder))
    assert open(pic.files[0], "rb").read() == b"JPEG"
    assert pic.text == f"Attached files:\n- {pic.files[0]}"
    assert doc.files == [str(folder / "plan.md")]
    assert doc.text.startswith("what is in this\n\nAttached files:\n- ")
    assert not bad.files
    assert "sent a video" in bad.text and "could not save it" in bad.text


def test_a_failed_page_still_delivers_the_messages(monkeypatch):
    @contextmanager
    def broken(settings):
        raise OSError("Whatsie is not answering")
        yield

    monkeypatch.setattr(whatsapp, "page", broken)
    pic = Incoming("whatsapp", "me", "", "look", message_id="wa:pic")
    whatsapp.receive(
        {"whatsapp_chat": "Indeed"}, [(pic, {"id": "pic", "kind": "image"})]
    )
    assert not pic.files
    assert pic.text.startswith("look\n\n(Emerson sent a picture")
    assert "Whatsie is not answering" in pic.text


def test_a_picture_still_loading_waits_for_its_file():
    state = {"wa_seen": ["old"]}
    old = {"id": "old", "me": True, "text": "hi"}
    blur = {"id": "p", "me": True, "text": "", "kind": "", "media": True}
    assert whatsapp.pick_new([old, blur], state) == []
    assert state["wa_wait"] == {"p": 0}
    # still loading on the next look; a text after it is not held up
    t = {"id": "t", "me": True, "text": "and this"}
    new = whatsapp.pick_new([old, blur, t], state)
    assert [m.message_id for m in new] == ["wa:t"]
    loaded = {**blur, "kind": "image"}
    new = whatsapp.pick_new([old, loaded, t], state)
    assert [m.message_id for m in new] == ["wa:p"] and "wa_wait" not in state
    # one that never loads goes on as a line saying so
    state = {"wa_seen": ["old"]}
    whatsapp.pick_new([old, blur], state)
    got = []
    for _ in range(whatsapp.WAIT_LOOKS):
        got += whatsapp.pick_new([old, blur], state)
    assert [m.message_id for m in got] == ["wa:p"]
    assert "never loaded" in got[0].text and "wa_wait" not in state
    # Relay's own picture, still loading, never waits
    state = {"wa_seen": ["old"]}
    assert whatsapp.pick_new([old, {**blur, "id": "mine"}], state, {"mine"}) == []
    assert "wa_wait" not in state


def test_poll_only_fetches_new_media(monkeypatch):
    rows = [
        {"id": "old", "me": True, "text": "hi"},
        {"id": "t", "me": True, "text": "plain text"},
        {"id": "p", "me": True, "text": "", "kind": "image"},
        {"id": "mine", "me": True, "text": "", "kind": "image"},
    ]
    monkeypatch.setattr(whatsapp, "messages", lambda s: rows)
    monkeypatch.setattr(chat, "sent_files", lambda: ["mine"])
    asked = []
    monkeypatch.setattr(
        whatsapp, "receive", lambda s, media: asked.extend(r["id"] for _, r in media)
    )
    state = {"wa_seen": ["old"]}
    new = whatsapp.poll({}, state)
    assert [m.message_id for m in new] == ["wa:t", "wa:p"]
    assert asked == ["p"]


# ---- where a message with files goes ------------------------------------------------


def test_files_skip_the_text_only_desk():
    store.save_settings({"whatsapp_frontdesk": "jan"})
    task, running = chat.route("hello")
    assert not running and task["status"] == chat.DESK
    task["status"] = "done"
    import items

    items.save(task)
    task, _ = chat.route(forge_attach.with_note("look", ["/tmp/a.png"]))
    assert task["status"] == "queued"


def test_files_with_claude_out_of_usage_stay_local():
    store.save_settings({"whatsapp_frontdesk": "local"})
    st = store.state()
    st["chat_wait"] = "no usage"
    store.save_state(st)
    task, _ = chat.route(forge_attach.with_note("look", ["/tmp/a.png"]))
    assert task["status"] == chat.DESK


# ---- Relay's page: files with a new request -----------------------------------------


@pytest.fixture
def web():
    from fastapi.testclient import TestClient

    import web_app

    return TestClient(web_app.app)


def test_page_upload_and_request_with_files(web):
    data = base64.b64encode(b"%PDF-1").decode()
    got = web.post("/api/attach", json={"name": "spec.pdf", "data": data}).json()
    assert got["name"] == "spec.pdf" and got["bytes"] == 6
    assert got["path"].startswith(str(store.path("attachments")))
    r = web.post("/api/tasks", json={"text": "build it", "files": [got["path"]]})
    assert r.status_code == 200, r.text
    import items

    task = items.find_task(r.json()["task"]["id"])
    assert task is not None
    assert f"build it\n\nAttached files:\n- {got['path']}" in task["body"]
    # a file alone makes a request too; a path Relay did not save does not
    assert (
        web.post("/api/tasks", json={"text": "", "files": [got["path"]]}).status_code
        == 200
    )
    bad = web.post("/api/tasks", json={"text": "x", "files": ["/etc/passwd"]})
    assert bad.status_code == 400
    assert web.post("/api/tasks", json={"text": " "}).status_code == 400
    assert web.post("/api/attach", json={"name": "a", "data": "!!"}).status_code == 400


def test_page_paste_reads_the_desktop_clipboard(web, tmp_path, monkeypatch):
    import sys

    fake = tmp_path / "wl-paste"
    fake.write_text(
        f"#!{sys.executable}\nimport sys\n"
        "if '--list-types' in sys.argv: print('image/jpeg'); sys.exit()\n"
        "sys.stdout.buffer.write(b'JPEGDATA')\n"
    )
    fake.chmod(0o755)
    monkeypatch.setenv("FORGE_WL_PASTE", str(fake))
    r = web.post("/api/attach/paste-image", json={})
    assert r.status_code == 200 and r.json()["name"] == "pasted.jpg"
    monkeypatch.setenv("FORGE_WL_PASTE", str(tmp_path / "missing"))
    assert web.post("/api/attach/paste-image", json={}).status_code == 404
    # a plain form post (what another site can send) is refused
    r = web.post("/api/attach/paste-image", data={"x": "1"})
    assert r.status_code == 415
