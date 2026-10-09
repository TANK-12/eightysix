#!/usr/bin/env python3
"""Clean copies: folders as a git repo with secrets, personal data and model
files left out, safe to browse and to push to a public GitHub repo.

clean.json is the registry: which folders go into a copy, what is always
left out (paths, file names, model files, big files) and the patterns. A build:
1. lists each folder's own git view (tracked files plus new files its
   .gitignore does not hide), so venvs, caches and downloads stay out;
2. drops whatever a leave-out rule names, then reads every remaining file
   (inside .gz files too) and drops any that matches a secret or personal
   pattern, holds a known secret value (the real tokens, passwords and
   addresses on this laptop, read from the places clean.json lists, kept in
   memory and never printed), or repeats a line of a private Claude note;
3. writes the rest as new commits of the copy's own history (it never shares
   history with the folder's real repo), with BACKUP-NOTES.txt saying what
   was left out and why; a change too big for one GitHub push is split
   over several commits;
4. writes each kept file into git from the very bytes it checked (a link
   that took a file's place is never followed), checks what landed again,
   notes file too, and only then moves the branch.

publish() checks every file of every commit (and the commit messages) again,
then pushes the commits one by one over SSH. It never forces, and never
pushes to a branch the copy lists under "protect".
"""

from __future__ import annotations

import datetime as dt
import fnmatch
import glob
import gzip
import hashlib
import io
import json
import os
import re
import stat
import subprocess
import tempfile
import zlib
from collections.abc import Iterator
from pathlib import Path

HERE = Path(__file__).resolve().parent
RULES = HERE / "clean.json"
GIT = ["git", "-c", "safe.directory=*", "-c", "core.quotepath=off"]
NOTES = "BACKUP-NOTES.txt"
AUTHOR = {
    "GIT_AUTHOR_NAME": "Forge backup",
    "GIT_AUTHOR_EMAIL": "forge-backup@localhost",
    "GIT_COMMITTER_NAME": "Forge backup",
    "GIT_COMMITTER_EMAIL": "forge-backup@localhost",
}


class Unsafe(Exception):
    """Something secret was found where it must not be, or a push was refused."""


def load_rules(path: Path = RULES) -> dict:
    return json.loads(path.read_text())


def git(*args: str, input: bytes | None = None, env: dict | None = None) -> bytes:
    out = subprocess.run(
        [*GIT, *args],
        input=input,
        capture_output=True,
        env={**os.environ, **(env or {})},
    )
    if out.returncode:
        raise RuntimeError(f"git {args[0]}: {out.stderr.decode(errors='replace')}")
    return out.stdout


# ---------------------------------------------------------------- rules


def name_hit(rel: str, globs: list[str]) -> str | None:
    """The first glob matching the file's name or any folder on its path."""
    for part in rel.lower().split("/"):
        for g in globs:
            if fnmatch.fnmatchcase(part, g.lower()):
                return g
    return None


def path_hit(rel: str, paths: list[str]) -> str | None:
    for p in paths:
        if rel == p.rstrip("/") or (p.endswith("/") and rel.startswith(p)):
            return p
    return None


def leave_out_reason(rel: str, size: int, rules: dict) -> str | None:
    """Why a file is left out by place, name or size alone (None: read it)."""
    out = rules["leave_out"]
    if hit := path_hit(rel, out.get("paths", [])):
        return f"in {hit}"
    if hit := name_hit(rel, out.get("models", [])):
        return f"model file ({hit})"
    if hit := name_hit(rel, out.get("names", [])):
        return f"secret-like name ({hit})"
    if size > rules["max_file_mb"] * 1e6:
        return f"over {rules['max_file_mb']} MB"
    return None


def _leaves(value: object) -> list[str]:
    if isinstance(value, dict):
        return [s for v in value.values() for s in _leaves(v)]
    if isinstance(value, list):
        return [s for v in value for s in _leaves(v)]
    return [value] if isinstance(value, str) else []


def secretish(s: str, loose: bool) -> bool:
    """A value worth hunting for. From a JSON file only addresses and long
    token-like strings count (not every setting); from a plain secret file
    any line of 8 characters or more does, spaces and all."""
    s = s.strip()
    if len(s) < 8 or (" " in s and not loose) or s.startswith(("/", "~", "http")):
        return False
    if "@" in s or loose:
        return True
    has_digit = bool(re.search(r"\d", s))
    return len(s) >= 16 and has_digit and bool(re.search(r"[A-Za-z]", s))


def values_in(path: Path) -> list[str]:
    """The secret values stored in one file (JSON leaves, key=value, or lines)."""
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return []
    try:
        return [v for v in _leaves(json.loads(text)) if secretish(v, False)]
    except ValueError:
        pass
    found = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith(("#", "-----", "[")):
            continue
        key, eq, val = line.partition("=")
        key = key.strip()
        plain = eq and key and " " not in key
        found.append(val.strip().strip("\"'") if plain else line)
    return [v for v in found if secretish(v, True)]


def files_at(spot: str) -> list[Path]:
    """Files at a path, under a folder, or under every match of a glob."""
    found = []
    for hit in sorted(glob.glob(spot)) if glob.has_magic(spot) else [spot]:
        path = Path(hit)
        try:
            if path.is_dir():
                found += sorted(p for p in path.rglob("*") if p.is_file())
            elif path.is_file():
                found.append(path)
        except OSError:
            pass
    return found


def variants(value: str) -> set[str]:
    """A known value as it may be written: as is, without its spaces (app
    passwords), and with @ link-encoded."""
    out = {value, value.replace(" ", "")}
    return out | {v.replace("@", "%40") for v in out if "@" in v}


def long_lines(data: bytes) -> set[bytes]:
    """Lines of 60+ characters: long enough that a match means copied text."""
    return {s for line in data.splitlines() if len(s := line.strip()) >= 60}


class Checker:
    """Everything a file is checked against, loaded once per run."""

    def __init__(self, rules: dict):
        self.rules = rules
        self.pats = []
        for group, text_only in (
            ("secret_patterns", False),
            ("personal_patterns", True),
        ):
            for p in rules.get(group, []):
                self.pats.append(
                    {
                        "name": p["name"],
                        "rx": re.compile(p["re"].encode()),
                        "needs": [n.lower().encode() for n in p.get("needs", [])],
                        "text_only": text_only,
                    }
                )
        found: set[str] = set()
        for spot in rules.get("known_secrets", []):
            for f in files_at(spot):
                found.update(values_in(f))
        personal = rules.get("personal_strings_file")
        for f in files_at(personal) if personal else []:
            found.update(
                line.strip()
                for line in f.read_text(errors="replace").splitlines()
                if line.strip() and not line.startswith("#")
            )
        # Lower-cased, in memory only; never printed or written anywhere.
        self.known = sorted(
            {x.lower().encode() for v in found for x in variants(v) if len(x) >= 8}
        )
        self.private: set[bytes] = set()
        for spot in rules.get("private_texts", []):
            for f in files_at(spot):
                if f.suffix in (".md", ".txt", ".json"):
                    try:
                        self.private.update(long_lines(f.read_bytes()))
                    except OSError:
                        pass

    def scan_bytes(self, data: bytes) -> list[str]:
        """Names of what the bytes hold, never the values. Personal patterns
        (addresses, phone numbers) skip binary files, where random bytes look
        like numbers; secret patterns and known values do not."""
        low = data.lower()
        binary = b"\0" in data[:8192]
        hits = []
        for p in self.pats:
            if p["text_only"] and binary:
                continue
            if p["needs"] and not any(n in low for n in p["needs"]):
                continue
            if p["rx"].search(data):
                hits.append(p["name"])
        if any(k in low for k in self.known):
            hits.append("a known secret or personal value")
        return hits

    def content(self, name: str, data: bytes) -> list[str]:
        """What a file's content holds (empty: clean), .gz unpacked too."""
        hits = self.scan_bytes(data)
        if self.private and b"\0" not in data[:8192]:
            if not self.private.isdisjoint(long_lines(data)):
                hits.append("text from a private Claude note")
        if name.lower().endswith(".gz"):
            limit = self.rules["max_gz_mb"] * 1e6
            try:
                with gzip.GzipFile(fileobj=io.BytesIO(data)) as f:
                    inner = f.read(int(limit) + 1)
            except (OSError, EOFError):
                return hits + ["unreadable .gz"]
            if len(inner) > limit:
                return hits + [f".gz over {self.rules['max_gz_mb']} MB unpacked"]
            hits += [f"{h} (inside .gz)" for h in self.content(name[:-3], inner)]
        return hits

    def file(self, name: str, size: int, data: bytes) -> str | None:
        """Why a file may not be in a copy (None: it may)."""
        reason = leave_out_reason(name, size, self.rules)
        named = [f"{h} in its name" for h in self.scan_bytes(name.encode())]
        if "\n" in name or "\r" in name:
            named.append("line break in its name")
        hits = self.content(name, data)
        return ", ".join(filter(None, [reason, *named, *hits])) or None


# ---------------------------------------------------------------- select


def candidates(src: Path) -> list[str]:
    """The folder's own git view: tracked files plus new files not ignored.
    A folder that is not a git repo gives every file under it."""
    if (src / ".git").exists():
        out = git("-C", str(src), "ls-files", "-z", "-co", "--exclude-standard")
        seen = {p for p in out.decode(errors="surrogateescape").split("\0") if p}
    else:
        seen = {
            str(p.relative_to(src))
            for p in src.rglob("*")
            if (p.is_file() or p.is_symlink())
            and ".git" not in p.relative_to(src).parts
        }
    return sorted(p for p in seen if os.path.lexists(src / p))


def items(copy: dict) -> list[tuple[Path, str]]:
    """(source folder, place in the copy) for each item of a copy."""
    return [
        (Path(it["from"]), it["to"].strip("/") + "/" if it.get("to") else "")
        for it in copy["items"]
    ]


def link_target(src: Path, rel: str) -> str | None:
    """A link as it goes into the copy: relative, and only to a place inside
    its own folder (an absolute link into the folder is made relative)."""
    target = os.readlink(src / rel)
    here = os.path.dirname(rel)
    if os.path.isabs(target):
        inside = os.path.relpath(target, src)
        target = os.path.relpath(inside, here or ".")
    else:
        inside = os.path.normpath(os.path.join(here, target))
    if inside == ".." or inside.startswith("../") or os.path.isabs(inside):
        return None
    return target


def read_file(path: Path) -> tuple[bytes, bool]:
    """(content, executable) of a regular file, never following a link that
    took its place since it was listed."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as f:
        st = os.fstat(f.fileno())
        if not stat.S_ISREG(st.st_mode):
            raise OSError(0, "not a regular file")
        return f.read(), bool(st.st_mode & 0o111)


class Blobs:
    """Writes contents into a repo's object store straight from the bytes
    that were checked, so what lands is exactly what was read."""

    def __init__(self, repo: Path):
        self.repo = repo
        out = git(
            "--git-dir", str(repo), "cat-file",
            "--batch-all-objects", "--batch-check=%(objectname)",
        )  # fmt: skip
        self.have = set(out.decode().split())

    def add(self, data: bytes) -> str:
        head = f"blob {len(data)}\0".encode()
        h = hashlib.sha1(head)
        h.update(data)
        sha = h.hexdigest()
        if sha not in self.have:
            obj = self.repo / "objects" / sha[:2] / sha[2:]
            obj.parent.mkdir(exist_ok=True)
            tmp = obj.parent / f"tmp-{sha[2:]}"
            with open(tmp, "wb") as f:
                z = zlib.compressobj(1)
                f.write(z.compress(head) + z.compress(data) + z.flush())
            os.replace(tmp, obj)
            self.have.add(sha)
        return sha


def select(
    copy: dict, check: Checker, blobs: Blobs
) -> tuple[dict[str, tuple[str, str]], dict[str, str]]:
    """({path in the copy: (mode, blob id)}, {left-out path: reason}). Rules
    apply to the path in the copy; each kept file is written to the repo from
    the same bytes that were checked."""
    keep: dict[str, tuple[str, str]] = {}
    left: dict[str, str] = {}
    for src, prefix in items(copy):
        if not src.is_dir():
            continue
        for rel in candidates(src):
            name, path = prefix + rel, src / rel
            if name == NOTES:
                left[name] = "name used by the notes file"
                continue
            if path.is_symlink():
                target = link_target(src, rel)
                if target is None:
                    left[name] = "link to a place outside its folder"
                    continue
                data, mode = target.encode(errors="surrogateescape"), "120000"
            elif path.is_file():
                reason = leave_out_reason(name, path.stat().st_size, check.rules)
                if reason:
                    left[name] = reason
                    continue
                try:
                    data, exe = read_file(path)
                except OSError as e:
                    left[name] = f"unreadable ({e.strerror})"
                    continue
                mode = "100755" if exe else "100644"
            else:
                continue
            if why := check.file(name, len(data), data):
                left[name] = why
            else:
                keep[name] = (mode, blobs.add(data))
    return keep, left


def notes_text(copy: dict, kept: int, left: dict[str, str], now: dt.datetime) -> str:
    froms = ", ".join(str(src) for src, _ in items(copy))
    lines = [
        f"Clean copy of {froms}, {now:%Y-%m-%d %H:%M}",
        "",
        "Made by Forge's Backup app (apps/backup/clean.py, rules in clean.json).",
        "Left out on purpose: secrets (keys, tokens, passwords, .env files,",
        "cookies, logins), personal data (addresses, phone numbers, notes about",
        "Emerson, chat notes, session transcripts), every model file (the apps",
        "download them again from their model lists), files over the size limit,",
        "logs, databases and archives. Nothing was deleted from the laptop, and",
        "the full private copies stay on the backup drive.",
        "",
        f"{kept} files kept, {len(left)} left out.",
        "",
        "Left out, by reason:",
    ]
    by_reason: dict[str, list[str]] = {}
    for rel, why in left.items():
        by_reason.setdefault(why, []).append(rel)
    for why in sorted(by_reason):
        files = sorted(by_reason[why])
        if why.startswith("in ") or "in its name" in why or "line break" in why:
            lines.append(f"- {why}: {len(files)} files")
            continue
        lines.append(f"- {why}:")
        lines += [f"    {f}" for f in files]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- git objects


def init_repo(repo: Path, branch: str) -> None:
    if not repo.exists():
        repo.parent.mkdir(parents=True, exist_ok=True)
        git("init", "--quiet", "--bare", "-b", branch, str(repo))
        (repo / "description").write_text(
            "Clean copy: no secrets, personal data or model files\n"
        )


def rev(repo: Path, name: str) -> str:
    """The object id a name points at, or '' when there is none."""
    out = subprocess.run(
        [*GIT, "--git-dir", str(repo), "rev-parse", "-q", "--verify", name],
        capture_output=True,
        text=True,
    )
    return out.stdout.strip() if out.returncode == 0 else ""


def hash_blob(repo: Path, data: bytes) -> str:
    out = git("--git-dir", str(repo), "hash-object", "-w", "--stdin", input=data)
    return out.decode().strip()


def tree_files(repo: Path, treeish: str) -> dict[str, tuple[str, str]]:
    """{path: (mode, blob id)} of every file in one commit or tree."""
    out = git("--git-dir", str(repo), "ls-tree", "-r", "-z", "--full-tree", treeish)
    rows = {}
    for rec in out.decode(errors="surrogateescape").split("\0"):
        if rec:
            meta, path = rec.split("\t", 1)
            mode, kind, sha = meta.split()
            if kind == "blob":
                rows[path] = (mode, sha)
    return rows


def blob_sizes(repo: Path, shas: list[str]) -> dict[str, int]:
    """{id: size} for the ids that are blobs."""
    if not shas:
        return {}
    out = git(
        "--git-dir",
        str(repo),
        "cat-file",
        "--batch-check=%(objectname) %(objecttype) %(objectsize)",
        input="\n".join(shas).encode() + b"\n",
    )
    sizes = {}
    for line in out.decode().splitlines():
        sha, kind, size = line.split()
        if kind == "blob":
            sizes[sha] = int(size)
    return sizes


def read_blobs(repo: Path, shas: list[str]) -> Iterator[tuple[str, bytes]]:
    """(id, content) for each blob, from one git process."""
    proc = subprocess.Popen(
        [*GIT, "--git-dir", str(repo), "cat-file", "--batch"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )
    assert proc.stdin and proc.stdout
    try:
        for sha in shas:
            proc.stdin.write(sha.encode() + b"\n")
            proc.stdin.flush()
            size = int(proc.stdout.readline().split()[2])
            data = proc.stdout.read(size)
            proc.stdout.read(1)
            yield sha, data
    finally:
        proc.stdin.close()
        proc.wait()


def write_tree(repo: Path, files: dict[str, tuple[str, str]]) -> str:
    with tempfile.TemporaryDirectory(prefix="forge-clean-") as tmp:
        env = {"GIT_INDEX_FILE": str(Path(tmp) / "index")}
        listing = b"".join(
            f"{mode} {sha}\t".encode() + name.encode(errors="surrogateescape") + b"\0"
            for name, (mode, sha) in sorted(files.items())
        )
        g = ["--git-dir", str(repo)]
        git(*g, "update-index", "--add", "-z", "--index-info", input=listing, env=env)
        return git(*g, "write-tree", env=env).decode().strip()


def scan_pairs(
    repo: Path, pairs: set[tuple[str, str]], check: Checker
) -> dict[str, str]:
    """(path, blob id) pairs checked by name, size and content -> {path: problem}."""
    by_sha: dict[str, list[str]] = {}
    for path, sha in pairs:
        by_sha.setdefault(sha, []).append(path)
    blobs = blob_sizes(repo, sorted(by_sha))
    found = {}
    for sha, data in read_blobs(repo, sorted(blobs)):
        for path in by_sha[sha]:
            if why := check.file(path, len(data), data):
                found[path] = why
    return found


def scan_repo(repo: Path, revs: list[str], check: Checker) -> dict[str, str]:
    """Every file of every commit reachable from revs, plus the commit
    messages and names. {path: problem}; empty means clean."""
    commits = git("--git-dir", str(repo), "rev-list", *revs).decode().split()
    pairs = {
        (path, sha)
        for commit in commits
        for path, (_, sha) in tree_files(repo, commit).items()
    }
    found = scan_pairs(repo, pairs, check)
    log = git("--git-dir", str(repo), "log", "--format=%an%n%ae%n%cn%n%ce%n%B", *revs)
    if hits := check.scan_bytes(log):
        found["(commit messages)"] = ", ".join(hits)
    return found


# ---------------------------------------------------------------- build


def batches(changed: list[str], sizes: dict[str, int], limit: float) -> list[list[str]]:
    """Split changed paths into groups whose new content stays under limit."""
    groups: list[list[str]] = [[]]
    total = 0
    for name in changed:
        size = sizes.get(name, 0)
        if groups[-1] and total + size > limit:
            groups.append([])
            total = 0
        groups[-1].append(name)
        total += size
    return groups


def build(
    copy: dict,
    git_root: Path,
    rules: dict | None = None,
    now: dt.datetime | None = None,
) -> dict:
    """New clean commits of the copy's folders in git_root/copy['name']."""
    rules = rules or load_rules()
    check = Checker(rules)
    now = now or dt.datetime.now().replace(microsecond=0)
    repo = git_root / copy["name"]
    branch = copy.get("branch", "main")
    ref = f"refs/heads/{branch}"
    init_repo(repo, branch)
    keep, left = select(copy, check, Blobs(repo))
    g = ["--git-dir", str(repo)]
    final = dict(keep)
    notes = notes_text(copy, len(keep), left, now).encode()
    final[NOTES] = ("100644", hash_blob(repo, notes))
    # What landed is checked again, notes too: only that ever goes anywhere.
    bad = scan_pairs(repo, {(n, sha) for n, (_, sha) in final.items()}, check)
    if bad:
        raise Unsafe(f"{len(bad)} files hold something secret: {sorted(bad)[:5]}")
    parent = rev(repo, ref)
    old = tree_files(repo, parent) if parent else {}
    result = {"name": copy["name"], "kept": len(keep), "left_out": len(left)}
    changed = sorted(n for n in final if old.get(n) != final[n] and n != NOTES)
    gone = [n for n in old if n not in final]
    if not changed and not gone:
        return {**result, "commits": [], "commit": parent}
    sizes = blob_sizes(repo, sorted({final[n][1] for n in changed}))
    by_name = {n: sizes.get(final[n][1], 0) for n in changed}
    groups = batches(changed, by_name, rules.get("max_push_mb", 1500) * 1e6)
    state = {n: v for n, v in old.items() if n in final}
    made = []
    for i, group in enumerate(groups, 1):
        state.update({n: final[n] for n in group})
        if i == len(groups):
            state[NOTES] = final[NOTES]
        tree = write_tree(repo, state)
        part = f" (part {i} of {len(groups)})" if len(groups) > 1 else ""
        msg = f"Clean copy {now:%Y-%m-%d %H:%M}{part}"
        args = [*g, "commit-tree", tree, "-m", msg]
        if parent:
            args += ["-p", parent]
        parent = git(*args, env=AUTHOR).decode().strip()
        made.append(parent)
    git(*g, "update-ref", ref, parent)
    git(*g, "symbolic-ref", "HEAD", ref)
    subprocess.run([*GIT, *g, "gc", "--auto", "--quiet"], capture_output=True)
    return {**result, "commits": made, "commit": parent}


# ---------------------------------------------------------------- publish


def remote_head(remote: str, branch: str) -> str:
    out = git("ls-remote", remote, f"refs/heads/{branch}").decode().split()
    return out[0] if out else ""


def publish(copy: dict, git_root: Path, rules: dict | None = None) -> str:
    """Check the whole history once more, then push it commit by commit."""
    rules = rules or load_rules()
    if os.geteuid() == 0:
        raise Unsafe("run publish as yourself, not root: it uses your SSH key")
    repo = git_root / copy["name"]
    target = copy["remote_branch"]
    if target in copy.get("protect", []):
        raise Unsafe(f"refusing to push to {target}: it is protected in clean.json")
    head = rev(repo, f"refs/heads/{copy.get('branch', 'main')}")
    if not head:
        raise Unsafe(f"{repo} has no clean copy yet: run a Vault backup first")
    bad = scan_repo(repo, [head], Checker(rules))
    if bad:
        raise Unsafe(f"not pushed: {len(bad)} files look secret: {sorted(bad)[:5]}")
    there = remote_head(copy["remote"], target)
    if there and not rev(repo, f"{there}^{{commit}}"):
        raise Unsafe(
            f"not pushed: {target} on the remote has commits this copy does not "
            "have, so it is left as it is"
        )
    g = ["--git-dir", str(repo)]
    span = [f"{there}..{head}"] if there else [head]
    todo = git(*g, "rev-list", "--reverse", *span).decode().split()
    for commit in todo:
        git(*g, "push", "--quiet", copy["remote"], f"{commit}:refs/heads/{target}")
    (repo / "forge-published.json").write_text(
        json.dumps(
            {
                "at": dt.datetime.now().isoformat(timespec="seconds"),
                "remote": copy["remote"],
                "branch": target,
                "commit": head,
            }
        )
    )
    return f"pushed {len(todo)} commits to {copy['remote']} branch {target}"
