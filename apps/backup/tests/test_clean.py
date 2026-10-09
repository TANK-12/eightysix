"""Clean copies (clean.py): secrets, personal data and model files never get
into the copy's git history, and publish refuses anything that slipped in.

Fake secrets are glued together at run time, so this file itself holds none.
The last test reads the real clean copy on the Vault drive when it is plugged
in: that one is the proof that the backup Emerson browses and pushes holds no
secret.
"""

import gzip
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import clean  # noqa: E402

GH_TOKEN = "gh" + "p_" + "A1b2C3d4" * 5
ANT_KEY = "sk-" + "ant-" + "api03-" + "x9Y8z7W6" * 4
KNOWN = "Hunter" + "2-" + "4417"
EMAIL = "someone.real" + "@" + "gmail.com"
PRIVATE_LINE = "Emerson likes his coffee black and his merge conflicts resolved early"


def sh(*cmd: str, cwd: Path | None = None) -> str:
    return subprocess.run(
        cmd, cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


def make_rules(tmp: Path, **extra) -> dict:
    rules = clean.load_rules()
    secrets = tmp / "secrets"
    secrets.mkdir(exist_ok=True)
    (secrets / "mail_password").write_text(KNOWN + "\n")
    notes = tmp / "private"
    notes.mkdir(exist_ok=True)
    (notes / "PROFILE.md").write_text(f"# Profile\n\n{PRIVATE_LINE}\n")
    rules["known_secrets"] = [str(secrets)]
    rules["personal_strings_file"] = str(tmp / "nowhere.txt")
    rules["private_texts"] = [str(notes)]
    rules["max_file_mb"] = 1
    rules.update(extra)
    return rules


def make_src(tmp: Path) -> Path:
    src = tmp / "Forge"
    (src / "apps" / "a").mkdir(parents=True)
    (src / "apps" / "a" / "app.py").write_text("print('hello')\n")
    (src / "README.md").write_text("# Forge\n")
    (src / "run.sh").write_text("#!/bin/sh\necho hi\n")
    (src / "run.sh").chmod(0o755)
    (src / ".env").write_text("API=1\n")
    (src / "apps" / "a" / "config.py").write_text(f'TOKEN = "{GH_TOKEN}"\n')
    (src / "apps" / "a" / "notes.txt").write_text(f"the mail one is {KNOWN}\n")
    (src / "apps" / "a" / "contact.md").write_text(f"write to {EMAIL}\n")
    (src / "apps" / "a" / "copied.md").write_text(f"notes\n{PRIVATE_LINE}\n")
    (src / "big.bin").write_bytes(b"\1" * 1_500_000)
    (src / "model.safetensors").write_bytes(b"weights")
    with gzip.open(src / "log.jsonl.gzip-free.gz", "wb") as f:
        f.write(f'{{"k": "{ANT_KEY}"}}'.encode())
    (src / "ignored.tmp").write_text("x")
    (src / ".gitignore").write_text("*.tmp\n")
    (src / "link").symlink_to("README.md")
    sh("git", "init", "-q", cwd=src)
    sh("git", "add", "README.md", cwd=src)
    return src


def copy_of(src: Path, **extra) -> dict:
    return {
        "name": "Forge-clean.git",
        "branch": "main",
        "items": [{"from": str(src), "to": ""}],
        "remote_branch": "forge",
        "protect": ["master", "main"],
        **extra,
    }


def files_in(repo: Path, rev: str = "main") -> dict:
    return clean.tree_files(repo, rev)


def test_build_leaves_out_secrets_models_and_personal(tmp_path):
    src = make_src(tmp_path)
    rules = make_rules(tmp_path)
    res = clean.build(copy_of(src), tmp_path / "git", rules)
    repo = tmp_path / "git" / "Forge-clean.git"
    names = set(files_in(repo))
    assert names == {
        "README.md",
        "apps/a/app.py",
        "run.sh",
        ".gitignore",
        "link",
        clean.NOTES,
    }
    assert res["kept"] == 5 and len(res["commits"]) == 1
    tree = files_in(repo)
    assert tree["run.sh"][0] == "100755" and tree["link"][0] == "120000"
    notes = sh("git", "--git-dir", str(repo), "show", f"main:{clean.NOTES}")
    for gone in ["config.py", "notes.txt", "contact.md", "copied.md", ".env"]:
        assert gone in notes
    assert "GitHub token" in notes and "known secret" in notes
    assert "private Claude note" in notes and "inside .gz" in notes
    # the notes name files and reasons, never the values
    assert GH_TOKEN not in notes and KNOWN not in notes and EMAIL not in notes
    assert clean.scan_repo(repo, ["main"], clean.Checker(rules)) == {}


def test_unchanged_folder_makes_no_commit_and_a_change_makes_one(tmp_path):
    src = make_src(tmp_path)
    rules = make_rules(tmp_path)
    first = clean.build(copy_of(src), tmp_path / "git", rules)
    again = clean.build(copy_of(src), tmp_path / "git", rules)
    assert again["commits"] == [] and again["commit"] == first["commit"]
    (src / "apps" / "a" / "app.py").write_text("print('changed')\n")
    (src / "run.sh").unlink()
    third = clean.build(copy_of(src), tmp_path / "git", rules)
    repo = tmp_path / "git" / "Forge-clean.git"
    assert len(third["commits"]) == 1
    parent = sh("git", "--git-dir", str(repo), "rev-parse", "main^").strip()
    assert parent == first["commit"]
    assert "run.sh" not in files_in(repo)


def test_big_change_is_split_into_pushable_parts(tmp_path):
    src = make_src(tmp_path)
    for i in range(6):
        (src / f"part{i}.dat").write_bytes(bytes([i + 2]) * 300_000)
    rules = make_rules(tmp_path, max_push_mb=0.7)
    res = clean.build(copy_of(src), tmp_path / "git", rules)
    repo = tmp_path / "git" / "Forge-clean.git"
    assert len(res["commits"]) >= 3
    msgs = sh("git", "--git-dir", str(repo), "log", "--format=%s", "main")
    assert "part 1 of" in msgs
    assert {f"part{i}.dat" for i in range(6)} <= set(files_in(repo))
    for c in res["commits"][:-1]:
        assert clean.NOTES not in files_in(repo, c)


def test_secret_that_slips_past_select_never_moves_the_branch(tmp_path, monkeypatch):
    src = make_src(tmp_path)
    rules = make_rules(tmp_path)
    first = clean.build(copy_of(src), tmp_path / "git", rules)
    real_select = clean.select

    def leaky(copy, check, blobs):
        keep, left = real_select(copy, check, blobs)
        secret = (src / "apps" / "a" / "config.py").read_bytes()
        keep["apps/a/config.py"] = ("100644", blobs.add(secret))
        return keep, left

    monkeypatch.setattr(clean, "select", leaky)
    with pytest.raises(clean.Unsafe):
        clean.build(copy_of(src), tmp_path / "git", rules)
    repo = tmp_path / "git" / "Forge-clean.git"
    assert clean.rev(repo, "refs/heads/main") == first["commit"]


def commit_secret_in_history(repo: Path) -> None:
    """An old commit holding a token, with a clean commit on top of it."""
    blob = clean.hash_blob(repo, f"key={GH_TOKEN}\n".encode())
    bad_tree = clean.write_tree(repo, {"old.cfg": ("100644", blob)})
    head = clean.rev(repo, "refs/heads/main")
    bad = clean.git(
        "--git-dir", str(repo), "commit-tree", bad_tree, "-p", head, "-m", "x",
        env=clean.AUTHOR,
    ).decode().strip()  # fmt: skip
    top = clean.git(
        "--git-dir", str(repo), "commit-tree", f"{head}^{{tree}}", "-p", bad,
        "-m", "y", env=clean.AUTHOR,
    ).decode().strip()  # fmt: skip
    clean.git("--git-dir", str(repo), "update-ref", "refs/heads/main", top)


def test_secret_or_line_break_in_a_file_name_is_left_out_and_not_named(
    tmp_path, monkeypatch
):
    src = make_src(tmp_path)
    (src / f"{GH_TOKEN}.txt").write_text("harmless\n")
    (src / "b").write_text("b\n")
    (src / "b\noutside.txt").write_text("odd\n")
    (tmp_path / "outside.txt").write_text("from outside the folder\n")
    (src / "docs" / "money").mkdir(parents=True)
    (src / "docs" / "money" / "trading-plan.md").write_text("plans\n")
    rules = make_rules(tmp_path)
    rules["leave_out"]["paths"] = rules["leave_out"]["paths"] + ["docs/money/"]
    monkeypatch.chdir(tmp_path)
    clean.build(copy_of(src), tmp_path / "git", rules)
    repo = tmp_path / "git" / "Forge-clean.git"
    names = set(files_in(repo))
    assert "b" in names and not any("outside" in n or GH_TOKEN in n for n in names)
    blobs = {sha for _, sha in files_in(repo).values()}
    assert clean.Blobs(repo).add(b"from outside the folder\n") not in blobs
    notes = sh("git", "--git-dir", str(repo), "show", f"main:{clean.NOTES}")
    assert GH_TOKEN not in notes and "outside.txt" not in notes
    assert "trading-plan" not in notes and "in docs/money/: 1 files" in notes


def test_links_stay_inside_the_copy_and_are_never_followed(tmp_path):
    src = make_src(tmp_path)
    (tmp_path / "private.txt").write_text("not for the copy\n")
    (src / "docs").mkdir()
    (src / "docs" / "abs-link").symlink_to(src / "README.md")
    (src / "out-link").symlink_to(tmp_path / "private.txt")
    (src / "up-link").symlink_to("../private.txt")
    rules = make_rules(tmp_path)
    clean.build(copy_of(src), tmp_path / "git", rules)
    repo = tmp_path / "git" / "Forge-clean.git"
    tree = files_in(repo)
    assert "out-link" not in tree and "up-link" not in tree
    target = sh(
        "git", "--git-dir", str(repo), "cat-file", "-p", tree["docs/abs-link"][1]
    )
    assert target == "../README.md"
    with pytest.raises(OSError):
        clean.read_file(src / "out-link")


def test_known_values_are_found_however_they_are_written(tmp_path):
    rules = make_rules(tmp_path)
    secrets = tmp_path / "secrets"
    (secrets / "app_password").write_text("abcd efgh ijkl mnop\n")
    (secrets / "mail").write_text("user=" + EMAIL + "\n")
    check = clean.Checker(rules)
    for text in ["abcdefghijklmnop", "abcd efgh ijkl mnop", EMAIL.replace("@", "%40")]:
        assert check.scan_bytes(f"x {text} y".encode()), text
    # private notes are matched in any text file, whatever its ending
    assert check.content("Makefile", f"a\n{PRIVATE_LINE}\n".encode())


def test_history_scan_checks_every_name_a_blob_had(tmp_path):
    src = make_src(tmp_path)
    rules = make_rules(tmp_path)
    clean.build(copy_of(src), tmp_path / "git", rules)
    repo = tmp_path / "git" / "Forge-clean.git"
    head = clean.rev(repo, "refs/heads/main")
    blob = files_in(repo)["README.md"][1]
    tree = clean.write_tree(repo, {**files_in(repo), "keys/prod.pem": ("100644", blob)})
    top = clean.git(
        "--git-dir", str(repo), "commit-tree", tree, "-p", head, "-m", "z",
        env=clean.AUTHOR,
    ).decode().strip()  # fmt: skip
    found = clean.scan_repo(repo, [top], clean.Checker(rules))
    assert "keys/prod.pem" in found


def test_history_scan_finds_a_secret_in_an_old_commit(tmp_path):
    src = make_src(tmp_path)
    rules = make_rules(tmp_path)
    clean.build(copy_of(src), tmp_path / "git", rules)
    repo = tmp_path / "git" / "Forge-clean.git"
    commit_secret_in_history(repo)
    found = clean.scan_repo(repo, ["main"], clean.Checker(rules))
    assert "old.cfg" in found and "GitHub token" in found["old.cfg"]


def test_history_scan_reads_commit_messages(tmp_path):
    src = make_src(tmp_path)
    rules = make_rules(tmp_path)
    clean.build(copy_of(src), tmp_path / "git", rules)
    repo = tmp_path / "git" / "Forge-clean.git"
    head = clean.rev(repo, "refs/heads/main")
    top = clean.git(
        "--git-dir", str(repo), "commit-tree", f"{head}^{{tree}}", "-p", head,
        "-m", f"mail {EMAIL}", env=clean.AUTHOR,
    ).decode().strip()  # fmt: skip
    clean.git("--git-dir", str(repo), "update-ref", "refs/heads/main", top)
    found = clean.scan_repo(repo, ["main"], clean.Checker(rules))
    assert "(commit messages)" in found


def bare(path: Path) -> Path:
    sh("git", "init", "-q", "--bare", "-b", "master", str(path))
    return path


def test_publish_pushes_every_commit_to_its_own_branch(tmp_path):
    src = make_src(tmp_path)
    rules = make_rules(tmp_path, max_push_mb=0.7)
    for i in range(4):
        (src / f"part{i}.dat").write_bytes(bytes([i + 2]) * 300_000)
    remote = bare(tmp_path / "remote.git")
    copy = copy_of(src, remote=str(remote))
    res = clean.build(copy, tmp_path / "git", rules)
    msg = clean.publish(copy, tmp_path / "git", rules)
    assert f"pushed {len(res['commits'])} commits" in msg
    assert clean.rev(remote, "refs/heads/forge") == res["commit"]
    assert clean.rev(remote, "refs/heads/master") == ""
    (src / "README.md").write_text("# Forge, changed\n")
    res2 = clean.build(copy, tmp_path / "git", rules)
    assert "pushed 1 commits" in clean.publish(copy, tmp_path / "git", rules)
    assert clean.rev(remote, "refs/heads/forge") == res2["commit"]


def test_publish_refuses_secret_history_protected_and_foreign_branches(tmp_path):
    src = make_src(tmp_path)
    rules = make_rules(tmp_path)
    remote = bare(tmp_path / "remote.git")
    copy = copy_of(src, remote=str(remote))
    clean.build(copy, tmp_path / "git", rules)
    with pytest.raises(clean.Unsafe, match="protected"):
        clean.publish({**copy, "remote_branch": "master"}, tmp_path / "git", rules)
    # someone else's work on the target branch is never overwritten
    other = tmp_path / "other"
    other.mkdir()
    sh("git", "init", "-q", "-b", "forge", cwd=other)
    (other / "game.txt").write_text("game\n")
    sh("git", "add", ".", cwd=other)
    sh(
        "git",
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@t",
        "commit",
        "-qm",
        "g",
        cwd=other,
    )
    sh("git", "push", "-q", str(remote), "forge", cwd=other)
    with pytest.raises(clean.Unsafe, match="commits this copy does not"):
        clean.publish(copy, tmp_path / "git", rules)
    # and a secret anywhere in history stops the push before it starts
    remote2 = bare(tmp_path / "remote2.git")
    repo = tmp_path / "git" / "Forge-clean.git"
    commit_secret_in_history(repo)
    with pytest.raises(clean.Unsafe, match="look secret"):
        clean.publish({**copy, "remote": str(remote2)}, tmp_path / "git", rules)
    assert clean.rev(remote2, "refs/heads/forge") == ""


def test_publish_refuses_to_run_as_root(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    with pytest.raises(clean.Unsafe, match="not root"):
        clean.publish(copy_of(tmp_path, remote="x"), tmp_path, make_rules(tmp_path))


def test_every_pattern_catches_its_example():
    check = clean.Checker(
        {**clean.load_rules(), "known_secrets": [], "private_texts": []}
    )
    examples = {
        "Anthropic key": ANT_KEY,
        "OpenAI key": "sk-" + "proj-" + "Ab1" * 12,
        "GitHub token": GH_TOKEN,
        "Hugging Face token": "hf" + "_" + "Ab1" * 12,
        "AWS key": "AKIA" + "ABCDEFGH12345678",
        "Google key": "AIza" + "Sy" + "A1b2C3d4E5" * 3 + "abc",
        "Google OAuth token": "ya29" + "." + "A1b2C3d4E5" * 3,
        "Slack token": "xox" + "b-" + "123456789012-abcdef",
        "Telegram bot token": "123456789" + ":AA" + "A1b2C3d4E5" * 3 + "abc",
        "Stripe key": "sk" + "_live_" + "A1b2C3d4E5" * 3,
        "private key": "-----BEGIN OPENSSH " + "PRIVATE KEY-----",
        "JSON web token": "eyJ" + "hbGciOiJIUzI1NiJ9" + ".eyJ" + "zdWIiOiIxMjM0NTY3ODkwIn0"
        + "." + "dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U",
        "password in a link": "https://bob" + ":hunter22" + "@example.com/x",
        "bearer token": "Authorization: Bearer " + "A1b2C3d4E5" * 3,
        "personal email address": EMAIL,
        "WhatsApp number": "447700900123" + "@s.whatsapp.net",
        "phone number": "call +44 " + "7700 900 123",
        "OpenAI or OpenRouter key": "sk-" + "or-v1-" + "a1b2c3d4" * 8,
        "key or password written in a setting": 'api_key = "' + "Zx9" * 8 + '"',
        "Australian phone number": "ring 04" + "12 345 678",
    }  # fmt: skip
    assert set(examples) == {p["name"] for p in check.pats}
    for name, text in examples.items():
        assert name in check.scan_bytes(f"x {text} y".encode()), name
    # personal patterns ignore binary files, secret patterns do not
    blob = b"\0" * 10 + f" {EMAIL} {GH_TOKEN}".encode()
    assert check.scan_bytes(blob) == ["GitHub token"]
    assert check.scan_bytes(b"def main():\n    return 'plain code'\n") == []


def test_rules_file_and_tool_are_clean_themselves():
    """clean.json and the tool may sit in the copy: they hold patterns, never
    the secrets or personal strings (those live outside the repo)."""
    rules = clean.load_rules()
    check = clean.Checker(rules)
    here = Path(clean.__file__).resolve().parent
    for f in ["clean.json", "clean.py", "backup.py", "tests/test_clean.py"]:
        assert check.file(f"apps/backup/{f}", 0, (here / f).read_bytes()) is None, f


def test_known_values_are_loaded_from_the_real_secret_files():
    """The real check is not empty: the laptop's own secrets are hunted for."""
    rules = clean.load_rules()
    present = [s for s in rules["known_secrets"] if Path(s).exists()]
    if not present:
        pytest.skip("no secret files on this machine")
    assert len(clean.Checker(rules).known) >= len(present)


def vault_clean_repo() -> Path | None:
    for spot in ["/run/media/ejb/Vault", "/mnt/forge-drive/vault"]:
        for copy in clean.load_rules()["copies"]:
            repo = Path(spot) / "git" / copy["name"]
            if (repo / "HEAD").exists():
                return repo
    return None


def test_real_clean_copy_on_the_drive_holds_no_secret():
    """The proof: every file of every commit of the clean copy on the Vault
    drive, checked against the real rules and this laptop's real secrets."""
    repo = vault_clean_repo()
    if repo is None:
        pytest.skip("Vault drive not plugged in or no clean copy yet")
    found = clean.scan_repo(repo, ["--all"], clean.Checker(clean.load_rules()))
    assert found == {}, json.dumps(found, indent=1)[:2000]
