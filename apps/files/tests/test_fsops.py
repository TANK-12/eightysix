"""File operations: trash never deletes, nothing escapes the allowed roots."""

from __future__ import annotations

import os
import re
import shutil
import sys
import uuid
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

import fsops  # noqa: E402


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setenv("FILES_ROOTS", str(tmp_path))
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "one.txt").write_text("hello")
    (tmp_path / "a" / ".secret").write_text("x")
    (tmp_path / "b").mkdir()
    return tmp_path


@pytest.fixture
def home_root(monkeypatch):
    """A folder on the home drive, where gio trash works, with its own trash
    (XDG_DATA_HOME) so tests never touch Emerson's real one."""
    base = APP / "tests" / f".scratch-{uuid.uuid4().hex[:6]}"
    (base / "data").mkdir(parents=True)
    (base / "files").mkdir()
    monkeypatch.setenv("FILES_ROOTS", str(base / "files"))
    monkeypatch.setenv("XDG_DATA_HOME", str(base / "data"))
    # without gvfs, whose metadata daemon would write into the folder after
    # it is removed and leave .scratch-* folders behind
    monkeypatch.setenv("GIO_USE_VFS", "local")
    yield base
    shutil.rmtree(base)


# ------------------------------------------------------------ path escapes


@pytest.mark.parametrize(
    "raw", ["/etc/passwd", "/", "relative/path", "", "/tmp/../etc", "a\x00b"]
)
def test_resolve_refuses_outside(root, raw):
    with pytest.raises(fsops.FsError):
        fsops.resolve(raw)


def test_resolve_refuses_dotdot_escape(root):
    with pytest.raises(fsops.FsError):
        fsops.resolve(str(root / "a" / ".." / ".." / "etc"))


def test_resolve_refuses_symlink_out(root):
    (root / "a" / "out").symlink_to("/etc")
    with pytest.raises(fsops.FsError):
        fsops.list_dir(str(root / "a" / "out"))
    with pytest.raises(fsops.FsError):
        fsops.read_text(str(root / "a" / "out" / "hostname"))


def test_rename_cannot_move_elsewhere(root):
    for bad in ("../x", "/etc/x", "..", "a/b", ""):
        with pytest.raises(fsops.FsError):
            fsops.rename(str(root / "a" / "one.txt"), bad)
    assert (root / "a" / "one.txt").exists()


def test_transfer_refuses_dest_outside(root):
    with pytest.raises(fsops.FsError):
        fsops.start_transfer("copy", [str(root / "a" / "one.txt")], "/tmp", wait=True)


def test_roots_themselves_are_protected(root):
    with pytest.raises(fsops.FsError):
        fsops.rename(str(root), "x")
    out = fsops.trash([str(root)])
    assert out["trashed"] == [] and root.exists()


# ------------------------------------------------------------ trash, never delete


def test_module_has_no_delete_calls():
    src = (APP / "fsops.py").read_text()
    code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
    code = re.sub(r'""".*?"""', "", code, flags=re.S)
    # The one allowed removal: a restored item's .trashinfo record (the trash
    # spec drops it when the item leaves the trash), fenced in _drop_trashinfo.
    code = code.replace("os.unlink(info)", "", 1)
    for bad in (".unlink(", "os.remove(", "rmtree(", ".rmdir(", "os.rmdir("):
        assert bad not in code, bad


def test_trash_moves_to_trash(home_root):
    f = home_root / "files" / "gone.txt"
    f.write_text("bye")
    d = home_root / "files" / "dir"
    d.mkdir()
    (d / "inner.txt").write_text("x")
    out = fsops.trash([str(f), str(d)])
    assert out["failed"] == [], out
    assert not f.exists() and not d.exists()
    trashed = {p.name for p in (home_root / "data" / "Trash" / "files").iterdir()}
    assert {"gone.txt", "dir"} <= trashed
    assert (home_root / "data" / "Trash" / "files" / "dir" / "inner.txt").exists()


def test_trash_failure_keeps_file(root):
    # /tmp is tmpfs: gio refuses to trash there, and the file must stay.
    f = root / "a" / "one.txt"
    out = fsops.trash([str(f)])
    assert out["trashed"] == []
    assert out["failed"] and out["failed"][0]["error"]
    assert f.read_text() == "hello"


def test_trash_symlink_trashes_link_not_target(home_root):
    target = home_root / "files" / "real.txt"
    target.write_text("keep")
    link = home_root / "files" / "link.txt"
    link.symlink_to(target)
    out = fsops.trash([str(link)])
    assert out["failed"] == []
    assert target.read_text() == "keep" and not os.path.lexists(link)


# ------------------------------------------------------------ listing and edits


def test_list_hides_dotfiles_unless_asked(root):
    names = {i["name"] for i in fsops.list_dir(str(root / "a"))["items"]}
    assert names == {"one.txt"}
    names = {i["name"] for i in fsops.list_dir(str(root / "a"), hidden=True)["items"]}
    assert names == {"one.txt", ".secret"}


def test_list_parent_stops_at_root(root):
    assert fsops.list_dir(str(root))["parent"] is None
    assert fsops.list_dir(str(root / "a"))["parent"] == str(root)


def test_mkdir_and_rename(root):
    p = fsops.make_folder(str(root / "b"), "New")
    assert Path(p).is_dir()
    with pytest.raises(fsops.FsError):
        fsops.make_folder(str(root / "b"), "New")
    q = fsops.rename(p, "Renamed")
    assert Path(q).is_dir() and not Path(p).exists()
    with pytest.raises(fsops.FsError):
        fsops.rename(str(root / "a" / "one.txt"), ".secret")


def test_unique_dest(root):
    a = root / "a"
    assert fsops.unique_dest(a, "one.txt").name == "one (copy).txt"
    (a / "one (copy).txt").write_text("")
    assert fsops.unique_dest(a, "one.txt").name == "one (copy 2).txt"
    assert fsops.unique_dest(a, ".secret").name == ".secret (copy)"
    assert fsops.unique_dest(a, "fresh.txt").name == "fresh.txt"


def test_copy_and_move(root):
    job = fsops.start_transfer("copy", [str(root / "a")], str(root / "b"), wait=True)
    assert job.state == "done", job.error
    assert (root / "b" / "a" / "one.txt").read_text() == "hello"
    assert job.done == job.total > 0
    # Copying into the same folder makes a copy beside it.
    job = fsops.start_transfer(
        "copy", [str(root / "a" / "one.txt")], str(root / "a"), wait=True
    )
    assert (root / "a" / "one (copy).txt").exists()
    job = fsops.start_transfer(
        "move", [str(root / "a" / "one.txt")], str(root / "b"), wait=True
    )
    assert job.state == "done"
    assert (root / "b" / "one.txt").exists() and not (root / "a" / "one.txt").exists()


def test_move_onto_own_folder_is_noop(root):
    job = fsops.start_transfer(
        "move", [str(root / "a" / "one.txt")], str(root / "a"), wait=True
    )
    assert job.state == "done" and (root / "a" / "one.txt").exists()
    assert not (root / "a" / "one (copy).txt").exists()


def test_cannot_copy_folder_into_itself(root):
    with pytest.raises(fsops.FsError):
        fsops.start_transfer("copy", [str(root / "a")], str(root / "a"), wait=True)
    (root / "a" / "sub").mkdir()
    with pytest.raises(fsops.FsError):
        fsops.start_transfer(
            "move", [str(root / "a")], str(root / "a" / "sub"), wait=True
        )


def test_search(root):
    (root / "b" / "deep").mkdir()
    (root / "b" / "deep" / "One-more.md").write_text("")
    names = sorted(i["name"] for i in fsops.search(str(root), "one")["items"])
    assert names == ["One-more.md", "one.txt"]
    assert fsops.search(str(root), "secret")["items"] == []
    assert len(fsops.search(str(root), "secret", hidden=True)["items"]) == 1


def test_read_text_and_binary(root):
    assert fsops.read_text(str(root / "a" / "one.txt"))["text"] == "hello"
    (root / "a" / "bin").write_bytes(b"\x00\x01\x02")
    assert fsops.read_text(str(root / "a" / "bin"))["binary"] is True


def test_places_has_home_and_forge():
    out = fsops.places()
    labels = [p["label"] for p in out["places"]]
    assert labels[0] == "Home"
    assert "Forge" in labels


def test_kind_of():
    k = fsops.kind_of
    assert k(Path("x.png"), False) == "image"
    assert k(Path("x.mkv"), False) == "video"
    assert k(Path("x.flac"), False) == "audio"
    assert k(Path("x.py"), False) == "text"
    assert k(Path("x"), True) == "folder"


# ------------------------------------------------------------ trash restore and archives


def test_restore_puts_a_trashed_file_back(home_root):
    f = home_root / "files" / "back.txt"
    f.write_text("again")
    fsops.trash([str(f)])
    trash_files = home_root / "data" / "Trash" / "files"
    out = fsops.restore([str(trash_files / "back.txt")])
    assert out == {"restored": [str(f)], "failed": []}
    assert f.read_text() == "again"
    assert not (trash_files / "back.txt").exists()
    assert list((home_root / "data" / "Trash" / "info").iterdir()) == []


def test_restore_never_overwrites_and_recreates_the_folder(home_root):
    d = home_root / "files" / "sub"
    d.mkdir()
    (d / "x.txt").write_text("old")
    fsops.trash([str(d / "x.txt")])
    (d / "x.txt").write_text("new one")
    out = fsops.restore([str(home_root / "data" / "Trash" / "files" / "x.txt")])
    assert (d / "x.txt").read_text() == "new one"
    assert Path(out["restored"][0]).read_text() == "old"
    fsops.trash([str(d)])
    out = fsops.restore([str(home_root / "data" / "Trash" / "files" / "sub")])
    assert out["failed"] == [] and (d / "x.txt").read_text() == "new one"


def test_restore_refuses_things_outside_the_trash(home_root):
    f = home_root / "files" / "here.txt"
    f.write_text("stay")
    out = fsops.restore([str(f)])
    assert out["restored"] == [] and out["failed"][0]["error"]
    assert f.read_text() == "stay"


def test_compress_then_extract_round_trip(root):
    (root / "a" / "two.txt").write_text("world")
    job = fsops.start_archive(
        "compress",
        [str(root / "a" / "one.txt"), str(root / "a" / "two.txt")],
        wait=True,
    )
    assert job.state == "done", job.error
    zipped = Path(job.results[0])
    assert zipped.parent == root / "a" and zipped.suffix == ".zip"
    job = fsops.start_archive("extract", [str(zipped)], wait=True)
    assert job.state == "done", job.error
    out = Path(job.results[0])
    assert out.is_dir() and out.parent == root / "a"
    assert (out / "one.txt").read_text() == "hello"
    assert (out / "two.txt").read_text() == "world"


def test_compress_needs_one_folder(root):
    with pytest.raises(fsops.FsError):
        fsops.start_archive(
            "compress", [str(root / "a" / "one.txt"), str(root / "b")], wait=True
        )


def test_extract_of_a_broken_archive_reports_an_error(root):
    bad = root / "a" / "broken.zip"
    bad.write_text("not a zip")
    job = fsops.start_archive("extract", [str(bad)], wait=True)
    assert job.state == "error" and job.error


def test_pdf_gets_a_thumbnail(root, monkeypatch, tmp_path):
    if not shutil.which("pdftoppm"):
        pytest.skip("no pdftoppm")
    monkeypatch.setattr(fsops, "OWN_THUMBS", tmp_path / "thumbs")
    pdf = root / "a" / "doc.pdf"
    pdf.write_bytes(MINI_PDF)
    out = fsops.thumbnail(str(pdf))
    assert out is not None and out.is_file() and out.read_bytes()[:2] == b"\xff\xd8"


MINI_PDF = (
    b"%PDF-1.1\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n"
    b"trailer<</Root 1 0 R>>\n%%EOF\n"
)
