"""Edge cases a critic found: odd file names, odd snapshot names, unreadable
sets, eject failing, merge diffs, unusual ref names, big folders, low space."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import backup  # noqa: E402
import browse  # noqa: E402
from test_browse import IS_ROOT, NOW, STAMP2, drive  # noqa: E402,F401


def as_json(data) -> bytes:
    """What FastAPI sends: fails on a name JSON cannot carry."""
    return json.dumps(data, ensure_ascii=False).encode("utf-8")


def test_non_utf8_names_list_but_do_not_open(drive):  # noqa: F811
    folder = drive["disk"] / "vault" / "forge" / STAMP2 / "Forge"
    bad = os.fsencode(folder) + b"/caf\xe9.txt"
    with open(bad, "wb") as f:
        f.write(b"x")
    os.symlink(b"/tmp/\xff", os.fsencode(folder) + b"/odd-link")
    d = browse.list_dir(drive["cfg"], "vault", "forge", STAMP2, "Forge")
    as_json(d)
    names = {e["name"]: e for e in d["entries"]}
    assert names["caf�.txt"]["openable"] is False
    assert names["same.txt"]["openable"] is True
    assert names["odd-link"]["target"] == "/tmp/�"
    as_json(browse.compare(drive["cfg"], "vault", "forge", STAMP2, "Forge"))
    # a folder holding it still copies back whole
    job = browse.restore(drive["cfg"], "vault", "forge", STAMP2, "Forge")
    import test_browse

    done = test_browse.wait_job(job["id"])
    assert done["state"] == "done" and not done["skipped"]
    assert os.path.exists(os.fsencode(done["dest"]) + b"/caf\xe9.txt")


def test_bad_snapshot_names_are_ignored(drive):  # noqa: F811
    set_dir = drive["disk"] / "vault" / "forge"
    (set_dir / "2026-13-45_999999").mkdir()
    (set_dir / "2026-02-30_120000.partial").mkdir()
    assert backup.parse_stamp("2026-13-45_999999") is None
    assert backup.parse_stamp(STAMP2) is not None
    assert all(backup.parse_stamp(p.name) for p in backup.snapshots(set_dir))
    st = browse.status(drive["cfg"], NOW)
    vault = next(a for a in st["areas"] if a["name"] == "vault")
    assert vault["sets"][0]["count"] == 2
    names = [s["name"] for s in browse.list_sets(drive["cfg"], "vault")[0]["snapshots"]]
    assert "2026-13-45_999999" not in names and "2026-02-30_120000.partial" not in names
    with pytest.raises(browse.BadInput):
        browse.list_dir(drive["cfg"], "vault", "forge", "2026-13-45_999999", "")


@pytest.mark.skipif(IS_ROOT, reason="root reads everything")
def test_unreadable_set_says_needs_admin(drive):  # noqa: F811
    set_dir = drive["disk"] / "vault" / "forge"
    set_dir.chmod(0)
    try:
        st = browse.status(drive["cfg"], NOW)
        vault = next(a for a in st["areas"] if a["name"] == "vault")
        assert vault["sets"][0]["needs_admin"] is True
        assert vault["due"] is None
        as_json(st)
    finally:
        set_dir.chmod(0o755)


def test_eject_failure_is_reported(drive, monkeypatch):  # noqa: F811
    units = drive["units"]

    def failing(cmd, timeout=30):
        if cmd[0] == sys.executable:
            return subprocess.CompletedProcess(
                cmd, 1, b"still mounted, sudo umount", b""
            )
        return units(cmd, timeout)

    monkeypatch.setattr(browse, "run_cmd", failing)
    with pytest.raises(browse.BadInput, match="sudo umount"):
        browse.eject(drive["cfg"])


def git_in(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=T", "-c", "user.email=t@t", *args],
        check=True,
        capture_output=True,
    )


def test_merge_diff_refs_and_tags(drive):  # noqa: F811
    repo = drive["live"] / "merge"
    repo.mkdir()
    git_in(repo, "init", "-q", "-b", "main")
    (repo / "a.txt").write_text("a\n")
    git_in(repo, "add", ".")
    git_in(repo, "commit", "-q", "-m", "base")
    git_in(repo, "checkout", "-q", "-b", "feat+x")
    (repo / "b.txt").write_text("from the branch\n")
    git_in(repo, "add", ".")
    git_in(repo, "commit", "-q", "-m", "on feat+x")
    git_in(repo, "checkout", "-q", "main")
    git_in(repo, "merge", "-q", "--no-ff", "-m", "merge feat+x", "feat+x")
    git_in(repo, "branch", "ünï")
    blob = subprocess.run(
        ["git", "-C", str(repo), "hash-object", "-w", "a.txt"],
        capture_output=True,
        text=True,
    ).stdout.strip()
    git_in(repo, "tag", "blobtag", blob)
    git_in(repo, "tag", "-a", "-m", "v1", "v1.0")
    git_dir = drive["disk"] / "vault" / "git"
    assert backup.mirror_repo(repo, git_dir)
    mirror = git_dir / backup.mirror_name(repo)

    merged = browse.commit(mirror, "main")
    assert len(merged["parents"]) == 2
    assert "from the branch" in merged["diff"]
    assert [f["name"] for f in merged["files"]] == ["b.txt"]

    for name in ("feat+x", "ünï", "v1.0"):
        assert len(browse.resolve(mirror, name)) == 40
    for bad in ("-n1", "a b", "x\ty", "main..feat+x", "--all"):
        with pytest.raises(browse.BadInput):
            browse.resolve(mirror, bad)
    refs = browse.refs(mirror)
    assert {t["name"] for t in refs["tags"]} == {"v1.0"}
    assert {"feat+x", "ünï", "main"} <= {b["name"] for b in refs["branches"]}


def test_empty_mirror_has_no_refs(drive):  # noqa: F811
    git_dir = drive["disk"] / "vault" / "git"
    subprocess.run(
        ["git", "init", "-q", "--bare", str(git_dir / "empty.git")], check=True
    )
    found = {r["name"]: r for r in browse.repos(drive["cfg"])}
    assert found["empty.git"]["branches"] == 0
    refs = browse.refs(browse.repo_path(drive["cfg"], "empty.git"))
    assert refs["branches"] == [] and refs["tags"] == []


def test_big_folder_sorts_then_pages(drive, monkeypatch):  # noqa: F811
    folder = drive["disk"] / "vault" / "forge" / STAMP2 / "Forge" / "many"
    folder.mkdir()
    for name in ("d", "b", "e", "a", "c"):
        (folder / f"{name}.txt").write_text(name)
    (folder / "zdir").mkdir()
    monkeypatch.setattr(browse, "LIST_LIMIT", 3)
    first = browse.list_dir(drive["cfg"], "vault", "forge", STAMP2, "Forge/many")
    assert [e["name"] for e in first["entries"]] == ["zdir", "a.txt", "b.txt"]
    assert first["more"] and first["total"] == 6
    second = browse.list_dir(drive["cfg"], "vault", "forge", STAMP2, "Forge/many", 3)
    assert [e["name"] for e in second["entries"]] == ["c.txt", "d.txt", "e.txt"]
    assert not second["more"]


def test_restore_keeps_free_space(drive, monkeypatch):  # noqa: F811
    monkeypatch.setattr(browse, "MIN_FREE", 1e18)
    with pytest.raises(browse.BadInput, match="free space"):
        browse.restore(drive["cfg"], "vault", "forge", STAMP2, "Forge/same.txt")
    import test_browse

    job = test_browse.wait_job(
        browse.restore(drive["cfg"], "vault", "forge", STAMP2, "Forge")["id"]
    )
    assert job["state"] == "failed" and "free space" in job["error"]


def test_backup_eject_says_how_when_root_mounted(monkeypatch, capsys, tmp_path):
    dev = tmp_path / "sdb1"
    dev.write_text("")
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        out = "/mnt/forge-drive/rescue\n" if cmd[0] == "findmnt" else ""
        return subprocess.CompletedProcess(cmd, 1 if cmd[0] == "umount" else 0, out, "")

    monkeypatch.setattr(backup.subprocess, "run", fake_run)
    real_exists = Path.exists
    monkeypatch.setattr(
        Path,
        "exists",
        lambda p: True if str(p).startswith("/dev/disk/by-label") else real_exists(p),
    )
    cfg = {"areas": {"rescue": {"label": "Rescue"}}}
    assert backup.eject(cfg) == 1
    out = capsys.readouterr().out
    assert "sudo umount /mnt/forge-drive/rescue" in out
    assert not any(c[:2] == ["udisksctl", "power-off"] for c in calls)


def test_run_unmounts_what_it_mounted(monkeypatch):
    calls = []
    monkeypatch.setattr(
        backup.subprocess,
        "run",
        lambda cmd, **kw: calls.append(cmd) or subprocess.CompletedProcess(cmd, 0),
    )
    backup.MOUNTED_HERE[:] = [Path("/mnt/forge-drive/vault")]
    backup.unmount_ours()
    assert ["umount", "/mnt/forge-drive/vault"] in calls
    assert backup.MOUNTED_HERE == []


# ---------------------------------------------------------------- critic 2


def test_link_with_non_utf8_target_reads(drive):  # noqa: F811
    snap = drive["disk"] / "vault" / "forge" / STAMP2
    os.symlink(b"/tmp/\xff", os.fsencode(snap / "badlink"))
    view = browse.read_file(drive["cfg"], "vault", "forge", STAMP2, "badlink")
    assert view["kind"] == "link" and "�" in view["target"]
    as_json(view)


def test_one_unreadable_set_does_not_block_the_area(drive):  # noqa: F811
    set_dir = drive["disk"] / "vault" / "forge"
    set_dir.chmod(0)
    try:
        sets = browse.list_sets(drive["cfg"], "vault")
        forge = next(s for s in sets if s["name"] == "forge")
        assert forge["needs_admin"] is True and forge["snapshots"] == []
    finally:
        set_dir.chmod(0o755)


def test_compare_needs_admin_when_it_cannot_look(drive):  # noqa: F811
    snap = drive["disk"] / "vault" / "forge" / STAMP2
    (snap / "Forge" / "locked").mkdir()
    (snap / "Forge" / "locked" / "x.txt").write_text("x")
    live = drive["live"] / "Forge" / "locked"
    live.mkdir()
    (live / "x.txt").write_text("x")
    live.chmod(0)
    try:
        out = browse.compare(
            drive["cfg"], "vault", "forge", STAMP2, "Forge/locked/x.txt"
        )
        assert out["state"] == "needs_admin"
    finally:
        live.chmod(0o755)


def test_unreadable_mirrors_need_admin(drive):  # noqa: F811
    git_dir = drive["disk"] / "vault" / "git"
    git_dir.chmod(0)
    try:
        with pytest.raises(browse.NeedsAdmin):
            browse.repos(drive["cfg"])
    finally:
        git_dir.chmod(0o755)


def test_entries_that_cannot_be_read_are_listed(drive):  # noqa: F811
    folder = drive["disk"] / "vault" / "forge" / STAMP2 / "Forge"
    folder.chmod(0o644)  # names readable, but nothing inside can be looked at
    try:
        out = browse.list_dir(drive["cfg"], "vault", "forge", STAMP2, "Forge")
        assert out["total"] == 5
        assert all(e["readable"] is False for e in out["entries"])
    finally:
        folder.chmod(0o755)


def test_due_is_shown_per_set(drive):  # noqa: F811
    st = browse.status(drive["cfg"], NOW)
    vault = next(a for a in st["areas"] if a["name"] == "vault")
    assert vault["sets"][0]["due"] in (True, False)


def test_after_eject_pages_do_not_mount_again(monkeypatch):
    cfg = backup.load_config()
    monkeypatch.delenv("BACKUP_DRIVE_DIR", raising=False)
    monkeypatch.setattr(browse, "EJECTED", set())
    monkeypatch.setattr(browse, "label_present", lambda label: True)
    asked: list[bool] = []

    def find_mount(label, mount_root, mount=True):
        asked.append(mount)
        return None

    monkeypatch.setattr(browse.backup, "find_mount", find_mount)
    ok = subprocess.CompletedProcess([], 0, b"Ejected.", b"")
    monkeypatch.setattr(browse, "run_cmd", lambda cmd, timeout=30: ok)
    monkeypatch.setattr(browse, "units", lambda cfg: [])
    browse.eject(cfg)
    asked.clear()
    st = browse.status(cfg)
    assert asked and not any(asked)
    assert "ejected" in st["message"]
    with pytest.raises(browse.NoDrive, match="ejected"):
        browse.need_mount(cfg, "vault")
    # unplugged: forgotten, so the next plug-in mounts as usual
    monkeypatch.setattr(browse, "label_present", lambda label: False)
    browse.status(cfg)
    assert browse.EJECTED == set()


def test_eject_waits_for_a_copy(drive, monkeypatch):  # noqa: F811
    monkeypatch.setitem(browse.JOBS, "x", {"state": "copying"})
    with pytest.raises(browse.Busy, match="copy"):
        browse.eject(drive["cfg"])


def test_restore_never_writes_through_a_link(drive):  # noqa: F811
    top = drive["tmp"] / "Restored" / STAMP2 / "forge"
    top.mkdir(parents=True)
    elsewhere = drive["tmp"] / "elsewhere"
    elsewhere.mkdir()
    (top / "Forge").symlink_to(elsewhere)
    with pytest.raises(browse.BadInput, match="link"):
        browse.restore(drive["cfg"], "vault", "forge", STAMP2, "Forge/same.txt")
    assert list(elsewhere.iterdir()) == []
