#!/usr/bin/env python3
"""U1 sweep sequencer (Relay task 74, 2026-10-08).

Queues the U1 every-app sweep groups as Relay tasks one by one, paced by the
5-hour usage meter (Emerson's rule for this sweep): under 70 % up to three
group tasks unfinished at once, from 70 % one, from 92 % none. When every
group task has ended, it queues the summary task once and exits.

The meter is Relay's own reading (state.json "meters", refreshed by the boss)
for the account with the most room, since Relay starts new work there. A
reading older than 10 minutes means no new group until it reads again.

Why: in-session subagent workers died every time the commander session
handed over (context), so each group is now its own Relay task, which hands
over by itself. This script is plain Python and spends no usage.

Run (transient user unit, survives the commander session):
    systemd-run --user --unit=u1-sequencer --collect \
        python3 ~/Forge/sessions/2026-10-07-overhaul/u1_sequencer.py
Stop:   systemctl --user stop u1-sequencer   (or touch u1-sequencer.stop here)
Look:   u1-sequencer.json (group -> Relay task id), u1-sequencer.log
Try:    python3 u1_sequencer.py --dry-run
Restarting carries on from the json; a group already queued under its title
is adopted, never queued twice.
"""

from __future__ import annotations

import fcntl
import json
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATE = HERE / "u1-sequencer.json"
LOG = HERE / "u1-sequencer.log"
STOP = HERE / "u1-sequencer.stop"
LOCK = HERE / "u1-sequencer.lock"
TASKS = Path.home() / ".local/share/forge/relay/tasks"
RELAY = Path.home() / ".local/bin/relay"
RELAY_STATE = Path.home() / ".local/share/forge/relay/state.json"
CREW = Path.home() / ".claude/skills/crew/crew.py"
TICK_S = 60
LIFETIME_S = 96 * 3600
STALE_S = 600
MISSING_S = 15 * 60
# Relay statuses that mean the task will not run again by itself. Every
# other status (queued, running, handing_over, anything new) is busy.
ENDED = {"done", "parked", "blocked", "stopped"}
GROUP_TITLE = "U1 every-app sweep, group {}:"
SUMMARY_TITLE = "U1 every-app sweep: the summary"
DRY = False

# (group, apps, effort). Browser first (Emerson's top complaint), then the
# groups with partial edits from the stopped runs, then the poll-wrapper
# apps of final-breaker break 6, then the rest.
GROUPS: list[tuple[str, str, str]] = [
    ("G1", "browser", "xhigh"),
    ("G2", "board, calendar", "high"),
    ("G12", "dossier, foresight", "high"),
    ("G3", "files, comix", "high"),
    ("G4", "crewroom, terminal", "high"),
    ("G5", "settings, code, logins", "high"),
    ("G6", "emberfield", "high"),
    ("G7", "arcade, driftpeaks", "high"),
    ("G8", "janhollow", "high"),
    ("G9", "cosmos, eightysix", "high"),
    ("G10", "acchan, jan-tune", "high"),
    ("G11", "ai-studio, pixelforge", "high"),
    ("G13", "novelforge, inkforge", "high"),
    ("G14", "panelforge, printforge", "high"),
    ("G15", "pulseforge", "high"),
    ("G16", "media, mediaforge", "high"),
    ("G17", "power, keymap, study-companion", "high"),
    ("G18", "codec-lab, codec-player", "high"),
]


def ports(group: str) -> str:
    base = 8900 + 10 * int(group[1:])
    return f"{base}-{base + 9}"


def group_request(group: str, apps: str, effort: str) -> str:
    return f"""folder: ~/Forge
effort: {effort}
model: opus
done when: every app of the group is swept, tested and committed, the critic has run and its confirmed breaks are fixed, and sessions/2026-10-07-overhaul/reports/u1-{group}.md is written

{GROUP_TITLE.format(group)} {apps}. Worker task queued by the U1 sequencer of Relay task 74 (2026-10-08).
date: 2026-10-08 · for: Claude

Read ~/Forge/sessions/2026-10-07-overhaul/U1-worker-brief.md first: the whole brief, its "Relay workers" section and the Group note for {group}. Do what it says for these apps only: {apps}. Your scratch ports are {ports(group)} (the critic gets the upper five).
Opus only for any helper or critic (Emerson). No fps, GPU or CPU-load measurements: list "measure this" items in the report instead. Never restart Emerson's Forge, an app backend on its real port, the Claude app on 8445, Relay or Jan; never touch CPU power caps. Commit per app with `git add <your paths>` only, never -A. Your final message: at most 4 short lines.
"""


SUMMARY_REQUEST = f"""folder: ~/Forge
effort: high
model: opus
done when: docs/library/power/2026-10-07-every-app-sweep.md is written and committed, and the idle-CPU before/after runs are done in one quiet window or left as a written plan

{SUMMARY_TITLE} (queued by the U1 sequencer of Relay task 74 when every group task had ended).
date: 2026-10-08 · for: Claude

1. Read ~/Forge/sessions/2026-10-07-overhaul/u1-sequencer.json (group -> Relay task id and how it ended), every reports/u1-G*.md and critics/u1-G*-critic.md in that folder, and `git log --oneline --grep "Relay task 74"`. A group with no report, or a task that ended parked, stopped, blocked or missing: say so plainly and list what is missing.
2. Write ~/Forge/docs/library/power/2026-10-07-every-app-sweep.md (title, `date: YYYY-MM-DD · for: both`): per app one short block (what changed, commit hashes, tests, verified versus not, critic findings fixed or open); then all "measure this" items in one list; the shared/ and hub changes the workers recommend (none were made; they need their own task); final-breaker.md breaks 1-5 (hub and Claude app, outside the sweep) as still open; questions for Emerson.
3. Idle-CPU before/after (Emerson, crew note 1054: performance runs go last): read docs/library/power/2026-10-07-overhaul-numbers.md for the plan and the "before" numbers. Only if `python3 ~/Forge/tools/quiet_window.py status` says the machine is quiet and `python3 ~/.claude/tools/usage.py` is under 70 %, run the after numbers in one quiet window and add them; otherwise write the exact run plan into the doc. Never restart Emerson's Forge, Relay, Jan or the Claude app on 8445; never touch CPU power caps.
4. Update ~/Forge/sessions/2026-10-07-overhaul/HANDOFF.md (a new dated Update section) and the U1 entry of ~/Forge/PROGRESS.json, post one note to crew board "forge", and commit only the files you wrote.
Your final message (phone): at most 8 short lines, no tables: how many apps swept and committed, what is verified, what is left, anything Emerson has to do.
"""


def log(text: str) -> None:
    if DRY:
        return
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with LOG.open("a") as fh:
        fh.write(f"{stamp} {text}\n")


def load_state() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {"groups": {}, "summary": None, "started": time.time()}


def save_state(state: dict) -> None:
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=1) + "\n")
    tmp.replace(STATE)


def front_matter(file: Path) -> dict[str, str]:
    """The `key: value` lines between a task file's first two `---` lines."""
    try:
        lines = file.read_text(errors="replace").splitlines()
    except OSError:
        return {}
    if not lines or lines[0].strip() != "---":
        return {}
    fields: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return fields
        key, sep, value = line.partition(":")
        if sep:
            fields[key.strip()] = value.strip()
    return {}


def task_status(tid: int | None) -> str:
    """The Relay task's status; 'unknown' when its file is not found."""
    if tid is None:
        return "unknown"
    for file in TASKS.glob(f"*/{tid:04d}-*.md"):
        status = front_matter(file).get("status")
        if status:
            return status
    return "unknown"


def find_task(title_start: str) -> int | None:
    """A Relay task already queued under this title (a lost queue, a second copy)."""
    for file in TASKS.glob("*/*.md"):
        fields = front_matter(file)
        tid = fields.get("id", "")
        if fields.get("title", "").startswith(title_start) and tid.isdigit():
            return int(tid)
    return None


def five_hour_percent() -> float | None:
    """The lowest fresh 5-hour reading among Relay's accounts, or None."""
    try:
        if time.time() - RELAY_STATE.stat().st_mtime > STALE_S:
            return None
        meters = json.loads(RELAY_STATE.read_text()).get("meters") or {}
    except (OSError, ValueError):
        return None
    fresh = [
        float(m["five"])
        for m in meters.values()
        if isinstance(m, dict)
        and m.get("five") is not None
        and float(m.get("age") or 0) < STALE_S
        and float(m.get("week") or 0) < 92
    ]
    return min(fresh) if fresh else None


def slots(percent: float | None) -> int:
    """How many group tasks may be unfinished at once."""
    if percent is None or percent >= 92:
        return 0
    if percent >= 70:
        return 1
    return 3


def queue(text: str) -> int | None:
    try:
        out = subprocess.run(
            [str(RELAY)], input=text, capture_output=True, text=True, timeout=120
        )
    except (OSError, subprocess.SubprocessError) as exc:
        log(f"queue failed: {exc}")
        return None
    match = re.search(r"task (\d+) queued", out.stdout)
    if not match:
        log(
            f"queue failed: rc={out.returncode} {out.stdout[-300:]} {out.stderr[-300:]}"
        )
        return None
    return int(match.group(1))


def step(
    state: dict, percent: float | None, status_of, queue_fn, find=find_task
) -> str:
    """One pass. Returns 'wait', 'done' or 'error'."""
    groups = state["groups"]
    now = time.time()
    for gid, info in groups.items():
        status = status_of(info.get("task"))
        if status == "unknown" and now - info.get("queued_at", now) > MISSING_S:
            if info.get("status") != "missing":
                log(f"{gid}: task {info.get('task')} file not found; counted as ended")
            status = "missing"
        info["status"] = status
    busy = [g for g, i in groups.items() if i["status"] not in ENDED | {"missing"}]
    pending = [g for g in GROUPS if g[0] not in groups]
    if pending:
        if len(busy) < slots(percent):
            gid, apps, effort = pending[0]
            tid = find(GROUP_TITLE.format(gid))
            if tid is not None:
                log(f"{gid} was already queued as task {tid}; adopted it")
            else:
                tid = queue_fn(group_request(gid, apps, effort))
                if tid is None:
                    return "error"
                log(f"queued {gid} ({apps}) as task {tid} at {percent}% five-hour")
            groups[gid] = {"task": tid, "queued_at": now, "status": "queued"}
        return "wait"
    if busy:
        return "wait"
    if state.get("summary") is None:
        if slots(percent) == 0:
            return "wait"
        tid = find(SUMMARY_TITLE)
        if tid is None:
            tid = queue_fn(SUMMARY_REQUEST)
            if tid is None:
                return "error"
            log(f"every group ended; queued the summary as task {tid}")
        state["summary"] = tid
    return "done"


def tell_board(text: str) -> None:
    try:
        subprocess.run(
            [sys.executable, str(CREW), "post", "forge", "u1-sequencer", "--fyi", text],
            capture_output=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        pass


def main(argv: list[str]) -> int:
    global DRY
    dry = DRY = "--dry-run" in argv
    once = "--once" in argv or dry
    if not dry:
        lock = LOCK.open("w")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            print("another u1 sequencer is running; leaving it be")
            return 1
    state = load_state()
    started = time.time()
    while True:
        if STOP.exists():
            log("stop file found; exiting")
            return 0
        if time.time() - started > LIFETIME_S:
            log("lifetime cap reached; exiting")
            tell_board(
                "U1 sequencer stopped at its 96 h cap before every group ended; "
                "see sessions/2026-10-07-overhaul/u1-sequencer.json"
            )
            return 0
        percent = five_hour_percent()
        if dry:

            def fake_queue(text: str) -> int:
                print("would queue:\n" + text)
                return 0

            result = step(
                json.loads(json.dumps(state)), percent, task_status, fake_queue
            )
            print(f"five-hour {percent}%, result {result}")
            return 0
        result = step(state, percent, task_status, queue)
        save_state(state)
        if result == "error":
            log("could not queue; exiting so nothing is queued twice")
            tell_board(
                "U1 sequencer could not queue the next group and stopped; "
                "see sessions/2026-10-07-overhaul/u1-sequencer.log"
            )
            return 1
        if result == "done":
            log("done")
            return 0
        if once:
            return 0
        time.sleep(TICK_S)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
