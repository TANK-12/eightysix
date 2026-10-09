import datetime as dt
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import backup  # noqa: E402

FLAGS = ["-aH"]
T0 = dt.datetime(2026, 10, 8, 12, 0, 0)


def make_src(tmp_path: Path) -> Path:
    src = tmp_path / "src"
    (src / "sub").mkdir(parents=True)
    (src / "a.txt").write_text("alpha")
    (src / "sub" / "b.txt").write_text("beta")
    (src / "skip.log").write_text("noise")
    return src


def items(src: Path, tmp_path: Path) -> list[dict]:
    single = tmp_path / "single.json"
    single.write_text("{}")
    return [
        {"from": str(src), "to": "data", "exclude": ["*.log"]},
        {"from": str(single), "to": "single.json"},
        {"from": str(tmp_path / "missing"), "to": "missing"},
    ]


def test_snapshot_copies_and_excludes(tmp_path):
    src = make_src(tmp_path)
    snap, codes = backup.take_snapshot(
        tmp_path / "set", items(src, tmp_path), FLAGS, T0
    )
    assert snap is not None and snap.name == "2026-10-08_120000"
    assert (snap / "data" / "sub" / "b.txt").read_text() == "beta"
    assert (snap / "single.json").exists()
    assert not (snap / "data" / "skip.log").exists()
    assert not list((tmp_path / "set").glob("*.partial"))


def test_unchanged_files_are_hard_links(tmp_path):
    src = make_src(tmp_path)
    its = items(src, tmp_path)
    s1, _ = backup.take_snapshot(tmp_path / "set", its, FLAGS, T0)
    (src / "a.txt").write_text("changed")
    s2, _ = backup.take_snapshot(
        tmp_path / "set", its, FLAGS, T0 + dt.timedelta(hours=1)
    )
    assert s1 and s2
    same = (s1 / "data/sub/b.txt").stat().st_ino == (
        s2 / "data/sub/b.txt"
    ).stat().st_ino
    assert same
    assert (s2 / "data/a.txt").read_text() == "changed"
    assert (s1 / "data/a.txt").read_text() == "alpha"
    assert (s1 / "single.json").stat().st_ino == (s2 / "single.json").stat().st_ino


def test_partial_is_resumed(tmp_path):
    src = make_src(tmp_path)
    set_dir = tmp_path / "set"
    stale = set_dir / "2026-10-07_090000.partial"
    (stale / "data").mkdir(parents=True)
    (stale / "data" / "old.txt").write_text("left over")
    snap, _ = backup.take_snapshot(set_dir, items(src, tmp_path), FLAGS, T0)
    assert snap is not None
    assert not (snap / "data" / "old.txt").exists()
    assert [p.name for p in set_dir.iterdir()] == [snap.name]


def test_prune_keeps_newest(tmp_path):
    set_dir = tmp_path / "set"
    for h in range(5):
        (set_dir / (T0 + dt.timedelta(hours=h)).strftime(backup.STAMP)).mkdir(
            parents=True
        )
    (set_dir / "not-a-snapshot").mkdir()
    gone = backup.prune(set_dir, 2)
    assert len(gone) == 3
    assert [p.name for p in backup.snapshots(set_dir)] == [
        "2026-10-08_150000",
        "2026-10-08_160000",
    ]
    assert (set_dir / "not-a-snapshot").exists()
    assert len(backup.prune(set_dir, 0)) == 1  # never drops the last one


def test_remove_refuses_foreign_paths(tmp_path):
    with pytest.raises(ValueError):
        backup.remove_snapshot(tmp_path / "set", tmp_path / "set" / "photos")
    with pytest.raises(ValueError):
        backup.remove_snapshot(tmp_path / "set", tmp_path / "2026-10-08_120000")


def test_is_due(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    assert backup.is_due([a, b], 48, T0)
    (a / T0.strftime(backup.STAMP)).mkdir(parents=True)
    assert backup.is_due([a, b], 48, T0)  # b has none
    (b / T0.strftime(backup.STAMP)).mkdir(parents=True)
    assert not backup.is_due([a, b], 48, T0 + dt.timedelta(hours=47))
    assert backup.is_due([a, b], 48, T0 + dt.timedelta(hours=48))


def test_git_mirror(tmp_path):
    repo = tmp_path / "home" / "me" / "proj"
    repo.mkdir(parents=True)
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    git = lambda *a: subprocess.run(
        ["git", "-C", str(repo), *a], check=True, env=env, capture_output=True
    )
    git("init", "-q")
    (repo / "f").write_text("1")
    git("add", "f")
    git("commit", "-qm", "one")
    gdir = tmp_path / "vault" / "git"
    assert backup.mirror_repo(repo, gdir)
    (repo / "f").write_text("2")
    git("commit", "-qam", "two")
    assert backup.mirror_repo(repo, gdir)
    mirror = gdir / backup.mirror_name(repo)
    log = subprocess.run(
        ["git", "--git-dir", str(mirror), "log", "--oneline", "--all"],
        capture_output=True,
        text=True,
    ).stdout
    assert "two" in log and "one" in log
    assert not backup.mirror_repo(tmp_path, gdir)


def test_mirror_name():
    assert backup.mirror_name(Path("/home/ejb/Forge")) == "Forge.git"
    assert (
        backup.mirror_name(Path("/home/ejb/Games/eightysix")) == "Games__eightysix.git"
    )


def test_config_is_valid():
    cfg = backup.load_config()
    for area in cfg["areas"].values():
        assert area["keep"] >= 1 and area["sets"]
        for s in area["sets"]:
            assert all({"from", "to"} <= set(i) for i in s["items"])
