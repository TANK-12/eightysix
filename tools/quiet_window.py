"""Quiet window: freeze the other Claude sessions so a power test runs on a quiet machine.

Emerson (2026-10-07): "if the power thing needs to it can tell sessions to stop
and then it can run tests, i'm allowing up to 10 mins total of stoppage, and then
it starts them again". So every pause is charged to one budget (600 s for the
2026-10-07 overhaul grant), no single pause is longer than MAX_WINDOW_S, and a
detached watchdog thaws everything at the deadline even if this process dies.

    python3 tools/quiet_window.py run --seconds 120 --label "hub idle" -- <command...>
    python3 tools/quiet_window.py status
    python3 tools/quiet_window.py release      # emergency: thaw every frozen session

What is frozen (SIGSTOP, then SIGCONT): every `claude` process that is not one
of this process's ancestors, with all its children (headless browsers, tests,
bots), plus the tool shells of sibling subagents inside this session's own
`claude` process. Never frozen: Emerson's Forge, Relay, Jan, GNOME, Whatsie.
Frozen sessions lose only wall-clock time; a test of theirs with a timeout
may fail once and should be rerun.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

GRANT_ID = "2026-10-07-overhaul"
BUDGET_S = 600.0
MAX_WINDOW_S = 180.0
LEDGER = Path.home() / ".local/share/forge/quiet_window.json"
CREW = Path.home() / ".claude/skills/crew/crew.py"
PROTECTED = re.compile(
    r"Forge/forge\.py|--port 8445\b|relay/boss\.py|--port 8463\b|llama-server"
    r"|gnome-shell|whatsie|Xwayland|ai\.jan\.Jan|quiet_window\.py"
)

Procs = dict[int, tuple[int, str, str]]  # pid -> (ppid, comm, cmdline)


def read_procs() -> Procs:
    procs: Procs = {}
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            stat = Path(f"/proc/{entry}/stat").read_text()
            raw = Path(f"/proc/{entry}/cmdline").read_bytes()
        except OSError:
            continue
        comm = stat[stat.index("(") + 1 : stat.rindex(")")]
        ppid = int(stat[stat.rindex(")") + 2 :].split()[1])
        procs[int(entry)] = (
            ppid,
            comm,
            raw.replace(b"\0", b" ").decode(errors="replace"),
        )
    return procs


def ancestors(pid: int, procs: Procs) -> list[int]:
    """pid and its parents, nearest first."""
    chain = []
    while pid in procs and pid not in chain:
        chain.append(pid)
        pid = procs[pid][0]
    return chain


def descendants(root: int, procs: Procs) -> set[int]:
    children: dict[int, list[int]] = {}
    for pid, (ppid, _, _) in procs.items():
        children.setdefault(ppid, []).append(pid)
    found, todo = set(), [root]
    while todo:
        pid = todo.pop()
        if pid not in found:
            found.add(pid)
            todo.extend(children.get(pid, []))
    return found


def is_claude(entry: tuple[int, str, str]) -> bool:
    return entry[1] == "claude"


def targets(procs: Procs, me: int) -> list[int]:
    """Processes to freeze so only this session (and Emerson's own apps) keep running."""
    mine = ancestors(me, procs)
    chain = set(mine)
    roots = [pid for pid, e in procs.items() if is_claude(e) and pid not in chain]
    # sibling subagents of this session run their commands as shells under the same claude
    own = next((pid for pid in mine if is_claude(procs[pid])), None)
    if own is not None:
        roots += [
            pid
            for pid, (ppid, comm, _) in procs.items()
            if ppid == own and comm == "bash" and pid not in chain
        ]
    picked: set[int] = set()
    for root in roots:
        picked |= descendants(root, procs)
    picked -= chain
    return sorted(pid for pid in picked if not PROTECTED.search(procs[pid][2]))


def send(pids: list[int], sig: int) -> None:
    for pid in pids:
        try:
            os.kill(pid, sig)
        except (ProcessLookupError, PermissionError):
            pass


def load(ledger: Path = LEDGER) -> dict:
    try:
        data = json.loads(ledger.read_text())
    except (OSError, ValueError):
        data = {}
    if data.get("grant") != GRANT_ID:
        data = {"grant": GRANT_ID, "budget_s": BUDGET_S, "windows": []}
    return data


def used(data: dict) -> float:
    return sum(w["seconds"] for w in data["windows"])


def window_for(requested: float, data: dict) -> float:
    """Seconds this pause may last: the request, capped per window and by what is left."""
    return max(0.0, min(requested, MAX_WINDOW_S, data["budget_s"] - used(data)))


def tell(text: str) -> None:
    if CREW.exists():
        subprocess.run(
            [sys.executable, str(CREW), "post", "forge", "quiet-window", text, "--fyi"],
            capture_output=True,
            timeout=20,
        )
    subprocess.run(
        ["notify-send", "Forge power test", text], capture_output=True, timeout=10
    )


def watchdog(deadline: float, pids: list[int]) -> subprocess.Popen:
    """A detached process that thaws pids at the deadline whatever happens to this one."""
    return subprocess.Popen(
        [sys.executable, os.path.abspath(__file__), "_watchdog", str(deadline)]
        + [str(p) for p in pids],
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def run(
    command: list[str],
    seconds: float,
    label: str,
    ledger: Path = LEDGER,
    pids: list[int] | None = None,
    notify: bool = True,
) -> int:
    data = load(ledger)
    window = window_for(seconds, data)
    if window < 5:
        print(
            f"quiet window refused: {used(data):.0f} of {data['budget_s']:.0f} s used"
        )
        return 2
    pids = targets(read_procs(), os.getpid()) if pids is None else pids
    if notify:
        tell(
            f"Sessions paused for up to {window:.0f} s for a power test ({label}); they resume on their own."
        )
    guard = watchdog(time.time() + window + 2, pids)
    start = time.monotonic()
    send(pids, signal.SIGSTOP)
    code = 124
    try:
        code = subprocess.run(command, timeout=window).returncode
    except subprocess.TimeoutExpired:
        print(f"quiet window: command cut off at {window:.0f} s")
    finally:
        send(pids, signal.SIGCONT)
        spent = time.monotonic() - start
        guard.terminate()
        data = load(ledger)
        data["windows"].append(
            {
                "label": label,
                "seconds": round(spent, 1),
                "frozen": len(pids),
                "at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text(json.dumps(data, indent=1))
        if notify:
            tell(
                f"Sessions resumed after {spent:.0f} s ({label}); {data['budget_s'] - used(data):.0f} s of the pause budget left."
            )
    print(
        f"quiet window: {spent:.1f} s, {len(pids)} processes, {data['budget_s'] - used(data):.0f} s left"
    )
    return code


def release() -> int:
    """Thaw every stopped process that a quiet window would have frozen."""
    procs = read_procs()
    stopped = []
    for pid in targets(procs, os.getpid()):
        try:
            state = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
        except OSError:
            continue
        if state == "T":
            stopped.append(pid)
    send(stopped, signal.SIGCONT)
    print(f"released {len(stopped)} processes")
    return 0


def main(argv: list[str]) -> int:
    if argv[:1] == ["_watchdog"]:
        deadline, pids = float(argv[1]), [int(p) for p in argv[2:]]
        time.sleep(max(0.0, deadline - time.time()))
        send(pids, signal.SIGCONT)
        return 0
    parser = argparse.ArgumentParser(
        description="Pause other Claude sessions for a power test."
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    go = sub.add_parser("run", help="freeze, run the command, thaw")
    go.add_argument("--seconds", type=float, default=120)
    go.add_argument("--label", default="power test")
    go.add_argument("command", nargs=argparse.REMAINDER)
    sub.add_parser("status")
    sub.add_parser("release")
    args = parser.parse_args(argv)
    if args.cmd == "status":
        data = load()
        print(
            f"grant {data['grant']}: {used(data):.0f} of {data['budget_s']:.0f} s used"
        )
        for w in data["windows"]:
            print(
                f"  {w['at']}  {w['seconds']:>6.1f} s  {w['frozen']:>3} procs  {w['label']}"
            )
        return 0
    if args.cmd == "release":
        return release()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("give the test command after --")
    return run(command, args.seconds, args.label)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
