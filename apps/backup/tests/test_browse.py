"""browse.py against a fake drive in a temp folder (BACKUP_DRIVE_DIR), a real
git mirror made by backup.mirror_repo, and systemctl/journalctl swapped out,
so no test touches the real drive or a running backup."""

import datetime as dt
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import backup  # noqa: E402
import browse  # noqa: E402

STAMP1 = "2026-10-07_120000"
STAMP2 = "2026-10-08_120000"
NOW = dt.datetime(2026, 10, 8, 18, 0, 0)
IS_ROOT = os.geteuid() == 0
REAL_RUN = browse.run_cmd


def make_cfg(tmp_path: Path, live: Path) -> dict:
    return {
        "lock": str(tmp_path / "lock"),
        "status_file": str(tmp_path / "status.json"),
        "mount_root": str(tmp_path / "mnt"),
        "areas": {
            "rescue": {
                "label": "Rescue",
                "about": "whole system",
                "every_hours": 48,
                "keep": 8,
                "min_free_gb": 1,
                "rsync": ["-a"],
                "sets": [
                    {"name": "system", "items": [{"from": str(live), "to": "root"}]}
                ],
            },
            "vault": {
                "label": "Vault",
                "about": "work",
                "every_hours": 24,
                "keep": 30,
                "min_free_gb": 1,
                "rsync": ["-a"],
                "sets": [
                    {
                        "name": "forge",
                        "items": [
                            {"from": str(live / "Forge"), "to": "Forge"},
                            {"from": str(live / "one.json"), "to": "one.json"},
                        ],
                    }
                ],
                "git": [str(live / "repo")],
            },
        },
    }


class Units:
    """Stands in for systemctl and journalctl; git still runs for real."""

    def __init__(self, running: bool = False):
        self.running = running
        self.calls: list[list[str]] = []

    def __call__(self, cmd, timeout=30):
        self.calls.append(list(cmd))
        if cmd[0] == "systemctl" and cmd[1] == "show":
            blocks = []
            for unit in cmd[3:]:
                state = (
                    "activating"
                    if self.running and unit == "forge-backup-now@all.service"
                    else "inactive"
                )
                blocks.append(f"Id={unit}\nActiveState={state}\nSubState=dead\n")
            out = "\n".join(blocks)
            return subprocess.CompletedProcess(cmd, 0, out.encode(), b"")
        if cmd[0] == "systemctl":
            return subprocess.CompletedProcess(cmd, 0, b"", b"")
        if cmd[0] == "journalctl":
            return subprocess.CompletedProcess(cmd, 0, b"line one\nline two\n", b"")
        if cmd[0] == sys.executable:
            return subprocess.CompletedProcess(cmd, 0, b"ejected", b"")
        return REAL_RUN(cmd, timeout)


@pytest.fixture
def drive(tmp_path, monkeypatch):
    """Live files, a fake drive with snapshots, and a git mirror."""
    live = tmp_path / "live"
    (live / "Forge" / "app").mkdir(parents=True)
    (live / "Forge" / "app" / "notes.txt").write_text("one\ntwo\nthree\n")
    (live / "Forge" / "same.txt").write_text("unchanged\n")
    (live / "one.json").write_text("{}")

    disk = tmp_path / "drive"
    snap = disk / "vault" / "forge" / STAMP2
    (snap / "Forge" / "app").mkdir(parents=True)
    (snap / "Forge" / "app" / "notes.txt").write_text("one\nTWO\nthree\n")
    (snap / "Forge" / "same.txt").write_text("unchanged\n")
    (snap / "Forge" / "gone.txt").write_text("deleted on the laptop\n")
    (snap / "Forge" / "blob.bin").write_bytes(b"\0\1\2" * 100)
    (snap / "Forge" / "pic.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (snap / "one.json").write_text("{}")
    (disk / "vault" / "forge" / STAMP1).mkdir()
    (disk / "vault" / "forge" / "2026-10-08_170000.partial").mkdir()
    (disk / "vault" / "last-run.json").write_text('{"ok": true, "seconds": 5}')

    root = disk / "rescue" / "system" / STAMP2 / "root"
    (root / "secret").mkdir(parents=True)
    (root / "secret" / "shadow").write_text("x")
    (root / "open.txt").write_text("hello")
    (root / "etc").symlink_to("/etc")
    if not IS_ROOT:
        (root / "secret").chmod(0)

    repo = live / "repo"
    repo.mkdir()
    g = ["git", "-C", str(repo), "-c", "user.name=T", "-c", "user.email=t@t"]
    subprocess.run([*g, "init", "-q", "-b", "main"], check=True)
    (repo / "README.md").write_text("# Hello\n\nfirst\n")
    (repo / "pic.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    subprocess.run([*g, "add", "."], check=True)
    subprocess.run([*g, "commit", "-q", "-m", "first commit"], check=True)
    (repo / "src").mkdir()
    (repo / "src" / "a.py").write_text("print('a')\n")
    (repo / "README.md").write_text("# Hello\n\nsecond\n")
    subprocess.run([*g, "add", "."], check=True)
    subprocess.run([*g, "commit", "-q", "-m", "second commit"], check=True)
    subprocess.run([*g, "branch", "side"], check=True)
    assert backup.mirror_repo(repo, disk / "vault" / "git")
    (disk / "vault" / "git" / backup.mirror_name(repo)).rename(
        disk / "vault" / "git" / "repo.git"
    )

    monkeypatch.setenv("BACKUP_DRIVE_DIR", str(disk))
    monkeypatch.setenv("BACKUP_RESTORE_DIR", str(tmp_path / "Restored"))
    units = Units()
    monkeypatch.setattr(browse, "run_cmd", units)
    yield {
        "cfg": make_cfg(tmp_path, live),
        "disk": disk,
        "live": live,
        "units": units,
        "tmp": tmp_path,
    }
    if not IS_ROOT:
        (root / "secret").chmod(0o755)


def tree_listing(path: Path) -> list[tuple[str, int]]:
    return sorted(
        (str(p.relative_to(path)), p.lstat().st_size) for p in path.rglob("*")
    )


# ---------------------------------------------------------------- status


def test_no_drive_is_a_friendly_message(drive, monkeypatch, tmp_path):
    empty = tmp_path / "nothing"
    empty.mkdir()
    monkeypatch.setenv("BACKUP_DRIVE_DIR", str(empty))
    st = browse.status(drive["cfg"], NOW)
    assert st["plugged"] is False
    assert "not plugged in" in st["message"]
    with pytest.raises(browse.NoDrive):
        browse.list_sets(drive["cfg"], "vault")
    with pytest.raises(browse.NoDrive):
        browse.repos(drive["cfg"])


def test_status_counts_sets(drive):
    st = browse.status(drive["cfg"], NOW)
    vault = next(a for a in st["areas"] if a["name"] == "vault")
    forge = vault["sets"][0]
    assert forge["count"] == 2 and forge["newest"] == STAMP2
    assert forge["age_hours"] == 6.0
    assert forge["unfinished"] == ["2026-10-08_170000.partial"]
    assert vault["due"] is False
    assert vault["last_run"] == {"ok": True, "seconds": 5}
    assert vault["mirrors"] == ["repo.git"]
    assert st["running"] is False and len(st["units"]) == 6


def test_list_sets_flags_unfinished(drive):
    sets = browse.list_sets(drive["cfg"], "vault")
    snaps = sets[0]["snapshots"]
    assert [s["name"] for s in snaps] == [
        "2026-10-08_170000.partial",
        STAMP2,
        STAMP1,
    ]
    assert snaps[0]["partial"] and not snaps[1]["partial"]


# ---------------------------------------------------------------- browsing


def test_list_dir_and_paths(drive):
    cfg = drive["cfg"]
    top = browse.list_dir(cfg, "vault", "forge", STAMP2, "")
    assert [e["name"] for e in top["entries"]] == ["Forge", "one.json"]
    inner = browse.list_dir(cfg, "vault", "forge", STAMP2, "Forge")
    assert inner["entries"][0] == inner["entries"][0] | {"name": "app", "type": "dir"}
    assert inner["live"] == str(drive["live"] / "Forge")
    for bad in ("../..", "Forge/../../x", "a/./b"):
        with pytest.raises(browse.BadInput):
            browse.list_dir(cfg, "vault", "forge", STAMP2, bad)
    with pytest.raises(browse.BadInput):
        browse.list_dir(cfg, "vault", "nope", STAMP2, "")
    with pytest.raises(browse.BadInput):
        browse.list_dir(cfg, "vault", "forge", "../rescue", "")
    with pytest.raises(browse.NotFound):
        browse.list_dir(cfg, "vault", "forge", STAMP2, "Forge/missing")


def test_links_are_shown_not_followed(drive):
    cfg = drive["cfg"]
    top = browse.list_dir(cfg, "rescue", "system", STAMP2, "root")
    etc = next(e for e in top["entries"] if e["name"] == "etc")
    assert etc["type"] == "link" and etc["target"] == "/etc"
    with pytest.raises(browse.BadInput):
        browse.read_file(cfg, "rescue", "system", STAMP2, "root/etc/hostname")
    with pytest.raises(browse.BadInput):
        browse.list_dir(cfg, "rescue", "system", STAMP2, "root/etc")


@pytest.mark.skipif(IS_ROOT, reason="root reads everything")
def test_root_owned_folder_needs_admin(drive):
    cfg = drive["cfg"]
    top = browse.list_dir(cfg, "rescue", "system", STAMP2, "root")
    secret = next(e for e in top["entries"] if e["name"] == "secret")
    assert secret["readable"] is False
    with pytest.raises(browse.NeedsAdmin):
        browse.list_dir(cfg, "rescue", "system", STAMP2, "root/secret")
    with pytest.raises(browse.NeedsAdmin):
        browse.read_file(cfg, "rescue", "system", STAMP2, "root/secret/shadow")
    with pytest.raises(browse.NeedsAdmin):
        browse.restore(cfg, "rescue", "system", STAMP2, "root/secret")


def test_read_file_kinds(drive):
    cfg = drive["cfg"]
    text = browse.read_file(cfg, "vault", "forge", STAMP2, "Forge/app/notes.txt")
    assert text["kind"] == "text" and "TWO" in text["text"]
    assert (
        browse.read_file(cfg, "vault", "forge", STAMP2, "Forge/blob.bin")["kind"]
        == "binary"
    )
    assert (
        browse.read_file(cfg, "vault", "forge", STAMP2, "Forge/pic.png")["kind"]
        == "image"
    )
    assert (
        browse.raw_file(cfg, "vault", "forge", STAMP2, "Forge/pic.png").name
        == "pic.png"
    )


def test_live_path_mapping(drive):
    cfg, live = drive["cfg"], drive["live"]
    assert browse.live_path(cfg, "vault", "forge", "Forge/app/x") == str(
        live / "Forge/app/x"
    )
    assert browse.live_path(cfg, "vault", "forge", "one.json") == str(live / "one.json")
    assert browse.live_path(cfg, "vault", "forge", "other") is None
    assert browse.live_path(cfg, "rescue", "system", "root/open.txt") == str(
        live / "open.txt"
    )
    real = backup.load_config()
    assert (
        browse.live_path(real, "rescue", "system", "root/home/ejb/x") == "/home/ejb/x"
    )
    assert (
        browse.live_path(real, "vault", "claude", ".claude.json")
        == "/home/ejb/.claude.json"
    )


def test_compare_with_laptop(drive):
    cfg = drive["cfg"]
    diff = browse.compare(cfg, "vault", "forge", STAMP2, "Forge/app/notes.txt")
    assert diff["state"] == "different"
    assert "-TWO" in diff["diff"] and "+two" in diff["diff"]
    same = browse.compare(cfg, "vault", "forge", STAMP2, "Forge/same.txt")
    assert same["state"] == "same"
    gone = browse.compare(cfg, "vault", "forge", STAMP2, "Forge/gone.txt")
    assert gone["state"] == "missing"
    folder = browse.compare(cfg, "vault", "forge", STAMP2, "Forge")
    assert folder["state"] == "different"
    assert "gone.txt" in folder["only_snapshot"]


# ---------------------------------------------------------------- restore


def wait_job(job_id: str) -> dict:
    for _ in range(100):
        job = browse.get_job(job_id)
        if job["state"] != "copying":
            return job
        time.sleep(0.05)
    raise AssertionError("copy job did not finish")


def test_restore_never_overwrites(drive):
    cfg, disk = drive["cfg"], drive["disk"]
    before_drive = tree_listing(disk)
    before_live = tree_listing(drive["live"])
    first = browse.restore(cfg, "vault", "forge", STAMP2, "Forge/app/notes.txt")
    second = browse.restore(cfg, "vault", "forge", STAMP2, "Forge/app/notes.txt")
    out = drive["tmp"] / "Restored" / STAMP2 / "forge" / "Forge" / "app"
    assert first["dest"] == str(out / "notes.txt") and first["state"] == "done"
    assert second["dest"] == str(out / "notes-2.txt")
    assert (out / "notes-2.txt").read_text() == "one\nTWO\nthree\n"
    # Restored/<snap>/Forge already exists from the file above
    folder = browse.restore(cfg, "vault", "forge", STAMP2, "Forge")
    job = wait_job(folder["id"])
    assert job["state"] == "done" and job["files"] == 5
    assert job["dest"].endswith("Forge-2")
    again = wait_job(browse.restore(cfg, "vault", "forge", STAMP2, "Forge")["id"])
    assert again["dest"].endswith("Forge-3") and again["state"] == "done"
    assert (out.parent.parent / "Forge-3" / "gone.txt").exists()
    # the drive and the laptop are untouched
    assert tree_listing(disk) == before_drive
    assert tree_listing(drive["live"]) == before_live
    with pytest.raises(browse.BadInput):
        browse.restore(cfg, "vault", "forge", STAMP2, "")


# ---------------------------------------------------------------- buttons


def test_start_backup_and_refusals(drive):
    cfg, units = drive["cfg"], drive["units"]
    assert browse.start_backup(cfg, "vault") == "forge-backup-now@vault.service"
    assert [
        "systemctl",
        "start",
        "--no-block",
        "forge-backup-now@vault.service",
    ] in units.calls
    with pytest.raises(browse.BadInput):
        browse.start_backup(cfg, "everything; rm -rf /")
    units.running = True
    with pytest.raises(browse.Busy):
        browse.start_backup(cfg, "all")
    with pytest.raises(browse.Busy):
        browse.eject(cfg)
    units.running = False
    assert browse.eject(cfg) == "ejected"
    assert browse.progress(cfg)["journal"] == ["line one", "line two"]


# ---------------------------------------------------------------- git


def test_git_mirror_browsing(drive):
    cfg = drive["cfg"]
    found = browse.repos(cfg)
    assert [r["name"] for r in found] == ["repo.git"]
    assert found[0]["branches"] == 2 and found[0]["last_subject"] == "second commit"
    repo = browse.repo_path(cfg, "repo.git")
    refs = browse.refs(repo)
    assert refs["head"] == "main"
    assert {b["name"] for b in refs["branches"]} == {"main", "side"}
    history = browse.log(repo, None)
    assert history["total"] == 2
    assert [c["subject"] for c in history["commits"]] == [
        "second commit",
        "first commit",
    ]
    first_sha = history["commits"][1]["sha"]
    change = browse.commit(repo, history["commits"][0]["sha"])
    assert "+second" in change["diff"] and "-first" in change["diff"]
    assert {f["name"] for f in change["files"]} == {"README.md", "src/a.py"}
    root = browse.tree(repo, None)
    assert root["readme"] == "README.md"
    assert [e["name"] for e in root["entries"]] == ["src", "pic.png", "README.md"]
    old = browse.tree(repo, first_sha)
    assert "src" not in [e["name"] for e in old["entries"]]
    assert browse.blob(repo, first_sha, "README.md")["text"] == "# Hello\n\nfirst\n"
    assert browse.blob(repo, "side", "src/a.py")["text"] == "print('a')\n"
    assert browse.blob_raw(repo, None, "pic.png")[1] == "image/png"
    assert browse.log(repo, None, path="src")["total"] == 1


def test_git_rejects_bad_input(drive):
    cfg = drive["cfg"]
    repo = browse.repo_path(cfg, "repo.git")
    for bad in ("--output=/tmp/x", "main..side", "-n1", ""):
        if bad:
            with pytest.raises(browse.BadInput):
                browse.resolve(repo, bad)
    with pytest.raises(browse.NotFound):
        browse.resolve(repo, "nosuchbranch")
    for name in ("../x.git", "x", ".git"):
        with pytest.raises(browse.BadInput):
            browse.repo_path(cfg, name)
    with pytest.raises(browse.BadInput):
        browse.tree(repo, None, "../..")
    with pytest.raises(browse.BadInput):
        browse.tree(repo, None, "README.md")
