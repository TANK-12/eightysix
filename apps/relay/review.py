"""The review a long task gets instead of a session cap (Emerson,
2026-10-08): after review_after_rounds sessions without finishing, then every
review_every_rounds (25, 35, 45...), a short fresh session reads what the
task's sessions did and answers continue or park. There is no hard cap.

picker.review_due says when; this module gathers what the reviewer reads
(evidence) and reads its answer (verdict); boss.py launches and finishes it.
"""

from __future__ import annotations

import re
import subprocess
import time

import items
import runs

# "verdict: continue - it lands commits every session", read only in the last
# TAIL lines of the reply (the prompt asks for it as the last line). A few
# words may come before it ("**Final verdict:**", "My verdict is:", "Verdict
# for Relay task 102:", "3. Verdict (task 102):"), and the word must end the
# line or be followed by a separator, so prose reads as no verdict rather
# than the wrong one: "parking it would be wrong", "park is not warranted",
# "Next verdict: park if nothing lands" (critics, task 112). No verdict
# means another try, then the task carries on: the safe side.
VERDICT = re.compile(
    r"^[ \t>*_`#~-]*(?:\d+[.)][ \t]*)?[*_`]*"
    r"(?:(?:my|the|final|overall|review|reviewer['’]?s?|relay['’]?s?)[ \t]+){0,3}"
    r"verdict"
    r"(?:[ \t]+(?:for|on)[ \t]+(?:relay[ \t]+)?(?:task[ \t]*)?#?\d+"
    r"|[ \t]*\([ \t]*(?:relay[ \t]+)?(?:task[ \t]*)?#?\d+[ \t]*\))?"
    r"(?:[ \t]+is)?[ \t]*[*_`]*[ \t]*(?:[:：=\-–—]|\n)[\W_]*?"
    r"(continue|continues|continuing|park|parks|parked)"
    r"(?![ \t]*(?:or|/)[ \t]*(?:continue|park))"
    r"(?=[ \t]*(?:$|[-–—:,.;!(*_`]))"
    r"[ \t*_`]*(?:[-–—:,.;!][ \t]*)?(.*)$",
    re.I | re.M,
)
TEMPLATE = re.compile(r"^<\s*why\s*>$", re.I)  # the prompt's own "<why>" read back
TAIL = 5  # lines at the end of the reply the verdict may be in
SHOWN = 30  # sessions listed at most, the newest
WORDS = 280  # characters of each session's last words
COMMITS_SHOWN = 30


def verdict(text: str) -> tuple[str, str]:
    """("continue" or "park", the one-line reason) from the reviewer's reply;
    ("", "") when it gave no verdict line."""
    lines = [line for line in (text or "").splitlines() if line.strip()]
    for word, why in reversed(VERDICT.findall("\n".join(lines[-TAIL:]))):
        why = why.strip().strip("*_`\"' ").strip()
        if TEMPLATE.match(why):
            continue
        word = "park" if word.lower().startswith("park") else "continue"
        return word, why[:300]
    return "", ""


def _when(at: float) -> str:
    return time.strftime("%m-%d %H:%M", time.localtime(at))


def _line(text: str, limit: int = WORDS) -> str:
    flat = " ".join((text or "").split())
    return flat if len(flat) <= limit else flat[: limit - 3] + "..."


def _git(repo: str, *args: str) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(
            ["git", "-C", repo, *args], capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        return None


def repos(folders) -> list[str]:
    """The git repos (top folders) the given folders are in, each once."""
    tops: list[str] = []
    for folder in folders:
        done = _git(folder, "rev-parse", "--show-toplevel") if folder else None
        top = done.stdout.strip() if done and not done.returncode else ""
        if top and top not in tops:
            tops.append(top)
    return tops


def commits(repo: str, task_id, since: float) -> list[dict]:
    """Commits in `repo` since `since` whose message names the task ("(Relay
    task 102)", as Relay sessions end them), oldest first. Not "subtask 1" or
    "task 1 of 3" (critic, task 112)."""
    done = _git(
        repo,
        "log",
        f"--since=@{int(since)}",
        "-E",
        "-i",
        f"--grep=(^|[^a-z0-9])relay task #?{task_id}([^0-9]|$)",
        "--format=%x1e%h%x1f%ct%x1f%s",
        "--shortstat",
        "-n",
        "300",
    )
    found = []
    for record in (done.stdout if done and not done.returncode else "").split("\x1e"):
        head, _, stat = record.strip("\n").partition("\n")
        sha, at, subject = (head.split("\x1f") + ["", "", ""])[:3]
        try:
            when = float(at)
        except ValueError:
            continue
        found.append(
            {"sha": sha, "at": when, "subject": subject, "stat": " ".join(stat.split())}
        )
    return sorted(found, key=lambda c: c["at"])


def all_since(repo: str, since: float) -> int:
    """How many commits `repo` got since `since`, whoever made them."""
    done = _git(repo, "rev-list", "--count", f"--since=@{int(since)}", "HEAD")
    try:
        return int(done.stdout.strip()) if done and not done.returncode else 0
    except ValueError:
        return 0


def sessions(task_id, every_run: list[dict] | None = None) -> tuple[list, list]:
    """The task's work runs and hand-over turns, oldest first."""
    every_run = runs.all_runs() if every_run is None else every_run
    mine = [r for r in every_run if str(r.get("task")) == str(task_id)]
    work = [r for r in mine if r.get("kind") == "work"]
    return work, [r for r in mine if r.get("kind") == "handoff"]


def _said(run: dict) -> str:
    info = runs.summary(run)
    return (info.get("result") or {}).get("text") or info.get("last_text") or ""


def evidence(task: dict, folder: str, now: float | None = None) -> str:
    """What the reviewer reads: each counted session (the newest SHOWN) with
    whether its State moved and how many commits naming the task landed in
    its time, its last words, then those commits themselves."""
    now = now or time.time()
    rounds = int(items.num(task, "attempts"))
    every_run = runs.all_runs()
    work, handoffs = sessions(task["id"], every_run)
    if rounds:
        work = work[-rounds:]  # a retry starts the count again
    since = float(items.num(task, "created")) or (work[0]["started"] if work else now)
    own = repos(dict.fromkeys([*(r.get("folder") for r in work), folder]))
    # a session may commit outside its folder (one started in the home folder
    # commits in ~/Forge): the repos other Relay tasks run in are searched too
    used = [r.get("folder") for r in every_run] + [
        str(t.get("folder") or "") for t in items.all_tasks()
    ]
    places = own + [r for r in repos(dict.fromkeys(used)) if r not in own]
    by_repo = {repo: commits(repo, task["id"], since) for repo in places}
    for repo, got in by_repo.items():
        for c in got:
            c["repo"] = repo
    found = sorted((c for got in by_repo.values() for c in got), key=lambda c: c["at"])
    current = items.state_mark(task.get("body", ""))
    lines = [f"Sessions counted: {rounds} (a retry starts the count again)."]
    seen = int(items.num(task, "reviewed_at"))
    if 0 < seen <= rounds:  # 0 or more: none since the last retry
        lines.append(
            f"Last review, after {seen} sessions: "
            f"{task.get('review_note') or '(no note)'}"
        )
    lines += [
        "",
        "Its sessions, oldest first. State moved: whether the State section "
        "changed between this session's start and the next one's; commits: "
        "commits naming the task made in that time.",
    ]
    if not work:
        lines.append("- none recorded")
    first = max(0, len(work) - SHOWN)
    for i in range(first, len(work)):
        run = work[i]
        start = float(run.get("started") or 0)
        nxt = work[i + 1] if i + 1 < len(work) else None
        until = float(nxt["started"]) if nxt else now
        before = run.get("state_before")
        after = nxt.get("state_before") if nxt else current
        moved = (
            "not recorded"
            if before is None or after is None
            else ("yes" if before != after else "no")
        )
        landed = sum(1 for c in found if start <= c["at"] < until)
        took = (float(run.get("ended") or now) - start) / 60
        outcome = run.get("outcome") or (
            "still running" if not run.get("ended") else ""
        )
        if (run.get("result") or {}).get("is_error"):
            outcome += ", ended with an error"
        number = rounds - len(work) + i + 1 if rounds >= len(work) else i + 1
        lines.append(
            f"{number}. {_when(start)}, {took:.0f} min, {run.get('account')}, "
            f"{outcome or 'ended'}; State moved: {moved}; commits: {landed}"
        )
        lines.append(f"   last words: {_line(_said(run)) or '(none)'}")
        hand = [
            h
            for h in handoffs
            if h.get("session") == run.get("session")
            and start <= float(h.get("started") or 0) < until
        ]
        if hand:
            lines.append(f"   hand-over note: {_line(_said(hand[-1])) or '(none)'}")
    lines += ["", f"Commits naming Relay task {task['id']} since it was created:"]
    if not own:
        lines.append("- its folder is not in a git repo")
    if not found:
        lines.append(f"- none (searched: {', '.join(places) or 'no repo'})")
    for c in found[::-1][:COMMITS_SHOWN]:
        stat = f" ({c['stat']})" if c["stat"] else ""
        where = "" if c["repo"] in own else f" [in {c['repo']}]"
        lines.append(f"- {c['sha']} {_when(c['at'])} {c['subject']}{stat}{where}")
    if len(found) > COMMITS_SHOWN:
        lines.append(f"- and {len(found) - COMMITS_SHOWN} older ones")
    for repo, got in by_repo.items():
        if repo not in own:
            continue
        other = all_since(repo, since) - len(got)
        if other > 0:
            lines.append(
                f"Other commits in {repo} in that time: {other} (other sessions "
                "share the tree; a session may also have forgotten the task tag)."
            )
    return "\n".join(lines)
